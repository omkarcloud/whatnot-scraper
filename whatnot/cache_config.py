"""Cache TTL per /whatnot/* endpoint (cache.py, keyed on the validated params).

Tiers follow how fast Whatnot moves each surface: a show's viewer count and
its auction bids change every second, a seller profile a few times a day,
the category tree a few times a month.
"""
from datetime import timedelta

# --- live surfaces -----------------------------------------------------------
LIVE_CACHE = timedelta(seconds=30)        # one livestream, similar shows
SHOP_CACHE = timedelta(seconds=20)        # a show's shop: live bids and stock
FEED_CACHE = timedelta(seconds=60)        # shows in a category, livestream search
# --- sellers -----------------------------------------------------------------
SELLER_CACHE = timedelta(minutes=5)       # profile (carries is_live), shows, shop
REVIEWS_CACHE = timedelta(minutes=15)
CLIPS_CACHE = timedelta(minutes=30)
REWARDS_CACHE = timedelta(hours=6)        # a rewards club is fixed for a season
# --- listings ----------------------------------------------------------------
LISTING_CACHE = timedelta(minutes=2)      # price / quantity / bids
SEARCH_CACHE = timedelta(minutes=3)
# --- catalogues --------------------------------------------------------------
SUGGEST_CACHE = timedelta(minutes=10)
FILTERS_CACHE = timedelta(minutes=30)
CATEGORIES_CACHE = timedelta(minutes=10)  # the tree carries live viewer counts
CATEGORY_CACHE = timedelta(minutes=5)
