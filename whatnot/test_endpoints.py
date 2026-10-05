"""Live endpoint smoke tests: one call per /whatnot/* route against a running
service, with example values proven to return data (2026-10-05). The
listing tooling reads each route's FIRST call from this file's AST as its
working example, so the values stay literals.

Skipped unless WHATNOT_BASE points at a running service:

    ONLY_SCRAPER=whatnot python run.py
    WHATNOT_BASE=http://127.0.0.1:6002 python -m pytest whatnot/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("WHATNOT_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set WHATNOT_BASE to run live endpoint tests")


def call(path, expect=200, **params):
    # `expect`, not `status`: several routes take a `status` query param
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=180)
    assert resp.status_code == expect, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def _live_show():
    """A show that is live right now (the busiest pokemon one)."""
    shows = call("/whatnot/search/livestreams", query="pokemon", status="live",
                 sort="viewers_high_to_low", limit=10)["livestreams"]
    assert shows, "no live pokemon show right now"
    return shows[0]["id"]


def test_search():
    mixed = call("/whatnot/search", query="pokemon")
    assert mixed["categories"] and mixed["livestreams"] and mixed["sellers"] and mixed["listings"]
    assert mixed["livestreams_total_count"] > 100

    listings = call("/whatnot/search/listings", query="charizard", limit=5)
    assert listings["count"] == 5 and listings["next_cursor"] and listings["total_count"] > 1000
    first = listings["listings"][0]
    assert first["id"] and first["price"] is not None and first["currency"] and first["seller"]["username"]
    assert first["link"].startswith("https://www.whatnot.com/listing/")
    page2 = call("/whatnot/search/listings", query="charizard", limit=5, cursor=listings["next_cursor"])
    assert not {r["id"] for r in listings["listings"]} & {r["id"] for r in page2["listings"]}

    cheap = call("/whatnot/search/listings", query="charizard", sort="price_low_to_high", min_price=20,
                 max_price=50, buying_format="buy_it_now", category="pokemon_cards", grading_service="PSA",
                 is_graded="true", min_seller_rating="4.5", seller_country="US", limit=10)["listings"]
    prices = [r["price"] for r in cheap]
    assert prices and prices == sorted(prices) and 20 <= prices[0] and prices[-1] <= 50
    assert all(r["buying_format"] == "buy_it_now" for r in cheap)
    sized = call("/whatnot/search/listings", query="jordan", attributes="Size=10;Brand=Jordan", limit=5)
    assert sized["listings"]
    assert "available:" in call("/whatnot/search/listings", 400, query="jordan", attributes="Nope=1")["error"]
    assert call("/whatnot/search/listings", 400, query="jordan", min_price=50, max_price=5)
    assert call("/whatnot/search/listings", 400, query="jordan", url="x")

    filters = call("/whatnot/search/listings/filters", query="jordan")
    params = {f["param"] for f in filters["filters"]}
    assert {"category", "buying_format", "min_price,max_price", "attributes"} <= params and filters["sorts"]

    shows = call("/whatnot/search/livestreams", query="pokemon", status="live", sort="viewers_high_to_low",
                 category="pokemon_cards", show_format="singles,breaks", seller_country="US", limit=5)
    viewers = [s["viewer_count"] for s in shows["livestreams"]]
    assert viewers and all(s["status"] == "live" for s in shows["livestreams"])
    assert viewers[0] >= viewers[-1]
    show_filters = call("/whatnot/search/livestreams/filters", query="pokemon")
    assert {"category", "status", "show_format", "tag"} <= {f["param"] for f in show_filters["filters"]}

    sellers = call("/whatnot/search/sellers", query="pokemon", limit=5)
    assert sellers["count"] == 5 and sellers["next_cursor"] and sellers["sellers"][0]["username"]
    assert call("/whatnot/search/categories", query="poke")["categories"][0]["slug"] == "pokemon_cards"
    suggestions = call("/whatnot/search/suggestions", query="poke")["suggestions"]
    assert {s["type"] for s in suggestions} >= {"query", "category"}


def test_sellers():
    details = call("/whatnot/sellers/details", seller="pokemonsuperstore")
    assert details["id"] == 11848495 and details["follower_count"] > 100_000 and details["sold_count"] > 100_000
    assert details["rating"]["overall"] and details["rating"]["shipping"] and details["joined_at"].startswith("2024-08-26")
    assert call("/whatnot/sellers/details", seller="https://www.whatnot.com/user/pokemonsuperstore/shop")["username"] == "pokemonsuperstore"
    assert call("/whatnot/sellers/details", seller="@PokemonSuperStore")["id"] == 11848495
    assert call("/whatnot/sellers/details", 404, seller="zzzz_not_a_user_981273")
    assert call("/whatnot/sellers/details", 400, seller="https://example.com/user/x")

    shop = call("/whatnot/sellers/listings", seller="rare_finds", sort="price_high_to_low", min_price=5, limit=5)
    prices = [r["price"] for r in shop["listings"]]
    assert shop["total_count"] > 100 and prices == sorted(prices, reverse=True) and shop["next_cursor"]
    assert call("/whatnot/sellers/listings", seller="rare_finds", limit=5, cursor=shop["next_cursor"])["listings"]
    shop_filters = call("/whatnot/sellers/listings/filters", seller="rare_finds")
    assert shop_filters["listing_count"] > 100 and shop_filters["filters"]

    reviews = call("/whatnot/sellers/reviews", seller="pokemonsuperstore", limit=5)
    assert reviews["count"] == 5 and reviews["total_count"] > 10_000 and reviews["next_cursor"]
    assert reviews["reviews"][0]["rating"] and reviews["reviews"][0]["reviewer"]["username"]
    assert call("/whatnot/sellers/reviews", seller="pokemonsuperstore", limit=5, cursor=reviews["next_cursor"])["reviews"]

    assert call("/whatnot/sellers/livestreams", seller="pokemonsuperstore", limit=5)["livestreams"]
    clips = call("/whatnot/sellers/clips", seller="pokemonsuperstore", limit=5)
    assert clips["clips"][0]["video"] and clips["total_count"] > 10
    rewards = call("/whatnot/sellers/rewards", seller="pokemonsuperstore")["rewards"]
    assert rewards["season"]["number"] and rewards["tiers"][0]["requirements"]


def test_listings():
    found = call("/whatnot/search/listings", query="pokemon", limit=1)["listings"][0]
    details = call("/whatnot/listings/details", listing=found["id"])
    assert details["id"] == found["id"] and details["title"] and details["seller"]["follower_count"] is not None
    assert details["images"] and details["created_at"]
    assert call("/whatnot/listings/details", listing=found["link"])["id"] == found["id"]
    assert call("/whatnot/listings/details", 404, listing="999999999999")
    assert call("/whatnot/listings/details", 400, listing="abc!")
    similar = call("/whatnot/listings/similar", listing=found["id"], limit=5)
    assert similar["listing"]["id"] == found["id"] and "listings" in similar


def test_livestreams():
    show = _live_show()
    details = call("/whatnot/livestreams/details", livestream=show)
    assert details["id"] == show and details["status"] == "live" and details["seller"]["username"]
    assert details["categories"] and details["starts_at"]
    assert call("/whatnot/livestreams/details", livestream=f"https://www.whatnot.com/live/{show}")["id"] == show
    assert call("/whatnot/livestreams/details", 404, livestream="00000000-0000-4000-8000-000000000000")
    shop = call("/whatnot/livestreams/listings", livestream=show, limit=24)
    assert shop["livestream"]["id"] == show and "listings" in shop and "credit_giveaways" in shop
    assert call("/whatnot/livestreams/similar", livestream=show)["livestreams"]


def test_categories():
    tree = call("/whatnot/categories")
    assert tree["count"] >= 20 and any(c["subcategories"] for c in tree["categories"])
    details = call("/whatnot/categories/details", category="trading_card_games")
    assert details["id"] == 899 and details["viewer_count"] and len(details["subcategories"]) > 5
    assert call("/whatnot/categories/details", category="https://www.whatnot.com/tag/pokemon_cards")["parent"]["slug"] == "trading_card_games"
    assert call("/whatnot/categories/details", category="907")["slug"] == "pokemon_cards"
    assert call("/whatnot/categories/details", 404, category="zz_nope_zz")
    shows = call("/whatnot/categories/livestreams", category="sports_cards", status="live",
                 sort="viewers_high_to_low", show_format="breaks", limit=5)
    assert shows["category"]["id"] == 1072 and shows["livestreams"] and shows["next_cursor"]
    assert call("/whatnot/categories/livestreams", category="sports_cards", status="live",
                sort="viewers_high_to_low", show_format="breaks", limit=5, cursor=shows["next_cursor"])["livestreams"]
    filters = call("/whatnot/categories/livestreams/filters", category="sports_cards")
    assert {"status", "show_format", "tag"} <= {f["param"] for f in filters["filters"]}
