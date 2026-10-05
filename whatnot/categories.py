"""/whatnot/categories* — the category tree with live viewer counts, one
category with its subcategories, the shows in a category (filterable,
sortable, cursor-paged) and the filters a category offers."""
from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot import shared
from whatnot.fetch import gql


def tree():
    """Every top-level category with its subcategories and how many people
    are watching each right now."""
    data = gql(Q.TAXONOMY, {})
    rows = [c for c in (P.category(n) for n in P.as_list(data.get("livestreamTaxonomyDirectDescendants"))
                        if isinstance(n, dict)) if c]
    for row in rows:
        row.pop("parent", None)
        for child in row.get("subcategories") or []:
            child.pop("parent", None)
    return {"count": len(rows), "categories": rows}


def details(category):
    """One category: description, live numbers, parent and subcategories."""
    node = shared.category_raw(category)
    out = P.category(node)
    # the tag's own `refinements` are empty below the first level; the
    # taxonomy query is what the browse page uses for children
    if not out.get("subcategories"):
        data = gql(Q.TAXONOMY, {"parent": node["id"]})
        children = [P.category(n, with_children=False)
                    for n in P.as_list(data.get("livestreamTaxonomyDirectDescendants")) if isinstance(n, dict)]
        out["subcategories"] = [c for c in children if c and c.get("id") != out.get("id")]
    for child in out["subcategories"]:
        child.pop("parent", None)
    return out


def _identity_ref(identity):
    return {"id": refs.numeric_id(identity["id"]), "slug": identity["slug"], "name": identity["name"],
            "link": refs.category_link(identity["slug"])}


def livestreams(category, status="all", sort="recommended", show_format=None, tag=None,
                min_seller_rating=None, is_premier_shop=None, seller_country=None, limit=24, cursor=None):
    """Live and scheduled shows in a category."""
    identity = shared.category_identity(category)
    filters = shared.livestream_filters(
        status=status, show_format=show_format, tag=tag, min_seller_rating=min_seller_rating,
        is_premier_shop=is_premier_shop, seller_country=seller_country)
    feed = P.as_dict(gql(Q.FEED, {"feedId": shared.category_feed_id(identity), "first": limit, "after": cursor,
                                  "filters": filters, "sort": shared.LIVESTREAM_SORTS.get(sort)}).get("feed"))
    out = {"category": _identity_ref(identity), "status": status, "sort": sort}
    out.update(shared.feed_page(feed, "livestream", "livestreams"))
    return out


def livestream_filters(category):
    """The filters a category's show feed offers (show formats, tags,
    seller countries) with live counts."""
    identity = shared.category_identity(category)
    feed = P.as_dict(gql(Q.FEED_OPTIONS, {"feedId": shared.category_feed_id(identity)})
                     .get("homeFeedFilterAndSortOptions"))
    out = {"category": _identity_ref(identity)}
    out.update(P.filter_options(feed.get("filterAndSortOptions")))
    return out
