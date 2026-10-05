"""Whatnot transport: plain curl_cffi with browser-impersonated TLS against
the site's own GraphQL gateway. No browser, no cookies, no login (validated
2026-10-05 from direct Indian egress: ~0.4-1.5 s a call, relay cursors).

One upstream does everything:

  * GQL  POST https://www.whatnot.com/services/graphql/
         {"query": ..., "variables": ...}
    The web app's GraphQL. It accepts RAW query documents (no persisted
    hash, so nothing rotates) from an anonymous session. Introspection is
    disabled, so whatnot/queries.py holds hand-trimmed documents rebuilt
    from the compiled ASTs in the site's JS bundles.

Login-only surfaces answer null / empty for an anonymous session and are
simply not offered: follower / following lists, the seller leaderboard and
the sold items of a show.

Blocks: none seen. If the pod's egress ever starts answering 403/429 or an
HTML challenge, a worker moves its session to a sticky residential exit
(config.whatnot_fallback_proxy()) for config.WHATNOT_BLOCK_COOLDOWN
seconds, the same shape as the twitch transport.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  WhatnotUpstreamError  transport failure / 5xx / stale query document  — retryable
  WhatnotBlocked        403 / 429 / HTML instead of JSON                — retryable on a new exit
  WhatnotBadRequest     GraphQL rejected a variable value               — never retried
  WhatnotNotFound       entity is null                                  — never retried
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://www.whatnot.com"
GQL_URL = SITE + "/services/graphql/"
IMPERSONATE = "chrome"

TIMEOUT = 45
FANOUT_WORKERS = 6

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": SITE,
    "referer": SITE + "/",
    "x-whatnot-app": "whatnot-web",
}


class WhatnotUpstreamError(UpstreamError):
    """Transport failure, 5xx or a stale query document — retryable."""


class WhatnotBlocked(WhatnotUpstreamError, Blocked):
    """403 / 429 or an HTML challenge — retryable on a fresh exit."""


class WhatnotBadRequest(BadRequest):
    """GraphQL rejected a variable value. Never retried."""


class WhatnotNotFound(NotFound):
    """Entity does not exist (GraphQL answered null) — never retried."""


# ---- sessions ------------------------------------------------------------------
# One curl session per worker thread. Direct egress by default; after a block
# the thread's sessions go through a sticky residential exit for a cooldown.
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy_for_new_session():
    forced = config.whatnot_proxy()
    if forced:
        return forced
    if time.time() < _fallback_until:
        return config.whatnot_fallback_proxy()
    return None


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = _proxy_for_new_session()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _note_block():
    """A 403/429 on direct egress: send new sessions through a residential
    exit for a while (no-op when no fallback country is configured)."""
    global _fallback_until
    if config.whatnot_fallback_proxy() is not None:
        with _fallback_lock:
            _fallback_until = time.time() + config.WHATNOT_BLOCK_COOLDOWN


def dump_debug(name, text):
    """Keep the last body of each failure kind when WHATNOT_DEBUG_DIR is set."""
    dbg = os.environ.get("WHATNOT_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(text if isinstance(text, str) else json.dumps(text, ensure_ascii=False))
        except OSError:
            pass


# ---- GraphQL ---------------------------------------------------------------------

# The document itself is wrong (Whatnot renamed / removed something).
_SCHEMA_RE = re.compile(r"Cannot query field|Unknown argument|Unknown type|Unknown fragment|must have a selection|"
                        r"must not have a selection|is required, but it was not provided|Syntax Error|"
                        r"is not defined by type|Unknown directive", re.I)
# A caller-supplied value is wrong (bad enum, malformed id).
_VALUE_RE = re.compile(r"got invalid value|does not exist in '|Expected value of type|cannot represent|"
                       r"Invalid (?:global )?id|could not be decoded", re.I)
_ERROR_ID_RE = re.compile(r"\s*\(ID: [0-9a-f]+\)\s*$")


def _retrying(fn):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except WhatnotUpstreamError as e:      # includes WhatnotBlocked
            last = e
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _post(payload, label):
    def once():
        sess = _session()
        try:
            resp = sess.post(GQL_URL, params={"operationName": label, "ssr": "0"}, headers=HEADERS,
                             data=json.dumps(payload), timeout=TIMEOUT)
        except Exception as e:
            raise WhatnotUpstreamError(f"request failed: {type(e).__name__}: {e}")
        status = resp.status_code
        body = resp.text or ""
        if status in (403, 429):
            dump_debug("blocked", body)
            _note_block()
            raise WhatnotBlocked(f"HTTP {status} on {label}")
        if status >= 500:
            raise WhatnotUpstreamError(f"HTTP {status} on {label}")
        if not body.lstrip().startswith("{"):
            dump_debug("nonjson", body)
            _note_block()
            raise WhatnotBlocked(f"{label} returned HTML, not JSON")
        try:
            return resp.json()
        except Exception:
            dump_debug("badjson", body)
            raise WhatnotUpstreamError(f"could not parse JSON from {label}")
    return _retrying(once)


def _clean_message(message):
    return _ERROR_ID_RE.sub("", str(message or "")).strip()


def _classify_errors(errors, data, label, tolerate):
    """GraphQL `errors[]` next to (possibly partial) `data`.

    * a schema error (unknown field / argument / missing selection) ->
      WhatnotUpstreamError: the document in queries.py is stale
    * a bad variable value (unknown enum, malformed id) -> WhatnotBadRequest
    * an error on a response path listed in `tolerate` -> ignored (that
      member is null in `data`; the caller treats it as optional)
    * anything else with no data at all -> WhatnotUpstreamError; with
      partial data the data is kept
    """
    tolerate = set(tolerate or ())
    for err in errors:
        if not isinstance(err, dict):
            continue
        message = _clean_message(err.get("message"))
        path = tuple(str(p) for p in (err.get("path") or ()))
        if _VALUE_RE.search(message):
            raise WhatnotBadRequest(message[:300])
        if _SCHEMA_RE.search(message):
            dump_debug("schema", {"label": label, "error": err})
            raise WhatnotUpstreamError(f"{label}: Whatnot changed its schema ({message[:160]})")
        if any(path[:len(t)] == t for t in tolerate if t):
            continue
        if data is None:
            raise WhatnotUpstreamError(f"{label}: {message[:200] or 'GraphQL error'}")
        dump_debug("partial", {"label": label, "error": err})


def gql(query, variables=None, *, label=None, tolerate=None):
    """Run ONE raw GraphQL document -> its `data` dict. `tolerate` lists
    response paths (tuples) whose errors leave that member null instead of
    failing the call."""
    label = label or _label_of(query)
    body = _post({"query": query, "variables": variables or {}}, label)
    if not isinstance(body, dict):
        raise WhatnotUpstreamError(f"{label}: unexpected response shape")
    data = body.get("data")
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        _classify_errors(errors, data, label, tolerate)
    if not isinstance(data, dict):
        raise WhatnotUpstreamError(f"{label}: no data in the response")
    return data


def _label_of(query):
    match = re.search(r"(?m)^\s*(?:query|mutation)\s+([A-Za-z0-9_]+)", query or "")
    return match.group(1) if match else "gql"


# ---- fan-out ------------------------------------------------------------------------

def run_parallel(fns):
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(FANOUT_WORKERS, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


if __name__ == "__main__":
    # Smoke test: python whatnot/fetch.py [username]
    username = sys.argv[1] if len(sys.argv) > 1 else "pokemonsuperstore"
    out = gql("query Smoke($u: String) { getUser(username: $u) { id username followerCount soldCount isLive } }",
              {"u": username})
    print(json.dumps(out, ensure_ascii=False))
