# coding: utf-8

# flake8: noqa

"""
Trakt API

At Trakt, we collect lots of interesting information about what tv shows and movies everyone is watching. Part of the fun with such data is making it available for anyone to mash up and use on their own site or app. The Trakt API was made just for this purpose. It is very easy to use, you basically call a URL and get some JSON back.  More complex API calls (such as adding a movie or show to your collection) involve sending us data. These are still easy to use, you simply POST some JSON data to a specific URL.  Make sure to check out the [**Required Headers**](#introduction/required-headers) and [**Authentication**](#reference/authentication-oauth) sections for more info on what needs to be sent with each API call. Also check out the [**Terminology**](#introduction/terminology) section insight into the features Trakt supports.  # Create an App  To use the Trakt API, you'll need to [**create a new API app**](https://trakt.tv/oauth/applications/new).  # Stay Connected  API discussion and bugs should be posted in the [**GitHub Developer Forum**](https://github.com/trakt/api-help/issues) and *watch* the repository if you'd like to get notifications. Make sure to follow our [**API Blog**](https://apiblog.trakt.tv) and [**@traktapi on Twitter**](https://twitter.com/traktapi) too.  # API URL  The API should always be accessed over SSL.  ``` https://api.trakt.tv ```  If you would like to use our sandbox environment to not fill production with test data, use this URL over SSL.  ``` https://api-staging.trakt.tv ```  > ### 🅽🅾🆃🅴 > _Staging is a completely separate environment, so you'll need to [**create a new API app on staging**](https://staging.trakt.tv/oauth/applications/new)._  # Verbs  The API uses restful verbs.  | Verb | Description | |---|---| | `GET` | Select one or more items. Success returns `200` status code. | | `POST` | Create a new item. Success returns `201` status code. | | `PUT` | Update an item. Success returns `200` status code. | | `DELETE` | Delete an item. Success returns `200` or `204` status code. |  # Status Codes  The API will respond with one of the following HTTP status codes.  | Code | Description | |---|---| | `200` | Success | `201` | Success - *new resource created (POST)* | `204` | Success - *no content to return (DELETE)* | `400` | Bad Request - *request couldn't be parsed* | `401` | Unauthorized - *OAuth must be provided* | `403` | Forbidden - *invalid API key or unapproved app* | `404` | Not Found - *method exists, but no record found* | `405` | Method Not Found - *method doesn't exist* | `409` | Conflict - *resource already created* | `412` | Precondition Failed - *use application/json content type* | `420` | Account Limit Exceeded - *list count, item count, etc* | `422` | Unprocessable Entity - *validation errors* | `423` | Locked User Account - *have the user contact support* | `426` | VIP Only - *user must upgrade to VIP* | `429` | Rate Limit Exceeded | `500` | Server Error - *please open a support ticket* | `502` | Service Unavailable - *server overloaded (try again in 30s)* | `503` | Service Unavailable - *server overloaded (try again in 30s)* | `504` | Service Unavailable - *server overloaded (try again in 30s)* | `520` | Service Unavailable - *Cloudflare error* | `521` | Service Unavailable - *Cloudflare error* | `522` | Service Unavailable - *Cloudflare error*  # Required Headers  You'll need to send some headers when making API calls to identify your application, set the version and set the content type to JSON.  | Header | Value | |---|---| | `Content-Type` <span style=\"color:red;\">*</a> | `application/json` | | `User-Agent` <span style=\"color:red;\">*</a> | We suggest using your app and version like `MyAppName/1.0.0` | | `trakt-api-key` <span style=\"color:red;\">*</a> | Your `client_id` listed under your Trakt applications. | | `trakt-api-version` <span style=\"color:red;\">*</a> | `2` | API version to use.  All `POST`, `PUT`, and `DELETE` methods require a valid OAuth `access_token`. Some `GET` calls require OAuth and others will return user specific data if OAuth is sent. Methods that &#128274; **require** or have &#128275; **optional** OAuth will be indicated.  Your OAuth library should take care of sending the auth headers for you, but for reference here's how the Bearer token should be sent.  | Header | Value | |---|---| | `Authorization` | `Bearer [access_token]` |  # Rate Limiting  All API methods are rate limited. A `429` HTTP status code is returned when the limit has been exceeded. Check the headers for detailed info, then try your API call in `Retry-After` seconds.  | Header | Value | |---|---| | `X-Ratelimit` | `{\"name\":\"UNAUTHED_API_GET_LIMIT\",\"period\":300,\"limit\":1000,\"remaining\":0,\"until\":\"2020-10-10T00:24:00Z\"}` | | `Retry-After` | `10` |  Here are the current limits. There are separate limits for authed (user level) and unauthed (application level) calls. We'll continue to adjust these limits to optimize API performance for everyone. The goal is to prevent API abuse and poor coding, but allow users to use apps normally.  | Name | Verb | Methods | Limit | |---|---|---|---| | `AUTHED_API_POST_LIMIT` | `POST`, `PUT`, `DELETE` | all | 1 call per second | | `AUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes | | `UNAUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes |  # Locked User Account  A `423` HTTP status code is returned when the OAuth user has a locked or deactivated user account. Please instruct the user to [**email Trakt support**](mailto:support@trakt.tv) so we can fix their account. API access will be suspended for the user until we fix their account.  | Header | Value | |---|---| | `X-Account-Locked` | `true` or `false` | | `X-Account-Deactivated` | `true` or `false` |  # VIP Methods  Some API methods are tagged 🔥 **VIP Only**. A `426` HTTP status code is returned when the user isn't a VIP, indicating they need to sign up for [**Trakt VIP**](https://trakt.tv/vip) in order to use this method. In your app, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` |  Some API methods are tagged 🔥 **VIP Enhanced**. A `420` HTTP status code is returned when the user has exceeded their account limit. Signing up for [**Trakt VIP**](https://trakt.tv/vip) will increase these limits. If the user isn't a VIP, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP. If they are already VIP and still exceeded the limit, please display a message indicating this.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` | | `X-VIP-User` | `true` or `false` | | `X-Account-Limit` | Limit allowed. |  # Pagination  Some methods are paginated. Methods with &#128196; **Pagination** will load 1 page of 10 items by default. Methods with &#128196; **Pagination Optional** will load all items by default. In either case, append a query string like `?page={page}&limit={limit}` to the URL to influence the results.  | Parameter | Type | Default | Value | |---|---|---|---| | `page` | integer | `1` | Number of page of results to be returned. | | `limit` | integer | `10` | Number of results to return per page. |  All paginated methods will return these HTTP headers.  | Header | Value | |---|---| | `X-Pagination-Page` | Current page. | | `X-Pagination-Limit` | Items per page. | | `X-Pagination-Page-Count` | Total number of pages. | | `X-Pagination-Item-Count` | Total number of items. |  # Extended Info  By default, all methods will return minimal info for movies, shows, episodes, people, and users. Minimal info is typically all you need to match locally cached items and includes the `title`, `year`, and `ids`. However, you can request different extended levels of information by adding `?extended={level}` to the URL. Send a comma separated string to get multiple types of extended info.  > ### 🅽🅾🆃🅴 > _This returns a lot of extra data, so please only use extended parameters if you actually need them!_  | Level | Description | |---|---| | `images` | Minimal info and all images. | | `full` | Complete info for an item. | | `full,images` | Complete info and all images. | | `metadata` | **Collection only.** Additional video and audio info. |  # Filters  Some `movies`, `shows`, `calendars`,  and `search` methods support additional filters and will be tagged with &#127898; **Filters**. Applying these filters refines the results and helps your users to more easily discover new items.  Add a query string (i.e. `?years=2016&genres=action`) with any filters you want to use. Some filters allow multiples which can be sent as comma delimited parameters. For example, `?genres=action,adventure` would match the `action` OR `adventure` genre.  *Please note*, subgenres are currently a technical preview.  We're currently in the process of smoothing this out.  > ### 🅽🅾🆃🅴 > _Make sure to properly URL encode the parameters including spaces and special characters._  #### Common Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `query` | | `batman` | Search titles and descriptions. | | `years` | | `2016` | 4 digit year or range of years. | | `genres` | &#10003; | `action` | [Genre slugs.](#reference/genres) | | `subgenres` | &#10003; | `android` | [Subgenre slugs.](#reference/subgenres) | | `languages` | &#10003; | `en` | [2 character language code.](#reference/languages) | | `countries` | &#10003; | `us` | [2 character country code.](#reference/countries) | | `runtimes` | | `30-90` | Range in minutes. | | `studio_ids` | &#10003; | `42` | Trakt studio ID. |  #### Rating Filters  Trakt, TMDB, and IMDB ratings apply to `movies`, `shows`, and `episodes`. Rotten Tomatoes and Metacritic apply to `movies`.  | Parameter | Multiples | Example | Value | |---|---|---|---| | `ratings` | | `75-100` | Trakt rating range between `0` and `100`. | | `votes` | | `5000-10000` | Trakt vote count between `0` and `100000`. | | `tmdb_ratings` | | `5.5-10.0` | TMDB rating range between `0.0` and `10.0`. | | `tmdb_votes` | | `5000-10000` | TMDB vote count between `0` and `100000`. | | `imdb_ratings` | | `5.5-10.0` | IMDB rating range between `0.0` and `10.0`. | | `imdb_votes` | | `5000-10000` | IMDB vote count between `0` and `3000000`. | | `rt_meters` | | `55-1000` | Rotten Tomatoes tomatometer range between `0` and `100`. | | `rt_user_meters` | | `65-100` | Rotten Tomatoes audience score range between `0` and `100`. | | `metascores` | | `5.5-10.0` | Metacritic score range between `0` and `100`. |  #### Movie Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `pg-13` | US content certification. |  #### Show Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `status` | &#10003; | `ended` | Set to `returning series`, `continuing`, `in production`, `planned`, `upcoming`,  `pilot`, `canceled`, or `ended`. |  #### Episode Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `episode_types` | &#10003; | `mid_season_premiere` | Set to `standard`, `series_premiere`, `season_premiere`, `mid_season_finale`, `mid_season_premiere`, `season_finale`,  or `series_finale`. |  # CORS  When creating your API app, specify the JavaScript (CORS) origins you'll be using. We use these origins to return the headers needed for CORS.  # Dates  All dates will be GMT and returned in the ISO 8601 format like `2014-09-01T09:10:11.000Z`. Adjust accordingly in your app for the user's local timezone.  # Emojis  We use short codes for emojis like `:smiley:` and `:raised_hands:` and render them on the Trakt website using [**JoyPixels**](https://www.joypixels.com/) _(verion 6.6.0)_. Methods that support emojis are tagged with &#128513; **Emojis**. For POST methods, you can send standard unicode emojis and we'll automatically convert them to short codes. For GET methods, we'll return the unicode emojis if possible, but some short codes might also be returned. It's up to your app to convert short codes back to unicode emojis.  # Standard Media Objects  All methods will accept or return standard media objects for `movie`, `show`, `season`, `episode`, `person`, and `user` items. Here are examples for all minimal objects.  #### movie  ``` {     \"title\": \"Batman Begins\",     \"year\": 2005,     \"ids\": {         \"trakt\": 1,         \"slug\": \"batman-begins-2005\",         \"imdb\": \"tt0372784\",         \"tmdb\": 272     } } ```  #### show  ``` {     \"title\": \"Breaking Bad\",     \"year\": 2008,     \"ids\": {         \"trakt\": 1,         \"slug\": \"breaking-bad\",         \"tvdb\": 81189,         \"imdb\": \"tt0903747\",         \"tmdb\": 1396     } } ```  #### season  ``` {     \"number\": 0,     \"ids\": {         \"trakt\": 1,         \"tvdb\": 439371,         \"tmdb\": 3577     } } ```  #### episode  ``` {     \"season\": 1,     \"number\": 1,     \"title\": \"Pilot\",     \"ids\": {         \"trakt\": 16,         \"tvdb\": 349232,         \"imdb\": \"tt0959621\",         \"tmdb\": 62085     } } ```  #### person  ``` {     \"name\": \"Bryan Cranston\",     \"ids\": {         \"trakt\": 142,         \"slug\": \"bryan-cranston\",         \"imdb\": \"nm0186505\",         \"tmdb\": 17419     } } ```  #### user  ``` {     \"username\": \"sean\",     \"private\": false,     \"name\": \"Sean Rudford\",     \"vip\": true,     \"vip_ep\": true,     \"ids\": {         \"slug\": \"sean\"     } } ```  # Images  #### Trakt Images  Trakt can return images by appending `?extended=images` to most URLs. This will return all images for a `movie`, `show`, `season`, `episode`, or `person`. Images are returned in a `images` object with keys for each image type. Each image type is an array of image URLs, but only 1 image URL will be returned for now. This is just future proofing.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > **Please cache all images!** All images are required to be cached in your app or server and not loaded directly from our CDN. Hotlinking images is not allowed and will be blocked.  > ### 🅽🅾🆃🅴 > All images are returned in WebP format for reduced file size, at the same image quality. You'll also need to prepend the https:// prefix to all image URLs.  ### Example Images Object  ```json {   \"title\": \"TRON: Legacy\",   \"year\": 2010,   \"ids\": {     \"trakt\": 12601,     \"slug\": \"tron-legacy-2010\",     \"imdb\": \"tt1104001\",     \"tmdb\": 20526   },   \"images\": {     \"fanart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/fanarts/medium/5aab754f58.jpg.webp\"     ],     \"poster\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/posters/thumb/e0d9dd35c5.jpg.webp\"     ],     \"logo\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/logos/medium/dbce70b4aa.png.webp\"     ],     \"clearart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/cleararts/medium/513a3688d1.png.webp\"     ],     \"banner\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/banners/medium/71dc0c3258.jpg.webp\"     ],     \"thumb\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/thumbs/medium/fcd7d7968c.jpg.webp\"     ]   } } ```  #### External Images  If you want more variety of images, there are several external services you can use. The standard Trakt media objects for all `movie`, `show`, `season`, `episode`, and `person` items include an `ids` object. These `ids` map to other services like [TMDB](https://www.themoviedb.org), [TVDB](https://thetvdb.com), [Fanart.tv](https://fanart.tv), [IMDB](https://www.imdb.com), and [OMDB](https://www.omdbapi.com/).  Most of these services have free APIs you can use to grab lots of great looking images. Here’s a chart to help you find the best artwork for your app. [**We also wrote an article to help with this.**](https://medium.com/api-news/how-to-find-the-best-images-516045bcc3b6)  | Media | Type | [TMDB](https://developers.themoviedb.org/3) | [TVDB](https://api.thetvdb.com/swagger) | [Fanart.tv](http://docs.fanarttv.apiary.io) | [OMDB](https://www.omdbapi.com) | |---|---|---|---|---|---| | `shows` | `poster` | &#10003; | &#10003; | &#10003; | &#10003; | |  | `fanart` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `seasons` | `poster` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `episodes` | `screenshot` | &#10003; | &#10003; |  |  | | `movies` | `poster` | &#10003; |  | &#10003; | &#10003; | |  | `fanart` | &#10003; |  | &#10003; |  | |  | `banner` |  |  | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `person` | `headshot` | &#10003; |  |  |  | |  | `character` |  | &#10003; |  |  |  # Website Media Links  There are several ways to construct direct links to media on the Trakt website. The website itself uses slugs so the URLs are more readable.  | Type | URL | |---|---| | `movie` | `/movies/:id` | | | `/movies/:slug` | | `show` | `/shows/:id` | | | `/shows/:slug` | | `season` | `/shows/:id/seasons/:num` | | | `/shows/:slug/seasons/:num` | | `episode` | `/shows/:id/seasons/:num/episodes/:num` | | | `/shows/:slug/seasons/:num/episodes/:num` | | `person` | `/people/:id` | | | `/people/:slug` | | `comment` | `/comments/:id` | | `list` | `/lists/:id` |  You can also create links using the Trakt, IMDB, TMDB, or TVDB IDs. We recommend using the Trakt ID if possible since that will always have full coverage. If you use the search url without an `id_type` it will return search results if multiple items are found.  | Type | URL | |---|---| | `trakt` | `/search/trakt/:id` | |  | `/search/trakt/:id?id_type=movie` | |  | `/search/trakt/:id?id_type=show` | |  | `/search/trakt/:id?id_type=season` | |  | `/search/trakt/:id?id_type=episode` | |  | `/search/trakt/:id?id_type=person` | | `imdb` | `/search/imdb/:id` | | `tmdb` | `/search/tmdb/:id` | |  | `/search/tmdb/:id?id_type=movie` | |  | `/search/tmdb/:id?id_type=show` | |  | `/search/tmdb/:id?id_type=episode` | |  | `/search/tmdb/:id?id_type=person` | | `tvdb` | `/search/tvdb/:id` | |  | `/search/tvdb/:id?id_type=show` | |  | `/search/tvdb/:id?id_type=episode` |  # Third Party Libraries  All of the libraries listed below are user contributed. If you find a bug or missing feature, please contact the developer directly. These might help give your project a head start, but we can't provide direct support for any of these libraries. Please help us keep this list up to date.  | Language | Name | Repository | |---|---|---| | `C#` | `Trakt.NET` | https://github.com/henrikfroehling/Trakt.NET | |  | `TraktSharp` | https://github.com/wwarby/TraktSharp | | `C++` | `libtraqt` | https://github.com/RobertMe/libtraqt | | `Clojure` | `clj-trakt` | https://github.com/niamu/clj-trakt | | `Java` | `trakt-java` | https://github.com/UweTrottmann/trakt-java | | `Kotlin` | `trakt-api` | https://github.com/MoviebaseApp/trakt-api | | `Node.js` | `Trakt.tv` | https://github.com/vankasteelj/trakt.tv | |  | `TraktApi2` | https://github.com/PatrickE94/traktapi2 | | `Python` | `trakt.py` | https://github.com/fuzeman/trakt.py | |  | `pyTrakt` | https://github.com/moogar0880/PyTrakt | | `R` | `tRakt` | https://github.com/jemus42/tRakt | | `React Native` | `nodeless-trakt` | https://github.com/kdemoya/nodeless-trakt | | `Ruby` | `omniauth-trakt` | https://github.com/wafcio/omniauth-trakt | |  | `omniauth-trakt` | https://github.com/alextakitani/omniauth-trakt | | `Swift` | `TraktKit` | https://github.com/MaxHasADHD/TraktKit | |  | `AKTrakt` | https://github.com/arsonik/AKTrakt |  # Terminology  Trakt has a lot of features and here's a chart to help explain the differences between some of them.  | Term | Description | |---|---| | `scrobble` | Automatic way to track what a user is watching in a media center. | | `checkin` | Manual action used by mobile apps allowing the user to indicate what they are watching right now. | | `history` | All watched items (scrobbles, checkins, watched) for a user. | | `collection` | Items a user has available to watch including Blu-Rays, DVDs, and digital downloads. | | `watchlist` | Items a user wants to watch in the future. Once watched, they are auto removed from this list. | | `list` | Personal list for any purpose. Items are not auto removed from any personal lists. | | `favorites` | A user's top 50 TV shows and movies. |

The version of the OpenAPI document:
Generated by OpenAPI Generator (https://openapi-generator.tech)

Do not edit the class manually.
"""  # noqa: E501


