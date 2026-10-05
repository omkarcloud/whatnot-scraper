"""Whatnot reference parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrIdField convention — never a sibling `url`/`id` pair).

  seller       pokemonsuperstore | @pokemonsuperstore
               | https://www.whatnot.com/user/pokemonsuperstore[/shop|/reviews|/shows|/clips]
               | https://www.whatnot.com/en-GB/user/pokemonsuperstore
  listing      2373630372 (numeric id) | TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg== (the id in listing links)
               | https://www.whatnot.com/listing/TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg==
  livestream   dc46af2c-5e85-496c-9011-82c053949cb0 | https://www.whatnot.com/live/dc46af2c-...
  category     pokemon_cards (slug) | 907 (numeric id)
               | https://www.whatnot.com/tag/pokemon_cards | https://www.whatnot.com/category/pokemon_cards

Whatnot's GraphQL ids are relay global ids: base64("<Type>:<number>"). The
API speaks the plain number everywhere and rebuilds the global id here.
"""
import base64
import binascii
import re
from urllib.parse import unquote, urlparse

SITE = "https://www.whatnot.com"

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_SLUG_RE = re.compile(r"^[\w\-]{1,100}$", re.UNICODE)
_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/_\-]+={0,2}$")


# ---- global ids ------------------------------------------------------------------------

def global_id(kind, number):
    """('ListingNode', 2373630372) -> 'TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg=='."""
    if number is None:
        return None
    return base64.b64encode(f"{kind}:{number}".encode()).decode()


def decode_global_id(value):
    """'TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg==' -> ('ListingNode', '2373630372');
    anything that is not a relay id -> (None, None)."""
    if not isinstance(value, str) or not value or not _B64_RE.match(value):
        return None, None
    raw = value.replace("-", "+").replace("_", "/")
    raw += "=" * (-len(raw) % 4)
    try:
        text = base64.b64decode(raw, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None, None
    kind, sep, rest = text.partition(":")
    if not sep or not kind.isidentifier() or not rest:
        return None, None
    return kind, rest


def numeric_id(value):
    """A relay id, a numeric string or a number -> int (the first number of a
    composite id); None when there is none."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    value = str(value).strip()
    if value.isdigit():
        return int(value)
    _, rest = decode_global_id(value)
    if rest:
        head = rest.split(":")[0]
        if head.isdigit():
            return int(head)
    return None


# ---- links -----------------------------------------------------------------------------

def seller_link(username):
    return f"{SITE}/user/{username}" if username else None


def listing_link(number):
    return f"{SITE}/listing/{global_id('ListingNode', number)}" if number is not None else None


def livestream_link(uuid):
    return f"{SITE}/live/{uuid}" if uuid else None


def category_link(slug):
    return f"{SITE}/tag/{slug}" if slug else None


def clip_link(uuid):
    return f"{SITE}/clip/{uuid}" if uuid else None


def _is_link(value):
    low = value.lower()
    return low.startswith(("http://", "https://", "//", "whatnot.com/", "www.whatnot.com/"))


def _segments(value):
    """A whatnot.com link -> its path segments without the locale prefix.
    Raises ValueError for another site."""
    url = value
    if url.startswith("//"):
        url = "https:" + url
    elif not url.lower().startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "whatnot.com" or host.endswith(".whatnot.com")):
        raise ValueError("not a whatnot.com link")
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    if segments and _LOCALE_RE.match(segments[0]):
        segments = segments[1:]
    return segments


# ---- resolvers -------------------------------------------------------------------------

def resolve_seller(value):
    """Username, @username or any whatnot.com profile link -> the username."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("seller is required")
    if _is_link(value):
        try:
            segments = _segments(value)
        except ValueError:
            raise ValueError("seller must be a Whatnot username or a whatnot.com profile link "
                             "(https://www.whatnot.com/user/pokemonsuperstore)")
        if len(segments) < 2 or segments[0].lower() != "user":
            raise ValueError("seller link must look like https://www.whatnot.com/user/pokemonsuperstore")
        value = segments[1]
    value = value.lstrip("@")
    if not _USERNAME_RE.match(value):
        raise ValueError("seller must be a Whatnot username (letters, digits, _ . -) or a whatnot.com profile link")
    return value.lower()


def resolve_listing(value):
    """Numeric listing id, the base64 id used in listing links, or a
    whatnot.com listing link -> the relay id the API takes."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("listing is required")
    if _is_link(value):
        try:
            segments = _segments(value)
        except ValueError:
            raise ValueError("listing must be a listing id or a whatnot.com listing link")
        if len(segments) < 2 or segments[0].lower() != "listing":
            raise ValueError("listing link must look like https://www.whatnot.com/listing/TGlzdGluZ05vZGU6...")
        value = segments[1]
    if value.isdigit():
        return global_id("ListingNode", int(value))
    kind, rest = decode_global_id(value)
    if kind == "ListingNode" and rest.isdigit():
        return global_id("ListingNode", int(rest))
    raise ValueError("listing must be a numeric listing id (2373630372), the id from a listing link "
                     "(TGlzdGluZ05vZGU6...) or a whatnot.com listing link")


def resolve_livestream(value):
    """Livestream uuid or a whatnot.com /live/ link -> the uuid."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("livestream is required")
    if _is_link(value):
        try:
            segments = _segments(value)
        except ValueError:
            raise ValueError("livestream must be a livestream id or a whatnot.com live link")
        candidate = next((s for s in segments if _UUID_RE.match(s)), None)
        if not candidate:
            raise ValueError("livestream link must look like https://www.whatnot.com/live/<id>")
        value = candidate
    if not _UUID_RE.match(value):
        raise ValueError("livestream must be a livestream id (dc46af2c-5e85-496c-9011-82c053949cb0) "
                         "or a whatnot.com live link")
    return value.lower()


def resolve_category(value):
    """Category slug, numeric id or a whatnot.com /tag/ or /category/ link ->
    {"slug": ...} or {"id": <relay id>}."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("category is required")
    if _is_link(value):
        try:
            segments = _segments(value)
        except ValueError:
            raise ValueError("category must be a category slug or a whatnot.com category link")
        if len(segments) < 2 or segments[0].lower() not in ("tag", "category"):
            raise ValueError("category link must look like https://www.whatnot.com/tag/pokemon_cards")
        value = segments[1]
    if value.isdigit():
        return {"id": global_id("LivestreamTagNode", int(value))}
    kind, rest = decode_global_id(value) if len(value) > 16 else (None, None)
    if kind == "LivestreamTagNode" and rest.isdigit():
        return {"id": global_id("LivestreamTagNode", int(rest))}
    if not _SLUG_RE.match(value):
        raise ValueError("category must be a Whatnot category slug (pokemon_cards), a numeric id "
                         "or a whatnot.com category link")
    return {"slug": value.lower()}


def category_label(ref):
    if not isinstance(ref, dict):
        return str(ref)
    if ref.get("slug"):
        return ref["slug"]
    return str(numeric_id(ref.get("id")) or ref.get("id"))
