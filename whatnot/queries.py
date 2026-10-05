"""Raw GraphQL documents for www.whatnot.com/services/graphql/.

Introspection is disabled upstream. These documents were rebuilt
(2026-10-05) from the compiled query ASTs in the web app's JS bundles
(Search, GetUser, GetSellerReviews, ProfileShop, GetUserLiveStreams,
GetLiveClipsOfUser, LiveShopFeed, LiveStreamExplore, GetFeed,
LivestreamTagDirectDescendants, SearchAutocomplete, QueryBreak,
GetLoyaltyProgramForSeller) plus field probing, then trimmed: every
viewer-relative field (isFollowing, userBookmark, isBlockedByMe,
isMyListing, canBeMessagedByMe, isUserOnWatchlist ...) is left out because
an anonymous session always gets the same constant for it.

A "Cannot query field" answer means Whatnot renamed something here; the
transport reports it as an upstream error naming the field.
"""

# ---- fragments -------------------------------------------------------------------------

MONEY = """
fragment Money on Money { amount currency }
"""

USER_REF = """
fragment UserRef on PublicUserNode {
  id username isLive isVerifiedSeller
  sellerRating { overall numReviews }
  profileImage { url }
  premierShopStatus { isPremierShop }
  sellerBadges { label asset }
}
"""

USER_TILE = """
fragment UserTile on PublicUserNode {
  id username displayName isLive isVerifiedSeller canGoLive followerCount followingCount soldCount
  sellerRating { overall numReviews }
  profileImage { url }
  storeImage { url }
  premierShopStatus { isPremierShop }
  sellerBadges { label asset }
}
"""

TIMED_EVENT = """
fragment TimedEvent on FlashSaleListingEvent {
  id type isAvailableForFullPrice endsAtMs
  originalPrice { ...Money }
  discountPrice { ...Money }
}
"""

BREAK = """
fragment BreakRef on Break {
  id title format status soldSpotCount totalBreakSpots filledBreakSpots spotType defaultTransactionType
}
"""

LISTING_TILE = """
fragment ListingTile on ListingNode {
  id title subtitle description
  publicStatus transactionType quantity
  price { ...Money }
  compareAtPrice { ...Money }
  currentBid { ...Money }
  currentBidCount
  isLive livestreamStartTime activeLivestreamId
  pendingPayment shippingDetails listingLabels: labels totalBookmarks createdAt updatedAtMs
  images { id url label }
  user { ...UserRef }
  product { id priceRange { min { ...Money } max { ...Money } } }
  break { ...BreakRef }
  variants { id title quantity }
  activeTimedListingEvent { ...TimedEvent }
  upcomingTimedListingEvent { ...TimedEvent }
  salesChannels { id channelId meta { id type } }
}
"""

LIVESTREAM_TILE = """
fragment LivestreamTile on LiveStream {
  id title status startTime endTime activeViewers totalWatchlistUsers
  isHiddenBySeller explicitContent livestreamLabels: labels streamService
  trailerUrl trailerThumbnailUrl
  shippingSourceCountryCode isFreeShippingEnabled
  buyerPaysMaxAmountForShipping { ...Money }
  thumbnail { url(width: 828, height: 1280, format: WEBP, fit: COVER) }
  livestreamCategories { id name label deeplink }
  categoryNodes { id type label }
  tags { id name label }
  sellerLanguage { languageCode displayName }
  user { ...UserRef }
}
"""

TAG_TILE = """
fragment TagTile on LivestreamTagNode {
  id name label description tagType viewerCount livestreamCount deeplink
  image { url(width: 632, format: WEBP, fit: COVER) }
  parent { id name label }
}
"""

CATEGORY_TILE = """
fragment CategoryTile on CategoryNode {
  id type label deeplink
  image { url(width: 632, format: WEBP, fit: COVER) }
}
"""

FILTER_OPTIONS = """
fragment FilterOptions on FilterAndSortOptions {
  filters {
    field displayField displayStyle selectionType
    options {
      maxAllowedMultiselect
      allowedValues { displayValue displaySublabelValue value section numResults directDescendantValues }
      allowedRange { minimum maximum }
    }
  }
  sorts { displayField field direction }
  defaultSort { displayField field direction }
}
"""

# Everything a feed row can be: search, category feeds, the browse feed and
# the "explore" rail of a show all return the same union of tiles.
_TILES = (MONEY + USER_REF + USER_TILE + TIMED_EVENT + BREAK + LISTING_TILE + LIVESTREAM_TILE
          + TAG_TILE + CATEGORY_TILE)