__version__ = "1.0.0"

# Define package exports
__all__ = [
    "AuthenticationDevicesApi",
    "AuthenticationOAuthApi",
    "CalendarsApi",
    "CertificationsApi",
    "CheckinApi",
    "CommentsApi",
    "CountriesApi",
    "EpisodesApi",
    "GenresApi",
    "LanguagesApi",
    "ListsApi",
    "MoviesApi",
    "NetworksApi",
    "NotesApi",
    "PeopleApi",
    "RecommendationsApi",
    "ScrobbleApi",
    "SearchApi",
    "SeasonsApi",
    "ShowsApi",
    "SyncApi",
    "UsersApi",
    "ApiResponse",
    "ApiClient",
    "Configuration",
    "OpenApiException",
    "ApiTypeError",
    "ApiValueError",
    "ApiKeyError",
    "ApiAttributeError",
    "ApiException",
    "AddHiddenItems201Response",
    "AddHiddenItems201ResponseAdded",
    "AddHiddenItems201ResponseNotFound",
    "AddHiddenItemsRequest",
    "AddHiddenItemsRequestSeasonsInner",
    "AddHiddenItemsRequestSeasonsInnerIds",
    "AddHiddenItemsRequestShowsInner",
    "AddHiddenItemsRequestShowsInnerSeasonsInner",
    "AddItemsToCollection201Response",
    "AddItemsToCollection201ResponseAdded",
    "AddItemsToCollection201ResponseNotFound",
    "AddItemsToCollection201ResponseNotFoundMoviesInner",
    "AddItemsToCollection201ResponseNotFoundMoviesInnerIds",
    "AddItemsToCollectionRequest",
    "AddItemsToCollectionRequestEpisodesInner",
    "AddItemsToCollectionRequestMoviesInner",
    "AddItemsToCollectionRequestSeasonsInner",
    "AddItemsToCollectionRequestShowsInner",
    "AddItemsToCollectionRequestShowsInnerSeasonsInner",
    "AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner",
    "AddItemsToFavorites201Response",
    "AddItemsToFavorites201ResponseAdded",
    "AddItemsToFavorites201ResponseNotFound",
    "AddItemsToFavoritesRequest",
    "AddItemsToFavoritesRequestShowsInner",
    "AddItemsToPersonalList201Response",
    "AddItemsToPersonalList201ResponseAdded",
    "AddItemsToPersonalList201ResponseNotFound",
    "AddItemsToPersonalListRequest",
    "AddItemsToPersonalListRequestMoviesInner",
    "AddItemsToPersonalListRequestMoviesInnerIds",
    "AddItemsToPersonalListRequestShowsInner",
    "AddItemsToWatchedHistory201Response",
    "AddItemsToWatchedHistoryRequest",
    "AddItemsToWatchedHistoryRequestEpisodesInner",
    "AddItemsToWatchedHistoryRequestMoviesInner",
    "AddItemsToWatchedHistoryRequestSeasonsInner",
    "AddItemsToWatchedHistoryRequestShowsInner",
    "AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner",
    "AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner",
    "AddItemsToWatchlist201Response",
    "AddItemsToWatchlist201ResponseList",
    "AddItemsToWatchlistRequest",
    "AddItemsToWatchlistRequestMoviesInner",
    "AddItemsToWatchlistRequestShowsInner",
    "AddNewRatings201Response",
    "AddNewRatings201ResponseAdded",
    "AddNewRatings201ResponseNotFound",
    "AddNewRatings201ResponseNotFoundMoviesInner",
    "AddNewRatingsRequest",
    "AddNewRatingsRequestEpisodesInner",
    "AddNewRatingsRequestMoviesInner",
    "AddNewRatingsRequestSeasonsInner",
    "AddNewRatingsRequestShowsInner",
    "AddNewRatingsRequestShowsInnerSeasonsInner",
    "AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner",
    "AddNotes201Response",
    "AddNotesRequest",
    "ApproveFollowRequest200Response",
    "CheckIntoAnItem201Response",
    "CheckIntoAnItem201ResponseEpisode",
    "CheckIntoAnItem201ResponseEpisodeIds",
    "CheckIntoAnItem409Response",
    "CheckIntoAnItemRequest",
    "CheckIntoAnItemRequestSharing",
    "CreatePersonalList201Response",
    "CreatePersonalListRequest",
    "ExchangeRefreshTokenForAccessToken200Response",
    "ExchangeRefreshTokenForAccessToken401Response",
    "ExchangeRefreshTokenForAccessTokenRequest",
    "FollowThisUser201Response",
    "GenerateNewDeviceCodes200Response",
    "GenerateNewDeviceCodesRequest",
    "GetACommentOrReply200Response",
    "GetACommentOrReply200ResponseUserStats",
    "GetAMovie200Response",
    "GetANote200Response",
    "GetASingleEpisodeForAShow200Response",
    "GetASinglePerson200Response",
    "GetASinglePerson200ResponseSocialIds",
    "GetASingleShow200Response",
    "GetASingleShow200ResponseAirs",
    "GetAUserSPersonalLists200ResponseInner",
    "GetAllEpisodesForASingleSeason200ResponseInner",
    "GetAllListComments200ResponseInner",
    "GetAllListsAUserCanCollaborateOn200ResponseInner",
    "GetAllMovieAliases200ResponseInner",
    "GetAllMovieReleases200ResponseInner",
    "GetAllMovieTranslations200ResponseInner",
    "GetAllPeopleForAMovie200Response",
    "GetAllPeopleForAMovie200ResponseCastInner",
    "GetAllPeopleForAMovie200ResponseCrew",
    "GetAllPeopleForAMovie200ResponseCrewArtInner",
    "GetAllPeopleForAMovie200ResponseCrewDirectingInner",
    "GetAllPeopleForAMovie200ResponseCrewProductionInner",
    "GetAllPeopleForASeason200Response",
    "GetAllPeopleForASeason200ResponseCrew",
    "GetAllPeopleForAShow200Response",
    "GetAllPeopleForAShow200ResponseCastInner",
    "GetAllPeopleForAShow200ResponseCrew",
    "GetAllPeopleForAShow200ResponseCrewArtInner",
    "GetAllPeopleForAShow200ResponseCrewVisualEffectsInner",
    "GetAllPeopleForAnEpisode200Response",
    "GetAllPeopleForAnEpisode200ResponseCrew",
    "GetAllPeopleForAnEpisode200ResponseGuestStarsInner",
    "GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson",
    "GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds",
    "GetAllSeasonTranslations200ResponseInner",
    "GetAllSeasonsForAShow200ResponseInner",
    "GetAllSeasonsForAShow200ResponseInnerEpisodesInner",
    "GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds",
    "GetAllSeasonsForAShow200ResponseInnerIds",
    "GetAllShowCertifications200ResponseInner",
    "GetAllShowTranslations200ResponseInner",
    "GetAllUsersWhoLikedAComment200ResponseInner",
    "GetAllVideos200ResponseInner",
    "GetCertifications200Response",
    "GetCertifications200ResponseUsInner",
    "GetCollection200ResponseInner",
    "GetCollection200ResponseInnerSeasonsInner",
    "GetCollection200ResponseInnerSeasonsInnerEpisodesInner",
    "GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata",
    "GetCountries200ResponseInner",
    "GetFavorites200ResponseInner",
    "GetFollowers200ResponseInner",
    "GetFriends200ResponseInner",
    "GetGenres200ResponseInner",
    "GetGenres200ResponseInnerSubgenresInner",
    "GetHiddenItems200ResponseInner",
    "GetIDLookupResults200ResponseInner",
    "GetItemsOnAList200ResponseInner",
    "GetItemsOnAList200ResponseInnerEpisode",
    "GetItemsOnAList200ResponseInnerEpisodeIds",
    "GetItemsOnAList200ResponseInnerPerson",
    "GetItemsOnAList200ResponseInnerSeason",
    "GetItemsOnAList200ResponseInnerSeasonIds",
    "GetItemsOnAPersonalList200ResponseInner",
    "GetLastActivity200Response",
    "GetLastActivity200ResponseAccount",
    "GetLastActivity200ResponseComments",
    "GetLastActivity200ResponseEpisodes",
    "GetLastActivity200ResponseLists",
    "GetLastActivity200ResponseMovies",
    "GetLastActivity200ResponseSeasons",
    "GetLastActivity200ResponseShows",
    "GetLastActivity200ResponseWatchlist",
    "GetLastEpisode200Response",
    "GetLikes200ResponseInner",
    "GetLikes200ResponseInnerList",
    "GetList200Response",
    "GetMovieCredits200Response",
    "GetMovieCredits200ResponseCastInner",
    "GetMovieCredits200ResponseCrew",
    "GetMovieCredits200ResponseCrewDirectingInner",
    "GetMovieRatings200Response",
    "GetMovieRatings200ResponseDistribution",
    "GetMovieRecommendations200ResponseInner",
    "GetMovieRecommendations200ResponseInnerFavoritedByInner",
    "GetMovieStats200Response",
    "GetMovieStudios200ResponseInner",
    "GetMovieStudios200ResponseInnerIds",
    "GetMovies200ResponseInner",
    "GetMovies200ResponseInnerMovie",
    "GetMovies200ResponseInnerMovieIds",
    "GetNetworks200ResponseInner",
    "GetNetworks200ResponseInnerIds",
    "GetNewShows200ResponseInner",
    "GetNewShows200ResponseInnerEpisode",
    "GetNewShows200ResponseInnerEpisodeIds",
    "GetNextEpisode200Response",
    "GetNotes200ResponseInner",
    "GetNotes200ResponseInnerAttachedTo",
    "GetNotes200ResponseInnerNote",
    "GetNotes200ResponseInnerNoteUser",
    "GetNotes200ResponseInnerNoteUserIds",
    "GetPendingFollowingRequests200ResponseInner",
    "GetPlaybackProgress200ResponseInner",
    "GetPopularMovies200ResponseInner",
    "GetPopularShows200ResponseInner",
    "GetRatings200ResponseInner",
    "GetRecentlyUpdatedMovies200ResponseInner",
    "GetRecentlyUpdatedPeople200ResponseInner",
    "GetRecentlyUpdatedShows200ResponseInner",
    "GetRepliesForAComment200ResponseInner",
    "GetSavedFilters200ResponseInner",
    "GetSeasonPremieres200ResponseInner",
    "GetSeasonRatings200Response",
    "GetSeasonStats200Response",
    "GetShowCollectionProgress200Response",
    "GetShowCollectionProgress200ResponseSeasonsInner",
    "GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner",
    "GetShowCredits200Response",
    "GetShowCredits200ResponseCastInner",
    "GetShowCredits200ResponseCrew",
    "GetShowCredits200ResponseCrewProductionInner",
    "GetShowRatings200Response",
    "GetShowRecommendations200ResponseInner",
    "GetShowStats200Response",
    "GetShowWatchedProgress200Response",
    "GetShowWatchedProgress200ResponseSeasonsInner",
    "GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner",
    "GetShows200ResponseInner",
    "GetShows200ResponseInnerEpisode",
    "GetShows200ResponseInnerEpisodeIds",
    "GetShows200ResponseInnerShow",
    "GetShows200ResponseInnerShowIds",
    "GetSingleSeasonsForAShow200Response",
    "GetStats200Response",
    "GetStats200ResponseMovies",
    "GetStats200ResponseNetwork",
    "GetStats200ResponseRatings",
    "GetStats200ResponseSeasons",
    "GetStats200ResponseShows",
    "GetTextQueryResults200ResponseInner",
    "GetTheAttachedItem200Response",
    "GetTheAttachedItem200ResponseAttachedTo",
    "GetTheAttachedMediaItem200Response",
    "GetTheMostAnticipatedMovies200ResponseInner",
    "GetTheMostAnticipatedShows200ResponseInner",
    "GetTheMostAnticipatedShows200ResponseInnerShow",
    "GetTheMostAnticipatedShows200ResponseInnerShowIds",
    "GetTheMostFavoritedMovies200ResponseInner",
    "GetTheMostFavoritedShows200ResponseInner",
    "GetTheMostPlayedMovies200ResponseInner",
    "GetTheMostPlayedShows200ResponseInner",
    "GetTheWeekendBoxOffice200ResponseInner",
    "GetTrendingComments200ResponseInner",
    "GetTrendingComments200ResponseInnerComment",
    "GetTrendingComments200ResponseInnerCommentUserStats",
    "GetTrendingComments200ResponseInnerList",
    "GetTrendingComments200ResponseInnerListIds",
    "GetTrendingComments200ResponseInnerSeason",
    "GetTrendingComments200ResponseInnerSeasonIds",
    "GetTrendingLists200ResponseInner",
    "GetTrendingLists200ResponseInnerList",
    "GetTrendingMovies200ResponseInner",
    "GetTrendingShows200ResponseInner",
    "GetUserProfile200Response",
    "GetUsersWatchingRightNow200ResponseInner",
    "GetWatched200ResponseInner",
    "GetWatchedHistory200ResponseInner",
    "GetWatching200Response",
    "GetWatchlist200ResponseInner",
    "PollForTheAccessTokenRequest",
    "PostAComment201Response",
    "PostAComment201ResponseUser",
    "PostAComment201ResponseUserIds",
    "PostAComment201ResponseUserStats",
    "PostACommentRequest",
    "PostACommentRequestSharing",
    "PostAReplyForAComment201Response",
    "PostAReplyForACommentRequest",
    "RemoveHiddenItems200Response",
    "RemoveHiddenItemsRequest",
    "RemoveHiddenItemsRequestShowsInner",
    "RemoveItemsFromCollection200Response",
    "RemoveItemsFromCollectionRequest",
    "RemoveItemsFromCollectionRequestMoviesInner",
    "RemoveItemsFromCollectionRequestShowsInner",
    "RemoveItemsFromCollectionRequestShowsInnerSeasonsInner",
    "RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner",
    "RemoveItemsFromFavorites200Response",
    "RemoveItemsFromFavoritesRequest",
    "RemoveItemsFromHistory200Response",
    "RemoveItemsFromHistory200ResponseNotFound",
    "RemoveItemsFromHistoryRequest",
    "RemoveItemsFromPersonalList200Response",
    "RemoveItemsFromPersonalListRequest",
    "RemoveItemsFromPersonalListRequestMoviesInner",
    "RemoveItemsFromPersonalListRequestShowsInner",
    "RemoveItemsFromWatchlist200Response",
    "RemoveRatings200Response",
    "ReorderAUserSLists200Response",
    "ReorderAUserSListsRequest",
    "ReorderFavoritedItems200Response",
    "ReorderItemsOnAList200Response",
    "ReorderWatchlistItems200Response",
    "ReorderWatchlistItemsRequest",
    "ResetShowProgress200Response",
    "RetrieveSettings200Response",
    "RetrieveSettings200ResponseAccount",
    "RetrieveSettings200ResponseConnections",
    "RetrieveSettings200ResponseLimits",
    "RetrieveSettings200ResponseLimitsList",
    "RetrieveSettings200ResponseLimitsSearch",
    "RetrieveSettings200ResponseLimitsWatchlist",
    "RetrieveSettings200ResponsePermissions",
    "RetrieveSettings200ResponseSharingText",
    "RetrieveSettings200ResponseUser",
    "RetrieveSettings200ResponseUserIds",
    "RetrieveSettings200ResponseUserImages",
    "RetrieveSettings200ResponseUserImagesAvatar",
    "RevokeAnAccessTokenRequest",
    "StartWatchingInAMediaCenter201Response",
    "StartWatchingInAMediaCenterRequest",
    "StopOrFinishWatchingInAMediaCenter201Response",
    "StopOrFinishWatchingInAMediaCenter409Response",
    "StopOrFinishWatchingInAMediaCenterRequest",
    "UpdateACommentOrReply200Response",
    "UpdateACommentOrReplyRequest",
    "UpdateANote200Response",
    "UpdateANoteRequest",
    "UpdateAWatchlistItemRequest",
    "UpdateFavorites200Response",
    "UpdateFavoritesRequest",
    "UpdatePersonalList200Response",
    "UpdatePersonalListRequest",
    "UpdateWatchlist200Response",
    "UpdateWatchlist200ResponseIds",
    "UpdateWatchlistRequest",
]

