"""/whatnot/listings/* — one listing with everything on its page (price,
bids, attributes, variants, the seller, the shows it is in) and the
similar-listings rail."""
from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot.fetch import WhatnotNotFound, gql


def _listing(data, listing):
    node = data.get("getListing") if isinstance(data, dict) else None
    if not isinstance(node, dict) or not node.get("id"):
        raise WhatnotNotFound(f"listing '{refs.numeric_id(listing) or listing}' not found")
    return node


def details(listing):
    node = _listing(gql(Q.LISTING_DETAILS, {"id": listing, "similar": 12}), listing)
    return P.listing_details(node)


def similar(listing, limit=24):
    """Listings Whatnot recommends next to this one."""
    node = _listing(gql(Q.LISTING_SIMILAR, {"id": listing, "first": limit}), listing)
    rows = [r for r in (P.listing(n) for n in P.nodes(node.get("recommendedListings"))) if r]
    number = refs.numeric_id(node.get("id"))
    return {
        "listing": {"id": number, "title": P.text(node.get("title")), "link": refs.listing_link(number)},
        "count": len(rows),
        "listings": rows,
    }
