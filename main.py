"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from whatnot import search, sellers
from whatnot.schemas import SearchLivestreamsSchema

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # items for sale, cheapest first (24 per page, cursor paging)
    save("listings_charizard.json", search.listings("charizard", sort="price_low_to_high", limit=24))

    # a username (the name in whatnot.com/user/<username>)
    save("seller_pokemonsuperstore.json", sellers.details("pokemonsuperstore"))

    # shows that are live right now, busiest first — the schema turns the same
    # query params the API takes into the function's arguments
    params = SearchLivestreamsSchema().load({"query": "pokemon", "status": "live", "sort": "viewers_high_to_low"})
    save("livestreams_pokemon.json", search.livestreams(**params))