FEED_OBJECTS = """
fragment FeedObjects on Feed {
  id title
  objects(first: $first, after: $after) {
    totalCount
    pageInfo { endCursor hasNextPage }
    edges {
      node {
        __typename
        ... on Section {
          id title subtitle sectionType
          feed { id searchParams { vertical } tag { id name } }
          contents {
            totalCount
            edges {
              node {
                __typename
                ... on ListingNode { ...ListingTile }
                ... on LiveStream { ...LivestreamTile }
                ... on PublicUserNode { ...UserTile }
                ... on LivestreamTagNode { ...TagTile }
                ... on CategoryNode { ...CategoryTile }
                ... on HighConfidenceUserNode { user { ...UserTile } livestream { ...LivestreamTile } }
              }
            }
          }
        }
        ... on FeedEntity {
          object {
            __typename
            ... on ListingNode { ...ListingTile }
            ... on LiveStream { ...LivestreamTile }
            ... on PublicUserNode { ...UserTile }
            ... on LivestreamTagNode { ...TagTile }
            ... on CategoryNode { ...CategoryTile }
          }
        }
      }
    }
  }
}
"""

# ---- search ----------------------------------------------------------------------------

SEARCH = """
query Search($query: String!, $vertical: SearchVertical, $first: Int, $after: String, $sort: SortInput,
             $filters: [FilterInput!], $withOptions: Boolean! = false) {
  search(query: $query, vertical: $vertical, sort: $sort, filters: $filters) {
    searchParams { vertical spellingCorrection { correctionType correctedQuery } }
    ...FeedObjects
    filterAndSortOptions @include(if: $withOptions) { ...FilterOptions }
  }
}
""" + FEED_OBJECTS + FILTER_OPTIONS + _TILES

SEARCH_OPTIONS = """
query SearchOptions($query: String!, $vertical: SearchVertical, $filters: [FilterInput!]) {
  search(query: $query, vertical: $vertical, filters: $filters) {
    id
    searchParams { vertical spellingCorrection { correctionType correctedQuery } }
    filterAndSortOptions { ...FilterOptions }
  }
}
""" + FILTER_OPTIONS

SEARCH_AUTOCOMPLETE = """
query SearchAutocomplete($prefix: String!) {
  searchAutocomplete(prefix: $prefix) {
    query subtitle resultType searchVertical isLive
    result {
      __typename
      ... on LiveStream { id title activeViewers user { ...UserRef } }
      ... on PublicUserNode { ...UserRef followerCount }
      ... on CategoryNode { id type label image { url } }
      ... on LivestreamTagNode { id name label image { url } }
    }
  }
}
""" + USER_REF

SEARCH_TAXONOMY = """
query SearchLivestreamTaxonomy($query: String!) {
  searchLivestreamTaxonomy(use_case: BROWSE, query: $query) { ...TagTile }
}
""" + TAG_TILE

# ---- sellers ---------------------------------------------------------------------------

USER_ID = """
query UserId($username: String) {
  getUser(username: $username, excludeBanned: false) { id username }
}
"""

USER_DETAILS = """
query GetUser($username: String) {
  getUser(username: $username, excludeBanned: false) {
    id username displayName bio createdAt
    isSeller isVerifiedSeller canGoLive isLive vacationMode
    followerCount followingCount soldCount averageShipDays shippingSourceCountryCode
    sellerRating { overall numReviews shipping packaging accuracy }
    profileImage { url }
    storeImage { url }
    premierShopStatus { isPremierShop }
    sellerBadges { label asset }
    profilePreferences { defaultTab }
    tsStanding
    livestreams(first: 5) { totalCount edges { node { ...LivestreamTile } } }
    sellerReviews(first: 1) { totalCount }
    sellerLiveClips(first: 1) { totalCount }
  }
}
""" + MONEY + USER_REF + LIVESTREAM_TILE

USER_REVIEWS = """
query GetSellerReviews($username: String, $first: Int, $after: String) {
  getUser(username: $username, excludeBanned: false) {
    id username
    sellerRating { overall numReviews shipping packaging accuracy }
    sellerReviews(first: $first, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id averageRating overallReview sellerResponse reviewedOn
          reviewedBy { id username profileImage { url } }
          ratingOverall { value explanation }
          ratingShipping { value explanation }
          ratingPackaging { value explanation }
          ratingAccuracy { value explanation }
        }
      }
    }
  }
}
"""