if __import__("typing").TYPE_CHECKING:
    # import apis into sdk package
    from schemas.trakt.api.authentication_devices_api import (
        AuthenticationDevicesApi as AuthenticationDevicesApi,
    )
    from schemas.trakt.api.authentication_o_auth_api import (
        AuthenticationOAuthApi as AuthenticationOAuthApi,
    )
    from schemas.trakt.api.calendars_api import CalendarsApi as CalendarsApi
    from schemas.trakt.api.certifications_api import (
        CertificationsApi as CertificationsApi,
    )
    from schemas.trakt.api.checkin_api import CheckinApi as CheckinApi
    from schemas.trakt.api.comments_api import CommentsApi as CommentsApi
    from schemas.trakt.api.countries_api import CountriesApi as CountriesApi
    from schemas.trakt.api.episodes_api import EpisodesApi as EpisodesApi
    from schemas.trakt.api.genres_api import GenresApi as GenresApi
    from schemas.trakt.api.languages_api import LanguagesApi as LanguagesApi
    from schemas.trakt.api.lists_api import ListsApi as ListsApi
    from schemas.trakt.api.movies_api import MoviesApi as MoviesApi
    from schemas.trakt.api.networks_api import NetworksApi as NetworksApi
    from schemas.trakt.api.notes_api import NotesApi as NotesApi
    from schemas.trakt.api.people_api import PeopleApi as PeopleApi
    from schemas.trakt.api.recommendations_api import (
        RecommendationsApi as RecommendationsApi,
    )
    from schemas.trakt.api.scrobble_api import ScrobbleApi as ScrobbleApi
    from schemas.trakt.api.search_api import SearchApi as SearchApi
    from schemas.trakt.api.seasons_api import SeasonsApi as SeasonsApi
    from schemas.trakt.api.shows_api import ShowsApi as ShowsApi
    from schemas.trakt.api.sync_api import SyncApi as SyncApi
    from schemas.trakt.api.users_api import UsersApi as UsersApi

    # import ApiClient
    from schemas.trakt.api_response import ApiResponse as ApiResponse
    from schemas.trakt.api_client import ApiClient as ApiClient
    from schemas.trakt.configuration import Configuration as Configuration
    from schemas.trakt.exceptions import OpenApiException as OpenApiException
    from schemas.trakt.exceptions import ApiTypeError as ApiTypeError
    from schemas.trakt.exceptions import ApiValueError as ApiValueError
    from schemas.trakt.exceptions import ApiKeyError as ApiKeyError
    from schemas.trakt.exceptions import ApiAttributeError as ApiAttributeError
    from schemas.trakt.exceptions import ApiException as ApiException

    # import models into sdk package
    from schemas.trakt.models.add_hidden_items201_response import (
        AddHiddenItems201Response as AddHiddenItems201Response,
    )
    from schemas.trakt.models.add_hidden_items201_response_added import (
        AddHiddenItems201ResponseAdded as AddHiddenItems201ResponseAdded,
    )
    from schemas.trakt.models.add_hidden_items201_response_not_found import (
        AddHiddenItems201ResponseNotFound as AddHiddenItems201ResponseNotFound,
    )
    from schemas.trakt.models.add_hidden_items_request import (
        AddHiddenItemsRequest as AddHiddenItemsRequest,
    )
    from schemas.trakt.models.add_hidden_items_request_seasons_inner import (
        AddHiddenItemsRequestSeasonsInner as AddHiddenItemsRequestSeasonsInner,
    )
    from schemas.trakt.models.add_hidden_items_request_seasons_inner_ids import (
        AddHiddenItemsRequestSeasonsInnerIds as AddHiddenItemsRequestSeasonsInnerIds,
    )
    from schemas.trakt.models.add_hidden_items_request_shows_inner import (
        AddHiddenItemsRequestShowsInner as AddHiddenItemsRequestShowsInner,
    )
    from schemas.trakt.models.add_hidden_items_request_shows_inner_seasons_inner import (
        AddHiddenItemsRequestShowsInnerSeasonsInner as AddHiddenItemsRequestShowsInnerSeasonsInner,
    )
    from schemas.trakt.models.add_items_to_collection201_response import (
        AddItemsToCollection201Response as AddItemsToCollection201Response,
    )
    from schemas.trakt.models.add_items_to_collection201_response_added import (
        AddItemsToCollection201ResponseAdded as AddItemsToCollection201ResponseAdded,
    )
    from schemas.trakt.models.add_items_to_collection201_response_not_found import (
        AddItemsToCollection201ResponseNotFound as AddItemsToCollection201ResponseNotFound,
    )
    from schemas.trakt.models.add_items_to_collection201_response_not_found_movies_inner import (
        AddItemsToCollection201ResponseNotFoundMoviesInner as AddItemsToCollection201ResponseNotFoundMoviesInner,
    )
    from schemas.trakt.models.add_items_to_collection201_response_not_found_movies_inner_ids import (
        AddItemsToCollection201ResponseNotFoundMoviesInnerIds as AddItemsToCollection201ResponseNotFoundMoviesInnerIds,
    )
    from schemas.trakt.models.add_items_to_collection_request import (
        AddItemsToCollectionRequest as AddItemsToCollectionRequest,
    )
    from schemas.trakt.models.add_items_to_collection_request_episodes_inner import (
        AddItemsToCollectionRequestEpisodesInner as AddItemsToCollectionRequestEpisodesInner,
    )
    from schemas.trakt.models.add_items_to_collection_request_movies_inner import (
        AddItemsToCollectionRequestMoviesInner as AddItemsToCollectionRequestMoviesInner,
    )
    from schemas.trakt.models.add_items_to_collection_request_seasons_inner import (
        AddItemsToCollectionRequestSeasonsInner as AddItemsToCollectionRequestSeasonsInner,
    )
    from schemas.trakt.models.add_items_to_collection_request_shows_inner import (
        AddItemsToCollectionRequestShowsInner as AddItemsToCollectionRequestShowsInner,
    )
    from schemas.trakt.models.add_items_to_collection_request_shows_inner_seasons_inner import (
        AddItemsToCollectionRequestShowsInnerSeasonsInner as AddItemsToCollectionRequestShowsInnerSeasonsInner,
    )
    from schemas.trakt.models.add_items_to_collection_request_shows_inner_seasons_inner_episodes_inner import (
        AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner as AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.add_items_to_favorites201_response import (
        AddItemsToFavorites201Response as AddItemsToFavorites201Response,
    )
    from schemas.trakt.models.add_items_to_favorites201_response_added import (
        AddItemsToFavorites201ResponseAdded as AddItemsToFavorites201ResponseAdded,
    )
    from schemas.trakt.models.add_items_to_favorites201_response_not_found import (
        AddItemsToFavorites201ResponseNotFound as AddItemsToFavorites201ResponseNotFound,
    )
    from schemas.trakt.models.add_items_to_favorites_request import (
        AddItemsToFavoritesRequest as AddItemsToFavoritesRequest,
    )
    from schemas.trakt.models.add_items_to_favorites_request_shows_inner import (
        AddItemsToFavoritesRequestShowsInner as AddItemsToFavoritesRequestShowsInner,
    )
    from schemas.trakt.models.add_items_to_personal_list201_response import (
        AddItemsToPersonalList201Response as AddItemsToPersonalList201Response,
    )
    from schemas.trakt.models.add_items_to_personal_list201_response_added import (
        AddItemsToPersonalList201ResponseAdded as AddItemsToPersonalList201ResponseAdded,
    )
    from schemas.trakt.models.add_items_to_personal_list201_response_not_found import (
        AddItemsToPersonalList201ResponseNotFound as AddItemsToPersonalList201ResponseNotFound,
    )
    from schemas.trakt.models.add_items_to_personal_list_request import (
        AddItemsToPersonalListRequest as AddItemsToPersonalListRequest,
    )
    from schemas.trakt.models.add_items_to_personal_list_request_movies_inner import (
        AddItemsToPersonalListRequestMoviesInner as AddItemsToPersonalListRequestMoviesInner,
    )
    from schemas.trakt.models.add_items_to_personal_list_request_movies_inner_ids import (
        AddItemsToPersonalListRequestMoviesInnerIds as AddItemsToPersonalListRequestMoviesInnerIds,
    )
    from schemas.trakt.models.add_items_to_personal_list_request_shows_inner import (
        AddItemsToPersonalListRequestShowsInner as AddItemsToPersonalListRequestShowsInner,
    )
    from schemas.trakt.models.add_items_to_watched_history201_response import (
        AddItemsToWatchedHistory201Response as AddItemsToWatchedHistory201Response,
    )
    from schemas.trakt.models.add_items_to_watched_history_request import (
        AddItemsToWatchedHistoryRequest as AddItemsToWatchedHistoryRequest,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_episodes_inner import (
        AddItemsToWatchedHistoryRequestEpisodesInner as AddItemsToWatchedHistoryRequestEpisodesInner,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_movies_inner import (
        AddItemsToWatchedHistoryRequestMoviesInner as AddItemsToWatchedHistoryRequestMoviesInner,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_seasons_inner import (
        AddItemsToWatchedHistoryRequestSeasonsInner as AddItemsToWatchedHistoryRequestSeasonsInner,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_shows_inner import (
        AddItemsToWatchedHistoryRequestShowsInner as AddItemsToWatchedHistoryRequestShowsInner,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_shows_inner_seasons_inner import (
        AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner as AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner,
    )
    from schemas.trakt.models.add_items_to_watched_history_request_shows_inner_seasons_inner_episodes_inner import (
        AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner as AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.add_items_to_watchlist201_response import (
        AddItemsToWatchlist201Response as AddItemsToWatchlist201Response,
    )
    from schemas.trakt.models.add_items_to_watchlist201_response_list import (
        AddItemsToWatchlist201ResponseList as AddItemsToWatchlist201ResponseList,
    )
    from schemas.trakt.models.add_items_to_watchlist_request import (
        AddItemsToWatchlistRequest as AddItemsToWatchlistRequest,
    )
    from schemas.trakt.models.add_items_to_watchlist_request_movies_inner import (
        AddItemsToWatchlistRequestMoviesInner as AddItemsToWatchlistRequestMoviesInner,
    )
    from schemas.trakt.models.add_items_to_watchlist_request_shows_inner import (
        AddItemsToWatchlistRequestShowsInner as AddItemsToWatchlistRequestShowsInner,
    )
    from schemas.trakt.models.add_new_ratings201_response import (
        AddNewRatings201Response as AddNewRatings201Response,
    )
    from schemas.trakt.models.add_new_ratings201_response_added import (
        AddNewRatings201ResponseAdded as AddNewRatings201ResponseAdded,
    )
    from schemas.trakt.models.add_new_ratings201_response_not_found import (
        AddNewRatings201ResponseNotFound as AddNewRatings201ResponseNotFound,
    )
    from schemas.trakt.models.add_new_ratings201_response_not_found_movies_inner import (
        AddNewRatings201ResponseNotFoundMoviesInner as AddNewRatings201ResponseNotFoundMoviesInner,
    )
    from schemas.trakt.models.add_new_ratings_request import (
        AddNewRatingsRequest as AddNewRatingsRequest,
    )
    from schemas.trakt.models.add_new_ratings_request_episodes_inner import (
        AddNewRatingsRequestEpisodesInner as AddNewRatingsRequestEpisodesInner,
    )
    from schemas.trakt.models.add_new_ratings_request_movies_inner import (
        AddNewRatingsRequestMoviesInner as AddNewRatingsRequestMoviesInner,
    )
    from schemas.trakt.models.add_new_ratings_request_seasons_inner import (
        AddNewRatingsRequestSeasonsInner as AddNewRatingsRequestSeasonsInner,
    )
    from schemas.trakt.models.add_new_ratings_request_shows_inner import (
        AddNewRatingsRequestShowsInner as AddNewRatingsRequestShowsInner,
    )
    from schemas.trakt.models.add_new_ratings_request_shows_inner_seasons_inner import (
        AddNewRatingsRequestShowsInnerSeasonsInner as AddNewRatingsRequestShowsInnerSeasonsInner,
    )
    from schemas.trakt.models.add_new_ratings_request_shows_inner_seasons_inner_episodes_inner import (
        AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner as AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.add_notes201_response import (
        AddNotes201Response as AddNotes201Response,
    )
    from schemas.trakt.models.add_notes_request import (
        AddNotesRequest as AddNotesRequest,
    )
    from schemas.trakt.models.approve_follow_request200_response import (
        ApproveFollowRequest200Response as ApproveFollowRequest200Response,
    )
    from schemas.trakt.models.check_into_an_item201_response import (
        CheckIntoAnItem201Response as CheckIntoAnItem201Response,
    )
    from schemas.trakt.models.check_into_an_item201_response_episode import (
        CheckIntoAnItem201ResponseEpisode as CheckIntoAnItem201ResponseEpisode,
    )
    from schemas.trakt.models.check_into_an_item201_response_episode_ids import (
        CheckIntoAnItem201ResponseEpisodeIds as CheckIntoAnItem201ResponseEpisodeIds,
    )
    from schemas.trakt.models.check_into_an_item409_response import (
        CheckIntoAnItem409Response as CheckIntoAnItem409Response,
    )
    from schemas.trakt.models.check_into_an_item_request import (
        CheckIntoAnItemRequest as CheckIntoAnItemRequest,
    )
    from schemas.trakt.models.check_into_an_item_request_sharing import (
        CheckIntoAnItemRequestSharing as CheckIntoAnItemRequestSharing,
    )
    from schemas.trakt.models.create_personal_list201_response import (
        CreatePersonalList201Response as CreatePersonalList201Response,
    )
    from schemas.trakt.models.create_personal_list_request import (
        CreatePersonalListRequest as CreatePersonalListRequest,
    )
    from schemas.trakt.models.exchange_refresh_token_for_access_token200_response import (
        ExchangeRefreshTokenForAccessToken200Response as ExchangeRefreshTokenForAccessToken200Response,
    )
    from schemas.trakt.models.exchange_refresh_token_for_access_token401_response import (
        ExchangeRefreshTokenForAccessToken401Response as ExchangeRefreshTokenForAccessToken401Response,
    )
    from schemas.trakt.models.exchange_refresh_token_for_access_token_request import (
        ExchangeRefreshTokenForAccessTokenRequest as ExchangeRefreshTokenForAccessTokenRequest,
    )
    from schemas.trakt.models.follow_this_user201_response import (
        FollowThisUser201Response as FollowThisUser201Response,
    )
    from schemas.trakt.models.generate_new_device_codes200_response import (
        GenerateNewDeviceCodes200Response as GenerateNewDeviceCodes200Response,
    )
    from schemas.trakt.models.generate_new_device_codes_request import (
        GenerateNewDeviceCodesRequest as GenerateNewDeviceCodesRequest,
    )
    from schemas.trakt.models.get_a_comment_or_reply200_response import (
        GetACommentOrReply200Response as GetACommentOrReply200Response,
    )
    from schemas.trakt.models.get_a_comment_or_reply200_response_user_stats import (
        GetACommentOrReply200ResponseUserStats as GetACommentOrReply200ResponseUserStats,
    )
    from schemas.trakt.models.get_a_movie200_response import (
        GetAMovie200Response as GetAMovie200Response,
    )
    from schemas.trakt.models.get_a_note200_response import (
        GetANote200Response as GetANote200Response,
    )
    from schemas.trakt.models.get_a_single_episode_for_a_show200_response import (
        GetASingleEpisodeForAShow200Response as GetASingleEpisodeForAShow200Response,
    )
    from schemas.trakt.models.get_a_single_person200_response import (
        GetASinglePerson200Response as GetASinglePerson200Response,
    )
    from schemas.trakt.models.get_a_single_person200_response_social_ids import (
        GetASinglePerson200ResponseSocialIds as GetASinglePerson200ResponseSocialIds,
    )
    from schemas.trakt.models.get_a_single_show200_response import (
        GetASingleShow200Response as GetASingleShow200Response,
    )
    from schemas.trakt.models.get_a_single_show200_response_airs import (
        GetASingleShow200ResponseAirs as GetASingleShow200ResponseAirs,
    )
    from schemas.trakt.models.get_a_user_s_personal_lists200_response_inner import (
        GetAUserSPersonalLists200ResponseInner as GetAUserSPersonalLists200ResponseInner,
    )
    from schemas.trakt.models.get_all_episodes_for_a_single_season200_response_inner import (
        GetAllEpisodesForASingleSeason200ResponseInner as GetAllEpisodesForASingleSeason200ResponseInner,
    )
    from schemas.trakt.models.get_all_list_comments200_response_inner import (
        GetAllListComments200ResponseInner as GetAllListComments200ResponseInner,
    )
    from schemas.trakt.models.get_all_lists_a_user_can_collaborate_on200_response_inner import (
        GetAllListsAUserCanCollaborateOn200ResponseInner as GetAllListsAUserCanCollaborateOn200ResponseInner,
    )
    from schemas.trakt.models.get_all_movie_aliases200_response_inner import (
        GetAllMovieAliases200ResponseInner as GetAllMovieAliases200ResponseInner,
    )
    from schemas.trakt.models.get_all_movie_releases200_response_inner import (
        GetAllMovieReleases200ResponseInner as GetAllMovieReleases200ResponseInner,
    )
    from schemas.trakt.models.get_all_movie_translations200_response_inner import (
        GetAllMovieTranslations200ResponseInner as GetAllMovieTranslations200ResponseInner,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response import (
        GetAllPeopleForAMovie200Response as GetAllPeopleForAMovie200Response,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response_cast_inner import (
        GetAllPeopleForAMovie200ResponseCastInner as GetAllPeopleForAMovie200ResponseCastInner,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response_crew import (
        GetAllPeopleForAMovie200ResponseCrew as GetAllPeopleForAMovie200ResponseCrew,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_art_inner import (
        GetAllPeopleForAMovie200ResponseCrewArtInner as GetAllPeopleForAMovie200ResponseCrewArtInner,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_directing_inner import (
        GetAllPeopleForAMovie200ResponseCrewDirectingInner as GetAllPeopleForAMovie200ResponseCrewDirectingInner,
    )
    from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_production_inner import (
        GetAllPeopleForAMovie200ResponseCrewProductionInner as GetAllPeopleForAMovie200ResponseCrewProductionInner,
    )
    from schemas.trakt.models.get_all_people_for_a_season200_response import (
        GetAllPeopleForASeason200Response as GetAllPeopleForASeason200Response,
    )
    from schemas.trakt.models.get_all_people_for_a_season200_response_crew import (
        GetAllPeopleForASeason200ResponseCrew as GetAllPeopleForASeason200ResponseCrew,
    )
    from schemas.trakt.models.get_all_people_for_a_show200_response import (
        GetAllPeopleForAShow200Response as GetAllPeopleForAShow200Response,
    )
    from schemas.trakt.models.get_all_people_for_a_show200_response_cast_inner import (
        GetAllPeopleForAShow200ResponseCastInner as GetAllPeopleForAShow200ResponseCastInner,
    )
    from schemas.trakt.models.get_all_people_for_a_show200_response_crew import (
        GetAllPeopleForAShow200ResponseCrew as GetAllPeopleForAShow200ResponseCrew,
    )
    from schemas.trakt.models.get_all_people_for_a_show200_response_crew_art_inner import (
        GetAllPeopleForAShow200ResponseCrewArtInner as GetAllPeopleForAShow200ResponseCrewArtInner,
    )
    from schemas.trakt.models.get_all_people_for_a_show200_response_crew_visual_effects_inner import (
        GetAllPeopleForAShow200ResponseCrewVisualEffectsInner as GetAllPeopleForAShow200ResponseCrewVisualEffectsInner,
    )
    from schemas.trakt.models.get_all_people_for_an_episode200_response import (
        GetAllPeopleForAnEpisode200Response as GetAllPeopleForAnEpisode200Response,
    )
    from schemas.trakt.models.get_all_people_for_an_episode200_response_crew import (
        GetAllPeopleForAnEpisode200ResponseCrew as GetAllPeopleForAnEpisode200ResponseCrew,
    )
    from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner import (
        GetAllPeopleForAnEpisode200ResponseGuestStarsInner as GetAllPeopleForAnEpisode200ResponseGuestStarsInner,
    )
    from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner_person import (
        GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson as GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson,
    )
    from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner_person_ids import (
        GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds as GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds,
    )
    from schemas.trakt.models.get_all_season_translations200_response_inner import (
        GetAllSeasonTranslations200ResponseInner as GetAllSeasonTranslations200ResponseInner,
    )
    from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner import (
        GetAllSeasonsForAShow200ResponseInner as GetAllSeasonsForAShow200ResponseInner,
    )
    from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_episodes_inner import (
        GetAllSeasonsForAShow200ResponseInnerEpisodesInner as GetAllSeasonsForAShow200ResponseInnerEpisodesInner,
    )
    from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_episodes_inner_ids import (
        GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds as GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds,
    )
    from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_ids import (
        GetAllSeasonsForAShow200ResponseInnerIds as GetAllSeasonsForAShow200ResponseInnerIds,
    )
    from schemas.trakt.models.get_all_show_certifications200_response_inner import (
        GetAllShowCertifications200ResponseInner as GetAllShowCertifications200ResponseInner,
    )
    from schemas.trakt.models.get_all_show_translations200_response_inner import (
        GetAllShowTranslations200ResponseInner as GetAllShowTranslations200ResponseInner,
    )
    from schemas.trakt.models.get_all_users_who_liked_a_comment200_response_inner import (
        GetAllUsersWhoLikedAComment200ResponseInner as GetAllUsersWhoLikedAComment200ResponseInner,
    )
    from schemas.trakt.models.get_all_videos200_response_inner import (
        GetAllVideos200ResponseInner as GetAllVideos200ResponseInner,
    )
    from schemas.trakt.models.get_certifications200_response import (
        GetCertifications200Response as GetCertifications200Response,
    )
    from schemas.trakt.models.get_certifications200_response_us_inner import (
        GetCertifications200ResponseUsInner as GetCertifications200ResponseUsInner,
    )
    from schemas.trakt.models.get_collection200_response_inner import (
        GetCollection200ResponseInner as GetCollection200ResponseInner,
    )
    from schemas.trakt.models.get_collection200_response_inner_seasons_inner import (
        GetCollection200ResponseInnerSeasonsInner as GetCollection200ResponseInnerSeasonsInner,
    )
    from schemas.trakt.models.get_collection200_response_inner_seasons_inner_episodes_inner import (
        GetCollection200ResponseInnerSeasonsInnerEpisodesInner as GetCollection200ResponseInnerSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.get_collection200_response_inner_seasons_inner_episodes_inner_metadata import (
        GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata as GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata,
    )
    from schemas.trakt.models.get_countries200_response_inner import (
        GetCountries200ResponseInner as GetCountries200ResponseInner,
    )
    from schemas.trakt.models.get_favorites200_response_inner import (
        GetFavorites200ResponseInner as GetFavorites200ResponseInner,
    )
    from schemas.trakt.models.get_followers200_response_inner import (
        GetFollowers200ResponseInner as GetFollowers200ResponseInner,
    )
    from schemas.trakt.models.get_friends200_response_inner import (
        GetFriends200ResponseInner as GetFriends200ResponseInner,
    )
    from schemas.trakt.models.get_genres200_response_inner import (
        GetGenres200ResponseInner as GetGenres200ResponseInner,
    )
    from schemas.trakt.models.get_genres200_response_inner_subgenres_inner import (
        GetGenres200ResponseInnerSubgenresInner as GetGenres200ResponseInnerSubgenresInner,
    )
    from schemas.trakt.models.get_hidden_items200_response_inner import (
        GetHiddenItems200ResponseInner as GetHiddenItems200ResponseInner,
    )
    from schemas.trakt.models.get_id_lookup_results200_response_inner import (
        GetIDLookupResults200ResponseInner as GetIDLookupResults200ResponseInner,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner import (
        GetItemsOnAList200ResponseInner as GetItemsOnAList200ResponseInner,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner_episode import (
        GetItemsOnAList200ResponseInnerEpisode as GetItemsOnAList200ResponseInnerEpisode,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner_episode_ids import (
        GetItemsOnAList200ResponseInnerEpisodeIds as GetItemsOnAList200ResponseInnerEpisodeIds,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner_person import (
        GetItemsOnAList200ResponseInnerPerson as GetItemsOnAList200ResponseInnerPerson,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner_season import (
        GetItemsOnAList200ResponseInnerSeason as GetItemsOnAList200ResponseInnerSeason,
    )
    from schemas.trakt.models.get_items_on_a_list200_response_inner_season_ids import (
        GetItemsOnAList200ResponseInnerSeasonIds as GetItemsOnAList200ResponseInnerSeasonIds,
    )
    from schemas.trakt.models.get_items_on_a_personal_list200_response_inner import (
        GetItemsOnAPersonalList200ResponseInner as GetItemsOnAPersonalList200ResponseInner,
    )
    from schemas.trakt.models.get_last_activity200_response import (
        GetLastActivity200Response as GetLastActivity200Response,
    )
    from schemas.trakt.models.get_last_activity200_response_account import (
        GetLastActivity200ResponseAccount as GetLastActivity200ResponseAccount,
    )
    from schemas.trakt.models.get_last_activity200_response_comments import (
        GetLastActivity200ResponseComments as GetLastActivity200ResponseComments,
    )
    from schemas.trakt.models.get_last_activity200_response_episodes import (
        GetLastActivity200ResponseEpisodes as GetLastActivity200ResponseEpisodes,
    )
    from schemas.trakt.models.get_last_activity200_response_lists import (
        GetLastActivity200ResponseLists as GetLastActivity200ResponseLists,
    )
    from schemas.trakt.models.get_last_activity200_response_movies import (
        GetLastActivity200ResponseMovies as GetLastActivity200ResponseMovies,
    )
    from schemas.trakt.models.get_last_activity200_response_seasons import (
        GetLastActivity200ResponseSeasons as GetLastActivity200ResponseSeasons,
    )
    from schemas.trakt.models.get_last_activity200_response_shows import (
        GetLastActivity200ResponseShows as GetLastActivity200ResponseShows,
    )
    from schemas.trakt.models.get_last_activity200_response_watchlist import (
        GetLastActivity200ResponseWatchlist as GetLastActivity200ResponseWatchlist,
    )
    from schemas.trakt.models.get_last_episode200_response import (
        GetLastEpisode200Response as GetLastEpisode200Response,
    )
    from schemas.trakt.models.get_likes200_response_inner import (
        GetLikes200ResponseInner as GetLikes200ResponseInner,
    )
    from schemas.trakt.models.get_likes200_response_inner_list import (
        GetLikes200ResponseInnerList as GetLikes200ResponseInnerList,
    )
    from schemas.trakt.models.get_list200_response import (
        GetList200Response as GetList200Response,
    )
    from schemas.trakt.models.get_movie_credits200_response import (
        GetMovieCredits200Response as GetMovieCredits200Response,
    )
    from schemas.trakt.models.get_movie_credits200_response_cast_inner import (
        GetMovieCredits200ResponseCastInner as GetMovieCredits200ResponseCastInner,
    )
    from schemas.trakt.models.get_movie_credits200_response_crew import (
        GetMovieCredits200ResponseCrew as GetMovieCredits200ResponseCrew,
    )
    from schemas.trakt.models.get_movie_credits200_response_crew_directing_inner import (
        GetMovieCredits200ResponseCrewDirectingInner as GetMovieCredits200ResponseCrewDirectingInner,
    )
    from schemas.trakt.models.get_movie_ratings200_response import (
        GetMovieRatings200Response as GetMovieRatings200Response,
    )
    from schemas.trakt.models.get_movie_ratings200_response_distribution import (
        GetMovieRatings200ResponseDistribution as GetMovieRatings200ResponseDistribution,
    )
    from schemas.trakt.models.get_movie_recommendations200_response_inner import (
        GetMovieRecommendations200ResponseInner as GetMovieRecommendations200ResponseInner,
    )
    from schemas.trakt.models.get_movie_recommendations200_response_inner_favorited_by_inner import (
        GetMovieRecommendations200ResponseInnerFavoritedByInner as GetMovieRecommendations200ResponseInnerFavoritedByInner,
    )
    from schemas.trakt.models.get_movie_stats200_response import (
        GetMovieStats200Response as GetMovieStats200Response,
    )
    from schemas.trakt.models.get_movie_studios200_response_inner import (
        GetMovieStudios200ResponseInner as GetMovieStudios200ResponseInner,
    )
    from schemas.trakt.models.get_movie_studios200_response_inner_ids import (
        GetMovieStudios200ResponseInnerIds as GetMovieStudios200ResponseInnerIds,
    )
    from schemas.trakt.models.get_movies200_response_inner import (
        GetMovies200ResponseInner as GetMovies200ResponseInner,
    )
    from schemas.trakt.models.get_movies200_response_inner_movie import (
        GetMovies200ResponseInnerMovie as GetMovies200ResponseInnerMovie,
    )
    from schemas.trakt.models.get_movies200_response_inner_movie_ids import (
        GetMovies200ResponseInnerMovieIds as GetMovies200ResponseInnerMovieIds,
    )
    from schemas.trakt.models.get_networks200_response_inner import (
        GetNetworks200ResponseInner as GetNetworks200ResponseInner,
    )
    from schemas.trakt.models.get_networks200_response_inner_ids import (
        GetNetworks200ResponseInnerIds as GetNetworks200ResponseInnerIds,
    )
    from schemas.trakt.models.get_new_shows200_response_inner import (
        GetNewShows200ResponseInner as GetNewShows200ResponseInner,
    )
    from schemas.trakt.models.get_new_shows200_response_inner_episode import (
        GetNewShows200ResponseInnerEpisode as GetNewShows200ResponseInnerEpisode,
    )
    from schemas.trakt.models.get_new_shows200_response_inner_episode_ids import (
        GetNewShows200ResponseInnerEpisodeIds as GetNewShows200ResponseInnerEpisodeIds,
    )
    from schemas.trakt.models.get_next_episode200_response import (
        GetNextEpisode200Response as GetNextEpisode200Response,
    )
    from schemas.trakt.models.get_notes200_response_inner import (
        GetNotes200ResponseInner as GetNotes200ResponseInner,
    )
    from schemas.trakt.models.get_notes200_response_inner_attached_to import (
        GetNotes200ResponseInnerAttachedTo as GetNotes200ResponseInnerAttachedTo,
    )
    from schemas.trakt.models.get_notes200_response_inner_note import (
        GetNotes200ResponseInnerNote as GetNotes200ResponseInnerNote,
    )
    from schemas.trakt.models.get_notes200_response_inner_note_user import (
        GetNotes200ResponseInnerNoteUser as GetNotes200ResponseInnerNoteUser,
    )
    from schemas.trakt.models.get_notes200_response_inner_note_user_ids import (
        GetNotes200ResponseInnerNoteUserIds as GetNotes200ResponseInnerNoteUserIds,
    )
    from schemas.trakt.models.get_pending_following_requests200_response_inner import (
        GetPendingFollowingRequests200ResponseInner as GetPendingFollowingRequests200ResponseInner,
    )
    from schemas.trakt.models.get_playback_progress200_response_inner import (
        GetPlaybackProgress200ResponseInner as GetPlaybackProgress200ResponseInner,
    )
    from schemas.trakt.models.get_popular_movies200_response_inner import (
        GetPopularMovies200ResponseInner as GetPopularMovies200ResponseInner,
    )
    from schemas.trakt.models.get_popular_shows200_response_inner import (
        GetPopularShows200ResponseInner as GetPopularShows200ResponseInner,
    )
    from schemas.trakt.models.get_ratings200_response_inner import (
        GetRatings200ResponseInner as GetRatings200ResponseInner,
    )
    from schemas.trakt.models.get_recently_updated_movies200_response_inner import (
        GetRecentlyUpdatedMovies200ResponseInner as GetRecentlyUpdatedMovies200ResponseInner,
    )
    from schemas.trakt.models.get_recently_updated_people200_response_inner import (
        GetRecentlyUpdatedPeople200ResponseInner as GetRecentlyUpdatedPeople200ResponseInner,
    )
    from schemas.trakt.models.get_recently_updated_shows200_response_inner import (
        GetRecentlyUpdatedShows200ResponseInner as GetRecentlyUpdatedShows200ResponseInner,
    )
    from schemas.trakt.models.get_replies_for_a_comment200_response_inner import (
        GetRepliesForAComment200ResponseInner as GetRepliesForAComment200ResponseInner,
    )
    from schemas.trakt.models.get_saved_filters200_response_inner import (
        GetSavedFilters200ResponseInner as GetSavedFilters200ResponseInner,
    )
    from schemas.trakt.models.get_season_premieres200_response_inner import (
        GetSeasonPremieres200ResponseInner as GetSeasonPremieres200ResponseInner,
    )
    from schemas.trakt.models.get_season_ratings200_response import (
        GetSeasonRatings200Response as GetSeasonRatings200Response,
    )
    from schemas.trakt.models.get_season_stats200_response import (
        GetSeasonStats200Response as GetSeasonStats200Response,
    )
    from schemas.trakt.models.get_show_collection_progress200_response import (
        GetShowCollectionProgress200Response as GetShowCollectionProgress200Response,
    )
    from schemas.trakt.models.get_show_collection_progress200_response_seasons_inner import (
        GetShowCollectionProgress200ResponseSeasonsInner as GetShowCollectionProgress200ResponseSeasonsInner,
    )
    from schemas.trakt.models.get_show_collection_progress200_response_seasons_inner_episodes_inner import (
        GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner as GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.get_show_credits200_response import (
        GetShowCredits200Response as GetShowCredits200Response,
    )
    from schemas.trakt.models.get_show_credits200_response_cast_inner import (
        GetShowCredits200ResponseCastInner as GetShowCredits200ResponseCastInner,
    )
    from schemas.trakt.models.get_show_credits200_response_crew import (
        GetShowCredits200ResponseCrew as GetShowCredits200ResponseCrew,
    )
    from schemas.trakt.models.get_show_credits200_response_crew_production_inner import (
        GetShowCredits200ResponseCrewProductionInner as GetShowCredits200ResponseCrewProductionInner,
    )
    from schemas.trakt.models.get_show_ratings200_response import (
        GetShowRatings200Response as GetShowRatings200Response,
    )
    from schemas.trakt.models.get_show_recommendations200_response_inner import (
        GetShowRecommendations200ResponseInner as GetShowRecommendations200ResponseInner,
    )
    from schemas.trakt.models.get_show_stats200_response import (
        GetShowStats200Response as GetShowStats200Response,
    )
    from schemas.trakt.models.get_show_watched_progress200_response import (
        GetShowWatchedProgress200Response as GetShowWatchedProgress200Response,
    )
    from schemas.trakt.models.get_show_watched_progress200_response_seasons_inner import (
        GetShowWatchedProgress200ResponseSeasonsInner as GetShowWatchedProgress200ResponseSeasonsInner,
    )
    from schemas.trakt.models.get_show_watched_progress200_response_seasons_inner_episodes_inner import (
        GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner as GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.get_shows200_response_inner import (
        GetShows200ResponseInner as GetShows200ResponseInner,
    )
    from schemas.trakt.models.get_shows200_response_inner_episode import (
        GetShows200ResponseInnerEpisode as GetShows200ResponseInnerEpisode,
    )
    from schemas.trakt.models.get_shows200_response_inner_episode_ids import (
        GetShows200ResponseInnerEpisodeIds as GetShows200ResponseInnerEpisodeIds,
    )
    from schemas.trakt.models.get_shows200_response_inner_show import (
        GetShows200ResponseInnerShow as GetShows200ResponseInnerShow,
    )
    from schemas.trakt.models.get_shows200_response_inner_show_ids import (
        GetShows200ResponseInnerShowIds as GetShows200ResponseInnerShowIds,
    )
    from schemas.trakt.models.get_single_seasons_for_a_show200_response import (
        GetSingleSeasonsForAShow200Response as GetSingleSeasonsForAShow200Response,
    )
    from schemas.trakt.models.get_stats200_response import (
        GetStats200Response as GetStats200Response,
    )
    from schemas.trakt.models.get_stats200_response_movies import (
        GetStats200ResponseMovies as GetStats200ResponseMovies,
    )
    from schemas.trakt.models.get_stats200_response_network import (
        GetStats200ResponseNetwork as GetStats200ResponseNetwork,
    )
    from schemas.trakt.models.get_stats200_response_ratings import (
        GetStats200ResponseRatings as GetStats200ResponseRatings,
    )
    from schemas.trakt.models.get_stats200_response_seasons import (
        GetStats200ResponseSeasons as GetStats200ResponseSeasons,
    )
    from schemas.trakt.models.get_stats200_response_shows import (
        GetStats200ResponseShows as GetStats200ResponseShows,
    )
    from schemas.trakt.models.get_text_query_results200_response_inner import (
        GetTextQueryResults200ResponseInner as GetTextQueryResults200ResponseInner,
    )
    from schemas.trakt.models.get_the_attached_item200_response import (
        GetTheAttachedItem200Response as GetTheAttachedItem200Response,
    )
    from schemas.trakt.models.get_the_attached_item200_response_attached_to import (
        GetTheAttachedItem200ResponseAttachedTo as GetTheAttachedItem200ResponseAttachedTo,
    )
    from schemas.trakt.models.get_the_attached_media_item200_response import (
        GetTheAttachedMediaItem200Response as GetTheAttachedMediaItem200Response,
    )
    from schemas.trakt.models.get_the_most_anticipated_movies200_response_inner import (
        GetTheMostAnticipatedMovies200ResponseInner as GetTheMostAnticipatedMovies200ResponseInner,
    )
    from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner import (
        GetTheMostAnticipatedShows200ResponseInner as GetTheMostAnticipatedShows200ResponseInner,
    )
    from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner_show import (
        GetTheMostAnticipatedShows200ResponseInnerShow as GetTheMostAnticipatedShows200ResponseInnerShow,
    )
    from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner_show_ids import (
        GetTheMostAnticipatedShows200ResponseInnerShowIds as GetTheMostAnticipatedShows200ResponseInnerShowIds,
    )
    from schemas.trakt.models.get_the_most_favorited_movies200_response_inner import (
        GetTheMostFavoritedMovies200ResponseInner as GetTheMostFavoritedMovies200ResponseInner,
    )
    from schemas.trakt.models.get_the_most_favorited_shows200_response_inner import (
        GetTheMostFavoritedShows200ResponseInner as GetTheMostFavoritedShows200ResponseInner,
    )
    from schemas.trakt.models.get_the_most_played_movies200_response_inner import (
        GetTheMostPlayedMovies200ResponseInner as GetTheMostPlayedMovies200ResponseInner,
    )
    from schemas.trakt.models.get_the_most_played_shows200_response_inner import (
        GetTheMostPlayedShows200ResponseInner as GetTheMostPlayedShows200ResponseInner,
    )
    from schemas.trakt.models.get_the_weekend_box_office200_response_inner import (
        GetTheWeekendBoxOffice200ResponseInner as GetTheWeekendBoxOffice200ResponseInner,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner import (
        GetTrendingComments200ResponseInner as GetTrendingComments200ResponseInner,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_comment import (
        GetTrendingComments200ResponseInnerComment as GetTrendingComments200ResponseInnerComment,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_comment_user_stats import (
        GetTrendingComments200ResponseInnerCommentUserStats as GetTrendingComments200ResponseInnerCommentUserStats,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_list import (
        GetTrendingComments200ResponseInnerList as GetTrendingComments200ResponseInnerList,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_list_ids import (
        GetTrendingComments200ResponseInnerListIds as GetTrendingComments200ResponseInnerListIds,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_season import (
        GetTrendingComments200ResponseInnerSeason as GetTrendingComments200ResponseInnerSeason,
    )
    from schemas.trakt.models.get_trending_comments200_response_inner_season_ids import (
        GetTrendingComments200ResponseInnerSeasonIds as GetTrendingComments200ResponseInnerSeasonIds,
    )
    from schemas.trakt.models.get_trending_lists200_response_inner import (
        GetTrendingLists200ResponseInner as GetTrendingLists200ResponseInner,
    )
    from schemas.trakt.models.get_trending_lists200_response_inner_list import (
        GetTrendingLists200ResponseInnerList as GetTrendingLists200ResponseInnerList,
    )
    from schemas.trakt.models.get_trending_movies200_response_inner import (
        GetTrendingMovies200ResponseInner as GetTrendingMovies200ResponseInner,
    )
    from schemas.trakt.models.get_trending_shows200_response_inner import (
        GetTrendingShows200ResponseInner as GetTrendingShows200ResponseInner,
    )
    from schemas.trakt.models.get_user_profile200_response import (
        GetUserProfile200Response as GetUserProfile200Response,
    )
    from schemas.trakt.models.get_users_watching_right_now200_response_inner import (
        GetUsersWatchingRightNow200ResponseInner as GetUsersWatchingRightNow200ResponseInner,
    )
    from schemas.trakt.models.get_watched200_response_inner import (
        GetWatched200ResponseInner as GetWatched200ResponseInner,
    )
    from schemas.trakt.models.get_watched_history200_response_inner import (
        GetWatchedHistory200ResponseInner as GetWatchedHistory200ResponseInner,
    )
    from schemas.trakt.models.get_watching200_response import (
        GetWatching200Response as GetWatching200Response,
    )
    from schemas.trakt.models.get_watchlist200_response_inner import (
        GetWatchlist200ResponseInner as GetWatchlist200ResponseInner,
    )
    from schemas.trakt.models.poll_for_the_access_token_request import (
        PollForTheAccessTokenRequest as PollForTheAccessTokenRequest,
    )
    from schemas.trakt.models.post_a_comment201_response import (
        PostAComment201Response as PostAComment201Response,
    )
    from schemas.trakt.models.post_a_comment201_response_user import (
        PostAComment201ResponseUser as PostAComment201ResponseUser,
    )
    from schemas.trakt.models.post_a_comment201_response_user_ids import (
        PostAComment201ResponseUserIds as PostAComment201ResponseUserIds,
    )
    from schemas.trakt.models.post_a_comment201_response_user_stats import (
        PostAComment201ResponseUserStats as PostAComment201ResponseUserStats,
    )
    from schemas.trakt.models.post_a_comment_request import (
        PostACommentRequest as PostACommentRequest,
    )
    from schemas.trakt.models.post_a_comment_request_sharing import (
        PostACommentRequestSharing as PostACommentRequestSharing,
    )
    from schemas.trakt.models.post_a_reply_for_a_comment201_response import (
        PostAReplyForAComment201Response as PostAReplyForAComment201Response,
    )
    from schemas.trakt.models.post_a_reply_for_a_comment_request import (
        PostAReplyForACommentRequest as PostAReplyForACommentRequest,
    )
    from schemas.trakt.models.remove_hidden_items200_response import (
        RemoveHiddenItems200Response as RemoveHiddenItems200Response,
    )
    from schemas.trakt.models.remove_hidden_items_request import (
        RemoveHiddenItemsRequest as RemoveHiddenItemsRequest,
    )
    from schemas.trakt.models.remove_hidden_items_request_shows_inner import (
        RemoveHiddenItemsRequestShowsInner as RemoveHiddenItemsRequestShowsInner,
    )
    from schemas.trakt.models.remove_items_from_collection200_response import (
        RemoveItemsFromCollection200Response as RemoveItemsFromCollection200Response,
    )
    from schemas.trakt.models.remove_items_from_collection_request import (
        RemoveItemsFromCollectionRequest as RemoveItemsFromCollectionRequest,
    )
    from schemas.trakt.models.remove_items_from_collection_request_movies_inner import (
        RemoveItemsFromCollectionRequestMoviesInner as RemoveItemsFromCollectionRequestMoviesInner,
    )
    from schemas.trakt.models.remove_items_from_collection_request_shows_inner import (
        RemoveItemsFromCollectionRequestShowsInner as RemoveItemsFromCollectionRequestShowsInner,
    )
    from schemas.trakt.models.remove_items_from_collection_request_shows_inner_seasons_inner import (
        RemoveItemsFromCollectionRequestShowsInnerSeasonsInner as RemoveItemsFromCollectionRequestShowsInnerSeasonsInner,
    )
    from schemas.trakt.models.remove_items_from_collection_request_shows_inner_seasons_inner_episodes_inner import (
        RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner as RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner,
    )
    from schemas.trakt.models.remove_items_from_favorites200_response import (
        RemoveItemsFromFavorites200Response as RemoveItemsFromFavorites200Response,
    )
    from schemas.trakt.models.remove_items_from_favorites_request import (
        RemoveItemsFromFavoritesRequest as RemoveItemsFromFavoritesRequest,
    )
    from schemas.trakt.models.remove_items_from_history200_response import (
        RemoveItemsFromHistory200Response as RemoveItemsFromHistory200Response,
    )
    from schemas.trakt.models.remove_items_from_history200_response_not_found import (
        RemoveItemsFromHistory200ResponseNotFound as RemoveItemsFromHistory200ResponseNotFound,
    )
    from schemas.trakt.models.remove_items_from_history_request import (
        RemoveItemsFromHistoryRequest as RemoveItemsFromHistoryRequest,
    )
    from schemas.trakt.models.remove_items_from_personal_list200_response import (
        RemoveItemsFromPersonalList200Response as RemoveItemsFromPersonalList200Response,
    )
    from schemas.trakt.models.remove_items_from_personal_list_request import (
        RemoveItemsFromPersonalListRequest as RemoveItemsFromPersonalListRequest,
    )
    from schemas.trakt.models.remove_items_from_personal_list_request_movies_inner import (
        RemoveItemsFromPersonalListRequestMoviesInner as RemoveItemsFromPersonalListRequestMoviesInner,
    )
    from schemas.trakt.models.remove_items_from_personal_list_request_shows_inner import (
        RemoveItemsFromPersonalListRequestShowsInner as RemoveItemsFromPersonalListRequestShowsInner,
    )
    from schemas.trakt.models.remove_items_from_watchlist200_response import (
        RemoveItemsFromWatchlist200Response as RemoveItemsFromWatchlist200Response,
    )
    from schemas.trakt.models.remove_ratings200_response import (
        RemoveRatings200Response as RemoveRatings200Response,
    )
    from schemas.trakt.models.reorder_a_user_s_lists200_response import (
        ReorderAUserSLists200Response as ReorderAUserSLists200Response,
    )
    from schemas.trakt.models.reorder_a_user_s_lists_request import (
        ReorderAUserSListsRequest as ReorderAUserSListsRequest,
    )
    from schemas.trakt.models.reorder_favorited_items200_response import (
        ReorderFavoritedItems200Response as ReorderFavoritedItems200Response,
    )
    from schemas.trakt.models.reorder_items_on_a_list200_response import (
        ReorderItemsOnAList200Response as ReorderItemsOnAList200Response,
    )
    from schemas.trakt.models.reorder_watchlist_items200_response import (
        ReorderWatchlistItems200Response as ReorderWatchlistItems200Response,
    )
    from schemas.trakt.models.reorder_watchlist_items_request import (
        ReorderWatchlistItemsRequest as ReorderWatchlistItemsRequest,
    )
    from schemas.trakt.models.reset_show_progress200_response import (
        ResetShowProgress200Response as ResetShowProgress200Response,
    )
    from schemas.trakt.models.retrieve_settings200_response import (
        RetrieveSettings200Response as RetrieveSettings200Response,
    )
    from schemas.trakt.models.retrieve_settings200_response_account import (
        RetrieveSettings200ResponseAccount as RetrieveSettings200ResponseAccount,
    )
    from schemas.trakt.models.retrieve_settings200_response_connections import (
        RetrieveSettings200ResponseConnections as RetrieveSettings200ResponseConnections,
    )
    from schemas.trakt.models.retrieve_settings200_response_limits import (
        RetrieveSettings200ResponseLimits as RetrieveSettings200ResponseLimits,
    )
    from schemas.trakt.models.retrieve_settings200_response_limits_list import (
        RetrieveSettings200ResponseLimitsList as RetrieveSettings200ResponseLimitsList,
    )
    from schemas.trakt.models.retrieve_settings200_response_limits_search import (
        RetrieveSettings200ResponseLimitsSearch as RetrieveSettings200ResponseLimitsSearch,
    )
    from schemas.trakt.models.retrieve_settings200_response_limits_watchlist import (
        RetrieveSettings200ResponseLimitsWatchlist as RetrieveSettings200ResponseLimitsWatchlist,
    )
    from schemas.trakt.models.retrieve_settings200_response_permissions import (
        RetrieveSettings200ResponsePermissions as RetrieveSettings200ResponsePermissions,
    )
    from schemas.trakt.models.retrieve_settings200_response_sharing_text import (
        RetrieveSettings200ResponseSharingText as RetrieveSettings200ResponseSharingText,
    )
    from schemas.trakt.models.retrieve_settings200_response_user import (
        RetrieveSettings200ResponseUser as RetrieveSettings200ResponseUser,
    )
    from schemas.trakt.models.retrieve_settings200_response_user_ids import (
        RetrieveSettings200ResponseUserIds as RetrieveSettings200ResponseUserIds,
    )
    from schemas.trakt.models.retrieve_settings200_response_user_images import (
        RetrieveSettings200ResponseUserImages as RetrieveSettings200ResponseUserImages,
    )
    from schemas.trakt.models.retrieve_settings200_response_user_images_avatar import (
        RetrieveSettings200ResponseUserImagesAvatar as RetrieveSettings200ResponseUserImagesAvatar,
    )
    from schemas.trakt.models.revoke_an_access_token_request import (
        RevokeAnAccessTokenRequest as RevokeAnAccessTokenRequest,
    )
    from schemas.trakt.models.start_watching_in_a_media_center201_response import (
        StartWatchingInAMediaCenter201Response as StartWatchingInAMediaCenter201Response,
    )
    from schemas.trakt.models.start_watching_in_a_media_center_request import (
        StartWatchingInAMediaCenterRequest as StartWatchingInAMediaCenterRequest,
    )
    from schemas.trakt.models.stop_or_finish_watching_in_a_media_center201_response import (
        StopOrFinishWatchingInAMediaCenter201Response as StopOrFinishWatchingInAMediaCenter201Response,
    )
    from schemas.trakt.models.stop_or_finish_watching_in_a_media_center409_response import (
        StopOrFinishWatchingInAMediaCenter409Response as StopOrFinishWatchingInAMediaCenter409Response,
    )
    from schemas.trakt.models.stop_or_finish_watching_in_a_media_center_request import (
        StopOrFinishWatchingInAMediaCenterRequest as StopOrFinishWatchingInAMediaCenterRequest,
    )
    from schemas.trakt.models.update_a_comment_or_reply200_response import (
        UpdateACommentOrReply200Response as UpdateACommentOrReply200Response,
    )
    from schemas.trakt.models.update_a_comment_or_reply_request import (
        UpdateACommentOrReplyRequest as UpdateACommentOrReplyRequest,
    )
    from schemas.trakt.models.update_a_note200_response import (
        UpdateANote200Response as UpdateANote200Response,
    )
    from schemas.trakt.models.update_a_note_request import (
        UpdateANoteRequest as UpdateANoteRequest,
    )
    from schemas.trakt.models.update_a_watchlist_item_request import (
        UpdateAWatchlistItemRequest as UpdateAWatchlistItemRequest,
    )
    from schemas.trakt.models.update_favorites200_response import (
        UpdateFavorites200Response as UpdateFavorites200Response,
    )
    from schemas.trakt.models.update_favorites_request import (
        UpdateFavoritesRequest as UpdateFavoritesRequest,
    )
    from schemas.trakt.models.update_personal_list200_response import (
        UpdatePersonalList200Response as UpdatePersonalList200Response,
    )
    from schemas.trakt.models.update_personal_list_request import (
        UpdatePersonalListRequest as UpdatePersonalListRequest,
    )
    from schemas.trakt.models.update_watchlist200_response import (
        UpdateWatchlist200Response as UpdateWatchlist200Response,
    )
    from schemas.trakt.models.update_watchlist200_response_ids import (
        UpdateWatchlist200ResponseIds as UpdateWatchlist200ResponseIds,
    )
    from schemas.trakt.models.update_watchlist_request import (
        UpdateWatchlistRequest as UpdateWatchlistRequest,
    )

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            ("__version__", __version__),
            ("__all__", __all__),
            """# import apis into sdk package
from schemas.trakt.api.authentication_devices_api import AuthenticationDevicesApi as AuthenticationDevicesApi
from schemas.trakt.api.authentication_o_auth_api import AuthenticationOAuthApi as AuthenticationOAuthApi
from schemas.trakt.api.calendars_api import CalendarsApi as CalendarsApi
from schemas.trakt.api.certifications_api import CertificationsApi as CertificationsApi
from schemas.trakt.api.checkin_api import CheckinApi as CheckinApi
from schemas.trakt.api.comments_api import CommentsApi as CommentsApi
from schemas.trakt.api.countries_api import CountriesApi as CountriesApi
from schemas.trakt.api.episodes_api import EpisodesApi as EpisodesApi
from schemas.trakt.api.genres_api import GenresApi as GenresApi
from schemas.trakt.api.languages_api import LanguagesApi as LanguagesApi
from schemas.trakt.api.lists_api import ListsApi as ListsApi
from schemas.trakt.api.movies_api import MoviesApi as MoviesApi
from schemas.trakt.api.networks_api import NetworksApi as NetworksApi
from schemas.trakt.api.notes_api import NotesApi as NotesApi
from schemas.trakt.api.people_api import PeopleApi as PeopleApi
from schemas.trakt.api.recommendations_api import RecommendationsApi as RecommendationsApi
from schemas.trakt.api.scrobble_api import ScrobbleApi as ScrobbleApi
from schemas.trakt.api.search_api import SearchApi as SearchApi
from schemas.trakt.api.seasons_api import SeasonsApi as SeasonsApi
from schemas.trakt.api.shows_api import ShowsApi as ShowsApi
from schemas.trakt.api.sync_api import SyncApi as SyncApi
from schemas.trakt.api.users_api import UsersApi as UsersApi

# import ApiClient
from schemas.trakt.api_response import ApiResponse as ApiResponse
from schemas.trakt.api_client import ApiClient as ApiClient
from schemas.trakt.configuration import Configuration as Configuration
from schemas.trakt.exceptions import OpenApiException as OpenApiException
from schemas.trakt.exceptions import ApiTypeError as ApiTypeError
from schemas.trakt.exceptions import ApiValueError as ApiValueError
from schemas.trakt.exceptions import ApiKeyError as ApiKeyError
from schemas.trakt.exceptions import ApiAttributeError as ApiAttributeError
from schemas.trakt.exceptions import ApiException as ApiException

# import models into sdk package
from schemas.trakt.models.add_hidden_items201_response import AddHiddenItems201Response as AddHiddenItems201Response
from schemas.trakt.models.add_hidden_items201_response_added import AddHiddenItems201ResponseAdded as AddHiddenItems201ResponseAdded
from schemas.trakt.models.add_hidden_items201_response_not_found import AddHiddenItems201ResponseNotFound as AddHiddenItems201ResponseNotFound
from schemas.trakt.models.add_hidden_items_request import AddHiddenItemsRequest as AddHiddenItemsRequest
from schemas.trakt.models.add_hidden_items_request_seasons_inner import AddHiddenItemsRequestSeasonsInner as AddHiddenItemsRequestSeasonsInner
from schemas.trakt.models.add_hidden_items_request_seasons_inner_ids import AddHiddenItemsRequestSeasonsInnerIds as AddHiddenItemsRequestSeasonsInnerIds
from schemas.trakt.models.add_hidden_items_request_shows_inner import AddHiddenItemsRequestShowsInner as AddHiddenItemsRequestShowsInner
from schemas.trakt.models.add_hidden_items_request_shows_inner_seasons_inner import AddHiddenItemsRequestShowsInnerSeasonsInner as AddHiddenItemsRequestShowsInnerSeasonsInner
from schemas.trakt.models.add_items_to_collection201_response import AddItemsToCollection201Response as AddItemsToCollection201Response
from schemas.trakt.models.add_items_to_collection201_response_added import AddItemsToCollection201ResponseAdded as AddItemsToCollection201ResponseAdded
from schemas.trakt.models.add_items_to_collection201_response_not_found import AddItemsToCollection201ResponseNotFound as AddItemsToCollection201ResponseNotFound
from schemas.trakt.models.add_items_to_collection201_response_not_found_movies_inner import AddItemsToCollection201ResponseNotFoundMoviesInner as AddItemsToCollection201ResponseNotFoundMoviesInner
from schemas.trakt.models.add_items_to_collection201_response_not_found_movies_inner_ids import AddItemsToCollection201ResponseNotFoundMoviesInnerIds as AddItemsToCollection201ResponseNotFoundMoviesInnerIds
from schemas.trakt.models.add_items_to_collection_request import AddItemsToCollectionRequest as AddItemsToCollectionRequest
from schemas.trakt.models.add_items_to_collection_request_episodes_inner import AddItemsToCollectionRequestEpisodesInner as AddItemsToCollectionRequestEpisodesInner
from schemas.trakt.models.add_items_to_collection_request_movies_inner import AddItemsToCollectionRequestMoviesInner as AddItemsToCollectionRequestMoviesInner
from schemas.trakt.models.add_items_to_collection_request_seasons_inner import AddItemsToCollectionRequestSeasonsInner as AddItemsToCollectionRequestSeasonsInner
from schemas.trakt.models.add_items_to_collection_request_shows_inner import AddItemsToCollectionRequestShowsInner as AddItemsToCollectionRequestShowsInner
from schemas.trakt.models.add_items_to_collection_request_shows_inner_seasons_inner import AddItemsToCollectionRequestShowsInnerSeasonsInner as AddItemsToCollectionRequestShowsInnerSeasonsInner
from schemas.trakt.models.add_items_to_collection_request_shows_inner_seasons_inner_episodes_inner import AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner as AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner
from schemas.trakt.models.add_items_to_favorites201_response import AddItemsToFavorites201Response as AddItemsToFavorites201Response
from schemas.trakt.models.add_items_to_favorites201_response_added import AddItemsToFavorites201ResponseAdded as AddItemsToFavorites201ResponseAdded
from schemas.trakt.models.add_items_to_favorites201_response_not_found import AddItemsToFavorites201ResponseNotFound as AddItemsToFavorites201ResponseNotFound
from schemas.trakt.models.add_items_to_favorites_request import AddItemsToFavoritesRequest as AddItemsToFavoritesRequest
from schemas.trakt.models.add_items_to_favorites_request_shows_inner import AddItemsToFavoritesRequestShowsInner as AddItemsToFavoritesRequestShowsInner
from schemas.trakt.models.add_items_to_personal_list201_response import AddItemsToPersonalList201Response as AddItemsToPersonalList201Response
from schemas.trakt.models.add_items_to_personal_list201_response_added import AddItemsToPersonalList201ResponseAdded as AddItemsToPersonalList201ResponseAdded
from schemas.trakt.models.add_items_to_personal_list201_response_not_found import AddItemsToPersonalList201ResponseNotFound as AddItemsToPersonalList201ResponseNotFound
from schemas.trakt.models.add_items_to_personal_list_request import AddItemsToPersonalListRequest as AddItemsToPersonalListRequest
from schemas.trakt.models.add_items_to_personal_list_request_movies_inner import AddItemsToPersonalListRequestMoviesInner as AddItemsToPersonalListRequestMoviesInner
from schemas.trakt.models.add_items_to_personal_list_request_movies_inner_ids import AddItemsToPersonalListRequestMoviesInnerIds as AddItemsToPersonalListRequestMoviesInnerIds
from schemas.trakt.models.add_items_to_personal_list_request_shows_inner import AddItemsToPersonalListRequestShowsInner as AddItemsToPersonalListRequestShowsInner
from schemas.trakt.models.add_items_to_watched_history201_response import AddItemsToWatchedHistory201Response as AddItemsToWatchedHistory201Response
from schemas.trakt.models.add_items_to_watched_history_request import AddItemsToWatchedHistoryRequest as AddItemsToWatchedHistoryRequest
from schemas.trakt.models.add_items_to_watched_history_request_episodes_inner import AddItemsToWatchedHistoryRequestEpisodesInner as AddItemsToWatchedHistoryRequestEpisodesInner
from schemas.trakt.models.add_items_to_watched_history_request_movies_inner import AddItemsToWatchedHistoryRequestMoviesInner as AddItemsToWatchedHistoryRequestMoviesInner
from schemas.trakt.models.add_items_to_watched_history_request_seasons_inner import AddItemsToWatchedHistoryRequestSeasonsInner as AddItemsToWatchedHistoryRequestSeasonsInner
from schemas.trakt.models.add_items_to_watched_history_request_shows_inner import AddItemsToWatchedHistoryRequestShowsInner as AddItemsToWatchedHistoryRequestShowsInner
from schemas.trakt.models.add_items_to_watched_history_request_shows_inner_seasons_inner import AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner as AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner
from schemas.trakt.models.add_items_to_watched_history_request_shows_inner_seasons_inner_episodes_inner import AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner as AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner
from schemas.trakt.models.add_items_to_watchlist201_response import AddItemsToWatchlist201Response as AddItemsToWatchlist201Response
from schemas.trakt.models.add_items_to_watchlist201_response_list import AddItemsToWatchlist201ResponseList as AddItemsToWatchlist201ResponseList
from schemas.trakt.models.add_items_to_watchlist_request import AddItemsToWatchlistRequest as AddItemsToWatchlistRequest
from schemas.trakt.models.add_items_to_watchlist_request_movies_inner import AddItemsToWatchlistRequestMoviesInner as AddItemsToWatchlistRequestMoviesInner
from schemas.trakt.models.add_items_to_watchlist_request_shows_inner import AddItemsToWatchlistRequestShowsInner as AddItemsToWatchlistRequestShowsInner
from schemas.trakt.models.add_new_ratings201_response import AddNewRatings201Response as AddNewRatings201Response
from schemas.trakt.models.add_new_ratings201_response_added import AddNewRatings201ResponseAdded as AddNewRatings201ResponseAdded
from schemas.trakt.models.add_new_ratings201_response_not_found import AddNewRatings201ResponseNotFound as AddNewRatings201ResponseNotFound
from schemas.trakt.models.add_new_ratings201_response_not_found_movies_inner import AddNewRatings201ResponseNotFoundMoviesInner as AddNewRatings201ResponseNotFoundMoviesInner
from schemas.trakt.models.add_new_ratings_request import AddNewRatingsRequest as AddNewRatingsRequest
from schemas.trakt.models.add_new_ratings_request_episodes_inner import AddNewRatingsRequestEpisodesInner as AddNewRatingsRequestEpisodesInner
from schemas.trakt.models.add_new_ratings_request_movies_inner import AddNewRatingsRequestMoviesInner as AddNewRatingsRequestMoviesInner
from schemas.trakt.models.add_new_ratings_request_seasons_inner import AddNewRatingsRequestSeasonsInner as AddNewRatingsRequestSeasonsInner
from schemas.trakt.models.add_new_ratings_request_shows_inner import AddNewRatingsRequestShowsInner as AddNewRatingsRequestShowsInner
from schemas.trakt.models.add_new_ratings_request_shows_inner_seasons_inner import AddNewRatingsRequestShowsInnerSeasonsInner as AddNewRatingsRequestShowsInnerSeasonsInner
from schemas.trakt.models.add_new_ratings_request_shows_inner_seasons_inner_episodes_inner import AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner as AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner
from schemas.trakt.models.add_notes201_response import AddNotes201Response as AddNotes201Response
from schemas.trakt.models.add_notes_request import AddNotesRequest as AddNotesRequest
from schemas.trakt.models.approve_follow_request200_response import ApproveFollowRequest200Response as ApproveFollowRequest200Response
from schemas.trakt.models.check_into_an_item201_response import CheckIntoAnItem201Response as CheckIntoAnItem201Response
from schemas.trakt.models.check_into_an_item201_response_episode import CheckIntoAnItem201ResponseEpisode as CheckIntoAnItem201ResponseEpisode
from schemas.trakt.models.check_into_an_item201_response_episode_ids import CheckIntoAnItem201ResponseEpisodeIds as CheckIntoAnItem201ResponseEpisodeIds
from schemas.trakt.models.check_into_an_item409_response import CheckIntoAnItem409Response as CheckIntoAnItem409Response
from schemas.trakt.models.check_into_an_item_request import CheckIntoAnItemRequest as CheckIntoAnItemRequest
from schemas.trakt.models.check_into_an_item_request_sharing import CheckIntoAnItemRequestSharing as CheckIntoAnItemRequestSharing
from schemas.trakt.models.create_personal_list201_response import CreatePersonalList201Response as CreatePersonalList201Response
from schemas.trakt.models.create_personal_list_request import CreatePersonalListRequest as CreatePersonalListRequest
from schemas.trakt.models.exchange_refresh_token_for_access_token200_response import ExchangeRefreshTokenForAccessToken200Response as ExchangeRefreshTokenForAccessToken200Response
from schemas.trakt.models.exchange_refresh_token_for_access_token401_response import ExchangeRefreshTokenForAccessToken401Response as ExchangeRefreshTokenForAccessToken401Response
from schemas.trakt.models.exchange_refresh_token_for_access_token_request import ExchangeRefreshTokenForAccessTokenRequest as ExchangeRefreshTokenForAccessTokenRequest
from schemas.trakt.models.follow_this_user201_response import FollowThisUser201Response as FollowThisUser201Response
from schemas.trakt.models.generate_new_device_codes200_response import GenerateNewDeviceCodes200Response as GenerateNewDeviceCodes200Response
from schemas.trakt.models.generate_new_device_codes_request import GenerateNewDeviceCodesRequest as GenerateNewDeviceCodesRequest
from schemas.trakt.models.get_a_comment_or_reply200_response import GetACommentOrReply200Response as GetACommentOrReply200Response
from schemas.trakt.models.get_a_comment_or_reply200_response_user_stats import GetACommentOrReply200ResponseUserStats as GetACommentOrReply200ResponseUserStats
from schemas.trakt.models.get_a_movie200_response import GetAMovie200Response as GetAMovie200Response
from schemas.trakt.models.get_a_note200_response import GetANote200Response as GetANote200Response
from schemas.trakt.models.get_a_single_episode_for_a_show200_response import GetASingleEpisodeForAShow200Response as GetASingleEpisodeForAShow200Response
from schemas.trakt.models.get_a_single_person200_response import GetASinglePerson200Response as GetASinglePerson200Response
from schemas.trakt.models.get_a_single_person200_response_social_ids import GetASinglePerson200ResponseSocialIds as GetASinglePerson200ResponseSocialIds
from schemas.trakt.models.get_a_single_show200_response import GetASingleShow200Response as GetASingleShow200Response
from schemas.trakt.models.get_a_single_show200_response_airs import GetASingleShow200ResponseAirs as GetASingleShow200ResponseAirs
from schemas.trakt.models.get_a_user_s_personal_lists200_response_inner import GetAUserSPersonalLists200ResponseInner as GetAUserSPersonalLists200ResponseInner
from schemas.trakt.models.get_all_episodes_for_a_single_season200_response_inner import GetAllEpisodesForASingleSeason200ResponseInner as GetAllEpisodesForASingleSeason200ResponseInner
from schemas.trakt.models.get_all_list_comments200_response_inner import GetAllListComments200ResponseInner as GetAllListComments200ResponseInner
from schemas.trakt.models.get_all_lists_a_user_can_collaborate_on200_response_inner import GetAllListsAUserCanCollaborateOn200ResponseInner as GetAllListsAUserCanCollaborateOn200ResponseInner
from schemas.trakt.models.get_all_movie_aliases200_response_inner import GetAllMovieAliases200ResponseInner as GetAllMovieAliases200ResponseInner
from schemas.trakt.models.get_all_movie_releases200_response_inner import GetAllMovieReleases200ResponseInner as GetAllMovieReleases200ResponseInner
from schemas.trakt.models.get_all_movie_translations200_response_inner import GetAllMovieTranslations200ResponseInner as GetAllMovieTranslations200ResponseInner
from schemas.trakt.models.get_all_people_for_a_movie200_response import GetAllPeopleForAMovie200Response as GetAllPeopleForAMovie200Response
from schemas.trakt.models.get_all_people_for_a_movie200_response_cast_inner import GetAllPeopleForAMovie200ResponseCastInner as GetAllPeopleForAMovie200ResponseCastInner
from schemas.trakt.models.get_all_people_for_a_movie200_response_crew import GetAllPeopleForAMovie200ResponseCrew as GetAllPeopleForAMovie200ResponseCrew
from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_art_inner import GetAllPeopleForAMovie200ResponseCrewArtInner as GetAllPeopleForAMovie200ResponseCrewArtInner
from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_directing_inner import GetAllPeopleForAMovie200ResponseCrewDirectingInner as GetAllPeopleForAMovie200ResponseCrewDirectingInner
from schemas.trakt.models.get_all_people_for_a_movie200_response_crew_production_inner import GetAllPeopleForAMovie200ResponseCrewProductionInner as GetAllPeopleForAMovie200ResponseCrewProductionInner
from schemas.trakt.models.get_all_people_for_a_season200_response import GetAllPeopleForASeason200Response as GetAllPeopleForASeason200Response
from schemas.trakt.models.get_all_people_for_a_season200_response_crew import GetAllPeopleForASeason200ResponseCrew as GetAllPeopleForASeason200ResponseCrew
from schemas.trakt.models.get_all_people_for_a_show200_response import GetAllPeopleForAShow200Response as GetAllPeopleForAShow200Response
from schemas.trakt.models.get_all_people_for_a_show200_response_cast_inner import GetAllPeopleForAShow200ResponseCastInner as GetAllPeopleForAShow200ResponseCastInner
from schemas.trakt.models.get_all_people_for_a_show200_response_crew import GetAllPeopleForAShow200ResponseCrew as GetAllPeopleForAShow200ResponseCrew
from schemas.trakt.models.get_all_people_for_a_show200_response_crew_art_inner import GetAllPeopleForAShow200ResponseCrewArtInner as GetAllPeopleForAShow200ResponseCrewArtInner
from schemas.trakt.models.get_all_people_for_a_show200_response_crew_visual_effects_inner import GetAllPeopleForAShow200ResponseCrewVisualEffectsInner as GetAllPeopleForAShow200ResponseCrewVisualEffectsInner
from schemas.trakt.models.get_all_people_for_an_episode200_response import GetAllPeopleForAnEpisode200Response as GetAllPeopleForAnEpisode200Response
from schemas.trakt.models.get_all_people_for_an_episode200_response_crew import GetAllPeopleForAnEpisode200ResponseCrew as GetAllPeopleForAnEpisode200ResponseCrew
from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner import GetAllPeopleForAnEpisode200ResponseGuestStarsInner as GetAllPeopleForAnEpisode200ResponseGuestStarsInner
from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner_person import GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson as GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson
from schemas.trakt.models.get_all_people_for_an_episode200_response_guest_stars_inner_person_ids import GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds as GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds
from schemas.trakt.models.get_all_season_translations200_response_inner import GetAllSeasonTranslations200ResponseInner as GetAllSeasonTranslations200ResponseInner
from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner import GetAllSeasonsForAShow200ResponseInner as GetAllSeasonsForAShow200ResponseInner
from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_episodes_inner import GetAllSeasonsForAShow200ResponseInnerEpisodesInner as GetAllSeasonsForAShow200ResponseInnerEpisodesInner
from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_episodes_inner_ids import GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds as GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds
from schemas.trakt.models.get_all_seasons_for_a_show200_response_inner_ids import GetAllSeasonsForAShow200ResponseInnerIds as GetAllSeasonsForAShow200ResponseInnerIds
from schemas.trakt.models.get_all_show_certifications200_response_inner import GetAllShowCertifications200ResponseInner as GetAllShowCertifications200ResponseInner
from schemas.trakt.models.get_all_show_translations200_response_inner import GetAllShowTranslations200ResponseInner as GetAllShowTranslations200ResponseInner
from schemas.trakt.models.get_all_users_who_liked_a_comment200_response_inner import GetAllUsersWhoLikedAComment200ResponseInner as GetAllUsersWhoLikedAComment200ResponseInner
from schemas.trakt.models.get_all_videos200_response_inner import GetAllVideos200ResponseInner as GetAllVideos200ResponseInner
from schemas.trakt.models.get_certifications200_response import GetCertifications200Response as GetCertifications200Response
from schemas.trakt.models.get_certifications200_response_us_inner import GetCertifications200ResponseUsInner as GetCertifications200ResponseUsInner
from schemas.trakt.models.get_collection200_response_inner import GetCollection200ResponseInner as GetCollection200ResponseInner
from schemas.trakt.models.get_collection200_response_inner_seasons_inner import GetCollection200ResponseInnerSeasonsInner as GetCollection200ResponseInnerSeasonsInner
from schemas.trakt.models.get_collection200_response_inner_seasons_inner_episodes_inner import GetCollection200ResponseInnerSeasonsInnerEpisodesInner as GetCollection200ResponseInnerSeasonsInnerEpisodesInner
from schemas.trakt.models.get_collection200_response_inner_seasons_inner_episodes_inner_metadata import GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata as GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata
from schemas.trakt.models.get_countries200_response_inner import GetCountries200ResponseInner as GetCountries200ResponseInner
from schemas.trakt.models.get_favorites200_response_inner import GetFavorites200ResponseInner as GetFavorites200ResponseInner
from schemas.trakt.models.get_followers200_response_inner import GetFollowers200ResponseInner as GetFollowers200ResponseInner
from schemas.trakt.models.get_friends200_response_inner import GetFriends200ResponseInner as GetFriends200ResponseInner
from schemas.trakt.models.get_genres200_response_inner import GetGenres200ResponseInner as GetGenres200ResponseInner
from schemas.trakt.models.get_genres200_response_inner_subgenres_inner import GetGenres200ResponseInnerSubgenresInner as GetGenres200ResponseInnerSubgenresInner
from schemas.trakt.models.get_hidden_items200_response_inner import GetHiddenItems200ResponseInner as GetHiddenItems200ResponseInner
from schemas.trakt.models.get_id_lookup_results200_response_inner import GetIDLookupResults200ResponseInner as GetIDLookupResults200ResponseInner
from schemas.trakt.models.get_items_on_a_list200_response_inner import GetItemsOnAList200ResponseInner as GetItemsOnAList200ResponseInner
from schemas.trakt.models.get_items_on_a_list200_response_inner_episode import GetItemsOnAList200ResponseInnerEpisode as GetItemsOnAList200ResponseInnerEpisode
from schemas.trakt.models.get_items_on_a_list200_response_inner_episode_ids import GetItemsOnAList200ResponseInnerEpisodeIds as GetItemsOnAList200ResponseInnerEpisodeIds
from schemas.trakt.models.get_items_on_a_list200_response_inner_person import GetItemsOnAList200ResponseInnerPerson as GetItemsOnAList200ResponseInnerPerson
from schemas.trakt.models.get_items_on_a_list200_response_inner_season import GetItemsOnAList200ResponseInnerSeason as GetItemsOnAList200ResponseInnerSeason
from schemas.trakt.models.get_items_on_a_list200_response_inner_season_ids import GetItemsOnAList200ResponseInnerSeasonIds as GetItemsOnAList200ResponseInnerSeasonIds
from schemas.trakt.models.get_items_on_a_personal_list200_response_inner import GetItemsOnAPersonalList200ResponseInner as GetItemsOnAPersonalList200ResponseInner
from schemas.trakt.models.get_last_activity200_response import GetLastActivity200Response as GetLastActivity200Response
from schemas.trakt.models.get_last_activity200_response_account import GetLastActivity200ResponseAccount as GetLastActivity200ResponseAccount
from schemas.trakt.models.get_last_activity200_response_comments import GetLastActivity200ResponseComments as GetLastActivity200ResponseComments
from schemas.trakt.models.get_last_activity200_response_episodes import GetLastActivity200ResponseEpisodes as GetLastActivity200ResponseEpisodes
from schemas.trakt.models.get_last_activity200_response_lists import GetLastActivity200ResponseLists as GetLastActivity200ResponseLists
from schemas.trakt.models.get_last_activity200_response_movies import GetLastActivity200ResponseMovies as GetLastActivity200ResponseMovies
from schemas.trakt.models.get_last_activity200_response_seasons import GetLastActivity200ResponseSeasons as GetLastActivity200ResponseSeasons
from schemas.trakt.models.get_last_activity200_response_shows import GetLastActivity200ResponseShows as GetLastActivity200ResponseShows
from schemas.trakt.models.get_last_activity200_response_watchlist import GetLastActivity200ResponseWatchlist as GetLastActivity200ResponseWatchlist
from schemas.trakt.models.get_last_episode200_response import GetLastEpisode200Response as GetLastEpisode200Response
from schemas.trakt.models.get_likes200_response_inner import GetLikes200ResponseInner as GetLikes200ResponseInner
from schemas.trakt.models.get_likes200_response_inner_list import GetLikes200ResponseInnerList as GetLikes200ResponseInnerList
from schemas.trakt.models.get_list200_response import GetList200Response as GetList200Response
from schemas.trakt.models.get_movie_credits200_response import GetMovieCredits200Response as GetMovieCredits200Response
from schemas.trakt.models.get_movie_credits200_response_cast_inner import GetMovieCredits200ResponseCastInner as GetMovieCredits200ResponseCastInner
from schemas.trakt.models.get_movie_credits200_response_crew import GetMovieCredits200ResponseCrew as GetMovieCredits200ResponseCrew
from schemas.trakt.models.get_movie_credits200_response_crew_directing_inner import GetMovieCredits200ResponseCrewDirectingInner as GetMovieCredits200ResponseCrewDirectingInner
from schemas.trakt.models.get_movie_ratings200_response import GetMovieRatings200Response as GetMovieRatings200Response
from schemas.trakt.models.get_movie_ratings200_response_distribution import GetMovieRatings200ResponseDistribution as GetMovieRatings200ResponseDistribution
from schemas.trakt.models.get_movie_recommendations200_response_inner import GetMovieRecommendations200ResponseInner as GetMovieRecommendations200ResponseInner
from schemas.trakt.models.get_movie_recommendations200_response_inner_favorited_by_inner import GetMovieRecommendations200ResponseInnerFavoritedByInner as GetMovieRecommendations200ResponseInnerFavoritedByInner
from schemas.trakt.models.get_movie_stats200_response import GetMovieStats200Response as GetMovieStats200Response
from schemas.trakt.models.get_movie_studios200_response_inner import GetMovieStudios200ResponseInner as GetMovieStudios200ResponseInner
from schemas.trakt.models.get_movie_studios200_response_inner_ids import GetMovieStudios200ResponseInnerIds as GetMovieStudios200ResponseInnerIds
from schemas.trakt.models.get_movies200_response_inner import GetMovies200ResponseInner as GetMovies200ResponseInner
from schemas.trakt.models.get_movies200_response_inner_movie import GetMovies200ResponseInnerMovie as GetMovies200ResponseInnerMovie
from schemas.trakt.models.get_movies200_response_inner_movie_ids import GetMovies200ResponseInnerMovieIds as GetMovies200ResponseInnerMovieIds
from schemas.trakt.models.get_networks200_response_inner import GetNetworks200ResponseInner as GetNetworks200ResponseInner
from schemas.trakt.models.get_networks200_response_inner_ids import GetNetworks200ResponseInnerIds as GetNetworks200ResponseInnerIds
from schemas.trakt.models.get_new_shows200_response_inner import GetNewShows200ResponseInner as GetNewShows200ResponseInner
from schemas.trakt.models.get_new_shows200_response_inner_episode import GetNewShows200ResponseInnerEpisode as GetNewShows200ResponseInnerEpisode
from schemas.trakt.models.get_new_shows200_response_inner_episode_ids import GetNewShows200ResponseInnerEpisodeIds as GetNewShows200ResponseInnerEpisodeIds
from schemas.trakt.models.get_next_episode200_response import GetNextEpisode200Response as GetNextEpisode200Response
from schemas.trakt.models.get_notes200_response_inner import GetNotes200ResponseInner as GetNotes200ResponseInner
from schemas.trakt.models.get_notes200_response_inner_attached_to import GetNotes200ResponseInnerAttachedTo as GetNotes200ResponseInnerAttachedTo
from schemas.trakt.models.get_notes200_response_inner_note import GetNotes200ResponseInnerNote as GetNotes200ResponseInnerNote
from schemas.trakt.models.get_notes200_response_inner_note_user import GetNotes200ResponseInnerNoteUser as GetNotes200ResponseInnerNoteUser
from schemas.trakt.models.get_notes200_response_inner_note_user_ids import GetNotes200ResponseInnerNoteUserIds as GetNotes200ResponseInnerNoteUserIds
from schemas.trakt.models.get_pending_following_requests200_response_inner import GetPendingFollowingRequests200ResponseInner as GetPendingFollowingRequests200ResponseInner
from schemas.trakt.models.get_playback_progress200_response_inner import GetPlaybackProgress200ResponseInner as GetPlaybackProgress200ResponseInner
from schemas.trakt.models.get_popular_movies200_response_inner import GetPopularMovies200ResponseInner as GetPopularMovies200ResponseInner
from schemas.trakt.models.get_popular_shows200_response_inner import GetPopularShows200ResponseInner as GetPopularShows200ResponseInner
from schemas.trakt.models.get_ratings200_response_inner import GetRatings200ResponseInner as GetRatings200ResponseInner
from schemas.trakt.models.get_recently_updated_movies200_response_inner import GetRecentlyUpdatedMovies200ResponseInner as GetRecentlyUpdatedMovies200ResponseInner
from schemas.trakt.models.get_recently_updated_people200_response_inner import GetRecentlyUpdatedPeople200ResponseInner as GetRecentlyUpdatedPeople200ResponseInner
from schemas.trakt.models.get_recently_updated_shows200_response_inner import GetRecentlyUpdatedShows200ResponseInner as GetRecentlyUpdatedShows200ResponseInner
from schemas.trakt.models.get_replies_for_a_comment200_response_inner import GetRepliesForAComment200ResponseInner as GetRepliesForAComment200ResponseInner
from schemas.trakt.models.get_saved_filters200_response_inner import GetSavedFilters200ResponseInner as GetSavedFilters200ResponseInner
from schemas.trakt.models.get_season_premieres200_response_inner import GetSeasonPremieres200ResponseInner as GetSeasonPremieres200ResponseInner
from schemas.trakt.models.get_season_ratings200_response import GetSeasonRatings200Response as GetSeasonRatings200Response
from schemas.trakt.models.get_season_stats200_response import GetSeasonStats200Response as GetSeasonStats200Response
from schemas.trakt.models.get_show_collection_progress200_response import GetShowCollectionProgress200Response as GetShowCollectionProgress200Response
from schemas.trakt.models.get_show_collection_progress200_response_seasons_inner import GetShowCollectionProgress200ResponseSeasonsInner as GetShowCollectionProgress200ResponseSeasonsInner
from schemas.trakt.models.get_show_collection_progress200_response_seasons_inner_episodes_inner import GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner as GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner
from schemas.trakt.models.get_show_credits200_response import GetShowCredits200Response as GetShowCredits200Response
from schemas.trakt.models.get_show_credits200_response_cast_inner import GetShowCredits200ResponseCastInner as GetShowCredits200ResponseCastInner
from schemas.trakt.models.get_show_credits200_response_crew import GetShowCredits200ResponseCrew as GetShowCredits200ResponseCrew
from schemas.trakt.models.get_show_credits200_response_crew_production_inner import GetShowCredits200ResponseCrewProductionInner as GetShowCredits200ResponseCrewProductionInner
from schemas.trakt.models.get_show_ratings200_response import GetShowRatings200Response as GetShowRatings200Response
from schemas.trakt.models.get_show_recommendations200_response_inner import GetShowRecommendations200ResponseInner as GetShowRecommendations200ResponseInner
from schemas.trakt.models.get_show_stats200_response import GetShowStats200Response as GetShowStats200Response
from schemas.trakt.models.get_show_watched_progress200_response import GetShowWatchedProgress200Response as GetShowWatchedProgress200Response
from schemas.trakt.models.get_show_watched_progress200_response_seasons_inner import GetShowWatchedProgress200ResponseSeasonsInner as GetShowWatchedProgress200ResponseSeasonsInner
from schemas.trakt.models.get_show_watched_progress200_response_seasons_inner_episodes_inner import GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner as GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner
from schemas.trakt.models.get_shows200_response_inner import GetShows200ResponseInner as GetShows200ResponseInner
from schemas.trakt.models.get_shows200_response_inner_episode import GetShows200ResponseInnerEpisode as GetShows200ResponseInnerEpisode
from schemas.trakt.models.get_shows200_response_inner_episode_ids import GetShows200ResponseInnerEpisodeIds as GetShows200ResponseInnerEpisodeIds
from schemas.trakt.models.get_shows200_response_inner_show import GetShows200ResponseInnerShow as GetShows200ResponseInnerShow
from schemas.trakt.models.get_shows200_response_inner_show_ids import GetShows200ResponseInnerShowIds as GetShows200ResponseInnerShowIds
from schemas.trakt.models.get_single_seasons_for_a_show200_response import GetSingleSeasonsForAShow200Response as GetSingleSeasonsForAShow200Response
from schemas.trakt.models.get_stats200_response import GetStats200Response as GetStats200Response
from schemas.trakt.models.get_stats200_response_movies import GetStats200ResponseMovies as GetStats200ResponseMovies
from schemas.trakt.models.get_stats200_response_network import GetStats200ResponseNetwork as GetStats200ResponseNetwork
from schemas.trakt.models.get_stats200_response_ratings import GetStats200ResponseRatings as GetStats200ResponseRatings
from schemas.trakt.models.get_stats200_response_seasons import GetStats200ResponseSeasons as GetStats200ResponseSeasons
from schemas.trakt.models.get_stats200_response_shows import GetStats200ResponseShows as GetStats200ResponseShows
from schemas.trakt.models.get_text_query_results200_response_inner import GetTextQueryResults200ResponseInner as GetTextQueryResults200ResponseInner
from schemas.trakt.models.get_the_attached_item200_response import GetTheAttachedItem200Response as GetTheAttachedItem200Response
from schemas.trakt.models.get_the_attached_item200_response_attached_to import GetTheAttachedItem200ResponseAttachedTo as GetTheAttachedItem200ResponseAttachedTo
from schemas.trakt.models.get_the_attached_media_item200_response import GetTheAttachedMediaItem200Response as GetTheAttachedMediaItem200Response
from schemas.trakt.models.get_the_most_anticipated_movies200_response_inner import GetTheMostAnticipatedMovies200ResponseInner as GetTheMostAnticipatedMovies200ResponseInner
from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner import GetTheMostAnticipatedShows200ResponseInner as GetTheMostAnticipatedShows200ResponseInner
from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner_show import GetTheMostAnticipatedShows200ResponseInnerShow as GetTheMostAnticipatedShows200ResponseInnerShow
from schemas.trakt.models.get_the_most_anticipated_shows200_response_inner_show_ids import GetTheMostAnticipatedShows200ResponseInnerShowIds as GetTheMostAnticipatedShows200ResponseInnerShowIds
from schemas.trakt.models.get_the_most_favorited_movies200_response_inner import GetTheMostFavoritedMovies200ResponseInner as GetTheMostFavoritedMovies200ResponseInner
from schemas.trakt.models.get_the_most_favorited_shows200_response_inner import GetTheMostFavoritedShows200ResponseInner as GetTheMostFavoritedShows200ResponseInner
from schemas.trakt.models.get_the_most_played_movies200_response_inner import GetTheMostPlayedMovies200ResponseInner as GetTheMostPlayedMovies200ResponseInner
from schemas.trakt.models.get_the_most_played_shows200_response_inner import GetTheMostPlayedShows200ResponseInner as GetTheMostPlayedShows200ResponseInner
from schemas.trakt.models.get_the_weekend_box_office200_response_inner import GetTheWeekendBoxOffice200ResponseInner as GetTheWeekendBoxOffice200ResponseInner
from schemas.trakt.models.get_trending_comments200_response_inner import GetTrendingComments200ResponseInner as GetTrendingComments200ResponseInner
from schemas.trakt.models.get_trending_comments200_response_inner_comment import GetTrendingComments200ResponseInnerComment as GetTrendingComments200ResponseInnerComment
from schemas.trakt.models.get_trending_comments200_response_inner_comment_user_stats import GetTrendingComments200ResponseInnerCommentUserStats as GetTrendingComments200ResponseInnerCommentUserStats
from schemas.trakt.models.get_trending_comments200_response_inner_list import GetTrendingComments200ResponseInnerList as GetTrendingComments200ResponseInnerList
from schemas.trakt.models.get_trending_comments200_response_inner_list_ids import GetTrendingComments200ResponseInnerListIds as GetTrendingComments200ResponseInnerListIds
from schemas.trakt.models.get_trending_comments200_response_inner_season import GetTrendingComments200ResponseInnerSeason as GetTrendingComments200ResponseInnerSeason
from schemas.trakt.models.get_trending_comments200_response_inner_season_ids import GetTrendingComments200ResponseInnerSeasonIds as GetTrendingComments200ResponseInnerSeasonIds
from schemas.trakt.models.get_trending_lists200_response_inner import GetTrendingLists200ResponseInner as GetTrendingLists200ResponseInner
from schemas.trakt.models.get_trending_lists200_response_inner_list import GetTrendingLists200ResponseInnerList as GetTrendingLists200ResponseInnerList
from schemas.trakt.models.get_trending_movies200_response_inner import GetTrendingMovies200ResponseInner as GetTrendingMovies200ResponseInner
from schemas.trakt.models.get_trending_shows200_response_inner import GetTrendingShows200ResponseInner as GetTrendingShows200ResponseInner
from schemas.trakt.models.get_user_profile200_response import GetUserProfile200Response as GetUserProfile200Response
from schemas.trakt.models.get_users_watching_right_now200_response_inner import GetUsersWatchingRightNow200ResponseInner as GetUsersWatchingRightNow200ResponseInner
from schemas.trakt.models.get_watched200_response_inner import GetWatched200ResponseInner as GetWatched200ResponseInner
from schemas.trakt.models.get_watched_history200_response_inner import GetWatchedHistory200ResponseInner as GetWatchedHistory200ResponseInner
from schemas.trakt.models.get_watching200_response import GetWatching200Response as GetWatching200Response
from schemas.trakt.models.get_watchlist200_response_inner import GetWatchlist200ResponseInner as GetWatchlist200ResponseInner
from schemas.trakt.models.poll_for_the_access_token_request import PollForTheAccessTokenRequest as PollForTheAccessTokenRequest
from schemas.trakt.models.post_a_comment201_response import PostAComment201Response as PostAComment201Response
from schemas.trakt.models.post_a_comment201_response_user import PostAComment201ResponseUser as PostAComment201ResponseUser
from schemas.trakt.models.post_a_comment201_response_user_ids import PostAComment201ResponseUserIds as PostAComment201ResponseUserIds
from schemas.trakt.models.post_a_comment201_response_user_stats import PostAComment201ResponseUserStats as PostAComment201ResponseUserStats
from schemas.trakt.models.post_a_comment_request import PostACommentRequest as PostACommentRequest
from schemas.trakt.models.post_a_comment_request_sharing import PostACommentRequestSharing as PostACommentRequestSharing
from schemas.trakt.models.post_a_reply_for_a_comment201_response import PostAReplyForAComment201Response as PostAReplyForAComment201Response
from schemas.trakt.models.post_a_reply_for_a_comment_request import PostAReplyForACommentRequest as PostAReplyForACommentRequest
from schemas.trakt.models.remove_hidden_items200_response import RemoveHiddenItems200Response as RemoveHiddenItems200Response
from schemas.trakt.models.remove_hidden_items_request import RemoveHiddenItemsRequest as RemoveHiddenItemsRequest
from schemas.trakt.models.remove_hidden_items_request_shows_inner import RemoveHiddenItemsRequestShowsInner as RemoveHiddenItemsRequestShowsInner
from schemas.trakt.models.remove_items_from_collection200_response import RemoveItemsFromCollection200Response as RemoveItemsFromCollection200Response
from schemas.trakt.models.remove_items_from_collection_request import RemoveItemsFromCollectionRequest as RemoveItemsFromCollectionRequest
from schemas.trakt.models.remove_items_from_collection_request_movies_inner import RemoveItemsFromCollectionRequestMoviesInner as RemoveItemsFromCollectionRequestMoviesInner
from schemas.trakt.models.remove_items_from_collection_request_shows_inner import RemoveItemsFromCollectionRequestShowsInner as RemoveItemsFromCollectionRequestShowsInner
from schemas.trakt.models.remove_items_from_collection_request_shows_inner_seasons_inner import RemoveItemsFromCollectionRequestShowsInnerSeasonsInner as RemoveItemsFromCollectionRequestShowsInnerSeasonsInner
from schemas.trakt.models.remove_items_from_collection_request_shows_inner_seasons_inner_episodes_inner import RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner as RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner
from schemas.trakt.models.remove_items_from_favorites200_response import RemoveItemsFromFavorites200Response as RemoveItemsFromFavorites200Response
from schemas.trakt.models.remove_items_from_favorites_request import RemoveItemsFromFavoritesRequest as RemoveItemsFromFavoritesRequest
from schemas.trakt.models.remove_items_from_history200_response import RemoveItemsFromHistory200Response as RemoveItemsFromHistory200Response
from schemas.trakt.models.remove_items_from_history200_response_not_found import RemoveItemsFromHistory200ResponseNotFound as RemoveItemsFromHistory200ResponseNotFound
from schemas.trakt.models.remove_items_from_history_request import RemoveItemsFromHistoryRequest as RemoveItemsFromHistoryRequest
from schemas.trakt.models.remove_items_from_personal_list200_response import RemoveItemsFromPersonalList200Response as RemoveItemsFromPersonalList200Response
from schemas.trakt.models.remove_items_from_personal_list_request import RemoveItemsFromPersonalListRequest as RemoveItemsFromPersonalListRequest
from schemas.trakt.models.remove_items_from_personal_list_request_movies_inner import RemoveItemsFromPersonalListRequestMoviesInner as RemoveItemsFromPersonalListRequestMoviesInner
from schemas.trakt.models.remove_items_from_personal_list_request_shows_inner import RemoveItemsFromPersonalListRequestShowsInner as RemoveItemsFromPersonalListRequestShowsInner
from schemas.trakt.models.remove_items_from_watchlist200_response import RemoveItemsFromWatchlist200Response as RemoveItemsFromWatchlist200Response
from schemas.trakt.models.remove_ratings200_response import RemoveRatings200Response as RemoveRatings200Response
from schemas.trakt.models.reorder_a_user_s_lists200_response import ReorderAUserSLists200Response as ReorderAUserSLists200Response
from schemas.trakt.models.reorder_a_user_s_lists_request import ReorderAUserSListsRequest as ReorderAUserSListsRequest
from schemas.trakt.models.reorder_favorited_items200_response import ReorderFavoritedItems200Response as ReorderFavoritedItems200Response
from schemas.trakt.models.reorder_items_on_a_list200_response import ReorderItemsOnAList200Response as ReorderItemsOnAList200Response
from schemas.trakt.models.reorder_watchlist_items200_response import ReorderWatchlistItems200Response as ReorderWatchlistItems200Response
from schemas.trakt.models.reorder_watchlist_items_request import ReorderWatchlistItemsRequest as ReorderWatchlistItemsRequest
from schemas.trakt.models.reset_show_progress200_response import ResetShowProgress200Response as ResetShowProgress200Response
from schemas.trakt.models.retrieve_settings200_response import RetrieveSettings200Response as RetrieveSettings200Response
from schemas.trakt.models.retrieve_settings200_response_account import RetrieveSettings200ResponseAccount as RetrieveSettings200ResponseAccount
from schemas.trakt.models.retrieve_settings200_response_connections import RetrieveSettings200ResponseConnections as RetrieveSettings200ResponseConnections
from schemas.trakt.models.retrieve_settings200_response_limits import RetrieveSettings200ResponseLimits as RetrieveSettings200ResponseLimits
from schemas.trakt.models.retrieve_settings200_response_limits_list import RetrieveSettings200ResponseLimitsList as RetrieveSettings200ResponseLimitsList
from schemas.trakt.models.retrieve_settings200_response_limits_search import RetrieveSettings200ResponseLimitsSearch as RetrieveSettings200ResponseLimitsSearch
from schemas.trakt.models.retrieve_settings200_response_limits_watchlist import RetrieveSettings200ResponseLimitsWatchlist as RetrieveSettings200ResponseLimitsWatchlist
from schemas.trakt.models.retrieve_settings200_response_permissions import RetrieveSettings200ResponsePermissions as RetrieveSettings200ResponsePermissions
from schemas.trakt.models.retrieve_settings200_response_sharing_text import RetrieveSettings200ResponseSharingText as RetrieveSettings200ResponseSharingText
from schemas.trakt.models.retrieve_settings200_response_user import RetrieveSettings200ResponseUser as RetrieveSettings200ResponseUser
from schemas.trakt.models.retrieve_settings200_response_user_ids import RetrieveSettings200ResponseUserIds as RetrieveSettings200ResponseUserIds
from schemas.trakt.models.retrieve_settings200_response_user_images import RetrieveSettings200ResponseUserImages as RetrieveSettings200ResponseUserImages
from schemas.trakt.models.retrieve_settings200_response_user_images_avatar import RetrieveSettings200ResponseUserImagesAvatar as RetrieveSettings200ResponseUserImagesAvatar
from schemas.trakt.models.revoke_an_access_token_request import RevokeAnAccessTokenRequest as RevokeAnAccessTokenRequest
from schemas.trakt.models.start_watching_in_a_media_center201_response import StartWatchingInAMediaCenter201Response as StartWatchingInAMediaCenter201Response
from schemas.trakt.models.start_watching_in_a_media_center_request import StartWatchingInAMediaCenterRequest as StartWatchingInAMediaCenterRequest
from schemas.trakt.models.stop_or_finish_watching_in_a_media_center201_response import StopOrFinishWatchingInAMediaCenter201Response as StopOrFinishWatchingInAMediaCenter201Response
from schemas.trakt.models.stop_or_finish_watching_in_a_media_center409_response import StopOrFinishWatchingInAMediaCenter409Response as StopOrFinishWatchingInAMediaCenter409Response
from schemas.trakt.models.stop_or_finish_watching_in_a_media_center_request import StopOrFinishWatchingInAMediaCenterRequest as StopOrFinishWatchingInAMediaCenterRequest
from schemas.trakt.models.update_a_comment_or_reply200_response import UpdateACommentOrReply200Response as UpdateACommentOrReply200Response
from schemas.trakt.models.update_a_comment_or_reply_request import UpdateACommentOrReplyRequest as UpdateACommentOrReplyRequest
from schemas.trakt.models.update_a_note200_response import UpdateANote200Response as UpdateANote200Response
from schemas.trakt.models.update_a_note_request import UpdateANoteRequest as UpdateANoteRequest
from schemas.trakt.models.update_a_watchlist_item_request import UpdateAWatchlistItemRequest as UpdateAWatchlistItemRequest
from schemas.trakt.models.update_favorites200_response import UpdateFavorites200Response as UpdateFavorites200Response
from schemas.trakt.models.update_favorites_request import UpdateFavoritesRequest as UpdateFavoritesRequest
from schemas.trakt.models.update_personal_list200_response import UpdatePersonalList200Response as UpdatePersonalList200Response
from schemas.trakt.models.update_personal_list_request import UpdatePersonalListRequest as UpdatePersonalListRequest
from schemas.trakt.models.update_watchlist200_response import UpdateWatchlist200Response as UpdateWatchlist200Response
from schemas.trakt.models.update_watchlist200_response_ids import UpdateWatchlist200ResponseIds as UpdateWatchlist200ResponseIds
from schemas.trakt.models.update_watchlist_request import UpdateWatchlistRequest as UpdateWatchlistRequest

""",
            name=__name__,
            doc=__doc__,
        )
    )
