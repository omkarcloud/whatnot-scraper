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
HTML challenge, the sessions move one fallback step down for
config.WHATNOT_BLOCK_COOLDOWN seconds: since 2026-11-11 first to the gateway
exit (config.WHATNOT_FALLBACK_EXIT = "gateway", exit_gateway.py: a fresh
gateway address on nearly every request; the numbers are in config.py's Whatnot
block), and only when that is refused too to a sticky residential exit
(config.WHATNOT_FALLBACK_PROXY_COUNTRY). A call the gateway keeps failing
makes its LAST retry on the residential exit, for that call only. When the
cooldown ends the next call is back on the server's own IP. The same shape
as the reed / soundcloud / woolworths transports.

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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as wait_futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from scraper_utils import fanout, ladder, retry, sessions

SITE = "https://www.whatnot.com"
GQL_URL = SITE + "/services/graphql/"
IMPERSONATE = "chrome"

TIMEOUT = 45
FANOUT_WORKERS = 6

HEADERS = {
    "accept": "*/*",
    "accept-language": egress.site_accept_language("whatnot"),
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
# One session per worker thread (egress.new_session: curl_cffi, or the gateway
# exit's look-alike). Direct egress by default; after a block the sessions
# move down the fallback steps (config.whatnot_fallback_exits(): the gateway
# exit, then a sticky residential exit) until `_fallback_until`, then go
# back to direct.
_local = threading.local()
_fallback_until = 0.0
_fallback_step = 1              # which fallback exit serves while the cooldown runs (1 = the first)
_fallback_lock = threading.Lock()


def _gateway_step(step):
    """True when fallback step `step` is the gateway exit with another exit
    configured behind it."""
    exits = config.whatnot_fallback_exits()
    return 0 < step < len(exits) and bool(config.gateway_exit(exits[step - 1]))


def _step():
    """The fallback step a session built NOW rides: 0 = the configured exit
    (the server's own IP), 1, 2 = config.whatnot_fallback_proxy(step) while
    the cooldown runs; one step past the gateway for the last retry of a
    call (_retrying)."""
    return ladder.current_step(_fallback_step, _fallback_until, _local, _gateway_step)


def _proxy_for_new_session(step=None):
    forced = config.whatnot_proxy()
    if forced:
        return forced
    step = _step() if step is None else step
    return config.whatnot_fallback_proxy(step) if step else None


def _session():
    sess = getattr(_local, "session", None)
    step = _step()
    if sess is not None and getattr(sess, "_whatnot_step", 0) != step:
        # 2026-11-11: a session follows its step. Before, a thread that took
        # the fallback exit during a cooldown stayed on it until that failed.
        _drop_session()
        sess = None
    if sess is None:
        # None (direct), a proxy URL, or the gateway exit ("gateway")
        sess = egress.new_session(_proxy_for_new_session(step), impersonate=IMPERSONATE)
        sess._whatnot_step = step
        _local.session = sess
    return sess


def _drop_session():
    sessions.drop(_local)


def _note_block():
    """The exit this thread's session rides was refused: new sessions move
    one fallback step down for a cooldown (own IP -> the gateway exit ->
    residential; on the last step they stay there, each on a fresh exit).
    No-op when no fallback is configured."""
    global _fallback_until, _fallback_step
    exits = config.whatnot_fallback_exits()
    if not exits:
        return
    held = getattr(getattr(_local, "session", None), "_whatnot_step", _step())
    if getattr(_local, "past_gateway", False) and held > (_fallback_step if time.time() < _fallback_until else 0):
        # the last retry of a call the gateway kept failing rides the step past
        # it for that call only: a refusal there is no verdict on the gateway,
        # so it must not move every session onto the residential exit
        return
    step = min(held + 1, len(exits))
    with _fallback_lock:
        if time.time() >= _fallback_until or step > _fallback_step:
            _fallback_step = step
        _fallback_until = time.time() + config.WHATNOT_BLOCK_COOLDOWN
    if len(exits) > 1:      # how often each step is refused is the number to watch
        print(f"whatnot: exit refused, sessions on fallback step {_fallback_step} "
              f"({exits[_fallback_step - 1]}) for {config.WHATNOT_BLOCK_COOLDOWN} s")


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
    """Run fn() under the shared retry policy, each retry on a fresh session
    / exit. While the sessions are on the gateway exit step the LAST retry of
    a call rides the next step (the residential exit), for that call only:
    a gateway failure then costs latency, not the call."""
    return retry.run_flagged(fn, config, WhatnotUpstreamError, lambda e: _drop_session(), _local)


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

# Long-lived pools (2026-10-23): their threads keep their thread-local curl
# sessions — and the sticky exits behind them — between requests. The
# per-call executor they replace opened fresh sessions/exits for every
# fan-out and threw them away when the call returned. Two levels: a fan-out
# running inside a fan-out goes to the second pool, so it neither waits on
# the workers it occupies (deadlock) nor loses its parallelism; a third
# level runs inline.
_pools = (ThreadPoolExecutor(max_workers=FANOUT_WORKERS * 4, thread_name_prefix="whatnot-fanout-0"),
          ThreadPoolExecutor(max_workers=FANOUT_WORKERS * 4, thread_name_prefix="whatnot-fanout-1"))


def _windowed(fns, workers):
    """Run `fns` on the pool for this nesting level, at most `workers` at a
    time; results align with `fns`. The first failure (in `fns` order)
    propagates once the callables already started have finished."""
    return fanout.windowed(_pools, "whatnot-fanout", fns, workers)


def run_parallel(fns):
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    return _windowed(fns, FANOUT_WORKERS)


if __name__ == "__main__":
    # Smoke test: python whatnot/fetch.py [username]
    username = sys.argv[1] if len(sys.argv) > 1 else "pokemonsuperstore"
    out = gql("query Smoke($u: String) { getUser(username: $u) { id username followerCount soldCount isLive } }",
              {"u": username})
    print(json.dumps(out, ensure_ascii=False))
