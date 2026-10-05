"""Helpers shared by the /whatnot/* endpoint modules: the category lookup
(slug <-> relay id, memoised in-process: ids never change), the filter /
sort builders and the feed-page envelope."""
import threading
import time

from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot.fetch import WhatnotNotFound, gql

_TAG_TTL = 12 * 3600
_tags = {}
_lock = threading.Lock()


# ---- categories ------------------------------------------------------------------------

def category_raw(ref):
    """A resolved category ref ({"slug"} or {"id"}) -> the LivestreamTagNode
    (fresh: it carries live viewer counts). Seeds the slug <-> id memo."""
    if ref.get("id"):
        node = gql(Q.TAG_BY_ID, {"id": ref["id"]}).get("getLivestreamTag")
    else:
        node = gql(Q.TAG_BY_NAME, {"name": ref["slug"]}).get("getLivestreamTagByName")
    if not isinstance(node, dict) or not node.get("id"):
        raise WhatnotNotFound(f"category '{refs.category_label(ref)}' not found")
    identity = {"id": node["id"], "slug": P.text(node.get("name")), "name": P.text(node.get("label")),
                "feed_id": P.text(P.as_dict(node.get("feed")).get("id"))}
    with _lock:
        expires = time.time() + _TAG_TTL
        _tags[("id", identity["id"])] = (expires, identity)
        if identity["slug"]:
            _tags[("slug", identity["slug"])] = (expires, identity)
    return node


def category_identity(ref):
    """{id (relay), slug, name, feed_id} for a category ref, memoised."""
    key = ("id", ref["id"]) if ref.get("id") else ("slug", ref["slug"])
    with _lock:
        hit = _tags.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    category_raw(ref)
    with _lock:
        return _tags[key][1]


def category_feed_id(identity):
    return identity.get("feed_id") or f"CATEGORY_FEED_V2:{identity['id']}"


# ---- filters / sorts -------------------------------------------------------------------

LISTING_SORTS = {
    "best_match": None,
    "price_low_to_high": {"field": "PRICE", "direction": "ASC"},
    "price_high_to_low": {"field": "PRICE", "direction": "DESC"},
    "newest": {"field": "CREATION_TIME", "direction": "DESC"},
}
LIVESTREAM_SORTS = {
    "recommended": None,
    "viewers_high_to_low": {"field": "VIEWER_COUNT", "direction": "DESC"},
    "viewers_low_to_high": {"field": "VIEWER_COUNT", "direction": "ASC"},
}
LIVESTREAM_STATUS = {"live": ["PLAYING"], "upcoming": ["CREATED"], "all": None}

# public param -> the product attribute it filters (stringAttributes.<name>)
ATTRIBUTE_FILTERS = {
    "condition": "Condition",
    "language": "Language",
    "product_type": "Product Type",
    "set": "Set",
    "rarity": "Rarity",
    "grade": "Grade",
    "grading_service": "Grading Service",
    "card_number": "Card Number",
}


def _values(field, values):
    return {"field": field, "values": [str(v) for v in values]}


def listing_filters(*, buying_format=None, category=None, min_price=None, max_price=None,
                    min_seller_rating=None, is_premier_shop=None, seller_country=None,
                    is_graded=None, is_autographed=None, **attributes):
    """The FilterInput list for a listing search / seller shop."""
    out = []
    if buying_format:
        out.append(_values("buyingFormat", [buying_format]))
    if category:
        out.append(_values("category.keyword", [category]))
    if min_price is not None or max_price is not None:
        price = {"field": "priceCents"}
        if min_price is not None:
            price["rangeValueMin"] = int(round(min_price * 100))
        if max_price is not None:
            price["rangeValueMax"] = int(round(max_price * 100))
        out.append(price)
    if min_seller_rating:
        out.append(_values("sellerRating", [min_seller_rating]))
    if is_premier_shop:
        out.append(_values("isPremierShop", ["true"]))
    if seller_country:
        out.append(_values("sellerCountry.keyword", seller_country))
    if is_graded:
        out.append(_values("booleanAttributes.Graded", ["True"]))
    if is_autographed:
        out.append(_values("booleanAttributes.Autographed", ["True"]))
    for param, values in attributes.items():
        if values and param in ATTRIBUTE_FILTERS:
            out.append(_values(f"stringAttributes.{ATTRIBUTE_FILTERS[param]}", values))
    return out or None


def attribute_filters(pairs, options):
    """The generic `attributes` param ([(name, value), ...]) -> FilterInputs.
    Which attributes exist depends on the query (sneakers have Size, cards
    have Set), so names are matched against the filter options Whatnot
    offers for it (`options`: the raw FilterAndSortOptions)."""
    fields = {}
    for item in P.as_list(P.as_dict(options).get("filters")):
        field = P.text(P.as_dict(item).get("field"))
        name = P.attribute_name(field) if field else None
        if name:
            fields.setdefault(name.lower(), field)
    grouped = {}
    for name, value in pairs:
        field = fields.get(name.lower())
        if field is None:
            offered = ", ".join(sorted({P.attribute_name(f) for f in fields.values()})) or "none"
            raise ValueError(f"unknown attribute '{name}' for this search — available: {offered}")
        if field.startswith("booleanAttributes."):
            value = "True" if value.lower() in ("true", "1", "yes") else "False"
        grouped.setdefault(field, [])
        if value not in grouped[field]:
            grouped[field].append(value)
    return [_values(field, values) for field, values in grouped.items()]


def livestream_filters(*, status=None, category_id=None, show_format=None, tag=None,
                       min_seller_rating=None, is_premier_shop=None, seller_country=None):
    """The FilterInput list for a livestream search / category feed."""
    out = []
    statuses = LIVESTREAM_STATUS.get(status or "all")
    if statuses:
        out.append(_values("status", statuses))
    if category_id is not None:
        out.append(_values("categories.keyword", [f"t__{category_id}"]))
    if show_format:
        out.append(_values("showFormats.keyword", [P.SHOW_FORMAT_PREFIX + f for f in show_format]))
    if tag:
        out.append(_values("inferredAndExplicitTagIds", tag))
    if min_seller_rating:
        out.append(_values("sellerRating", [min_seller_rating]))
    if is_premier_shop:
        out.append(_values("isPremierShop", ["true"]))
    if seller_country:
        out.append(_values("userCountry.keyword", seller_country))
    return out or None


def check_price_range(min_price, max_price):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("min_price must not be greater than max_price")


# ---- envelopes -------------------------------------------------------------------------

def feed_page(feed, want, key):
    """One kind of row out of a feed + the paging envelope."""
    feed = P.as_dict(feed)
    return P.page(feed.get("objects"), P.feed_rows(feed, want), key)
