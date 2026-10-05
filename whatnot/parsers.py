"""Whatnot normalizers: GraphQL objects -> one clean snake_case shape per
entity.

Output conventions (shared with the other scrapers here): `link` for
canonical page URLs (always absolute), `image` / `thumbnail` /
`profile_image` for pictures, `*_count` for counters, `is_*` / `has_*` for
booleans, ISO-8601 UTC ("2026-10-04T21:13:31Z") for timestamps, prices as
a number in major units next to a `currency` code, numbers as numbers,
null for missing. Ids are the plain numbers inside Whatnot's relay ids
(base64 "ListingNode:2373630372" -> 2373630372); livestream ids are the
uuids the site uses in /live/ links. Entity refs share one vocabulary:

  seller      {id, username, link, profile_image, rating, review_count, is_live, ...}
  listing     an item for sale (buy it now / auction / giveaway), with its seller
  livestream  a show: live now, scheduled or ended
  category    {id, slug, name, link, image}  (Whatnot calls these livestream tags)

Deliberately dropped as noise:
  * `__typename`, edge `cursor`s (surfaced once as `next_cursor`), feed
    `id` / `sessionId` / `rankingRequestId` / `returnBatchId` (ranking
    session bookkeeping), `relevanceExplanation` / `debugInfo`
  * every viewer-relative flag — isFollowing, isFollower, userBookmark,
    isBlockedByMe, isBlockingMe, canBeMessagedByMe, isMyListing,
    isUserOnWatchlist, isUserModerator, unlockStatus, myUnlockedRewards:
    constants for an anonymous session (they are not even requested)
  * `amountSafe` (same number as `amount`), `localizedPrice` and the
    "(est. ₹…)" suffixes: conversions into the currency of the REQUESTING
    IP, which is our server, not the caller
  * image `id` / `key` / `bucket` (S3 internals; the signed link is kept)
    and ListingImage `label` (the file's uuid or the title again)
  * `version` / `variantsVersion` (optimistic-locking tokens),
    `salesChannels[].meta` (internal product ids; the channel itself is
    kept as the listing's `livestream_id`), `streamToken` /
    `streamAgoraAppId` / `liveCommerceChannel` (player credentials, null
    without a login), `tsStanding` / `tsActionState` (trust & safety state,
    null for other accounts), `profilePreferences`, `adCampaign` /
    `livestreamPromotion` (the seller's own ad state), LiveClip `url`
    (an s3:// path; `urlForDisplay` is the playable one), `categories`
    ("t__907": the tag id again), `isAutoplayEnabled`, `canScheduleLive`,
    `isFollowable`, loyalty `brand.status`
"""
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from whatnot import refs

# Currencies whose `amount` is already in major units (no cents).
_ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF", "TWD", "IDR"}
_UUID_ONLY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_EST_RE = re.compile(r"\s*\(est\.[^)]*\)")

_STATUS = {"PLAYING": "live", "CREATED": "upcoming", "ENDED": "ended", "STOPPED": "ended",
           "CANCELLED": "cancelled", "CANCELED": "cancelled"}
_BUYING_FORMAT = {"BUY_IT_NOW": "buy_it_now", "AUCTION": "auction", "LIVESTREAM_AUCTION": "auction",
                  "GIVEAWAY": "giveaway"}

# upstream filter field -> the public query param that sets it. Item
# attributes without a param of their own (Size, Colorway ...) are set
# through the generic `attributes` param.
FILTER_PARAMS = {
    "category.keyword": "category",
    "categories.keyword": "category",
    "buyingFormat": "buying_format",
    "sellerRating": "min_seller_rating",
    "isPremierShop": "is_premier_shop",
    "sellerCountry.keyword": "seller_country",
    "userCountry.keyword": "seller_country",
    "priceCents": "min_price,max_price",
    "status": "status",
    "showFormats.keyword": "show_format",
    "inferredAndExplicitTagIds": "tag",
    "booleanAttributes.Graded": "is_graded",
    "booleanAttributes.Autographed": "is_autographed",
    "stringAttributes.Condition": "condition",
    "stringAttributes.Language": "language",
    "stringAttributes.Product Type": "product_type",
    "stringAttributes.Set": "set",
    "stringAttributes.Rarity": "rarity",
    "stringAttributes.Grade": "grade",
    "stringAttributes.Grading Service": "grading_service",
    "stringAttributes.Card Number": "card_number",
}
ATTRIBUTE_PREFIXES = ("stringAttributes.", "integerAttributes.", "booleanAttributes.")
# upstream option tokens -> the values our params take
_OPTION_VALUES = {
    "buyingFormat": {"BUY_IT_NOW": "buy_it_now", "LIVESTREAM_AUCTION": "auction"},
    "status": {"PLAYING": "live", "CREATED": "upcoming"},
    "booleanAttributes.Graded": {"True": "true"},
    "booleanAttributes.Autographed": {"True": "true"},
}
SHOW_FORMAT_PREFIX = "primary_show_format_"


