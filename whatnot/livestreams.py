"""/whatnot/livestreams/* — one show (status, viewers, host, categories,
shipping), the items in its shop with live auction state, and the shows
Whatnot recommends next to it."""
from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot.fetch import WhatnotNotFound, gql, run_parallel


def _show(data, livestream):
    node = data.get("liveStream") if isinstance(data, dict) else None
    if not isinstance(node, dict) or not node.get("id"):
        raise WhatnotNotFound(f"livestream '{livestream}' not found")
    return node


def details(livestream):
    node = _show(gql(Q.LIVESTREAM_DETAILS, {"id": livestream}), livestream)
    return P.livestream_details(node)


def _shop_rows(feed):
    """Shop rows sit directly on the feed or inside sections ("Products",
    "Upcoming Giveaways" ...)."""
    listings, giveaways, seen = [], [], set()

    def take(node):
        if not isinstance(node, dict):
            return
        if node.get("__typename") == "ListingNode":
            row = P.shop_listing(node)
            if row and row["id"] not in seen:
                seen.add(row["id"])
                listings.append(row)
        elif node.get("__typename") == "GiveawayNode":
            row = P.giveaway(node)
            if row:
                giveaways.append(row)

    for node in P.nodes(P.as_dict(feed).get("objects")):
        if node.get("__typename") == "Section":
            for inner in P.nodes(node.get("contents")):
                take(inner)
        else:
            take(node.get("object"))
    return listings, giveaways


def listings(livestream, limit=24, cursor=None):
    """What is for sale in a show's shop: buy-it-now items, auctions (with
    the current bid) and giveaways. (The in-shop keyword search answers
    empty for an anonymous session, so it is not offered.)"""
    def shop():
        return gql(Q.LIVESTREAM_SHOP, {"liveId": livestream, "first": limit, "after": cursor})

    def show():
        return gql(Q.LIVESTREAM_TITLE, {"id": livestream})

    shop_data, show_data = run_parallel([shop, show])
    node = _show(show_data, livestream)
    feed = P.as_dict(P.as_dict(shop_data.get("liveShop")).get("feed"))
    rows, giveaways = _shop_rows(feed)
    out = {
        "livestream": {"id": livestream, "title": P.text(node.get("title")), "link": refs.livestream_link(livestream)},
    }
    out.update(P.page(feed.get("objects"), rows, "listings"))
    # item giveaways are listings (buying_format "giveaway"); these are the
    # separate store-credit giveaways a host can run
    out["credit_giveaways"] = giveaways
    return out


def similar(livestream):
    """The "explore" rail of a show: other shows Whatnot recommends to its
    viewers."""
    node = _show(gql(Q.LIVESTREAM_SIMILAR, {"id": livestream}), livestream)
    explore = P.as_dict(node.get("explore"))
    rows = []
    for item in P.nodes(explore.get("objects")):
        row = P.livestream(item.get("object"))
        if row and row["id"] != livestream:
            rows.append(row)
    return {
        "livestream": {"id": livestream, "title": P.text(node.get("title")), "link": refs.livestream_link(livestream)},
        "count": len(rows),
        "livestreams": rows,
    }
