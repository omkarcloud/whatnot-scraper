# 🛍️ Whatnot Scraper

Whatnot Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Whatnot data for free.

## ✨ What Can I Get?

- 🛒 **Search every listing with 21 filters** — price, format, seller rating, country, grade, set & more
- 🏪 **Full seller profiles** — followers, items sold, 4-part rating, shop listings & buyer reviews
- 📺 **Live shows as they happen** — viewers, start time, tags & every item in the show's shop
- 🗂️ **All 30 top-level categories** — subcategories, live viewer counts & show feeds

## 🎥 Example: A Whatnot Listing Search

```json
{
  "query": "charizard",
  "sort": "best_match",
  "count": 24,
  "total_count": 10000,
  "listings": [
    {
      "id": 2363778865,
      "title": "Charizard Metal Celebrations Promo",
      "subtitle": "Near Mint",
      "description": "Charizard Metal Celebrations Promo\nNM",
      "link": "https://www.whatnot.com/listing/TGlzdGluZ05vZGU6MjM2Mzc3ODg2NQ==",
      "status": "active",
      "buying_format": "buy_it_now",
      "price": 340.0,
      "currency": "USD",
      "quantity": 1,
      "image": "https://images.whatnot.com/eyJidWNrZXQiOiAid2hhdG5vdC1pbWFnZXMi...",
      "is_live": false,
      "livestream": {
        "id": "50ac2a1b-8c5b-4d22-9654-7d5db9332ca3",
        "link": "https://www.whatnot.com/live/50ac2a1b-8c5b-4d22-9654-7d5db9332ca3"
      },
      "seller": {
        "id": 49473381,
        "username": "bigmacspokeshack",
        "link": "https://www.whatnot.com/user/bigmacspokeshack",
        "rating": 5.0,
        "review_count": 614,
        "is_live": false
      },
      "created_at": "2026-09-28T23:26:39Z",
      "updated_at": "2026-09-28T23:26:40Z"
    }
  ],
  "next_cursor": "YXJyYXljb25uZWN0aW9uOjIz",
  "has_more": true
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Whatnot Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/whatnot-scraper
cd whatnot-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/search/listings?query=charizard"
```

```json
{
  "query": "charizard",
  "sort": "best_match",
  "count": 24,
  "total_count": 10000,
  "listings": [
    {
      "id": 2363778865,
      "title": "Charizard Metal Celebrations Promo",
      "subtitle": "Near Mint",
      "link": "https://www.whatnot.com/listing/TGlzdGluZ05vZGU6MjM2Mzc3ODg2NQ==",
      "status": "active",
      "buying_format": "buy_it_now",
      "price": 340.0,
      "currency": "USD",
      "quantity": 1,
      "seller": { "id": 49473381, "username": "bigmacspokeshack", "rating": 5.0, "review_count": 614 },
      "created_at": "2026-09-28T23:26:39Z"
    }
  ],
  "next_cursor": "YXJyYXljb25uZWN0aW9uOjIz",
  "has_more": true
}
```

All 24 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

24 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Search Listings | `/search/listings` | Items for sale with price, format, images and seller; 21 filters |
| Listing Details | `/listings/details` | Everything about one listing in a single call |
| Seller Details | `/sellers/details` | Followers, items sold, rating breakdown, shipping speed, upcoming shows |
| Seller Listings | `/sellers/listings` | A seller's whole shop, searchable and filterable |
| Seller Reviews | `/sellers/reviews` | Buyer reviews with stars, text and seller replies |
| Livestream Details | `/livestreams/details` | Status, viewers, start time, categories, tags and host |
| Livestream Listings | `/livestreams/listings` | Every item in a show's shop: buy-it-now, auctions, giveaways |
| Search Livestreams | `/search/livestreams` | Live and scheduled shows by keyword, sortable by viewers |
| Category Livestreams | `/categories/livestreams` | Live and scheduled shows in a category, sortable by viewers |
| Search | `/search` | Categories, live shows, sellers and listings in one call |
| Search Sellers | `/search/sellers` | Sellers by name with followers, sales and rating |
| Search Suggestions | `/search/suggestions` | Autocomplete: queries, categories and sellers live right now |
| Search Categories | `/search/categories` | Categories by keyword with live viewer counts |
| Seller Livestreams | `/sellers/livestreams` | A seller's live and scheduled shows |
| Seller Clips | `/sellers/clips` | Short clips from a seller's shows with video links |
| Seller Rewards | `/sellers/rewards` | A seller's rewards club: tiers, requirements and rewards |
| Similar Listings | `/listings/similar` | Listings Whatnot recommends next to a listing |
| Similar Livestreams | `/livestreams/similar` | Shows Whatnot recommends to a show's viewers |
| Categories | `/categories` | Every top-level category with subcategories and live viewers |
| Category Details | `/categories/details` | One category: live viewers, live shows, parent, subcategories |
| Filters (listing search / livestream search / seller shop / category shows) | `/search/listings/filters`, `/search/livestreams/filters`, `/sellers/listings/filters`, `/categories/livestreams/filters` | Every filter a search offers, with the values available right now |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-whatnot-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-whatnot-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-whatnot-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/search/listings",
    params={"query": "charizard"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Whatnot Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Whatnot%20Scraper%20API.)

[![Ask Us by Email about Whatnot Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Whatnot%20Scraper%20API&body=I%20need%20help%20using%20the%20Whatnot%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/whatnot-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/whatnot-scraper)