# ---- value helpers ---------------------------------------------------------------------

def to_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def to_float(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def text(value):
    """Trimmed string, or None for empty / non-string."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def boolean(value):
    return value if isinstance(value, bool) else None


def lower(value):
    value = text(value)
    return value.lower() if value else None


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def iso_from_ms(value):
    """Epoch milliseconds -> '2026-10-04T21:13:31Z'."""
    ms = to_float(value)
    if not ms or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def iso_from_http_date(value):
    """'Sun, 04 Oct 2026 21:13:31 GMT' (or an ISO string) -> '2026-10-04T21:13:31Z'."""
    value = text(value)
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def amount(money):
    """Money {amount: 1000, currency: 'GBP'} -> 10.0 (major units)."""
    money = as_dict(money)
    raw = to_float(money.get("amount"))
    if raw is None:
        return None
    if (text(money.get("currency")) or "").upper() in _ZERO_DECIMAL:
        return float(raw)
    return round(raw / 100, 2)


def currency(*moneys):
    """The first currency code among several Money objects."""
    for money in moneys:
        code = text(as_dict(money).get("currency"))
        if code:
            return code.upper()
    return None


def money(value):
    """Money -> {amount, currency} or None."""
    if not isinstance(value, dict) or value.get("amount") is None:
        return None
    return {"amount": amount(value), "currency": currency(value)}


def image(value):
    """{url} -> the link."""
    return text(as_dict(value).get("url"))


def nodes(connection):
    """A relay connection -> its node dicts."""
    return [e["node"] for e in as_list(as_dict(connection).get("edges"))
            if isinstance(e, dict) and isinstance(e.get("node"), dict)]


def _cursor_offset(cursor):
    """base64 'arrayconnection:23' -> 23; None for any other cursor."""
    kind, rest = refs.decode_global_id(cursor)
    return int(rest) if kind == "arrayconnection" and rest.isdigit() else None


def page(connection, rows, key):
    """Relay connection + parsed rows -> the list envelope every paged
    endpoint returns."""
    connection = as_dict(connection)
    info = as_dict(connection.get("pageInfo"))
    has_more = bool(info.get("hasNextPage")) and bool(rows)
    cursor = text(info.get("endCursor"))
    total = to_int(connection.get("totalCount"))
    # feed connections answer hasNextPage true (cursor = offset + first - 1)
    # even when the page already reached the end of the result set
    offset = _cursor_offset(cursor)
    if has_more and total is not None and offset is not None and offset + 1 >= total:
        has_more = False
    return {
        "count": len(rows),
        "total_count": total,
        key: rows,
        "next_cursor": cursor if has_more else None,
        "has_more": has_more and bool(cursor),
    }


def clean_estimate(value):
    """Strip the '(est. ₹963.26)' conversions Whatnot appends for the
    requesting IP's currency."""
    value = text(value)
    return text(_EST_RE.sub("", value)) if value else None


# ---- sellers ---------------------------------------------------------------------------

def _badges(value):
    return [b for b in (text(as_dict(x).get("label")) for x in as_list(value)) if b]


def user_ref(node):
    """The seller card embedded in listings, livestreams and search rows."""
    if not isinstance(node, dict) or not (node.get("username") or node.get("id")):
        return None
    username = text(node.get("username"))
    rating = as_dict(node.get("sellerRating"))
    return {
        "id": refs.numeric_id(node.get("id")),
        "username": username,
        "link": refs.seller_link(username),
        "profile_image": image(node.get("profileImage")),
        "rating": to_float(rating.get("overall")),
        "review_count": to_int(rating.get("numReviews")),
        "is_live": boolean(node.get("isLive")),
        "is_verified": boolean(node.get("isVerifiedSeller")),
        "is_premier_shop": boolean(as_dict(node.get("premierShopStatus")).get("isPremierShop")),
        "badges": _badges(node.get("sellerBadges")),
    }


def user_min(node):
    """{id, username, link} for bidders, reviewers, moderators, clippers."""
    if not isinstance(node, dict) or not (node.get("username") or node.get("id")):
        return None
    username = text(node.get("username"))
    out = {"id": refs.numeric_id(node.get("id")), "username": username, "link": refs.seller_link(username)}
    if "profileImage" in node:
        out["profile_image"] = image(node.get("profileImage"))
    return out


def user_tile(node):
    """A seller row in search results: the ref plus audience numbers."""
    base = user_ref(node)
    if base is None:
        return None
    return {
        "id": base["id"],
        "username": base["username"],
        "display_name": text(node.get("displayName")),
        "link": base["link"],
        "profile_image": base["profile_image"],
        "store_image": image(node.get("storeImage")),
        "rating": base["rating"],
        "review_count": base["review_count"],
        "follower_count": to_int(node.get("followerCount")),
        "following_count": to_int(node.get("followingCount")),
        "sold_count": to_int(node.get("soldCount")),
        "is_live": base["is_live"],
        "is_verified": base["is_verified"],
        "is_premier_shop": base["is_premier_shop"],
        "can_go_live": boolean(node.get("canGoLive")),
        "badges": base["badges"],
    }


def seller_details(node):
    base = user_ref(node) or {}
    rating = as_dict(node.get("sellerRating"))
    shows = as_dict(node.get("livestreams"))
    upcoming = [livestream(n, with_seller=False) for n in nodes(shows)]
    return {
        "id": base.get("id"),
        "username": base.get("username"),
        "display_name": text(node.get("displayName")),
        "link": base.get("link"),
        "bio": text(node.get("bio")),
        "profile_image": base.get("profile_image"),
        "store_image": image(node.get("storeImage")),
        "ships_from_country": text(node.get("shippingSourceCountryCode")),
        "average_ship_days": to_int(node.get("averageShipDays")),
        "follower_count": to_int(node.get("followerCount")),
        "following_count": to_int(node.get("followingCount")),
        "sold_count": to_int(node.get("soldCount")),
        "livestream_count": to_int(shows.get("totalCount")),
        "clip_count": to_int(as_dict(node.get("sellerLiveClips")).get("totalCount")),
        "rating": seller_rating(rating, as_dict(node.get("sellerReviews")).get("totalCount")),
        "is_live": base.get("is_live"),
        "is_verified": base.get("is_verified"),
        "is_premier_shop": base.get("is_premier_shop"),
        "is_on_vacation": boolean(node.get("vacationMode")),
        "can_go_live": boolean(node.get("canGoLive")),
        "badges": base.get("badges") or [],
        "livestreams": [s for s in upcoming if s],
        "joined_at": iso_from_http_date(node.get("createdAt")),
    }


def seller_rating(rating, written_review_count=None):
    """SellerRating -> the overall score, its three components and the
    review count (numReviews and sellerReviews.totalCount are one number)."""
    rating = as_dict(rating)
    count = to_int(rating.get("numReviews"))
    return {
        "overall": to_float(rating.get("overall")),
        "shipping": to_float(rating.get("shipping")),
        "packaging": to_float(rating.get("packaging")),
        "accuracy": to_float(rating.get("accuracy")),
        "review_count": count if count is not None else to_int(written_review_count),
    }


def review(node):
    reviewer = user_min(node.get("reviewedBy"))
    scores = {}
    comments = {}
    for key, field in (("overall", "ratingOverall"), ("shipping", "ratingShipping"),
                       ("packaging", "ratingPackaging"), ("accuracy", "ratingAccuracy")):
        answer = as_dict(node.get(field))
        scores[key] = to_int(answer.get("value"))
        note = text(answer.get("explanation"))
        if key != "overall":
            comments[key] = note
    body = text(node.get("overallReview")) or text(as_dict(node.get("ratingOverall")).get("explanation"))
    return {
        "id": refs.numeric_id(node.get("id")),
        "rating": to_float(node.get("averageRating")),
        "text": body,
        "seller_response": text(node.get("sellerResponse")),
        "ratings": scores,
        "comments": comments,
        "reviewer": reviewer,
        "reviewed_at": iso_from_http_date(node.get("reviewedOn")),
    }


def clip(node, seller=None):
    uuid = text(node.get("uuid"))
    livestream_id = text(node.get("livestreamId"))
    return {
        "id": to_int(node.get("id")),
        "uuid": uuid,
        "title": text(node.get("name")),
        "link": refs.clip_link(uuid),
        "video": text(node.get("urlForDisplay")),
        "thumbnail": text(node.get("thumbnailUrl")),
        "view_count": to_int(node.get("totalViews")),
        "is_published": boolean(node.get("isPublished")),
        "livestream": {"id": livestream_id, "link": refs.livestream_link(livestream_id)} if livestream_id else None,
        "clipped_by": user_min(node.get("clipper")),
    }


# ---- categories ------------------------------------------------------------------------

def category_ref(node):
    """LivestreamTagNode -> {id, slug, name, link}."""
    if not isinstance(node, dict) or not (node.get("name") or node.get("label") or node.get("id")):
        return None
    slug = text(node.get("name")) or _slug_from_deeplink(node.get("deeplink"))
    return {
        "id": refs.numeric_id(node.get("id")),
        "slug": slug,
        "name": text(node.get("label")),
        "link": refs.category_link(slug),
    }


def _slug_from_deeplink(value):
    value = text(value)
    return value.rsplit("/", 1)[-1] if value else None


def category(node, with_children=True):
    """A browsable category (LivestreamTagNode) with its live numbers."""
    base = category_ref(node)
    if base is None:
        return None
    out = {
        "id": base["id"],
        "slug": base["slug"],
        "name": base["name"],
        "link": base["link"],
        "description": text(node.get("description")),
        "image": image(node.get("image")),
        "viewer_count": to_int(node.get("viewerCount")),
        "live_show_count": to_int(node.get("livestreamCount")),
        "parent": category_ref(node.get("parent")),
    }
    if with_children and "refinements" in node:
        children = [category(c, with_children=False) for c in as_list(node.get("refinements")) if isinstance(c, dict)]
        out["subcategories"] = [c for c in children if c]
    return out


def product_category(node):
    """CategoryNode (the catalogue category of an item) -> {id, slug, name, link}."""
    if not isinstance(node, dict) or not (node.get("type") or node.get("label")):
        return None
    slug = text(node.get("type"))
    out = {
        "id": refs.numeric_id(node.get("id")),
        "slug": slug,
        "name": text(node.get("label")),
        "link": refs.category_link(slug),
    }
    if "image" in node:
        out["image"] = image(node.get("image"))
    return out


# ---- livestreams -----------------------------------------------------------------------

def _labels(value):
    out = []
    for item in as_list(value):
        label = text(item) if isinstance(item, str) else text(as_dict(item).get("label") or as_dict(item).get("type"))
        if label:
            out.append(label.lower())
    return out


def _dedupe(rows):
    seen, out = set(), []
    for row in rows:
        if not row:
            continue
        key = row.get("id") or row.get("slug")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def livestream(node, with_seller=True):
    """LiveStream tile. `with_seller=False` where the host is the entity
    the response is already about (a seller's own shows, a listing's shows)."""
    if not isinstance(node, dict) or not node.get("id"):
        return None
    uuid = text(node.get("id"))
    status = text(node.get("status"))
    language = as_dict(node.get("sellerLanguage"))
    max_shipping = node.get("buyerPaysMaxAmountForShipping")
    out = {
        "id": uuid,
        "title": text(node.get("title")),
        "link": refs.livestream_link(uuid),
        "status": _STATUS.get(status, status.lower() if status else None),
        "is_live": status == "PLAYING" if status else None,
        "viewer_count": to_int(node.get("activeViewers")),
        "saved_count": to_int(node.get("totalWatchlistUsers")),
        "thumbnail": image(node.get("thumbnail")),
        "trailer": text(node.get("trailerUrl")),
        "trailer_thumbnail": text(node.get("trailerThumbnailUrl")),
        "language": {"code": text(language.get("languageCode")), "name": text(language.get("displayName"))} if language else None,
        "ships_from_country": text(node.get("shippingSourceCountryCode")),
        "has_free_shipping": boolean(node.get("isFreeShippingEnabled")),
        "max_shipping_cost": money(max_shipping),
        "is_explicit": boolean(node.get("explicitContent")),
        "is_hidden": boolean(node.get("isHiddenBySeller")),
        "labels": _labels(node.get("livestreamLabels")),
        "categories": _dedupe(category_ref(c) for c in as_list(node.get("livestreamCategories"))),
        "product_categories": _dedupe(product_category(c) for c in as_list(node.get("categoryNodes"))),
        "tags": _dedupe(category_ref(t) for t in as_list(node.get("tags"))),
        "seller": user_ref(node.get("user")),
        "starts_at": iso_from_ms(node.get("startTime")),
        "ended_at": iso_from_ms(node.get("endTime")),
    }
    if not with_seller:
        out.pop("seller")
    return out


def livestream_details(node):
    base = livestream(node)
    if base is None:
        return None
    host = as_dict(node.get("user"))
    seller = base.pop("seller") or {}
    starts_at, ended_at = base.pop("starts_at"), base.pop("ended_at")
    seller.update({
        "display_name": text(host.get("displayName")),
        "bio": text(host.get("bio")),
        "store_image": image(host.get("storeImage")),
        "follower_count": to_int(host.get("followerCount")),
        "following_count": to_int(host.get("followingCount")),
        "sold_count": to_int(host.get("soldCount")),
        "average_ship_days": to_int(host.get("averageShipDays")),
    })
    notes = [t for t in (text(as_dict(as_dict(n).get("content")).get("text")) for n in as_list(node.get("showNotes"))) if t]
    base.update({
        "description": text(node.get("description")),
        "notes": notes,
        "stream_service": text(node.get("streamService")),
        "pinned_product_id": text(node.get("pinnedProductId")),
        "has_shop": boolean(node.get("buyerShopEnabled")),
        "has_captions": boolean(node.get("captionsEnabled")),
        "has_local_pickup": boolean(as_dict(node.get("localPickupSettings")).get("enabled")),
        "accepts_prebids": (not node["prebidsDisabled"]) if isinstance(node.get("prebidsDisabled"), bool) else None,
        "moderators": [m for m in (user_min(u) for u in as_list(node.get("nominatedModerators"))) if m],
        "seller": seller or None,
        "starts_at": starts_at,
        "ended_at": ended_at,
    })
    return base


# ---- listings --------------------------------------------------------------------------

def _images(value):
    out = []
    for item in as_list(value):
        link = image(item)
        if link and link not in out:
            out.append(link)
    return out


def _timed_event(node, fallback_currency=None):
    """A flash sale on a listing -> {type, price, original_price, currency, ends_at}."""
    if not isinstance(node, dict):
        return None
    return {
        "type": lower(node.get("type")),
        "price": amount(node.get("discountPrice")),
        "original_price": amount(node.get("originalPrice")),
        "currency": currency(node.get("discountPrice"), node.get("originalPrice")) or fallback_currency,
        "is_available_at_full_price": boolean(node.get("isAvailableForFullPrice")),
        "ends_at": iso_from_ms(node.get("endsAtMs")),
    }


def break_ref(node):
    """A card break attached to a listing (spots sold out of a box / case)."""
    if not isinstance(node, dict) or not node.get("id"):
        return None
    return {
        "id": refs.numeric_id(node.get("id")) or text(node.get("id")),
        "title": text(node.get("title")),
        "format": lower(node.get("format")),
        "status": lower(node.get("status")),
        "spot_type": lower(node.get("spotType")),
        "buying_format": _BUYING_FORMAT.get(text(node.get("defaultTransactionType")), lower(node.get("defaultTransactionType"))),
        "total_spot_count": to_int(node.get("totalBreakSpots")),
        "filled_spot_count": to_int(node.get("filledBreakSpots")),
        "sold_spot_count": to_int(node.get("soldSpotCount")),
    }


def _variants(value):
    out = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        title = text(item.get("title"))
        if title is None and len(as_list(value)) == 1:
            continue        # the single untitled default variant: quantity is already on the listing
        out.append({"id": text(item.get("id")), "title": title, "quantity": to_int(item.get("quantity"))})
    return out


def _attributes(value):
    """[{value, attribute {key, label}}] -> [{key, name, value}]."""
    out = []
    for item in as_list(value):
        item = as_dict(item)
        attribute = as_dict(item.get("attribute"))
        name = text(attribute.get("label")) or text(attribute.get("key"))
        if not name or item.get("value") in (None, ""):
            continue
        raw = item.get("value")
        out.append({
            "key": text(attribute.get("key")) or name.lower().replace(" ", "_"),
            "name": name,
            "value": raw if isinstance(raw, (bool, int, float)) else text(str(raw)),
        })
    return out


def _livestream_id_of(node):
    """The show a listing is attached to: the active one, else the first
    sales channel that is a livestream uuid."""
    active = text(node.get("activeLivestreamId"))
    if active:
        return active
    for channel in as_list(node.get("salesChannels")):
        cid = text(as_dict(channel).get("channelId"))
        if cid and _UUID_ONLY_RE.match(cid):
            return cid
    return None


def listing(node, with_seller=True):
    """ListingNode tile -> the listing shape shared by search, shops,
    livestream shops and similar-listing rails."""
    if not isinstance(node, dict) or not node.get("id"):
        return None
    number = refs.numeric_id(node.get("id"))
    price, bid, compare = node.get("price"), node.get("currentBid"), node.get("compareAtPrice")
    live_auction = as_dict(node.get("liveAuction"))
    if live_auction:
        bid = live_auction.get("currentPrice") or bid
    kind = text(node.get("transactionType"))
    pics = _images(node.get("images"))
    code = currency(price, bid, compare)
    price_range = as_dict(as_dict(node.get("product")).get("priceRange"))
    low, high = amount(price_range.get("min")), amount(price_range.get("max"))
    livestream_id = _livestream_id_of(node)
    # livestreamStartTime is the listing's NEXT show: with several scheduled
    # shows and none active it need not be the show picked as livestream_id
    shows = [c for c in as_list(node.get("salesChannels"))
             if _UUID_ONLY_RE.match(text(as_dict(c).get("channelId")) or "")]
    start_known = bool(text(node.get("activeLivestreamId"))) or len(shows) <= 1
    bid_count = to_int(live_auction.get("bidCount")) if live_auction else None
    if bid_count is None:
        bid_count = to_int(node.get("currentBidCount"))
    out = {
        "id": number,
        "title": text(node.get("title")),
        "subtitle": text(node.get("subtitle")),
        "description": text(node.get("description")),
        "link": refs.listing_link(number),
        "status": lower(node.get("publicStatus")),
        "buying_format": _BUYING_FORMAT.get(kind, kind.lower() if kind else None),
        "price": amount(price),
        "compare_at_price": amount(compare),
        "price_range": {"min": low, "max": high} if (low is not None and high is not None and low != high) else None,
        "currency": code,
        "current_bid": amount(bid),
        "bid_count": bid_count,
        "quantity": to_int(node.get("quantity")),
        "bookmark_count": to_int(node.get("totalBookmarks")),
        "image": pics[0] if pics else None,
        "images": pics,
        "is_live": boolean(node.get("isLive")),
        "is_pending_payment": boolean(node.get("pendingPayment")),
        "shipping_details": text(node.get("shippingDetails")) if isinstance(node.get("shippingDetails"), str) else None,
        "labels": _labels(node.get("listingLabels")),
        "variants": _variants(node.get("variants")),
        "sale": _timed_event(node.get("activeTimedListingEvent"), code),
        "upcoming_sale": _timed_event(node.get("upcomingTimedListingEvent"), code),
        "break": break_ref(node.get("break")),
        "livestream": {
            "id": livestream_id,
            "link": refs.livestream_link(livestream_id),
            "starts_at": iso_from_ms(node.get("livestreamStartTime")) if start_known else None,
        } if livestream_id else None,
    }
    if "category" in node:
        out["category"] = product_category(node.get("category"))
    if with_seller:
        out["seller"] = user_ref(node.get("user"))
    out["created_at"] = iso_from_http_date(node.get("createdAt"))
    out["updated_at"] = iso_from_ms(node.get("updatedAtMs"))
    return out


def _auction(node):
    """transactionProps.auction + the live auction state -> one object."""
    props = as_dict(as_dict(node.get("transactionProps")).get("auction"))
    state = as_dict(node.get("liveAuction"))
    if not props and not state:
        return None
    return {
        "duration_seconds": to_int(props.get("durationSeconds")),
        "is_sudden_death": boolean(props.get("isSuddenDeath")),
        "current_bid": amount(state.get("currentPrice")),
        "bid_count": to_int(state.get("bidCount")),
        "highest_bidder": user_min(state.get("currentBidUser")),
        "ends_at": iso_from_ms(state.get("endTime")) or iso_from_http_date(state.get("endTime"))
                   or iso_from_ms(props.get("endTime")) or iso_from_http_date(props.get("endTime")),
    }


def _videos(value):
    out = []
    for item in as_list(value):
        item = as_dict(item)
        link = text(item.get("url"))
        if not link:
            continue
        out.append({
            "link": link,
            "thumbnail": text(item.get("thumbnailUrl")),
            "duration_seconds": to_float(item.get("duration")),
            "has_audio": boolean(item.get("hasAudioTrack")),
        })
    return out


def _offers(node):
    props = as_dict(node.get("transactionProps"))
    return {
        "accepts_offers": boolean(props.get("isOfferable")),
        "max_offer_discount_percent": to_float(as_dict(props.get("offers")).get("maxDiscount")),
    }


def shop_listing(node):
    """A listing inside a livestream's shop: the tile plus auction state,
    offer rules, giveaway rules and videos. The seller is the show's host,
    so it is not repeated on every row."""
    base = listing(node, with_seller=False)
    if base is None:
        return None
    created, updated = base.pop("created_at"), base.pop("updated_at")
    base.pop("livestream", None)
    giveaway = as_dict(as_dict(node.get("transactionProps")).get("giveaway"))
    spot = as_dict(node.get("breakSpot"))
    base.update(_offers(node))
    base.update({
        "product_id": refs.numeric_id(node.get("productId")),
        "structure": lower(node.get("structure")),
        "selling_mechanic": lower(as_dict(node.get("sellingMechanic")).get("sellingMechanicType")),
        "auction": _auction(node),
        "giveaway": {
            "is_followers_only": boolean(giveaway.get("onlyFollowers")),
            "is_domestic_only": boolean(giveaway.get("onlyDomestic")),
            "is_buyer_appreciation": boolean(giveaway.get("buyerAppreciation")),
        } if giveaway else None,
        "break_spot": {"id": text(spot.get("id")), "title": text(spot.get("title"))} if spot.get("id") else None,
        "videos": _videos(node.get("videos")),
        "created_at": created,
        "updated_at": updated,
    })
    return base


def giveaway(node):
    """A standalone giveaway row in a livestream shop."""
    if not isinstance(node, dict) or not node.get("id"):
        return None
    credit = as_dict(as_dict(node.get("credit")).get("amount"))
    return {
        "id": refs.numeric_id(node.get("id")) or text(node.get("id")),
        "eligibility": lower(node.get("eligibilityType")),
        "credit": money(credit),
    }


def listing_details(node):
    base = listing(node)
    if base is None:
        return None
    created, updated = base.pop("created_at"), base.pop("updated_at")
    seller = base.pop("seller") or {}
    owner = as_dict(node.get("user"))
    seller.update({
        "display_name": text(owner.get("displayName")),
        "bio": text(owner.get("bio")),
        "store_image": image(owner.get("storeImage")),
        "follower_count": to_int(owner.get("followerCount")),
        "following_count": to_int(owner.get("followingCount")),
        "sold_count": to_int(owner.get("soldCount")),
        "average_ship_days": to_int(owner.get("averageShipDays")),
        "ships_from_country": text(owner.get("shippingSourceCountryCode")),
        "is_on_vacation": boolean(owner.get("vacationMode")),
    })
    product = as_dict(node.get("product"))
    options = []
    for option in as_list(product.get("variantOptions")):
        option = as_dict(option)
        attribute = as_dict(option.get("productAttribute"))
        values = [v for v in (text(as_dict(x).get("value")) for x in as_list(option.get("values"))) if v]
        if attribute.get("label") or attribute.get("key"):
            options.append({"name": text(attribute.get("label")) or text(attribute.get("key")), "values": values})
    attributes = _attributes(node.get("listingAttributeValues")) or _attributes(product.get("attributeValues"))
    similar = [listing(n) for n in nodes(node.get("recommendedListings"))]
    shows = [livestream(s, with_seller=False) for s in as_list(node.get("livestreams"))]
    base.pop("livestream", None)
    base.update(_offers(node))
    base.update({
        "uuid": text(node.get("uuid")),
        "sku": text(node.get("sku")),
        "structure": lower(node.get("structure")),
        "discounted_price": amount(node.get("discountedPrice")),
        "is_view_only": boolean(node.get("viewOnly")),
        "has_right_of_withdrawal": boolean(node.get("allowsRightOfWithdrawal")),
        "category": product_category(node.get("category")) or product_category(product.get("category")),
        "attributes": attributes,
        "variant_options": options,
        "auction": _auction(node),
        "videos": _videos(node.get("videos")),
        "product": {
            "id": refs.numeric_id(product.get("id")),
            "name": text(product.get("name")),
            "subtitle": text(product.get("subtitle")),
            "description": text(product.get("description")),
            "variant_count": to_int(product.get("numVariants")),
        } if product.get("id") else None,
        "seller": seller or None,
        "livestreams": [s for s in shows if s],
        "similar_listings": [s for s in similar if s],
        "created_at": created,
        "updated_at": updated or iso_from_http_date(node.get("updatedAt")),
    })
    return base


# ---- feeds (search, category feeds, browse) --------------------------------------------

def entity(node):
    """One feed object -> (kind, parsed) where kind is listing / livestream /
    seller / category, or (None, None) for anything else."""
    if not isinstance(node, dict):
        return None, None
    kind = node.get("__typename")
    if kind == "ListingNode":
        return "listing", listing(node)
    if kind == "LiveStream":
        return "livestream", livestream(node)
    if kind == "PublicUserNode":
        return "seller", user_tile(node)
    if kind == "LivestreamTagNode":
        return "category", category(node, with_children=False)
    if kind == "CategoryNode":
        return "category", product_category(node)
    if kind == "HighConfidenceUserNode":
        # the exact-match seller card on top of a search, with their live show
        seller = user_tile(node.get("user"))
        if seller is not None:
            seller["livestream"] = livestream(node.get("livestream"))
        return "seller", seller
    return None, None


def feed_rows(feed, want):
    """The rows of one kind in a paged feed, in feed order. Only the feed's
    own rows count: a Section inside a paged feed is a promotional rail
    ("Buy direct from Japan") that is not part of the result set, repeats
    rows and ignores the page size."""
    out = []
    for node in nodes(as_dict(feed).get("objects")):
        if node.get("__typename") == "Section":
            continue
        kind, row = entity(node.get("object"))
        if kind == want and row:
            out.append(row)
    return out


def feed_sections(feed):
    """A mixed feed -> {listings, livestreams, sellers, categories} plus the
    per-section totals Whatnot reports."""
    rows = {"categories": [], "livestreams": [], "sellers": [], "listings": []}
    totals = {}
    plural = {"category": "categories", "livestream": "livestreams", "seller": "sellers", "listing": "listings"}
    vertical_key = {"CATEGORY": "categories", "LIVESTREAM": "livestreams", "USER": "sellers", "PRODUCT": "listings"}
    for node in nodes(as_dict(feed).get("objects")):
        if node.get("__typename") == "Section":
            contents = as_dict(node.get("contents"))
            vertical = text(as_dict(as_dict(node.get("feed")).get("searchParams")).get("vertical"))
            if vertical in vertical_key and contents.get("totalCount") is not None:
                totals[vertical_key[vertical]] = to_int(contents.get("totalCount"))
            for inner in nodes(contents):
                kind, row = entity(inner)
                if row:
                    rows[plural[kind]].append(row)
            continue
        kind, row = entity(node.get("object"))
        if row:
            rows[plural[kind]].append(row)
    for key in rows:
        rows[key] = _dedupe(rows[key])
    return rows, totals


def spelling(feed):
    correction = as_dict(as_dict(as_dict(feed).get("searchParams")).get("spellingCorrection"))
    return text(correction.get("correctedQuery"))


# ---- filters ---------------------------------------------------------------------------

def _option(value, field):
    value = as_dict(value)
    raw = text(str(value.get("value"))) if value.get("value") is not None else None
    if raw and field == "showFormats.keyword" and raw.startswith(SHOW_FORMAT_PREFIX):
        raw = raw[len(SHOW_FORMAT_PREFIX):]
    if raw and raw.startswith("t__") and raw[3:].isdigit():
        raw = raw[3:]           # livestream category filter: "t__907" is tag 907
    raw = _OPTION_VALUES.get(field, {}).get(raw, raw)
    return {"value": raw, "name": text(value.get("displayValue")), "count": to_int(value.get("numResults"))}


def attribute_name(field):
    """'stringAttributes.Card Number' -> 'Card Number'; None for a
    non-attribute filter."""
    for prefix in ATTRIBUTE_PREFIXES:
        if field.startswith(prefix):
            return field[len(prefix):]
    return None


def filter_options(options):
    """FilterAndSortOptions -> {filters: [...], sorts: [...]} described in
    terms of the public query params: `param` is the param to send and
    `options[].value` what to put in it. Item attributes that have no param
    of their own carry `param: "attributes"` and are sent as
    attributes=<attribute>=<value>."""
    options = as_dict(options)
    filters = []
    for item in as_list(options.get("filters")):
        item = as_dict(item)
        field = text(item.get("field"))
        if not field:
            continue
        opts = as_dict(item.get("options"))
        allowed = as_dict(opts.get("allowedRange"))
        attribute = attribute_name(field)
        param = FILTER_PARAMS.get(field) or ("attributes" if attribute else None)
        is_price = field == "priceCents"
        low, high = to_float(allowed.get("minimum")), to_float(allowed.get("maximum"))
        filters.append({
            "param": param,
            "attribute": attribute if param == "attributes" else None,
            "name": text(item.get("displayField")),
            "type": lower(item.get("selectionType")),
            "options": [o for o in (_option(v, field) for v in as_list(opts.get("allowedValues"))) if o["value"]],
            "range": {
                "min": round(low / 100, 2) if (is_price and low is not None) else low,
                "max": round(high / 100, 2) if (is_price and high is not None) else high,
            } if allowed else None,
        })
    sorts = [text(as_dict(s).get("displayField")) for s in as_list(options.get("sorts"))]
    return {"filters": filters, "sorts": [s for s in sorts if s]}


# ---- search suggestions ----------------------------------------------------------------

_SUGGESTION_TYPE = {"SEARCH_QUERY": "query", "LIVESTREAM_TAG": "category", "CATEGORY": "category",
                    "USER": "seller", "LIVESTREAM": "livestream"}


def suggestion(node):
    if not isinstance(node, dict) or not text(node.get("query")):
        return None
    kind = text(node.get("resultType"))
    result = as_dict(node.get("result"))
    typename = result.get("__typename")
    out = {
        "text": text(node.get("query")),
        "type": _SUGGESTION_TYPE.get(kind, kind.lower() if kind else None),
        "subtitle": text(node.get("subtitle")),
        "is_live": boolean(node.get("isLive")),
        "seller": None,
        "category": None,
        "livestream": None,
    }
    if typename == "PublicUserNode":
        out["seller"] = user_ref(result)
        if out["seller"]:
            out["seller"]["follower_count"] = to_int(result.get("followerCount"))
    elif typename == "LiveStream":
        out["seller"] = user_ref(result.get("user"))
        uuid = text(result.get("id"))
        out["livestream"] = {"id": uuid, "title": text(result.get("title")), "link": refs.livestream_link(uuid),
                             "viewer_count": to_int(result.get("activeViewers"))}
    elif typename == "LivestreamTagNode":
        ref = category_ref(result)
        if ref:
            ref["image"] = image(result.get("image"))
        out["category"] = ref
    elif typename == "CategoryNode":
        out["category"] = product_category(result)
    return out


# ---- seller rewards (loyalty program) --------------------------------------------------

def _achievement(node):
    node = as_dict(node)
    kind = lower(node.get("achievementType"))
    if not kind:
        return None
    required = node.get("moneyRequirement")
    if isinstance(required, dict):
        return {"type": kind, "required": amount(required), "currency": currency(required)}
    return {"type": kind, "required": to_int(node.get("requirement")), "currency": None}


def _reward(node):
    node = as_dict(node)
    return {"type": lower(node.get("rewardType")), "description": clean_estimate(node.get("description"))}


def rewards(program):
    """LoyaltyProgramNode -> the seller's rewards club: season + tiers, each
    with what a buyer must do (requirements: ANY one group unlocks it) and
    what they get."""
    if not isinstance(program, dict) or not program.get("id"):
        return None
    season = as_dict(program.get("seasonInfo"))
    brands = as_dict(as_dict(program.get("brand")).get("tierBrands"))
    tiers = []
    for tier in as_list(program.get("tiers")):
        tier = as_dict(tier)
        level = lower(tier.get("level"))
        brand = as_dict(brands.get(level)) if level else {}
        groups = []
        for group in as_list(tier.get("achievementGroups")):
            items = [a for a in (_achievement(x) for x in as_list(as_dict(group).get("achievements"))) if a]
            if items:
                groups.append(items)
        tiers.append({
            "level": level,
            "name": text(brand.get("displayName")),
            "badge_image": image(brand.get("largeBadgeImage")),
            "banner_image": image(brand.get("bannerImage")),
            "requirements": groups,
            "rewards": [_reward(r) for r in as_list(tier.get("rewards")) if isinstance(r, dict)],
        })
    return {
        "id": to_int(program.get("id")),
        "status": lower(program.get("status")),
        "season": {
            "number": to_int(season.get("seasonNumber")),
            "name": text(season.get("seasonName")),
            "starts_at": iso_from_ms(season.get("seasonStartMs")),
            "ends_at": iso_from_ms(season.get("seasonEndMs")),
        } if season else None,
        "tiers": tiers,
    }