USER_CLIPS = """
query GetLiveClipsOfUser($username: String, $first: Int, $after: String) {
  getUser(username: $username, excludeBanned: false) {
    id username
    sellerLiveClips(first: $first, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id uuid name livestreamId url urlForDisplay thumbnailUrl totalViews isPublished
          clipper { id username }
        }
      }
    }
  }
}
"""

USER_LIVESTREAMS = """
query GetUserLiveStreams($username: String, $first: Int, $after: String) {
  getUser(username: $username, excludeBanned: false) {
    id username
    livestreams(first: $first, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges { node { ...LivestreamTile } }
    }
  }
}
""" + MONEY + USER_REF + LIVESTREAM_TILE

USER_SHOP = """
query ProfileShop($username: String, $query: String, $first: Int, $after: String, $filters: [FilterInput],
                  $sort: SortInput, $withOptions: Boolean! = false) {
  getUser(username: $username, excludeBanned: false) {
    id username
    searchShop(query: $query, filters: $filters, sort: $sort, useBuyerView: true) {
      id
      objects(first: $first, after: $after) {
        totalCount
        pageInfo { endCursor hasNextPage }
        edges { node { ... on FeedEntity { object { __typename ... on ListingNode { ...ListingTile category { id type label } } } } } }
      }
      filterAndSortOptions @include(if: $withOptions) { ...FilterOptions }
    }
  }
}
""" + MONEY + USER_REF + TIMED_EVENT + BREAK + LISTING_TILE + FILTER_OPTIONS

_TIER_BRAND = "{ level displayName bannerImage { url } largeBadgeImage { url(format: PNG) } }"

USER_REWARDS = """
query GetLoyaltyProgramForSeller($username: String) {
  getUser(username: $username, excludeBanned: false) {
    id username
    loyaltyProgram(relativeSeason: CURRENT) {
      id status
      seasonInfo { seasonName seasonNumber seasonStartMs seasonEndMs seasonEndDescription }
      brand {
        status
        tierBrands { bronze %(tb)s silver %(tb)s gold %(tb)s platinum %(tb)s diamond %(tb)s }
      }
      tiers {
        level
        achievementGroups {
          achievements {
            __typename
            ... on MoneyLoyaltyAchievement { achievementType moneyRequirement { ...Money } }
            ... on NumberLoyaltyAchievement { achievementType requirement }
          }
        }
        rewards {
          __typename id description rewardType
        }
      }
    }
  }
}
""" % {"tb": _TIER_BRAND} + MONEY

# ---- listings --------------------------------------------------------------------------

LISTING_DETAILS = """
query GetListing($id: ID!, $similar: Int!) {
  getListing(id: $id) {
    ...ListingTile
    uuid sku status structure allowsRightOfWithdrawal viewOnly updatedAt
    discountedPrice { ...Money }
    category { id type label deeplink }
    listingAttributeValues { value attribute { id key label } }
    videos { id url thumbnailUrl duration hasAudioTrack }
    transactionProps {
      isOfferable
      offers { maxDiscount }
      auction { durationSeconds isSuddenDeath endTime }
    }
    product {
      id key name subtitle description numVariants
      category { id type label }
      attributeValues { value attribute { id key label } }
      variantOptions { productAttribute { key label } values { value } }
      priceRange { min { ...Money } max { ...Money } }
    }
    livestreams { ...LivestreamTile }
    user {
      ...UserRef
      displayName bio followerCount followingCount soldCount averageShipDays
      shippingSourceCountryCode vacationMode
      storeImage { url }
    }
    recommendedListings(first: $similar) { edges { node { ...ListingTile } } }
  }
}
""" + MONEY + USER_REF + TIMED_EVENT + BREAK + LISTING_TILE + LIVESTREAM_TILE

LISTING_SIMILAR = """
query ListingSimilar($id: ID!, $first: Int!) {
  getListing(id: $id) {
    id title
    recommendedListings(first: $first) { edges { node { ...ListingTile } } }
  }
}
""" + MONEY + USER_REF + TIMED_EVENT + BREAK + LISTING_TILE

BREAK_DETAILS = """
query QueryBreak($id: ID!) {
  getBreak(breakId: $id) {
    ...BreakRef
    description
    spots { id title buyer { id username } listing { id status transactionType price { ...Money } } }
    spotOptions { id title available description assignedBreakSpot { id title buyer { id username } } }
  }
}
""" + MONEY + BREAK

# ---- livestreams -----------------------------------------------------------------------

