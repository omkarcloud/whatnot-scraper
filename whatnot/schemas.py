"""Marshmallow request schemas for every /whatnot/* route. Generic fields
come from the shared schema_fields.py; this module adds the Whatnot
resolvers. Every schema's load() output is the kwargs dict its endpoint
function takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    seller       a username (pokemonsuperstore, @pokemonsuperstore) OR a whatnot.com profile link
    listing      a listing id (numeric, or the id inside a listing link) OR a whatnot.com listing link
    livestream   a livestream id (uuid) OR a whatnot.com live link
    category     a category slug (pokemon_cards), a numeric id OR a whatnot.com category link
"""
from marshmallow import ValidationError, fields

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, LimitField, Price, QueryField,
                           RefField, StrippedString, COUNTRY_CODES)
from whatnot import refs
from whatnot.shared import LISTING_SORTS, LIVESTREAM_SORTS

BUYING_FORMATS = {"buy_it_now": "BUY_IT_NOW", "auction": "LIVESTREAM_AUCTION"}
SELLER_RATINGS = {"4": "4.0", "4.0": "4.0", "4.5": "4.5", "5": "5.0", "5.0": "5.0"}
SHOW_FORMATS = ["auction", "breaks", "buy_it_now", "graded", "singles", "mystery_bags"]


# ---- id-or-link fields -------------------------------------------------------------

class SellerField(RefField):
    resolver = staticmethod(refs.resolve_seller)


class ListingField(RefField):
    resolver = staticmethod(refs.resolve_listing)


class LivestreamField(RefField):
    resolver = staticmethod(refs.resolve_livestream)


class CategoryField(RefField):
    resolver = staticmethod(refs.resolve_category)


class CursorField(StrippedString):
    """Opaque next_cursor from the previous page (absent = first page)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class ValuesField(fields.Field):
    """'Near Mint, Mint' -> ['Near Mint', 'Mint'] — comma-separated filter
    values passed to Whatnot as typed (they are matched exactly; the
    */filters endpoints list the values a query offers)."""

    def __init__(self, max_items=10, **kwargs):
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        items = []
        for raw in str(value).split(","):
            item = " ".join(raw.split())
            if item and item not in items:
                items.append(item)
        if not items:
            return None
        if len(items) > self.max_items:
            raise ValidationError(f"At most {self.max_items} values.")
        return items


class AttributesField(fields.Field):
    """'Size=L;Brand=Nike;Brand=Jordan' -> [('Size', 'L'), ('Brand', 'Nike'),
    ('Brand', 'Jordan')] — any item attribute a search offers (the
    */filters endpoints list them), `;`-separated name=value pairs."""

    def __init__(self, max_items=10, **kwargs):
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        pairs = []
        for raw in str(value).replace("|", ";").split(";"):
            raw = raw.strip()
            if not raw:
                continue
            name, sep, item = raw.partition("=")
            name, item = " ".join(name.split()), " ".join(item.split())
            if not sep or not name or not item:
                raise ValidationError("Must be name=value pairs separated by ';' (Size=L;Brand=Nike).")
            if (name, item) not in pairs:
                pairs.append((name, item))
        if not pairs:
            return None
        if len(pairs) > self.max_items:
            raise ValidationError(f"At most {self.max_items} attribute values.")
        return pairs


class CountriesField(CommaListField):
    """'us, gb' -> ['US', 'GB'] (ISO 3166-1 alpha-2, max 10)."""

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        for item in items or []:
            if item not in COUNTRY_CODES:
                raise ValidationError(f"'{item}' is not a 2-letter ISO country code (US, GB, FR ...).")
        return items


class TagIdsField(ValuesField):
    """Comma-separated show-tag ids (the `tag` values of a */filters call)."""

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        for item in items or []:
            if not item.isdigit():
                raise ValidationError("Must be numeric tag ids (see the filters endpoint), comma-separated.")
        return items


def _limit():
    return LimitField(default=24, max_size=100)


# ---- schemas ---------------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class QuerySchema(BaseSchema):
    query = QueryField(max_length=200)


class _AttributeFilters(BaseSchema):
    """Item-attribute filters shared by listing search and seller shops."""
    buying_format = ChoiceField(BUYING_FORMATS)
    category = CategoryField(required=False, load_default=None)
    min_price = Price()
    max_price = Price()
    is_graded = Flag()
    is_autographed = Flag()
    condition = ValuesField()
    language = ValuesField()
    product_type = ValuesField()
    set = ValuesField()
    rarity = ValuesField()
    grade = ValuesField()
    grading_service = ValuesField()
    card_number = ValuesField()
    attributes = AttributesField()


class SearchListingsSchema(_AttributeFilters):
    query = QueryField(max_length=200)
    sort = ChoiceField(list(LISTING_SORTS), load_default="best_match")
    min_seller_rating = ChoiceField(SELLER_RATINGS)
    is_premier_shop = Flag()
    seller_country = CountriesField()
    limit = _limit()
    cursor = CursorField()


class _LivestreamFilters(BaseSchema):
    status = ChoiceField(["live", "upcoming", "all"], load_default="all")
    sort = ChoiceField(list(LIVESTREAM_SORTS), load_default="recommended")
    show_format = CommaListField(allowed=SHOW_FORMATS, upper=False, max_items=6)
    tag = TagIdsField()
    min_seller_rating = ChoiceField(SELLER_RATINGS)
    is_premier_shop = Flag()
    seller_country = CountriesField()
    limit = _limit()
    cursor = CursorField()


class SearchLivestreamsSchema(_LivestreamFilters):
    query = QueryField(max_length=200)
    category = CategoryField(required=False, load_default=None)


class SearchSellersSchema(BaseSchema):
    query = QueryField(max_length=200)
    limit = _limit()
    cursor = CursorField()


class SellerSchema(BaseSchema):
    seller = SellerField()


class SellerPageSchema(SellerSchema):
    limit = _limit()
    cursor = CursorField()


class SellerListingsSchema(_AttributeFilters):
    seller = SellerField()
    query = StrippedString(required=False, load_default=None)
    sort = ChoiceField(list(LISTING_SORTS), load_default="best_match")
    limit = _limit()
    cursor = CursorField()


class SellerFiltersSchema(SellerSchema):
    query = StrippedString(required=False, load_default=None)


class ListingSchema(BaseSchema):
    listing = ListingField()


class ListingSimilarSchema(ListingSchema):
    limit = _limit()


class LivestreamSchema(BaseSchema):
    livestream = LivestreamField()


class LivestreamListingsSchema(LivestreamSchema):
    limit = _limit()
    cursor = CursorField()


class CategorySchema(BaseSchema):
    category = CategoryField()


class CategoryLivestreamsSchema(_LivestreamFilters):
    category = CategoryField()
