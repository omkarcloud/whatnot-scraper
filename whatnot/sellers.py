"""/whatnot/sellers/* — one seller: profile and ratings, shop listings (with
the same filters as search), buyer reviews, shows, clips and the rewards
club."""
from whatnot import parsers as P
from whatnot import queries as Q
from whatnot import refs
from whatnot import shared
from whatnot.fetch import WhatnotNotFound, gql


def _user(data, seller):
    user = data.get("getUser") if isinstance(data, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        raise WhatnotNotFound(f"seller '{seller}' not found")
    return user


def _identity(user):
    username = P.text(user.get("username"))
    return {"id": refs.numeric_id(user.get("id")), "username": username,
            "link": refs.seller_link(username)}


def details(seller):
    """Profile, audience, sales, the rating breakdown and the next shows."""
    user = _user(gql(Q.USER_DETAILS, {"username": seller}), seller)
    return P.seller_details(user)


def listings(seller, query=None, sort="best_match", buying_format=None, category=None, min_price=None,
             max_price=None, is_graded=None, is_autographed=None, condition=None, language=None,
             product_type=None, set=None, rarity=None, grade=None, grading_service=None, card_number=None,
             attributes=None, limit=24, cursor=None):
    """What the seller has in their shop right now, searchable and filterable."""
    shared.check_price_range(min_price, max_price)
    slug = shared.category_identity(category)["slug"] if category else None
    filters = shared.listing_filters(
        buying_format=buying_format, category=slug, min_price=min_price, max_price=max_price,
        is_graded=is_graded, is_autographed=is_autographed, condition=condition, language=language,
        product_type=product_type, set=set, rarity=rarity, grade=grade, grading_service=grading_service,
        card_number=card_number) or []
    if attributes:
        offered = _user(gql(Q.USER_SHOP, {"username": seller, "query": query, "first": 1, "withOptions": True}), seller)
        filters += shared.attribute_filters(
            attributes, P.as_dict(offered.get("searchShop")).get("filterAndSortOptions"))
    user = _user(gql(Q.USER_SHOP, {"username": seller, "query": query, "first": limit, "after": cursor,
                                   "filters": filters or None, "sort": shared.LISTING_SORTS.get(sort)}), seller)
    shop = P.as_dict(user.get("searchShop"))
    rows = []
    for node in P.nodes(shop.get("objects")):
        row = P.listing(node.get("object"), with_seller=False)
        if row:
            rows.append(row)
    out = {"seller": _identity(user), "query": query, "sort": sort}
    out.update(P.page(shop.get("objects"), rows, "listings"))
    return out


def listing_filters(seller, query=None):
    """The filters this seller's shop offers (categories, price range,
    item attributes) with the values available right now."""
    user = _user(gql(Q.USER_SHOP, {"username": seller, "query": query, "first": 1, "withOptions": True}), seller)
    shop = P.as_dict(user.get("searchShop"))
    out = {"seller": _identity(user), "query": query,
           "listing_count": P.to_int(P.as_dict(shop.get("objects")).get("totalCount"))}
    out.update(P.filter_options(shop.get("filterAndSortOptions")))
    return out


def reviews(seller, limit=24, cursor=None):
    """Buyer reviews, newest first, with the seller's rating summary."""
    user = _user(gql(Q.USER_REVIEWS, {"username": seller, "first": limit, "after": cursor}), seller)
    connection = P.as_dict(user.get("sellerReviews"))
    rows = [P.review(n) for n in P.nodes(connection)]
    out = {"seller": _identity(user),
           "rating": P.seller_rating(user.get("sellerRating"), connection.get("totalCount"))}
    out.update(P.page(connection, rows, "reviews"))
    return out


def livestreams(seller, limit=24, cursor=None):
    """The seller's shows: live now and scheduled (Whatnot does not list
    past shows publicly)."""
    user = _user(gql(Q.USER_LIVESTREAMS, {"username": seller, "first": limit, "after": cursor}), seller)
    connection = P.as_dict(user.get("livestreams"))
    rows = [r for r in (P.livestream(n, with_seller=False) for n in P.nodes(connection)) if r]
    out = {"seller": _identity(user)}
    out.update(P.page(connection, rows, "livestreams"))
    return out


def clips(seller, limit=24, cursor=None):
    """Short clips cut from the seller's shows."""
    user = _user(gql(Q.USER_CLIPS, {"username": seller, "first": limit, "after": cursor}), seller)
    connection = P.as_dict(user.get("sellerLiveClips"))
    rows = [P.clip(n) for n in P.nodes(connection)]
    out = {"seller": _identity(user)}
    out.update(P.page(connection, rows, "clips"))
    return out


def rewards(seller):
    """The seller's rewards club for the current season: tiers, what a
    buyer must do to reach each one and what it unlocks. `rewards` is null
    for a seller without a club."""
    user = _user(gql(Q.USER_REWARDS, {"username": seller}, tolerate=[("getUser", "loyaltyProgram")]), seller)
    return {"seller": _identity(user), "rewards": P.rewards(user.get("loyaltyProgram"))}
