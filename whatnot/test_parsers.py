"""Offline tests: ref parsing, request schemas and the normalizers against
raw www.whatnot.com/services/graphql/ responses captured 2026-10-05
(whatnot/fixtures/*.json).

    python -m pytest whatnot/test_parsers.py -q
"""
import json
import os
import re

import pytest

from schema_fields import load_query
from whatnot import livestreams
from whatnot import parsers as P
from whatnot import refs
from whatnot import schemas
from whatnot import shared

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def fx(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _clean(obj, path="$"):
    """Every emitted key is snake_case, no key is named *url*, no
    __typename survives and no value is an empty string."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key == key.lower() and " " not in key, f"{path}.{key} not snake_case"
            assert "url" not in key, f"{path}.{key} should be a *link"
            assert key != "__typename"
            _clean(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _clean(value, f"{path}[{i}]")
    else:
        assert obj != "", f"{path} is an empty string (should be null)"


# ---- refs --------------------------------------------------------------------------

def test_global_ids():
    assert refs.global_id("ListingNode", 2373630372) == "TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg=="
    assert refs.decode_global_id("TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg==") == ("ListingNode", "2373630372")
    assert refs.decode_global_id("pokemon_cards") == (None, None)
    assert refs.numeric_id("UHVibGljVXNlck5vZGU6MTE4NDg0OTU=") == 11848495
    assert refs.numeric_id("11848495") == 11848495 and refs.numeric_id(7) == 7
    # composite review id: SellerReviewNode:<review>:<seller>:<buyer>
    assert refs.numeric_id("U2VsbGVyUmV2aWV3Tm9kZTo0Nzg1NzM1NTM6MTE4NDg0OTU6NTU2Mjg4NA==") == 478573553
    assert refs.numeric_id(None) is None and refs.numeric_id("abc") is None and refs.numeric_id(True) is None


@pytest.mark.parametrize("value", [
    "pokemonsuperstore", "@PokemonSuperStore", "https://www.whatnot.com/user/pokemonsuperstore",
    "https://www.whatnot.com/user/pokemonsuperstore/shop", "whatnot.com/user/pokemonsuperstore/reviews?x=1",
    "https://www.whatnot.com/en-GB/user/pokemonsuperstore",
])
def test_resolve_seller(value):
    assert refs.resolve_seller(value) == "pokemonsuperstore"


@pytest.mark.parametrize("value", ["", "https://example.com/user/x", "https://www.whatnot.com/live/abc", "bad name!"])
def test_resolve_seller_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_seller(value)


@pytest.mark.parametrize("value", [
    "2373630372", "TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg==",
    "https://www.whatnot.com/listing/TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg==",
    "https://www.whatnot.com/fr-FR/listing/TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg%3D%3D",
])
def test_resolve_listing(value):
    assert refs.resolve_listing(value) == "TGlzdGluZ05vZGU6MjM3MzYzMDM3Mg=="


@pytest.mark.parametrize("value", ["abc!", "UHVibGljVXNlck5vZGU6MTE4NDg0OTU=", "https://www.whatnot.com/user/x"])
def test_resolve_listing_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_listing(value)


def test_resolve_livestream_and_category():
    uuid = "dc46af2c-5e85-496c-9011-82c053949cb0"
    assert refs.resolve_livestream(uuid.upper()) == uuid
    assert refs.resolve_livestream(f"https://www.whatnot.com/live/{uuid}?x=1") == uuid
    with pytest.raises(ValueError):
        refs.resolve_livestream("not-a-uuid")
    assert refs.resolve_category("Pokemon_Cards") == {"slug": "pokemon_cards"}
    assert refs.resolve_category("https://www.whatnot.com/tag/pokemon_cards") == {"slug": "pokemon_cards"}
    assert refs.resolve_category("https://www.whatnot.com/category/other_funko") == {"slug": "other_funko"}
    assert refs.resolve_category("907") == {"id": "TGl2ZXN0cmVhbVRhZ05vZGU6OTA3"}
    assert refs.resolve_category("weiß_schwarz") == {"slug": "weiß_schwarz"}
    with pytest.raises(ValueError):
        refs.resolve_category("https://www.whatnot.com/user/x")


# ---- schemas -----------------------------------------------------------------------

def test_listing_search_schema():
    data, error = load_query(schemas.SearchListingsSchema, {
        "query": " charizard ", "sort": "PRICE_LOW_TO_HIGH", "buying_format": "auction", "min_price": "5",
        "seller_country": "us, gb", "min_seller_rating": "4.5", "is_graded": "true", "grading_service": "PSA, CGC",
        "attributes": "Size=L;Brand=Nike|Brand=Jordan", "category": "https://www.whatnot.com/tag/pokemon_cards",
        "limit": "50",
    })
    assert error is None
    assert data["query"] == "charizard" and data["sort"] == "price_low_to_high"
    assert data["buying_format"] == "LIVESTREAM_AUCTION" and data["min_price"] == 5.0
    assert data["seller_country"] == ["US", "GB"] and data["min_seller_rating"] == "4.5"
    assert data["grading_service"] == ["PSA", "CGC"] and data["category"] == {"slug": "pokemon_cards"}
    assert data["attributes"] == [("Size", "L"), ("Brand", "Nike"), ("Brand", "Jordan")]
    assert data["limit"] == 50 and data["cursor"] is None and data["is_premier_shop"] is None


@pytest.mark.parametrize("schema,params,field", [
    (schemas.SearchListingsSchema, {}, "query"),
    (schemas.SearchListingsSchema, {"query": "x", "url": "y"}, "url"),
    (schemas.SearchListingsSchema, {"query": "x", "limit": "500"}, "limit"),
    (schemas.SearchListingsSchema, {"query": "x", "seller_country": "zz"}, "seller_country"),
    (schemas.SearchListingsSchema, {"query": "x", "attributes": "Size"}, "attributes"),
    (schemas.SearchListingsSchema, {"query": "x", "min_price": "-1"}, "min_price"),
    (schemas.SearchLivestreamsSchema, {"query": "x", "status": "ended"}, "status"),
    (schemas.SearchLivestreamsSchema, {"query": "x", "show_format": "karaoke"}, "show_format"),
    (schemas.SearchLivestreamsSchema, {"query": "x", "tag": "vintage"}, "tag"),
    (schemas.SellerSchema, {"seller": "https://example.com/x"}, "seller"),
    (schemas.ListingSchema, {"listing": "abc!"}, "listing"),
    (schemas.LivestreamSchema, {"livestream": "123"}, "livestream"),
    (schemas.CategorySchema, {}, "category"),
])
def test_schema_rejects(schema, params, field):
    data, error = load_query(schema, params)
    assert data is None and field in error["errors"]


def test_filter_builders():
    filters = shared.listing_filters(buying_format="BUY_IT_NOW", category="pokemon_cards", min_price=20, max_price=49.99,
                                     min_seller_rating="4.5", is_premier_shop=True, seller_country=["US"],
                                     is_graded=True, grading_service=["PSA"], condition=None)
    assert {"field": "priceCents", "rangeValueMin": 2000, "rangeValueMax": 4999} in filters
    assert {"field": "stringAttributes.Grading Service", "values": ["PSA"]} in filters
    assert {"field": "booleanAttributes.Graded", "values": ["True"]} in filters
    assert shared.listing_filters() is None
    shows = shared.livestream_filters(status="live", category_id=907, show_format=["breaks"], tag=["97"])
    assert {"field": "status", "values": ["PLAYING"]} in shows
    assert {"field": "categories.keyword", "values": ["t__907"]} in shows
    assert {"field": "showFormats.keyword", "values": ["primary_show_format_breaks"]} in shows
    assert shared.livestream_filters(status="all") is None
    with pytest.raises(ValueError):
        shared.check_price_range(50, 5)


def test_attribute_filters():
    offered = fx("search_listing_filters")["search"]["filterAndSortOptions"]
    built = shared.attribute_filters([("size", "10"), ("Brand", "Nike"), ("brand", "Jordan")], offered)
    assert {"field": "stringAttributes.Size", "values": ["10"]} in built
    assert {"field": "stringAttributes.Brand", "values": ["Nike", "Jordan"]} in built
    with pytest.raises(ValueError, match="available: .*Size"):
        shared.attribute_filters([("Nope", "1")], offered)


# ---- value helpers -----------------------------------------------------------------

def test_values():
    assert P.amount({"amount": 1000, "currency": "GBP"}) == 10.0
    assert P.amount({"amount": 51000, "currency": "JPY"}) == 51000.0     # yen has no minor unit
    assert P.amount(None) is None and P.amount({"amount": None}) is None
    assert P.money({"amount": 5000, "currency": "USD"}) == {"amount": 50.0, "currency": "USD"}
    assert P.iso_from_ms(1791185256944.0) == "2026-10-05T07:27:36Z"
    assert P.iso_from_ms(None) is None and P.iso_from_ms("x") is None
    assert P.iso_from_http_date("Sun, 04 Oct 2026 21:13:31 GMT") == "2026-10-04T21:13:31Z"
    assert P.iso_from_http_date("garbage") is None
    assert P.clean_estimate("20% off next $10 (est. ₹963.26)+ purchase, up to $50 (est. ₹4,816.28) off") \
        == "20% off next $10+ purchase, up to $50 off"
    assert P.text("  ") is None and P.to_int("12") == 12 and P.to_int(True) is None


def test_never_crashes_on_junk():
    for junk in (None, {}, [], "x", 5, {"id": None}, {"__typename": "ListingNode"}):
        for fn in (P.listing, P.shop_listing, P.listing_details, P.livestream, P.livestream_details,
                   P.user_ref, P.user_tile, P.user_min, P.category, P.category_ref, P.product_category,
                   P.suggestion, P.rewards, P.giveaway, P.break_ref):
            assert fn(junk) is None
        assert P.entity(junk) == (None, None) or junk == {"__typename": "ListingNode"}
        assert P.feed_rows(junk, "listing") == []
        assert P.filter_options(junk) == {"filters": [], "sorts": []}
        assert P.page(junk, [], "rows")["next_cursor"] is None
    # partial objects keep their shape with nulls
    row = P.listing({"id": "TGlzdGluZ05vZGU6MQ==", "__typename": "ListingNode"})
    assert row["id"] == 1 and row["price"] is None and row["images"] == [] and row["seller"] is None
    assert P.review({})["rating"] is None and P.clip({})["id"] is None
    assert P.seller_details({})["username"] is None


# ---- search ------------------------------------------------------------------------

def test_search_universal():
    feed = fx("search_universal")["search"]
    rows, totals = P.feed_sections(feed)
    _clean(rows)
    assert rows["categories"] and rows["livestreams"] and rows["sellers"] and rows["listings"]
    assert totals["livestreams"] > 100 and totals["sellers"] > 5
    assert rows["categories"][0]["slug"] == "pokemon_cards" and rows["categories"][0]["viewer_count"] > 0
    assert rows["sellers"][0]["link"].startswith("https://www.whatnot.com/user/")


def test_search_listings():
    feed = fx("search_listings")["search"]
    out = shared.feed_page(feed, "listing", "listings")
    _clean(out)
    assert out["count"] == 8 and out["total_count"] >= 1000 and out["has_more"] and out["next_cursor"]
    for row in out["listings"]:
        assert isinstance(row["id"], int) and row["title"] and row["currency"]
        assert isinstance(row["price"], float) and row["buying_format"] in ("buy_it_now", "auction", "giveaway")
        assert row["link"] == refs.listing_link(row["id"]) and row["status"] == "active"
        assert row["seller"]["username"] and isinstance(row["seller"]["id"], int)
        assert ISO.match(row["created_at"]) and (row["image"] is None or row["image"] == row["images"][0])
    auctions = shared.feed_page(fx("search_listings_auction")["search"], "listing", "listings")["listings"]
    assert auctions and all(r["buying_format"] == "auction" for r in auctions)
    assert all(r["livestream"]["id"] and ISO.match(r["livestream"]["starts_at"]) for r in auctions if r["livestream"])


def test_search_livestreams_sellers_categories():
    shows = shared.feed_page(fx("search_livestreams")["search"], "livestream", "livestreams")
    _clean(shows)
    assert shows["count"] == 8
    viewers = [s["viewer_count"] for s in shows["livestreams"]]
    assert viewers == sorted(viewers, reverse=True)
    first = shows["livestreams"][0]
    assert first["status"] == "live" and first["is_live"] is True and ISO.match(first["starts_at"])
    assert first["seller"]["username"] and first["categories"][0]["slug"] and first["link"].endswith(first["id"])
    assert first["language"]["code"]

    sellers = shared.feed_page(fx("search_sellers")["search"], "seller", "sellers")
    _clean(sellers)
    assert sellers["count"] == 8 and sellers["total_count"] > 1000
    assert all("follower_count" in s and s["username"] for s in sellers["sellers"])

    categories = P.feed_rows(fx("search_categories")["search"], "category")
    assert [c["slug"] for c in categories][0] == "pokemon_cards"
    extra = [P.category(n, with_children=False) for n in fx("search_taxonomy")["searchLivestreamTaxonomy"]]
    assert extra[0]["parent"]["slug"] == "trading_card_games"


def test_filter_options():
    listing = P.filter_options(fx("search_listing_filters")["search"]["filterAndSortOptions"])
    _clean(listing)
    by_param = {}
    for f in listing["filters"]:
        by_param.setdefault(f["param"], []).append(f)
    assert {"category", "buying_format", "min_seller_rating", "is_premier_shop", "seller_country",
            "min_price,max_price", "condition", "attributes"} <= set(by_param)
    assert {o["value"] for o in by_param["buying_format"][0]["options"]} == {"buy_it_now", "auction"}
    price = by_param["min_price,max_price"][0]
    assert price["type"] == "price_range" and price["range"]["min"] < price["range"]["max"]
    assert {f["attribute"] for f in by_param["attributes"]} >= {"Size", "Brand"}
    assert all(f["attribute"] is None for f in by_param["category"])
    assert listing["sorts"] == ["Best Match", "Lowest Price", "Highest Price", "Newly Listed"]

    show = P.filter_options(fx("search_livestream_filters")["search"]["filterAndSortOptions"])
    params = {f["param"]: f for f in show["filters"]}
    assert {o["value"] for o in params["status"]["options"]} == {"live", "upcoming"}
    assert all(o["value"].isdigit() for o in params["category"]["options"])       # t__907 -> 907
    assert "breaks" in {o["value"] for o in params["show_format"]["options"]}
    assert all(o["value"].isdigit() for o in params["tag"]["options"])
    feed = P.filter_options(fx("category_livestream_filters")["homeFeedFilterAndSortOptions"]["filterAndSortOptions"])
    assert {"status", "show_format", "tag", "seller_country"} <= {f["param"] for f in feed["filters"]}


def test_suggestions():
    rows = [P.suggestion(n) for n in fx("search_suggestions")["searchAutocomplete"]]
    _clean(rows)
    assert rows[0] == {"text": "poke", "type": "query", "subtitle": None, "is_live": False,
                       "seller": None, "category": None, "livestream": None}
    kinds = {r["type"] for r in rows}
    assert {"query", "category"} <= kinds
    category = next(r for r in rows if r["type"] == "category")
    assert category["category"]["slug"] == "pokemon_cards" and category["category"]["image"]
    for row in rows:
        if row["type"] == "seller":
            assert row["seller"]["username"]
            if row["livestream"]:
                assert row["livestream"]["link"].endswith(row["livestream"]["id"])


# ---- sellers -----------------------------------------------------------------------

def test_seller_details():
    out = P.seller_details(fx("seller_details")["getUser"])
    _clean(out)
    assert out["id"] == 11848495 and out["username"] == "pokemonsuperstore"
    assert out["link"] == "https://www.whatnot.com/user/pokemonsuperstore"
    assert out["display_name"] == "PKMN Super Store"            # trailing space trimmed
    assert out["follower_count"] > 100_000 and out["sold_count"] > 100_000 and out["ships_from_country"] == "US"
    assert out["rating"]["overall"] >= 4.5 and out["rating"]["shipping"] and out["rating"]["review_count"] > 10_000
    assert out["is_premier_shop"] is True and out["is_on_vacation"] is False
    assert out["joined_at"] == "2024-08-26T21:31:27Z" and out["clip_count"] > 10
    assert out["livestreams"] and "seller" not in out["livestreams"][0]
    assert fx("seller_missing")["getUser"] is None


def test_seller_reviews_clips_shows():
    user = fx("seller_reviews")["getUser"]
    connection = user["sellerReviews"]
    rows = [P.review(n) for n in P.nodes(connection)]
    out = P.page(connection, rows, "reviews")
    _clean(out)
    assert out["count"] == 8 and out["total_count"] > 10_000 and out["next_cursor"]
    first = rows[0]
    assert isinstance(first["id"], int) and 1 <= first["rating"] <= 5 and ISO.match(first["reviewed_at"])
    assert set(first["ratings"]) == {"overall", "shipping", "packaging", "accuracy"}
    assert first["reviewer"]["username"] and first["reviewer"]["link"]

    clips = [P.clip(n) for n in P.nodes(fx("seller_clips")["getUser"]["sellerLiveClips"])]
    _clean(clips)
    assert clips[0]["video"].startswith("https://") and clips[0]["thumbnail"] and clips[0]["view_count"] >= 0
    assert clips[0]["livestream"]["link"].endswith(clips[0]["livestream"]["id"])
    assert clips[0]["link"] == refs.clip_link(clips[0]["uuid"])

    shows = [P.livestream(n, with_seller=False) for n in P.nodes(fx("seller_livestreams")["getUser"]["livestreams"])]
    _clean(shows)
    assert shows and all("seller" not in s and s["status"] in ("live", "upcoming") for s in shows)


def test_seller_listings_and_rewards():
    shop = fx("seller_listings")["getUser"]["searchShop"]
    rows = [P.listing(n["object"], with_seller=False) for n in P.nodes(shop["objects"])]
    _clean(rows)
    assert len(rows) == 8 and all("seller" not in r and r["category"]["slug"] for r in rows)
    options = P.filter_options(shop["filterAndSortOptions"])
    assert {"category", "min_price,max_price"} <= {f["param"] for f in options["filters"]}

    out = P.rewards(fx("seller_rewards")["getUser"]["loyaltyProgram"])
    _clean(out)
    assert out["season"]["number"] >= 1 and ISO.match(out["season"]["ends_at"])
    assert [t["level"] for t in out["tiers"]] == ["bronze", "silver", "gold", "platinum", "diamond"]
    bronze = out["tiers"][0]
    assert bronze["requirements"][0][0] == {"type": "money_amount_purchased", "required": 50.0, "currency": "USD"}
    assert all("est." not in (r["description"] or "") for t in out["tiers"] for r in t["rewards"])


# ---- listings ----------------------------------------------------------------------

def test_listing_details():
    out = P.listing_details(fx("listing_details")["getListing"])
    _clean(out)
    assert isinstance(out["id"], int) and out["title"] and out["uuid"] and out["currency"]
    assert out["link"] == refs.listing_link(out["id"])
    assert out["seller"]["username"] and out["seller"]["follower_count"] is not None
    assert out["seller"]["ships_from_country"] and "accepts_offers" in out
    assert isinstance(out["attributes"], list) and isinstance(out["variant_options"], list)
    assert out["category"] is None or out["category"]["slug"]
    assert all("seller" not in s for s in out["livestreams"])
    assert all(s["seller"]["username"] for s in out["similar_listings"])
    assert ISO.match(out["created_at"]) and ISO.match(out["updated_at"])
    assert "livestream" not in out                     # replaced by the full `livestreams` list
    similar = [P.listing(n) for n in P.nodes(fx("listing_similar")["getListing"]["recommendedListings"])]
    _clean(similar)
    assert similar and all(isinstance(r["id"], int) for r in similar)


def test_listing_attributes_and_sale():
    node = {
        "id": refs.global_id("ListingNode", 5), "__typename": "ListingNode", "title": "Card",
        "price": {"amount": 1000, "currency": "GBP"},
        "listingAttributeValues": [{"value": "PSA", "attribute": {"id": "x", "key": "grading_service", "label": "Grading Service"}},
                                   {"value": None, "attribute": {"label": "Grade"}}],
        "upcomingTimedListingEvent": {"type": "FLASH_SALE", "isAvailableForFullPrice": True, "endsAtMs": None,
                                      "originalPrice": {"amount": 1000, "currency": "GBP"},
                                      "discountPrice": {"amount": 850, "currency": "GBP"}},
        "transactionProps": {"isOfferable": True, "offers": {"maxDiscount": 20},
                             "auction": {"durationSeconds": 30, "isSuddenDeath": True, "endTime": None}},
        "product": {"id": refs.global_id("ProductNode", 9), "numVariants": 2,
                    "variantOptions": [{"productAttribute": {"key": "size", "label": "Size"},
                                        "values": [{"value": "S"}, {"value": "M"}]}]},
        "variants": [{"id": "a", "title": "S", "quantity": 1}, {"id": "b", "title": "M", "quantity": 0}],
    }
    out = P.listing_details(node)
    assert out["attributes"] == [{"key": "grading_service", "name": "Grading Service", "value": "PSA"}]
    assert out["upcoming_sale"] == {"type": "flash_sale", "price": 8.5, "original_price": 10.0, "currency": "GBP",
                                    "is_available_at_full_price": True, "ends_at": None}
    assert out["accepts_offers"] is True and out["max_offer_discount_percent"] == 20.0
    assert out["auction"]["duration_seconds"] == 30 and out["auction"]["is_sudden_death"] is True
    assert out["variant_options"] == [{"name": "Size", "values": ["S", "M"]}]
    assert [v["title"] for v in out["variants"]] == ["S", "M"] and out["product"] == {
        "id": 9, "name": None, "subtitle": None, "description": None, "variant_count": 2}


# ---- livestreams -------------------------------------------------------------------

def test_livestream_details():
    out = P.livestream_details(fx("livestream_details")["liveStream"])
    _clean(out)
    assert out["id"] and out["link"] == refs.livestream_link(out["id"]) and out["status"] == "live"
    assert out["seller"]["username"] and out["seller"]["follower_count"] is not None
    assert out["categories"] and ISO.match(out["starts_at"]) and out["ended_at"] is None
    assert isinstance(out["moderators"], list) and isinstance(out["notes"], list)
    assert out["accepts_prebids"] in (True, False)
    similar = [P.livestream(n.get("object")) for n in P.nodes(fx("livestream_similar")["liveStream"]["explore"]["objects"])]
    assert similar and all(s["seller"]["username"] for s in similar)


def test_livestream_shop():
    feed = fx("livestream_listings")["liveShop"]["feed"]
    rows, credit = livestreams._shop_rows(feed)
    _clean(rows)
    assert rows and len({r["id"] for r in rows}) == len(rows) and credit == []
    assert all("seller" not in r and "livestream" not in r for r in rows)
    auction = next(r for r in rows if r["buying_format"] == "auction")
    assert auction["auction"]["duration_seconds"] and auction["price"] is not None
    assert P.page(feed["objects"], rows, "listings")["count"] == len(rows)

    give_rows, _ = livestreams._shop_rows(fx("livestream_listings_giveaway")["liveShop"]["feed"])
    give = next(r for r in give_rows if r["buying_format"] == "giveaway")
    assert give["price"] == 0.0 and give["giveaway"]["is_followers_only"] in (True, False)
    assert P.giveaway({"id": "R2l2ZWF3YXlOb2RlOjc=", "eligibilityType": "EVERYONE",
                       "credit": {"amount": {"amount": 500, "currency": "USD"}}}) \
        == {"id": 7, "eligibility": "everyone", "credit": {"amount": 5.0, "currency": "USD"}}


# ---- categories --------------------------------------------------------------------

def test_categories():
    rows = [P.category(n) for n in fx("categories")["livestreamTaxonomyDirectDescendants"]]
    _clean(rows)
    assert len(rows) >= 20 and any(r["subcategories"] for r in rows)
    tcg = next(r for r in rows if r["slug"] == "trading_card_games")
    assert tcg["id"] == 899 and tcg["link"] == "https://www.whatnot.com/tag/trading_card_games" and tcg["image"]
    assert "pokemon_cards" in {c["slug"] for c in tcg["subcategories"]}

    for name, key in (("category_details", "getLivestreamTagByName"), ("category_by_id", "getLivestreamTag")):
        one = P.category(fx(name)[key])
        assert one["id"] == 907 and one["slug"] == "pokemon_cards" and one["parent"]["id"] == 899
        assert one["viewer_count"] is not None and one["live_show_count"] is not None

    shows = shared.feed_page(fx("category_livestreams")["feed"], "livestream", "livestreams")
    assert shows["count"] == 8 and shows["total_count"] > 100 and shows["next_cursor"]
