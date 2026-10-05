"""/whatnot/search* — the site search: one mixed call (categories + live
shows + sellers + listings), each vertical on its own with filters, sorts
and a cursor, the filter options a query offers, and the search-box
autocomplete."""
from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot import shared
from whatnot.fetch import gql


def _search(variables):
    return P.as_dict(gql(Q.SEARCH, variables).get("search"))


def search(query):
    """What the whatnot.com search page shows for a query: matching
    categories, live shows, sellers and the first page of listings."""
    feed = _search({"query": query, "vertical": "UNIVERSAL", "first": 24})
    rows, totals = P.feed_sections(feed)
    return {
        "query": query,
        "corrected_query": P.spelling(feed),
        "categories_total_count": totals.get("categories"),
        "livestreams_total_count": totals.get("livestreams"),
        "sellers_total_count": totals.get("sellers"),
        "categories": rows["categories"],
        "livestreams": rows["livestreams"],
        "sellers": rows["sellers"],
        "listings": rows["listings"],
    }


def listings(query, sort="best_match", buying_format=None, category=None, min_price=None, max_price=None,
             min_seller_rating=None, is_premier_shop=None, seller_country=None, is_graded=None,
             is_autographed=None, condition=None, language=None, product_type=None, set=None, rarity=None,
             grade=None, grading_service=None, card_number=None, attributes=None, limit=24, cursor=None):
    """Items for sale matching a query (Whatnot serves about the first
    10,000 matches of a search)."""
    shared.check_price_range(min_price, max_price)
    slug = shared.category_identity(category)["slug"] if category else None
    filters = shared.listing_filters(
        buying_format=buying_format, category=slug, min_price=min_price, max_price=max_price,
        min_seller_rating=min_seller_rating, is_premier_shop=is_premier_shop, seller_country=seller_country,
        is_graded=is_graded, is_autographed=is_autographed, condition=condition, language=language,
        product_type=product_type, set=set, rarity=rarity, grade=grade, grading_service=grading_service,
        card_number=card_number) or []
    if attributes:
        offered = P.as_dict(gql(Q.SEARCH_OPTIONS, {"query": query, "vertical": "PRODUCT"}).get("search"))
        filters += shared.attribute_filters(attributes, offered.get("filterAndSortOptions"))
    feed = _search({"query": query, "vertical": "PRODUCT", "first": limit, "after": cursor,
                    "sort": shared.LISTING_SORTS.get(sort), "filters": filters or None})
    out = {"query": query, "corrected_query": P.spelling(feed), "sort": sort}
    out.update(shared.feed_page(feed, "listing", "listings"))
    return out


def listing_filters(query):
    """Every filter Whatnot offers for a listing query, with the values and
    result counts it has right now (categories, card sets, grades ...)."""
    feed = P.as_dict(gql(Q.SEARCH_OPTIONS, {"query": query, "vertical": "PRODUCT"}).get("search"))
    out = {"query": query, "corrected_query": P.spelling(feed)}
    out.update(P.filter_options(feed.get("filterAndSortOptions")))
    return out


def livestreams(query, status="all", sort="recommended", category=None, show_format=None, tag=None,
                min_seller_rating=None, is_premier_shop=None, seller_country=None, limit=24, cursor=None):
    """Live and scheduled shows matching a query."""
    category_id = refs.numeric_id(shared.category_identity(category)["id"]) if category else None
    filters = shared.livestream_filters(
        status=status, category_id=category_id, show_format=show_format, tag=tag,
        min_seller_rating=min_seller_rating, is_premier_shop=is_premier_shop, seller_country=seller_country)
    feed = _search({"query": query, "vertical": "LIVESTREAM", "first": limit, "after": cursor,
                    "sort": shared.LIVESTREAM_SORTS.get(sort), "filters": filters})
    out = {"query": query, "corrected_query": P.spelling(feed), "status": status, "sort": sort}
    out.update(shared.feed_page(feed, "livestream", "livestreams"))
    return out


def livestream_filters(query):
    """Every filter Whatnot offers for a livestream query (categories, show
    formats, tags, seller countries) with live counts."""
    feed = P.as_dict(gql(Q.SEARCH_OPTIONS, {"query": query, "vertical": "LIVESTREAM"}).get("search"))
    out = {"query": query, "corrected_query": P.spelling(feed)}
    out.update(P.filter_options(feed.get("filterAndSortOptions")))
    return out


def sellers(query, limit=24, cursor=None):
    """Sellers (and other users) whose name matches a query."""
    feed = _search({"query": query, "vertical": "USER", "first": limit, "after": cursor})
    out = {"query": query}
    out.update(shared.feed_page(feed, "seller", "sellers"))
    return out


def categories(query):
    """Categories matching a query: the search page's category results
    first, then the taxonomy's own name matches."""
    feed = _search({"query": query, "vertical": "CATEGORY", "first": 48})
    rows = P.feed_rows(feed, "category")
    taxonomy = gql(Q.SEARCH_TAXONOMY, {"query": query}).get("searchLivestreamTaxonomy")
    seen = {r.get("slug") for r in rows}
    for node in P.as_list(taxonomy):
        row = P.category(node, with_children=False) if isinstance(node, dict) else None
        if row and row.get("slug") not in seen:
            seen.add(row.get("slug"))
            rows.append(row)
    return {"query": query, "count": len(rows), "categories": rows}


def suggestions(query):
    """The search-box autocomplete: query completions, categories, sellers
    and sellers who are live right now."""
    data = gql(Q.SEARCH_AUTOCOMPLETE, {"prefix": query})
    rows = [s for s in (P.suggestion(n) for n in P.as_list(data.get("searchAutocomplete"))) if s]
    return {"query": query, "count": len(rows), "suggestions": rows}