LIVESTREAM_DETAILS = """
query Livestream($id: ID!) {
  liveStream(id: $id) {
    ...LivestreamTile
    description pinnedProductId buyerShopEnabled prebidsDisabled captionsEnabled isAutoplayEnabled
    categories
    showNotes { id content { text } updatedAt }
    nominatedModerators { id username }
    localPickupSettings { enabled }
    user {
      ...UserRef
      displayName bio followerCount followingCount soldCount averageShipDays
      storeImage { url }
    }
  }
}
""" + MONEY + USER_REF + LIVESTREAM_TILE

LIVESTREAM_TITLE = """
query LivestreamTitle($id: ID!) {
  liveStream(id: $id) { id title status }
}
"""

LIVESTREAM_SHOP = """
query LiveShopFeed($liveId: ID!, $first: Int, $after: String) {
  liveShop(liveId: $liveId) {
    feed {
      id
      objects(first: $first, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            __typename
            ... on Section {
              id title sectionType
              contents { totalCount edges { node { __typename ... on ListingNode { ...ShopListing } ... on GiveawayNode { ...Giveaway } } } }
            }
            ... on FeedEntity {
              object { __typename ... on ListingNode { ...ShopListing } ... on GiveawayNode { ...Giveaway } }
            }
          }
        }
      }
    }
  }
}
fragment Giveaway on GiveawayNode { id eligibilityType credit { id amount { amount currency } } }
fragment ShopListing on ListingNode {
  ...ListingTile
  productId: productIdV2
  structure
  videos { id url thumbnailUrl duration hasAudioTrack }
  transactionProps {
    isOfferable
    offers { maxDiscount }
    auction { durationSeconds isSuddenDeath endTime }
    giveaway { onlyFollowers onlyDomestic buyerAppreciation }
  }
  liveAuction: auctionState(channelType: LIVE, channelId: $liveId) {
    bidCount endTime
    currentPrice { ...Money }
    currentBidUser { id username }
  }
  breakSpot { id title }
  sellingMechanic { __typename sellingMechanicType }
}
""" + MONEY + USER_REF + TIMED_EVENT + BREAK + LISTING_TILE

LIVESTREAM_SIMILAR = """
query LiveStreamExplore($id: ID!) {
  liveStream(id: $id) {
    id title
    explore {
      id
      objects {
        totalCount
        pageInfo { endCursor hasNextPage }
        edges { node { ... on FeedEntity { object { __typename ... on LiveStream { ...LivestreamTile } } } } }
      }
    }
  }
}
""" + MONEY + USER_REF + LIVESTREAM_TILE

# ---- categories / feeds ----------------------------------------------------------------

TAXONOMY = """
query LivestreamTagDirectDescendants($parent: ID) {
  livestreamTaxonomyDirectDescendants(starting_entity_id: $parent, use_case: BROWSE) {
    ...TagTile
    refinements(use_case: BROWSE) { ...TagTile }
  }
}
""" + TAG_TILE

TAG_BY_NAME = """
query GetLivestreamTagByName($name: String!) {
  getLivestreamTagByName(name: $name) {
    ...TagTile
    isFollowable canScheduleLive
    feed { id }
    refinements(use_case: BROWSE) { ...TagTile }
  }
}
""" + TAG_TILE

TAG_BY_ID = """
query GetLivestreamTag($id: ID!) {
  getLivestreamTag(livestreamTagId: $id) {
    ...TagTile
    isFollowable canScheduleLive
    feed { id }
    refinements(use_case: BROWSE) { ...TagTile }
  }
}
""" + TAG_TILE

FEED = """
query GetFeed($feedId: ID!, $first: Int, $after: String, $filters: [FilterInput], $sort: SortInput,
              $withOptions: Boolean! = false) {
  feed: getFeedFromOnboardingOption(id: $feedId, filters: $filters, sort: $sort) {
    ...FeedObjects
    suggestedTags { id name label }
    filterAndSortOptions @include(if: $withOptions) { ...FilterOptions }
  }
}
""" + FEED_OBJECTS + FILTER_OPTIONS + _TILES

FEED_OPTIONS = """
query HomeFeedFilterAndSortOptions($feedId: ID!, $filters: [FilterInput]) {
  homeFeedFilterAndSortOptions: getFeedFromOnboardingOption(id: $feedId, filters: $filters) {
    id title
    filterAndSortOptions { ...FilterOptions }
  }
}
""" + FILTER_OPTIONS
