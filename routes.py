"""The 24 Whatnot endpoints. Every path is served with and without the
`/whatnot` prefix, so code generated against the hosted API on RapidAPI
(paths like /search/listings) runs unchanged against this server.

Params are validated by the marshmallow schemas in whatnot/schemas.py — ONE
param per input: `seller` takes a username or a whatnot.com profile link,
`listing` a listing id or link, `livestream` a livestream id or live link,
`category` a slug, numeric id or category link. Unknown params are a 400."""
import json

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from whatnot import categories, listings, livestreams, schemas, search, sellers


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Pokémon" would arrive as "PokÃ©mon")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def call(label, schema, fn):
    """Validate with the schema, run the scraper, map errors: bad params ->
    400, missing entity -> 404, transport/blocks -> 500."""
    data, error = load_query(schema, query_dict())
    if error:
        return json_response(error, 400)
    try:
        return json_response(fn(**data))
    except ValueError as e:                # bad id / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"whatnot rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"whatnot {label} failed: {e}"}, 500)


def mount(path, schema, fn):
    """Serve a scraper function at /path and /whatnot/path."""
    def handler():
        return call(path.strip("/"), schema, fn)
    handler.__name__ = "whatnot_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/whatnot" + path, method="GET")(handler)


ENDPOINTS = [
    ("/search/listings", schemas.SearchListingsSchema, search.listings),
    ("/listings/details", schemas.ListingSchema, listings.details),
    ("/sellers/details", schemas.SellerSchema, sellers.details),
    ("/sellers/listings", schemas.SellerListingsSchema, sellers.listings),
    ("/sellers/reviews", schemas.SellerPageSchema, sellers.reviews),
    ("/livestreams/details", schemas.LivestreamSchema, livestreams.details),
    ("/livestreams/listings", schemas.LivestreamListingsSchema, livestreams.listings),
    ("/search/livestreams", schemas.SearchLivestreamsSchema, search.livestreams),
    ("/categories/livestreams", schemas.CategoryLivestreamsSchema, categories.livestreams),
    ("/search", schemas.QuerySchema, search.search),
    ("/search/sellers", schemas.SearchSellersSchema, search.sellers),
    ("/search/suggestions", schemas.QuerySchema, search.suggestions),
    ("/search/categories", schemas.QuerySchema, search.categories),
    ("/sellers/livestreams", schemas.SellerPageSchema, sellers.livestreams),
    ("/sellers/clips", schemas.SellerPageSchema, sellers.clips),
    ("/sellers/rewards", schemas.SellerSchema, sellers.rewards),
    ("/listings/similar", schemas.ListingSimilarSchema, listings.similar),
    ("/livestreams/similar", schemas.LivestreamSchema, livestreams.similar),
    ("/categories", schemas.EmptySchema, categories.tree),
    ("/categories/details", schemas.CategorySchema, categories.details),
    ("/search/listings/filters", schemas.QuerySchema, search.listing_filters),
    ("/search/livestreams/filters", schemas.QuerySchema, search.livestream_filters),
    ("/sellers/listings/filters", schemas.SellerFiltersSchema, sellers.listing_filters),
    ("/categories/livestreams/filters", schemas.CategorySchema, categories.livestream_filters),
]

for _path, _schema, _fn in ENDPOINTS:
    mount(_path, _schema, _fn)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, _, _ in ENDPOINTS]})
