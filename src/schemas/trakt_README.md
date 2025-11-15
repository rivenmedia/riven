# schemas.trakt
At Trakt, we collect lots of interesting information about what tv shows and movies everyone is watching. Part of the fun with such data is making it available for anyone to mash up and use on their own site or app. The Trakt API was made just for this purpose. It is very easy to use, you basically call a URL and get some JSON back.  More complex API calls (such as adding a movie or show to your collection) involve sending us data. These are still easy to use, you simply POST some JSON data to a specific URL.  Make sure to check out the [**Required Headers**](#introduction/required-headers) and [**Authentication**](#reference/authentication-oauth) sections for more info on what needs to be sent with each API call. Also check out the [**Terminology**](#introduction/terminology) section insight into the features Trakt supports.  # Create an App  To use the Trakt API, you'll need to [**create a new API app**](https://trakt.tv/oauth/applications/new).  # Stay Connected  API discussion and bugs should be posted in the [**GitHub Developer Forum**](https://github.com/trakt/api-help/issues) and *watch* the repository if you'd like to get notifications. Make sure to follow our [**API Blog**](https://apiblog.trakt.tv) and [**@traktapi on Twitter**](https://twitter.com/traktapi) too.  # API URL  The API should always be accessed over SSL.  ``` https://api.trakt.tv ```  If you would like to use our sandbox environment to not fill production with test data, use this URL over SSL.  ``` https://api-staging.trakt.tv ```  > ### 🅽🅾🆃🅴 > _Staging is a completely separate environment, so you'll need to [**create a new API app on staging**](https://staging.trakt.tv/oauth/applications/new)._  # Verbs  The API uses restful verbs.  | Verb | Description | |---|---| | `GET` | Select one or more items. Success returns `200` status code. | | `POST` | Create a new item. Success returns `201` status code. | | `PUT` | Update an item. Success returns `200` status code. | | `DELETE` | Delete an item. Success returns `200` or `204` status code. |  # Status Codes  The API will respond with one of the following HTTP status codes.  | Code | Description | |---|---| | `200` | Success | `201` | Success - *new resource created (POST)* | `204` | Success - *no content to return (DELETE)* | `400` | Bad Request - *request couldn't be parsed* | `401` | Unauthorized - *OAuth must be provided* | `403` | Forbidden - *invalid API key or unapproved app* | `404` | Not Found - *method exists, but no record found* | `405` | Method Not Found - *method doesn't exist* | `409` | Conflict - *resource already created* | `412` | Precondition Failed - *use application/json content type* | `420` | Account Limit Exceeded - *list count, item count, etc* | `422` | Unprocessable Entity - *validation errors* | `423` | Locked User Account - *have the user contact support* | `426` | VIP Only - *user must upgrade to VIP* | `429` | Rate Limit Exceeded | `500` | Server Error - *please open a support ticket* | `502` | Service Unavailable - *server overloaded (try again in 30s)* | `503` | Service Unavailable - *server overloaded (try again in 30s)* | `504` | Service Unavailable - *server overloaded (try again in 30s)* | `520` | Service Unavailable - *Cloudflare error* | `521` | Service Unavailable - *Cloudflare error* | `522` | Service Unavailable - *Cloudflare error*  # Required Headers  You'll need to send some headers when making API calls to identify your application, set the version and set the content type to JSON.  | Header | Value | |---|---| | `Content-Type` <span style=\"color:red;\">*</a> | `application/json` | | `User-Agent` <span style=\"color:red;\">*</a> | We suggest using your app and version like `MyAppName/1.0.0` | | `trakt-api-key` <span style=\"color:red;\">*</a> | Your `client_id` listed under your Trakt applications. | | `trakt-api-version` <span style=\"color:red;\">*</a> | `2` | API version to use.  All `POST`, `PUT`, and `DELETE` methods require a valid OAuth `access_token`. Some `GET` calls require OAuth and others will return user specific data if OAuth is sent. Methods that &#128274; **require** or have &#128275; **optional** OAuth will be indicated.  Your OAuth library should take care of sending the auth headers for you, but for reference here's how the Bearer token should be sent.  | Header | Value | |---|---| | `Authorization` | `Bearer [access_token]` |  # Rate Limiting  All API methods are rate limited. A `429` HTTP status code is returned when the limit has been exceeded. Check the headers for detailed info, then try your API call in `Retry-After` seconds.  | Header | Value | |---|---| | `X-Ratelimit` | `{\"name\":\"UNAUTHED_API_GET_LIMIT\",\"period\":300,\"limit\":1000,\"remaining\":0,\"until\":\"2020-10-10T00:24:00Z\"}` | | `Retry-After` | `10` |  Here are the current limits. There are separate limits for authed (user level) and unauthed (application level) calls. We'll continue to adjust these limits to optimize API performance for everyone. The goal is to prevent API abuse and poor coding, but allow users to use apps normally.  | Name | Verb | Methods | Limit | |---|---|---|---| | `AUTHED_API_POST_LIMIT` | `POST`, `PUT`, `DELETE` | all | 1 call per second | | `AUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes | | `UNAUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes |  # Locked User Account  A `423` HTTP status code is returned when the OAuth user has a locked or deactivated user account. Please instruct the user to [**email Trakt support**](mailto:support@trakt.tv) so we can fix their account. API access will be suspended for the user until we fix their account.  | Header | Value | |---|---| | `X-Account-Locked` | `true` or `false` | | `X-Account-Deactivated` | `true` or `false` |  # VIP Methods  Some API methods are tagged 🔥 **VIP Only**. A `426` HTTP status code is returned when the user isn't a VIP, indicating they need to sign up for [**Trakt VIP**](https://trakt.tv/vip) in order to use this method. In your app, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` |  Some API methods are tagged 🔥 **VIP Enhanced**. A `420` HTTP status code is returned when the user has exceeded their account limit. Signing up for [**Trakt VIP**](https://trakt.tv/vip) will increase these limits. If the user isn't a VIP, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP. If they are already VIP and still exceeded the limit, please display a message indicating this.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` | | `X-VIP-User` | `true` or `false` | | `X-Account-Limit` | Limit allowed. |  # Pagination  Some methods are paginated. Methods with &#128196; **Pagination** will load 1 page of 10 items by default. Methods with &#128196; **Pagination Optional** will load all items by default. In either case, append a query string like `?page={page}&limit={limit}` to the URL to influence the results.  | Parameter | Type | Default | Value | |---|---|---|---| | `page` | integer | `1` | Number of page of results to be returned. | | `limit` | integer | `10` | Number of results to return per page. |  All paginated methods will return these HTTP headers.  | Header | Value | |---|---| | `X-Pagination-Page` | Current page. | | `X-Pagination-Limit` | Items per page. | | `X-Pagination-Page-Count` | Total number of pages. | | `X-Pagination-Item-Count` | Total number of items. |  # Extended Info  By default, all methods will return minimal info for movies, shows, episodes, people, and users. Minimal info is typically all you need to match locally cached items and includes the `title`, `year`, and `ids`. However, you can request different extended levels of information by adding `?extended={level}` to the URL. Send a comma separated string to get multiple types of extended info.  > ### 🅽🅾🆃🅴 > _This returns a lot of extra data, so please only use extended parameters if you actually need them!_  | Level | Description | |---|---| | `images` | Minimal info and all images. | | `full` | Complete info for an item. | | `full,images` | Complete info and all images. | | `metadata` | **Collection only.** Additional video and audio info. |  # Filters  Some `movies`, `shows`, `calendars`,  and `search` methods support additional filters and will be tagged with &#127898; **Filters**. Applying these filters refines the results and helps your users to more easily discover new items.  Add a query string (i.e. `?years=2016&genres=action`) with any filters you want to use. Some filters allow multiples which can be sent as comma delimited parameters. For example, `?genres=action,adventure` would match the `action` OR `adventure` genre.  *Please note*, subgenres are currently a technical preview.  We're currently in the process of smoothing this out.  > ### 🅽🅾🆃🅴 > _Make sure to properly URL encode the parameters including spaces and special characters._  #### Common Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `query` | | `batman` | Search titles and descriptions. | | `years` | | `2016` | 4 digit year or range of years. | | `genres` | &#10003; | `action` | [Genre slugs.](#reference/genres) | | `subgenres` | &#10003; | `android` | [Subgenre slugs.](#reference/subgenres) | | `languages` | &#10003; | `en` | [2 character language code.](#reference/languages) | | `countries` | &#10003; | `us` | [2 character country code.](#reference/countries) | | `runtimes` | | `30-90` | Range in minutes. | | `studio_ids` | &#10003; | `42` | Trakt studio ID. |  #### Rating Filters  Trakt, TMDB, and IMDB ratings apply to `movies`, `shows`, and `episodes`. Rotten Tomatoes and Metacritic apply to `movies`.  | Parameter | Multiples | Example | Value | |---|---|---|---| | `ratings` | | `75-100` | Trakt rating range between `0` and `100`. | | `votes` | | `5000-10000` | Trakt vote count between `0` and `100000`. | | `tmdb_ratings` | | `5.5-10.0` | TMDB rating range between `0.0` and `10.0`. | | `tmdb_votes` | | `5000-10000` | TMDB vote count between `0` and `100000`. | | `imdb_ratings` | | `5.5-10.0` | IMDB rating range between `0.0` and `10.0`. | | `imdb_votes` | | `5000-10000` | IMDB vote count between `0` and `3000000`. | | `rt_meters` | | `55-1000` | Rotten Tomatoes tomatometer range between `0` and `100`. | | `rt_user_meters` | | `65-100` | Rotten Tomatoes audience score range between `0` and `100`. | | `metascores` | | `5.5-10.0` | Metacritic score range between `0` and `100`. |  #### Movie Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `pg-13` | US content certification. |  #### Show Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `status` | &#10003; | `ended` | Set to `returning series`, `continuing`, `in production`, `planned`, `upcoming`,  `pilot`, `canceled`, or `ended`. |  #### Episode Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `episode_types` | &#10003; | `mid_season_premiere` | Set to `standard`, `series_premiere`, `season_premiere`, `mid_season_finale`, `mid_season_premiere`, `season_finale`,  or `series_finale`. |  # CORS  When creating your API app, specify the JavaScript (CORS) origins you'll be using. We use these origins to return the headers needed for CORS.  # Dates  All dates will be GMT and returned in the ISO 8601 format like `2014-09-01T09:10:11.000Z`. Adjust accordingly in your app for the user's local timezone.  # Emojis  We use short codes for emojis like `:smiley:` and `:raised_hands:` and render them on the Trakt website using [**JoyPixels**](https://www.joypixels.com/) _(verion 6.6.0)_. Methods that support emojis are tagged with &#128513; **Emojis**. For POST methods, you can send standard unicode emojis and we'll automatically convert them to short codes. For GET methods, we'll return the unicode emojis if possible, but some short codes might also be returned. It's up to your app to convert short codes back to unicode emojis.  # Standard Media Objects  All methods will accept or return standard media objects for `movie`, `show`, `season`, `episode`, `person`, and `user` items. Here are examples for all minimal objects.  #### movie  ``` {     \"title\": \"Batman Begins\",     \"year\": 2005,     \"ids\": {         \"trakt\": 1,         \"slug\": \"batman-begins-2005\",         \"imdb\": \"tt0372784\",         \"tmdb\": 272     } } ```  #### show  ``` {     \"title\": \"Breaking Bad\",     \"year\": 2008,     \"ids\": {         \"trakt\": 1,         \"slug\": \"breaking-bad\",         \"tvdb\": 81189,         \"imdb\": \"tt0903747\",         \"tmdb\": 1396     } } ```  #### season  ``` {     \"number\": 0,     \"ids\": {         \"trakt\": 1,         \"tvdb\": 439371,         \"tmdb\": 3577     } } ```  #### episode  ``` {     \"season\": 1,     \"number\": 1,     \"title\": \"Pilot\",     \"ids\": {         \"trakt\": 16,         \"tvdb\": 349232,         \"imdb\": \"tt0959621\",         \"tmdb\": 62085     } } ```  #### person  ``` {     \"name\": \"Bryan Cranston\",     \"ids\": {         \"trakt\": 142,         \"slug\": \"bryan-cranston\",         \"imdb\": \"nm0186505\",         \"tmdb\": 17419     } } ```  #### user  ``` {     \"username\": \"sean\",     \"private\": false,     \"name\": \"Sean Rudford\",     \"vip\": true,     \"vip_ep\": true,     \"ids\": {         \"slug\": \"sean\"     } } ```  # Images  #### Trakt Images  Trakt can return images by appending `?extended=images` to most URLs. This will return all images for a `movie`, `show`, `season`, `episode`, or `person`. Images are returned in a `images` object with keys for each image type. Each image type is an array of image URLs, but only 1 image URL will be returned for now. This is just future proofing.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > **Please cache all images!** All images are required to be cached in your app or server and not loaded directly from our CDN. Hotlinking images is not allowed and will be blocked.  > ### 🅽🅾🆃🅴 > All images are returned in WebP format for reduced file size, at the same image quality. You'll also need to prepend the https:// prefix to all image URLs.  ### Example Images Object  ```json {   \"title\": \"TRON: Legacy\",   \"year\": 2010,   \"ids\": {     \"trakt\": 12601,     \"slug\": \"tron-legacy-2010\",     \"imdb\": \"tt1104001\",     \"tmdb\": 20526   },   \"images\": {     \"fanart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/fanarts/medium/5aab754f58.jpg.webp\"     ],     \"poster\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/posters/thumb/e0d9dd35c5.jpg.webp\"     ],     \"logo\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/logos/medium/dbce70b4aa.png.webp\"     ],     \"clearart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/cleararts/medium/513a3688d1.png.webp\"     ],     \"banner\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/banners/medium/71dc0c3258.jpg.webp\"     ],     \"thumb\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/thumbs/medium/fcd7d7968c.jpg.webp\"     ]   } } ```  #### External Images  If you want more variety of images, there are several external services you can use. The standard Trakt media objects for all `movie`, `show`, `season`, `episode`, and `person` items include an `ids` object. These `ids` map to other services like [TMDB](https://www.themoviedb.org), [TVDB](https://thetvdb.com), [Fanart.tv](https://fanart.tv), [IMDB](https://www.imdb.com), and [OMDB](https://www.omdbapi.com/).  Most of these services have free APIs you can use to grab lots of great looking images. Here’s a chart to help you find the best artwork for your app. [**We also wrote an article to help with this.**](https://medium.com/api-news/how-to-find-the-best-images-516045bcc3b6)  | Media | Type | [TMDB](https://developers.themoviedb.org/3) | [TVDB](https://api.thetvdb.com/swagger) | [Fanart.tv](http://docs.fanarttv.apiary.io) | [OMDB](https://www.omdbapi.com) | |---|---|---|---|---|---| | `shows` | `poster` | &#10003; | &#10003; | &#10003; | &#10003; | |  | `fanart` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `seasons` | `poster` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `episodes` | `screenshot` | &#10003; | &#10003; |  |  | | `movies` | `poster` | &#10003; |  | &#10003; | &#10003; | |  | `fanart` | &#10003; |  | &#10003; |  | |  | `banner` |  |  | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `person` | `headshot` | &#10003; |  |  |  | |  | `character` |  | &#10003; |  |  |  # Website Media Links  There are several ways to construct direct links to media on the Trakt website. The website itself uses slugs so the URLs are more readable.  | Type | URL | |---|---| | `movie` | `/movies/:id` | | | `/movies/:slug` | | `show` | `/shows/:id` | | | `/shows/:slug` | | `season` | `/shows/:id/seasons/:num` | | | `/shows/:slug/seasons/:num` | | `episode` | `/shows/:id/seasons/:num/episodes/:num` | | | `/shows/:slug/seasons/:num/episodes/:num` | | `person` | `/people/:id` | | | `/people/:slug` | | `comment` | `/comments/:id` | | `list` | `/lists/:id` |  You can also create links using the Trakt, IMDB, TMDB, or TVDB IDs. We recommend using the Trakt ID if possible since that will always have full coverage. If you use the search url without an `id_type` it will return search results if multiple items are found.  | Type | URL | |---|---| | `trakt` | `/search/trakt/:id` | |  | `/search/trakt/:id?id_type=movie` | |  | `/search/trakt/:id?id_type=show` | |  | `/search/trakt/:id?id_type=season` | |  | `/search/trakt/:id?id_type=episode` | |  | `/search/trakt/:id?id_type=person` | | `imdb` | `/search/imdb/:id` | | `tmdb` | `/search/tmdb/:id` | |  | `/search/tmdb/:id?id_type=movie` | |  | `/search/tmdb/:id?id_type=show` | |  | `/search/tmdb/:id?id_type=episode` | |  | `/search/tmdb/:id?id_type=person` | | `tvdb` | `/search/tvdb/:id` | |  | `/search/tvdb/:id?id_type=show` | |  | `/search/tvdb/:id?id_type=episode` |  # Third Party Libraries  All of the libraries listed below are user contributed. If you find a bug or missing feature, please contact the developer directly. These might help give your project a head start, but we can't provide direct support for any of these libraries. Please help us keep this list up to date.  | Language | Name | Repository | |---|---|---| | `C#` | `Trakt.NET` | https://github.com/henrikfroehling/Trakt.NET | |  | `TraktSharp` | https://github.com/wwarby/TraktSharp | | `C++` | `libtraqt` | https://github.com/RobertMe/libtraqt | | `Clojure` | `clj-trakt` | https://github.com/niamu/clj-trakt | | `Java` | `trakt-java` | https://github.com/UweTrottmann/trakt-java | | `Kotlin` | `trakt-api` | https://github.com/MoviebaseApp/trakt-api | | `Node.js` | `Trakt.tv` | https://github.com/vankasteelj/trakt.tv | |  | `TraktApi2` | https://github.com/PatrickE94/traktapi2 | | `Python` | `trakt.py` | https://github.com/fuzeman/trakt.py | |  | `pyTrakt` | https://github.com/moogar0880/PyTrakt | | `R` | `tRakt` | https://github.com/jemus42/tRakt | | `React Native` | `nodeless-trakt` | https://github.com/kdemoya/nodeless-trakt | | `Ruby` | `omniauth-trakt` | https://github.com/wafcio/omniauth-trakt | |  | `omniauth-trakt` | https://github.com/alextakitani/omniauth-trakt | | `Swift` | `TraktKit` | https://github.com/MaxHasADHD/TraktKit | |  | `AKTrakt` | https://github.com/arsonik/AKTrakt |  # Terminology  Trakt has a lot of features and here's a chart to help explain the differences between some of them.  | Term | Description | |---|---| | `scrobble` | Automatic way to track what a user is watching in a media center. | | `checkin` | Manual action used by mobile apps allowing the user to indicate what they are watching right now. | | `history` | All watched items (scrobbles, checkins, watched) for a user. | | `collection` | Items a user has available to watch including Blu-Rays, DVDs, and digital downloads. | | `watchlist` | Items a user wants to watch in the future. Once watched, they are auto removed from this list. | | `list` | Personal list for any purpose. Items are not auto removed from any personal lists. | | `favorites` | A user's top 50 TV shows and movies. |

The `schemas.trakt` package is automatically generated by the [OpenAPI Generator](https://openapi-generator.tech) project:

- API version:
- Package version: 1.0.0
- Generator version: 7.17.0
- Build package: org.openapitools.codegen.languages.PythonClientCodegen

## Requirements.

Python 3.9+

## Installation & Usage

This python library package is generated without supporting files like setup.py or requirements files

To be able to use it, you will need these dependencies in your own package that uses this library:

* urllib3 >= 2.1.0, < 3.0.0
* python-dateutil >= 2.8.2
* pydantic >= 2
* typing-extensions >= 4.7.1

## Getting Started

In your own code, to use this library to connect and interact with schemas.trakt,
you can run the following:

```python

import schemas.trakt
from schemas.trakt.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://api.trakt.tv
# See configuration.py for a list of all supported configuration parameters.
configuration = schemas.trakt.Configuration(
    host = "https://api.trakt.tv"
)



# Enter a context with an instance of the API client
with schemas.trakt.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = schemas.trakt.AuthenticationDevicesApi(api_client)
    generate_new_device_codes_request = schemas.trakt.GenerateNewDeviceCodesRequest() # GenerateNewDeviceCodesRequest |  (optional)

    try:
        # Generate new device codes
        api_response = api_instance.generate_new_device_codes(generate_new_device_codes_request=generate_new_device_codes_request)
        print("The response of AuthenticationDevicesApi->generate_new_device_codes:\n")
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AuthenticationDevicesApi->generate_new_device_codes: %s\n" % e)

```

## Documentation for API Endpoints

All URIs are relative to *https://api.trakt.tv*

Class | Method | HTTP request | Description
------------ | ------------- | ------------- | -------------
*AuthenticationDevicesApi* | [**generate_new_device_codes**](schemas/trakt/docs/AuthenticationDevicesApi.md#generate_new_device_codes) | **POST** /oauth/device/code | Generate new device codes
*AuthenticationDevicesApi* | [**poll_for_the_access_token**](schemas/trakt/docs/AuthenticationDevicesApi.md#poll_for_the_access_token) | **POST** /oauth/device/token | Poll for the access_token
*AuthenticationOAuthApi* | [**authorize_application**](schemas/trakt/docs/AuthenticationOAuthApi.md#authorize_application) | **GET** /oauth/authorize | Authorize Application
*AuthenticationOAuthApi* | [**exchange_refresh_token_for_access_token**](schemas/trakt/docs/AuthenticationOAuthApi.md#exchange_refresh_token_for_access_token) | **POST** /oauth/token | Exchange refresh_token for access_token
*AuthenticationOAuthApi* | [**revoke_an_access_token**](schemas/trakt/docs/AuthenticationOAuthApi.md#revoke_an_access_token) | **POST** /oauth/revoke | Revoke an access_token
*CalendarsApi* | [**get_dvd_releases**](schemas/trakt/docs/CalendarsApi.md#get_dvd_releases) | **GET** /calendars/my/dvd/{start_date}/{days} | Get DVD releases
*CalendarsApi* | [**get_dvd_releases_0**](schemas/trakt/docs/CalendarsApi.md#get_dvd_releases_0) | **GET** /calendars/all/dvd/{start_date}/{days} | Get DVD releases
*CalendarsApi* | [**get_finales**](schemas/trakt/docs/CalendarsApi.md#get_finales) | **GET** /calendars/my/shows/finales/{start_date}/{days} | Get finales
*CalendarsApi* | [**get_finales_0**](schemas/trakt/docs/CalendarsApi.md#get_finales_0) | **GET** /calendars/all/shows/finales/{start_date}/{days} | Get finales
*CalendarsApi* | [**get_movies**](schemas/trakt/docs/CalendarsApi.md#get_movies) | **GET** /calendars/my/movies/{start_date}/{days} | Get movies
*CalendarsApi* | [**get_movies_0**](schemas/trakt/docs/CalendarsApi.md#get_movies_0) | **GET** /calendars/all/movies/{start_date}/{days} | Get movies
*CalendarsApi* | [**get_new_shows**](schemas/trakt/docs/CalendarsApi.md#get_new_shows) | **GET** /calendars/my/shows/new/{start_date}/{days} | Get new shows
*CalendarsApi* | [**get_new_shows_0**](schemas/trakt/docs/CalendarsApi.md#get_new_shows_0) | **GET** /calendars/all/shows/new/{start_date}/{days} | Get new shows
*CalendarsApi* | [**get_season_premieres**](schemas/trakt/docs/CalendarsApi.md#get_season_premieres) | **GET** /calendars/my/shows/premieres/{start_date}/{days} | Get season premieres
*CalendarsApi* | [**get_season_premieres_0**](schemas/trakt/docs/CalendarsApi.md#get_season_premieres_0) | **GET** /calendars/all/shows/premieres/{start_date}/{days} | Get season premieres
*CalendarsApi* | [**get_shows**](schemas/trakt/docs/CalendarsApi.md#get_shows) | **GET** /calendars/my/shows/{start_date}/{days} | Get shows
*CalendarsApi* | [**get_shows_0**](schemas/trakt/docs/CalendarsApi.md#get_shows_0) | **GET** /calendars/all/shows/{start_date}/{days} | Get shows
*CalendarsApi* | [**get_streaming_releases**](schemas/trakt/docs/CalendarsApi.md#get_streaming_releases) | **GET** /calendars/my/streaming/{start_date}/{days} | Get streaming releases
*CalendarsApi* | [**get_streaming_releases_0**](schemas/trakt/docs/CalendarsApi.md#get_streaming_releases_0) | **GET** /calendars/all/streaming/{start_date}/{days} | Get streaming releases
*CertificationsApi* | [**get_certifications**](schemas/trakt/docs/CertificationsApi.md#get_certifications) | **GET** /certifications/{type} | Get certifications
*CheckinApi* | [**check_into_an_item**](schemas/trakt/docs/CheckinApi.md#check_into_an_item) | **POST** /checkin | Check into an item
*CheckinApi* | [**delete_any_active_checkins**](schemas/trakt/docs/CheckinApi.md#delete_any_active_checkins) | **DELETE** /checkin | Delete any active checkins
*CommentsApi* | [**delete_a_comment_or_reply**](schemas/trakt/docs/CommentsApi.md#delete_a_comment_or_reply) | **DELETE** /comments/{id} | Delete a comment or reply
*CommentsApi* | [**get_a_comment_or_reply**](schemas/trakt/docs/CommentsApi.md#get_a_comment_or_reply) | **GET** /comments/{id} | Get a comment or reply
*CommentsApi* | [**get_all_users_who_liked_a_comment**](schemas/trakt/docs/CommentsApi.md#get_all_users_who_liked_a_comment) | **GET** /comments/{id}/likes | Get all users who liked a comment
*CommentsApi* | [**get_recently_created_comments**](schemas/trakt/docs/CommentsApi.md#get_recently_created_comments) | **GET** /comments/recent/{comment_type}/{type} | Get recently created comments
*CommentsApi* | [**get_recently_updated_comments**](schemas/trakt/docs/CommentsApi.md#get_recently_updated_comments) | **GET** /comments/updates/{comment_type}/{type} | Get recently updated comments
*CommentsApi* | [**get_replies_for_a_comment**](schemas/trakt/docs/CommentsApi.md#get_replies_for_a_comment) | **GET** /comments/{id}/replies | Get replies for a comment
*CommentsApi* | [**get_the_attached_media_item**](schemas/trakt/docs/CommentsApi.md#get_the_attached_media_item) | **GET** /comments/{id}/item | Get the attached media item
*CommentsApi* | [**get_trending_comments**](schemas/trakt/docs/CommentsApi.md#get_trending_comments) | **GET** /comments/trending/{comment_type}/{type} | Get trending comments
*CommentsApi* | [**like_a_comment**](schemas/trakt/docs/CommentsApi.md#like_a_comment) | **POST** /comments/{id}/like | Like a comment
*CommentsApi* | [**post_a_comment**](schemas/trakt/docs/CommentsApi.md#post_a_comment) | **POST** /comments | Post a comment
*CommentsApi* | [**post_a_reply_for_a_comment**](schemas/trakt/docs/CommentsApi.md#post_a_reply_for_a_comment) | **POST** /comments/{id}/replies | Post a reply for a comment
*CommentsApi* | [**remove_like_on_a_comment**](schemas/trakt/docs/CommentsApi.md#remove_like_on_a_comment) | **DELETE** /comments/{id}/like | Remove like on a comment
*CommentsApi* | [**update_a_comment_or_reply**](schemas/trakt/docs/CommentsApi.md#update_a_comment_or_reply) | **PUT** /comments/{id} | Update a comment or reply
*CountriesApi* | [**get_countries**](schemas/trakt/docs/CountriesApi.md#get_countries) | **GET** /countries/{type} | Get countries
*EpisodesApi* | [**get_a_single_episode_for_a_show**](schemas/trakt/docs/EpisodesApi.md#get_a_single_episode_for_a_show) | **GET** /shows/{id}/seasons/{season}/episodes/{episode} | Get a single episode for a show
*EpisodesApi* | [**get_all_episode_comments**](schemas/trakt/docs/EpisodesApi.md#get_all_episode_comments) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/comments/{sort} | Get all episode comments
*EpisodesApi* | [**get_all_episode_translations**](schemas/trakt/docs/EpisodesApi.md#get_all_episode_translations) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/translations/{language} | Get all episode translations
*EpisodesApi* | [**get_all_people_for_an_episode**](schemas/trakt/docs/EpisodesApi.md#get_all_people_for_an_episode) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/people | Get all people for an episode
*EpisodesApi* | [**get_all_videos**](schemas/trakt/docs/EpisodesApi.md#get_all_videos) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/watching | Get all videos
*EpisodesApi* | [**get_episode_ratings**](schemas/trakt/docs/EpisodesApi.md#get_episode_ratings) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/ratings | Get episode ratings
*EpisodesApi* | [**get_episode_stats**](schemas/trakt/docs/EpisodesApi.md#get_episode_stats) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/stats | Get episode stats
*EpisodesApi* | [**get_lists_containing_this_episode**](schemas/trakt/docs/EpisodesApi.md#get_lists_containing_this_episode) | **GET** /shows/{id}/seasons/{season}/episodes/{episode}/lists/{type}/{sort} | Get lists containing this episode
*GenresApi* | [**get_genres**](schemas/trakt/docs/GenresApi.md#get_genres) | **GET** /genres/{type} | Get genres
*LanguagesApi* | [**get_languages**](schemas/trakt/docs/LanguagesApi.md#get_languages) | **GET** /languages/{type} | Get languages
*ListsApi* | [**get_all_list_comments**](schemas/trakt/docs/ListsApi.md#get_all_list_comments) | **GET** /lists/{id}/comments/{sort} | Get all list comments
*ListsApi* | [**get_all_users_who_liked_a_list**](schemas/trakt/docs/ListsApi.md#get_all_users_who_liked_a_list) | **GET** /lists/{id}/likes | Get all users who liked a list
*ListsApi* | [**get_items_on_a_list**](schemas/trakt/docs/ListsApi.md#get_items_on_a_list) | **GET** /lists/{id}/items/{type}/{sort_by}/{sort_how} | Get items on a list
*ListsApi* | [**get_list**](schemas/trakt/docs/ListsApi.md#get_list) | **GET** /lists/{id} | Get list
*ListsApi* | [**get_popular_lists**](schemas/trakt/docs/ListsApi.md#get_popular_lists) | **GET** /lists/popular/{type} | Get popular lists
*ListsApi* | [**get_trending_lists**](schemas/trakt/docs/ListsApi.md#get_trending_lists) | **GET** /lists/trending/{type} | Get trending lists
*ListsApi* | [**like_a_list**](schemas/trakt/docs/ListsApi.md#like_a_list) | **POST** /lists/{id}/like | Like a list
*ListsApi* | [**remove_like_on_a_list**](schemas/trakt/docs/ListsApi.md#remove_like_on_a_list) | **DELETE** /lists/{id}/like | Remove like on a list
*MoviesApi* | [**get_a_movie**](schemas/trakt/docs/MoviesApi.md#get_a_movie) | **GET** /movies/{id} | Get a movie
*MoviesApi* | [**get_all_movie_aliases**](schemas/trakt/docs/MoviesApi.md#get_all_movie_aliases) | **GET** /movies/{id}/aliases | Get all movie aliases
*MoviesApi* | [**get_all_movie_comments**](schemas/trakt/docs/MoviesApi.md#get_all_movie_comments) | **GET** /movies/{id}/comments/{sort} | Get all movie comments
*MoviesApi* | [**get_all_movie_releases**](schemas/trakt/docs/MoviesApi.md#get_all_movie_releases) | **GET** /movies/{id}/releases/{country} | Get all movie releases
*MoviesApi* | [**get_all_movie_translations**](schemas/trakt/docs/MoviesApi.md#get_all_movie_translations) | **GET** /movies/{id}/translations/{language} | Get all movie translations
*MoviesApi* | [**get_all_people_for_a_movie**](schemas/trakt/docs/MoviesApi.md#get_all_people_for_a_movie) | **GET** /movies/{id}/people | Get all people for a movie
*MoviesApi* | [**get_all_videos**](schemas/trakt/docs/MoviesApi.md#get_all_videos) | **GET** /movies/{id}/videos | Get all videos
*MoviesApi* | [**get_lists_containing_this_movie**](schemas/trakt/docs/MoviesApi.md#get_lists_containing_this_movie) | **GET** /movies/{id}/lists/{type}/{sort} | Get lists containing this movie
*MoviesApi* | [**get_movie_ratings**](schemas/trakt/docs/MoviesApi.md#get_movie_ratings) | **GET** /movies/{id}/ratings | Get movie ratings
*MoviesApi* | [**get_movie_stats**](schemas/trakt/docs/MoviesApi.md#get_movie_stats) | **GET** /movies/{id}/stats | Get movie stats
*MoviesApi* | [**get_movie_studios**](schemas/trakt/docs/MoviesApi.md#get_movie_studios) | **GET** /movies/{id}/studios | Get movie studios
*MoviesApi* | [**get_popular_movies**](schemas/trakt/docs/MoviesApi.md#get_popular_movies) | **GET** /movies/popular | Get popular movies
*MoviesApi* | [**get_recently_updated_movie_trakt_ids**](schemas/trakt/docs/MoviesApi.md#get_recently_updated_movie_trakt_ids) | **GET** /movies/updates/id/{start_date} | Get recently updated movie Trakt IDs
*MoviesApi* | [**get_recently_updated_movies**](schemas/trakt/docs/MoviesApi.md#get_recently_updated_movies) | **GET** /movies/updates/{start_date} | Get recently updated movies
*MoviesApi* | [**get_related_movies**](schemas/trakt/docs/MoviesApi.md#get_related_movies) | **GET** /movies/{id}/related | Get related movies
*MoviesApi* | [**get_the_most_anticipated_movies**](schemas/trakt/docs/MoviesApi.md#get_the_most_anticipated_movies) | **GET** /movies/anticipated | Get the most anticipated movies
*MoviesApi* | [**get_the_most_collected_movies**](schemas/trakt/docs/MoviesApi.md#get_the_most_collected_movies) | **GET** /movies/collected/{period} | Get the most Collected movies
*MoviesApi* | [**get_the_most_favorited_movies**](schemas/trakt/docs/MoviesApi.md#get_the_most_favorited_movies) | **GET** /movies/favorited/{period} | Get the most favorited movies
*MoviesApi* | [**get_the_most_played_movies**](schemas/trakt/docs/MoviesApi.md#get_the_most_played_movies) | **GET** /movies/played/{period} | Get the most played movies
*MoviesApi* | [**get_the_most_watched_movies**](schemas/trakt/docs/MoviesApi.md#get_the_most_watched_movies) | **GET** /movies/watched/{period} | Get the most watched movies
*MoviesApi* | [**get_the_weekend_box_office**](schemas/trakt/docs/MoviesApi.md#get_the_weekend_box_office) | **GET** /movies/boxoffice | Get the weekend box office
*MoviesApi* | [**get_trending_movies**](schemas/trakt/docs/MoviesApi.md#get_trending_movies) | **GET** /movies/trending | Get trending movies
*MoviesApi* | [**get_users_watching_right_now**](schemas/trakt/docs/MoviesApi.md#get_users_watching_right_now) | **GET** /movies/{id}/watching | Get users watching right now
*MoviesApi* | [**refresh_movie_metadata**](schemas/trakt/docs/MoviesApi.md#refresh_movie_metadata) | **POST** /movies/{id}/refresh | Refresh movie metadata
*NetworksApi* | [**get_networks**](schemas/trakt/docs/NetworksApi.md#get_networks) | **GET** /networks | Get networks
*NotesApi* | [**add_notes**](schemas/trakt/docs/NotesApi.md#add_notes) | **POST** /notes | Add notes
*NotesApi* | [**delete_a_note**](schemas/trakt/docs/NotesApi.md#delete_a_note) | **DELETE** /notes/{id} | Delete a note
*NotesApi* | [**get_a_note**](schemas/trakt/docs/NotesApi.md#get_a_note) | **GET** /notes/{id} | Get a note
*NotesApi* | [**get_the_attached_item**](schemas/trakt/docs/NotesApi.md#get_the_attached_item) | **GET** /notes/{id}/item | Get the attached item
*NotesApi* | [**update_a_note**](schemas/trakt/docs/NotesApi.md#update_a_note) | **PUT** /notes/{id} | Update a note
*PeopleApi* | [**get_a_single_person**](schemas/trakt/docs/PeopleApi.md#get_a_single_person) | **GET** /people/{id} | Get a single person
*PeopleApi* | [**get_lists_containing_this_person**](schemas/trakt/docs/PeopleApi.md#get_lists_containing_this_person) | **GET** /people/{id}/lists/{type}/{sort} | Get lists containing this person
*PeopleApi* | [**get_movie_credits**](schemas/trakt/docs/PeopleApi.md#get_movie_credits) | **GET** /people/{id}/movies | Get movie credits
*PeopleApi* | [**get_recently_updated_people**](schemas/trakt/docs/PeopleApi.md#get_recently_updated_people) | **GET** /people/updates/{start_date} | Get recently updated people
*PeopleApi* | [**get_recently_updated_people_trakt_ids**](schemas/trakt/docs/PeopleApi.md#get_recently_updated_people_trakt_ids) | **GET** /people/updates/id/{start_date} | Get recently updated people Trakt IDs
*PeopleApi* | [**get_show_credits**](schemas/trakt/docs/PeopleApi.md#get_show_credits) | **GET** /people/{id}/shows | Get show credits
*PeopleApi* | [**refresh_person_metadata**](schemas/trakt/docs/PeopleApi.md#refresh_person_metadata) | **POST** /people/{id}/refresh | Refresh person metadata
*RecommendationsApi* | [**get_movie_recommendations**](schemas/trakt/docs/RecommendationsApi.md#get_movie_recommendations) | **GET** /recommendations/movies | Get movie recommendations
*RecommendationsApi* | [**get_show_recommendations**](schemas/trakt/docs/RecommendationsApi.md#get_show_recommendations) | **GET** /recommendations/shows | Get show recommendations
*RecommendationsApi* | [**hide_a_movie_recommendation**](schemas/trakt/docs/RecommendationsApi.md#hide_a_movie_recommendation) | **DELETE** /recommendations/movies/{id} | Hide a movie recommendation
*RecommendationsApi* | [**hide_a_show_recommendation**](schemas/trakt/docs/RecommendationsApi.md#hide_a_show_recommendation) | **DELETE** /recommendations/shows/{id} | Hide a show recommendation
*ScrobbleApi* | [**start_watching_in_a_media_center**](schemas/trakt/docs/ScrobbleApi.md#start_watching_in_a_media_center) | **POST** /scrobble/start | Start watching in a media center
*ScrobbleApi* | [**stop_or_finish_watching_in_a_media_center**](schemas/trakt/docs/ScrobbleApi.md#stop_or_finish_watching_in_a_media_center) | **POST** /scrobble/stop | Stop or finish watching in a media center
*SearchApi* | [**get_id_lookup_results**](schemas/trakt/docs/SearchApi.md#get_id_lookup_results) | **GET** /search/{id_type}/{id} | Get ID lookup results
*SearchApi* | [**get_text_query_results**](schemas/trakt/docs/SearchApi.md#get_text_query_results) | **GET** /search/{type} | Get text query results
*SeasonsApi* | [**get_all_episodes_for_a_single_season**](schemas/trakt/docs/SeasonsApi.md#get_all_episodes_for_a_single_season) | **GET** /shows/{id}/seasons/{season} | Get all episodes for a single season
*SeasonsApi* | [**get_all_people_for_a_season**](schemas/trakt/docs/SeasonsApi.md#get_all_people_for_a_season) | **GET** /shows/{id}/seasons/{season}/people | Get all people for a season
*SeasonsApi* | [**get_all_season_comments**](schemas/trakt/docs/SeasonsApi.md#get_all_season_comments) | **GET** /shows/{id}/seasons/{season}/comments/{sort} | Get all season comments
*SeasonsApi* | [**get_all_season_translations**](schemas/trakt/docs/SeasonsApi.md#get_all_season_translations) | **GET** /shows/{id}/seasons/{season}/translations/{language} | Get all season translations
*SeasonsApi* | [**get_all_seasons_for_a_show**](schemas/trakt/docs/SeasonsApi.md#get_all_seasons_for_a_show) | **GET** /shows/{id}/seasons | Get all seasons for a show
*SeasonsApi* | [**get_all_videos**](schemas/trakt/docs/SeasonsApi.md#get_all_videos) | **GET** /shows/{id}/seasons/{season}/videos | Get all videos
*SeasonsApi* | [**get_lists_containing_this_season**](schemas/trakt/docs/SeasonsApi.md#get_lists_containing_this_season) | **GET** /shows/{id}/seasons/{season}/lists/{type}/{sort} | Get lists containing this season
*SeasonsApi* | [**get_season_ratings**](schemas/trakt/docs/SeasonsApi.md#get_season_ratings) | **GET** /shows/{id}/seasons/{season}/ratings | Get season ratings
*SeasonsApi* | [**get_season_stats**](schemas/trakt/docs/SeasonsApi.md#get_season_stats) | **GET** /shows/{id}/seasons/{season}/stats | Get season stats
*SeasonsApi* | [**get_single_seasons_for_a_show**](schemas/trakt/docs/SeasonsApi.md#get_single_seasons_for_a_show) | **GET** /shows/{id}/seasons/{season}/info | Get single seasons for a show
*SeasonsApi* | [**get_users_watching_right_now**](schemas/trakt/docs/SeasonsApi.md#get_users_watching_right_now) | **GET** /shows/{id}/seasons/{season}/watching | Get users watching right now
*ShowsApi* | [**get_a_single_show**](schemas/trakt/docs/ShowsApi.md#get_a_single_show) | **GET** /shows/{id} | Get a single show
*ShowsApi* | [**get_all_people_for_a_show**](schemas/trakt/docs/ShowsApi.md#get_all_people_for_a_show) | **GET** /shows/{id}/people | Get all people for a show
*ShowsApi* | [**get_all_show_aliases**](schemas/trakt/docs/ShowsApi.md#get_all_show_aliases) | **GET** /shows/{id}/aliases | Get all show aliases
*ShowsApi* | [**get_all_show_certifications**](schemas/trakt/docs/ShowsApi.md#get_all_show_certifications) | **GET** /shows/{id}/certifications | Get all show certifications
*ShowsApi* | [**get_all_show_comments**](schemas/trakt/docs/ShowsApi.md#get_all_show_comments) | **GET** /shows/{id}/comments/{sort} | Get all show comments
*ShowsApi* | [**get_all_show_translations**](schemas/trakt/docs/ShowsApi.md#get_all_show_translations) | **GET** /shows/{id}/translations/{language} | Get all show translations
*ShowsApi* | [**get_all_videos**](schemas/trakt/docs/ShowsApi.md#get_all_videos) | **GET** /shows/{id}/videos | Get all videos
*ShowsApi* | [**get_last_episode**](schemas/trakt/docs/ShowsApi.md#get_last_episode) | **GET** /shows/{id}/last_episode | Get last episode
*ShowsApi* | [**get_lists_containing_this_show**](schemas/trakt/docs/ShowsApi.md#get_lists_containing_this_show) | **GET** /shows/{id}/lists/{type}/{sort} | Get lists containing this show
*ShowsApi* | [**get_next_episode**](schemas/trakt/docs/ShowsApi.md#get_next_episode) | **GET** /shows/{id}/next_episode | Get next episode
*ShowsApi* | [**get_popular_shows**](schemas/trakt/docs/ShowsApi.md#get_popular_shows) | **GET** /shows/popular | Get popular shows
*ShowsApi* | [**get_recently_updated_show_trakt_ids**](schemas/trakt/docs/ShowsApi.md#get_recently_updated_show_trakt_ids) | **GET** /shows/updates/id/{start_date} | Get recently updated show Trakt IDs
*ShowsApi* | [**get_recently_updated_shows**](schemas/trakt/docs/ShowsApi.md#get_recently_updated_shows) | **GET** /shows/updates/{start_date} | Get recently updated shows
*ShowsApi* | [**get_related_shows**](schemas/trakt/docs/ShowsApi.md#get_related_shows) | **GET** /shows/{id}/related | Get related shows
*ShowsApi* | [**get_show_collection_progress**](schemas/trakt/docs/ShowsApi.md#get_show_collection_progress) | **GET** /shows/{id}/progress/collection | Get show collection progress
*ShowsApi* | [**get_show_ratings**](schemas/trakt/docs/ShowsApi.md#get_show_ratings) | **GET** /shows/{id}/ratings | Get show ratings
*ShowsApi* | [**get_show_stats**](schemas/trakt/docs/ShowsApi.md#get_show_stats) | **GET** /shows/{id}/stats | Get show stats
*ShowsApi* | [**get_show_studios**](schemas/trakt/docs/ShowsApi.md#get_show_studios) | **GET** /shows/{id}/studios | Get show studios
*ShowsApi* | [**get_show_watched_progress**](schemas/trakt/docs/ShowsApi.md#get_show_watched_progress) | **GET** /shows/{id}/progress/watched | Get show watched progress
*ShowsApi* | [**get_the_most_anticipated_shows**](schemas/trakt/docs/ShowsApi.md#get_the_most_anticipated_shows) | **GET** /shows/anticipated | Get the most anticipated shows
*ShowsApi* | [**get_the_most_collected_shows**](schemas/trakt/docs/ShowsApi.md#get_the_most_collected_shows) | **GET** /shows/collected/{period} | Get the most collected shows
*ShowsApi* | [**get_the_most_favorited_shows**](schemas/trakt/docs/ShowsApi.md#get_the_most_favorited_shows) | **GET** /shows/favorited/{period} | Get the most favorited shows
*ShowsApi* | [**get_the_most_played_shows**](schemas/trakt/docs/ShowsApi.md#get_the_most_played_shows) | **GET** /shows/played/{period} | Get the most played shows
*ShowsApi* | [**get_the_most_watched_shows**](schemas/trakt/docs/ShowsApi.md#get_the_most_watched_shows) | **GET** /shows/watched/{period} | Get the most watched shows
*ShowsApi* | [**get_trending_shows**](schemas/trakt/docs/ShowsApi.md#get_trending_shows) | **GET** /shows/trending | Get trending shows
*ShowsApi* | [**get_users_watching_right_now**](schemas/trakt/docs/ShowsApi.md#get_users_watching_right_now) | **GET** /shows/{id}/watching | Get users watching right now
*ShowsApi* | [**refresh_show_metadata**](schemas/trakt/docs/ShowsApi.md#refresh_show_metadata) | **POST** /shows/{id}/refresh | Refresh show metadata
*ShowsApi* | [**reset_show_progress**](schemas/trakt/docs/ShowsApi.md#reset_show_progress) | **POST** /shows/{id}/progress/watched/reset | Reset show progress
*ShowsApi* | [**undo_reset_show_progress**](schemas/trakt/docs/ShowsApi.md#undo_reset_show_progress) | **DELETE** /shows/{id}/progress/watched/reset | Undo reset show progress
*SyncApi* | [**add_items_to_collection**](schemas/trakt/docs/SyncApi.md#add_items_to_collection) | **POST** /sync/collection | Add items to collection
*SyncApi* | [**add_items_to_favorites**](schemas/trakt/docs/SyncApi.md#add_items_to_favorites) | **POST** /sync/favorites | Add items to favorites
*SyncApi* | [**add_items_to_watched_history**](schemas/trakt/docs/SyncApi.md#add_items_to_watched_history) | **POST** /sync/history | Add items to watched history
*SyncApi* | [**add_items_to_watchlist**](schemas/trakt/docs/SyncApi.md#add_items_to_watchlist) | **POST** /sync/watchlist | Add items to watchlist
*SyncApi* | [**add_new_ratings**](schemas/trakt/docs/SyncApi.md#add_new_ratings) | **POST** /sync/ratings | Add new ratings
*SyncApi* | [**get_collection**](schemas/trakt/docs/SyncApi.md#get_collection) | **GET** /sync/collection/{type} | Get collection
*SyncApi* | [**get_favorites**](schemas/trakt/docs/SyncApi.md#get_favorites) | **GET** /sync/favorites/{type}/{sort_by}/{sort_how} | Get favorites
*SyncApi* | [**get_last_activity**](schemas/trakt/docs/SyncApi.md#get_last_activity) | **GET** /sync/last_activities | Get last activity
*SyncApi* | [**get_playback_progress**](schemas/trakt/docs/SyncApi.md#get_playback_progress) | **GET** /sync/playback/{type} | Get playback progress
*SyncApi* | [**get_ratings**](schemas/trakt/docs/SyncApi.md#get_ratings) | **GET** /sync/ratings/{type}/{rating} | Get ratings
*SyncApi* | [**get_watched**](schemas/trakt/docs/SyncApi.md#get_watched) | **GET** /sync/watched/{type} | Get watched
*SyncApi* | [**get_watched_history**](schemas/trakt/docs/SyncApi.md#get_watched_history) | **GET** /sync/history/{type}/{id} | Get watched history
*SyncApi* | [**get_watchlist**](schemas/trakt/docs/SyncApi.md#get_watchlist) | **GET** /sync/watchlist/{type}/{sort_by}/{sort_how} | Get watchlist
*SyncApi* | [**remove_a_playback_item**](schemas/trakt/docs/SyncApi.md#remove_a_playback_item) | **DELETE** /sync/playback/{id} | Remove a playback item
*SyncApi* | [**remove_items_from_collection**](schemas/trakt/docs/SyncApi.md#remove_items_from_collection) | **POST** /sync/collection/remove | Remove items from collection
*SyncApi* | [**remove_items_from_favorites**](schemas/trakt/docs/SyncApi.md#remove_items_from_favorites) | **POST** /sync/favorites/remove | Remove items from favorites
*SyncApi* | [**remove_items_from_history**](schemas/trakt/docs/SyncApi.md#remove_items_from_history) | **POST** /sync/history/remove | Remove items from history
*SyncApi* | [**remove_items_from_watchlist**](schemas/trakt/docs/SyncApi.md#remove_items_from_watchlist) | **POST** /sync/watchlist/remove | Remove items from watchlist
*SyncApi* | [**remove_ratings**](schemas/trakt/docs/SyncApi.md#remove_ratings) | **POST** /sync/ratings/remove | Remove ratings
*SyncApi* | [**reorder_favorited_items**](schemas/trakt/docs/SyncApi.md#reorder_favorited_items) | **POST** /sync/favorites/reorder | Reorder favorited items
*SyncApi* | [**reorder_watchlist_items**](schemas/trakt/docs/SyncApi.md#reorder_watchlist_items) | **POST** /sync/watchlist/reorder | Reorder watchlist items
*SyncApi* | [**update_a_favorite_item**](schemas/trakt/docs/SyncApi.md#update_a_favorite_item) | **PUT** /sync/favorites/{list_item_id} | Update a favorite item
*SyncApi* | [**update_a_watchlist_item**](schemas/trakt/docs/SyncApi.md#update_a_watchlist_item) | **PUT** /sync/watchlist/{list_item_id} | Update a watchlist item
*SyncApi* | [**update_favorites**](schemas/trakt/docs/SyncApi.md#update_favorites) | **PUT** /sync/favorites | Update favorites
*SyncApi* | [**update_watchlist**](schemas/trakt/docs/SyncApi.md#update_watchlist) | **PUT** /sync/watchlist | Update watchlist
*UsersApi* | [**add_hidden_items**](schemas/trakt/docs/UsersApi.md#add_hidden_items) | **POST** /users/hidden/{section} | Add hidden items
*UsersApi* | [**add_items_to_personal_list**](schemas/trakt/docs/UsersApi.md#add_items_to_personal_list) | **POST** /users/{id}/lists/{list_id}/items | Add items to personal list
*UsersApi* | [**approve_follow_request**](schemas/trakt/docs/UsersApi.md#approve_follow_request) | **POST** /users/requests/{id} | Approve follow request
*UsersApi* | [**create_personal_list**](schemas/trakt/docs/UsersApi.md#create_personal_list) | **POST** /users/{id}/lists | Create personal list
*UsersApi* | [**delete_a_users_personal_list**](schemas/trakt/docs/UsersApi.md#delete_a_users_personal_list) | **DELETE** /users/{id}/lists/{list_id} | Delete a user&#39;s personal list
*UsersApi* | [**deny_follow_request**](schemas/trakt/docs/UsersApi.md#deny_follow_request) | **DELETE** /users/requests/{id} | Deny follow request
*UsersApi* | [**follow_this_user**](schemas/trakt/docs/UsersApi.md#follow_this_user) | **POST** /users/{id}/follow | Follow this user
*UsersApi* | [**get_a_users_personal_lists**](schemas/trakt/docs/UsersApi.md#get_a_users_personal_lists) | **GET** /users/{id}/lists | Get a user&#39;s personal lists
*UsersApi* | [**get_all_favorites_comments**](schemas/trakt/docs/UsersApi.md#get_all_favorites_comments) | **GET** /users/{id}/watchlist/comments/{sort} | Get all favorites comments
*UsersApi* | [**get_all_favorites_comments_0**](schemas/trakt/docs/UsersApi.md#get_all_favorites_comments_0) | **GET** /users/{id}/favorites/comments/{sort} | Get all favorites comments
*UsersApi* | [**get_all_list_comments**](schemas/trakt/docs/UsersApi.md#get_all_list_comments) | **GET** /users/{id}/lists/{list_id}/comments/{sort} | Get all list comments
*UsersApi* | [**get_all_lists_a_user_can_collaborate_on**](schemas/trakt/docs/UsersApi.md#get_all_lists_a_user_can_collaborate_on) | **GET** /users/{id}/lists/collaborations | Get all lists a user can collaborate on
*UsersApi* | [**get_all_users_who_liked_a_list**](schemas/trakt/docs/UsersApi.md#get_all_users_who_liked_a_list) | **GET** /users/{id}/lists/{list_id}/likes | Get all users who liked a list
*UsersApi* | [**get_collection**](schemas/trakt/docs/UsersApi.md#get_collection) | **GET** /users/{id}/collection/{type} | Get collection
*UsersApi* | [**get_comments**](schemas/trakt/docs/UsersApi.md#get_comments) | **GET** /users/{id}/comments/{comment_type}/{type} | Get comments
*UsersApi* | [**get_favorites**](schemas/trakt/docs/UsersApi.md#get_favorites) | **GET** /users/{id}/favorites/{type}/{sort_by}/{sort_how} | Get favorites
*UsersApi* | [**get_follow_requests**](schemas/trakt/docs/UsersApi.md#get_follow_requests) | **GET** /users/requests | Get follow requests
*UsersApi* | [**get_followers**](schemas/trakt/docs/UsersApi.md#get_followers) | **GET** /users/{id}/followers | Get followers
*UsersApi* | [**get_following**](schemas/trakt/docs/UsersApi.md#get_following) | **GET** /users/{id}/following | Get following
*UsersApi* | [**get_friends**](schemas/trakt/docs/UsersApi.md#get_friends) | **GET** /users/{id}/friends | Get friends
*UsersApi* | [**get_hidden_items**](schemas/trakt/docs/UsersApi.md#get_hidden_items) | **GET** /users/hidden/{section} | Get hidden items
*UsersApi* | [**get_items_on_a_personal_list**](schemas/trakt/docs/UsersApi.md#get_items_on_a_personal_list) | **GET** /users/{id}/lists/{list_id}/items/{type}/{sort_by}/{sort_how} | Get items on a personal list
*UsersApi* | [**get_likes**](schemas/trakt/docs/UsersApi.md#get_likes) | **GET** /users/{id}/likes/{type} | Get likes
*UsersApi* | [**get_notes**](schemas/trakt/docs/UsersApi.md#get_notes) | **GET** /users/{id}/notes/{type} | Get notes
*UsersApi* | [**get_pending_following_requests**](schemas/trakt/docs/UsersApi.md#get_pending_following_requests) | **GET** /users/requests/following | Get pending following requests
*UsersApi* | [**get_personal_list**](schemas/trakt/docs/UsersApi.md#get_personal_list) | **GET** /users/{id}/lists/{list_id} | Get personal list
*UsersApi* | [**get_ratings**](schemas/trakt/docs/UsersApi.md#get_ratings) | **GET** /users/{id}/ratings/{type}/{rating} | Get ratings
*UsersApi* | [**get_saved_filters**](schemas/trakt/docs/UsersApi.md#get_saved_filters) | **GET** /users/saved_filters/{section} | Get saved filters
*UsersApi* | [**get_stats**](schemas/trakt/docs/UsersApi.md#get_stats) | **GET** /users/{id}/stats | Get stats
*UsersApi* | [**get_user_profile**](schemas/trakt/docs/UsersApi.md#get_user_profile) | **GET** /users/{id} | Get user profile
*UsersApi* | [**get_watched**](schemas/trakt/docs/UsersApi.md#get_watched) | **GET** /users/{id}/watched/{type} | Get watched
*UsersApi* | [**get_watched_history**](schemas/trakt/docs/UsersApi.md#get_watched_history) | **GET** /users/{id}/history/{type}/{item_id} | Get watched history
*UsersApi* | [**get_watching**](schemas/trakt/docs/UsersApi.md#get_watching) | **GET** /users/{id}/watching | Get watching
*UsersApi* | [**get_watchlist**](schemas/trakt/docs/UsersApi.md#get_watchlist) | **GET** /users/{id}/watchlist/{type}/{sort_by}/{sort_how} | Get watchlist
*UsersApi* | [**like_a_list**](schemas/trakt/docs/UsersApi.md#like_a_list) | **POST** /users/{id}/lists/{list_id}/like | Like a list
*UsersApi* | [**remove_hidden_items**](schemas/trakt/docs/UsersApi.md#remove_hidden_items) | **POST** /users/hidden/{section}/remove | Remove hidden items
*UsersApi* | [**remove_items_from_personal_list**](schemas/trakt/docs/UsersApi.md#remove_items_from_personal_list) | **POST** /users/{id}/lists/{list_id}/items/remove | Remove items from personal list
*UsersApi* | [**remove_like_on_a_list**](schemas/trakt/docs/UsersApi.md#remove_like_on_a_list) | **DELETE** /users/{id}/lists/{list_id}/like | Remove like on a list
*UsersApi* | [**reorder_a_users_lists**](schemas/trakt/docs/UsersApi.md#reorder_a_users_lists) | **POST** /users/{id}/lists/reorder | Reorder a user&#39;s lists
*UsersApi* | [**reorder_items_on_a_list**](schemas/trakt/docs/UsersApi.md#reorder_items_on_a_list) | **POST** /users/{id}/lists/{list_id}/items/reorder | Reorder items on a list
*UsersApi* | [**retrieve_settings**](schemas/trakt/docs/UsersApi.md#retrieve_settings) | **GET** /users/settings | Retrieve settings
*UsersApi* | [**unfollow_this_user**](schemas/trakt/docs/UsersApi.md#unfollow_this_user) | **DELETE** /users/{id}/follow | Unfollow this user
*UsersApi* | [**update_a_list_item**](schemas/trakt/docs/UsersApi.md#update_a_list_item) | **PUT** /users/{id}/lists/{list_id}/items/{list_item_id} | Update a list item
*UsersApi* | [**update_personal_list**](schemas/trakt/docs/UsersApi.md#update_personal_list) | **PUT** /users/{id}/lists/{list_id} | Update personal list


## Documentation For Models

 - [AddHiddenItems201Response](schemas/trakt/docs/AddHiddenItems201Response.md)
 - [AddHiddenItems201ResponseAdded](schemas/trakt/docs/AddHiddenItems201ResponseAdded.md)
 - [AddHiddenItems201ResponseNotFound](schemas/trakt/docs/AddHiddenItems201ResponseNotFound.md)
 - [AddHiddenItemsRequest](schemas/trakt/docs/AddHiddenItemsRequest.md)
 - [AddHiddenItemsRequestSeasonsInner](schemas/trakt/docs/AddHiddenItemsRequestSeasonsInner.md)
 - [AddHiddenItemsRequestSeasonsInnerIds](schemas/trakt/docs/AddHiddenItemsRequestSeasonsInnerIds.md)
 - [AddHiddenItemsRequestShowsInner](schemas/trakt/docs/AddHiddenItemsRequestShowsInner.md)
 - [AddHiddenItemsRequestShowsInnerSeasonsInner](schemas/trakt/docs/AddHiddenItemsRequestShowsInnerSeasonsInner.md)
 - [AddItemsToCollection201Response](schemas/trakt/docs/AddItemsToCollection201Response.md)
 - [AddItemsToCollection201ResponseAdded](schemas/trakt/docs/AddItemsToCollection201ResponseAdded.md)
 - [AddItemsToCollection201ResponseNotFound](schemas/trakt/docs/AddItemsToCollection201ResponseNotFound.md)
 - [AddItemsToCollection201ResponseNotFoundMoviesInner](schemas/trakt/docs/AddItemsToCollection201ResponseNotFoundMoviesInner.md)
 - [AddItemsToCollection201ResponseNotFoundMoviesInnerIds](schemas/trakt/docs/AddItemsToCollection201ResponseNotFoundMoviesInnerIds.md)
 - [AddItemsToCollectionRequest](schemas/trakt/docs/AddItemsToCollectionRequest.md)
 - [AddItemsToCollectionRequestEpisodesInner](schemas/trakt/docs/AddItemsToCollectionRequestEpisodesInner.md)
 - [AddItemsToCollectionRequestMoviesInner](schemas/trakt/docs/AddItemsToCollectionRequestMoviesInner.md)
 - [AddItemsToCollectionRequestSeasonsInner](schemas/trakt/docs/AddItemsToCollectionRequestSeasonsInner.md)
 - [AddItemsToCollectionRequestShowsInner](schemas/trakt/docs/AddItemsToCollectionRequestShowsInner.md)
 - [AddItemsToCollectionRequestShowsInnerSeasonsInner](schemas/trakt/docs/AddItemsToCollectionRequestShowsInnerSeasonsInner.md)
 - [AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner](schemas/trakt/docs/AddItemsToCollectionRequestShowsInnerSeasonsInnerEpisodesInner.md)
 - [AddItemsToFavorites201Response](schemas/trakt/docs/AddItemsToFavorites201Response.md)
 - [AddItemsToFavorites201ResponseAdded](schemas/trakt/docs/AddItemsToFavorites201ResponseAdded.md)
 - [AddItemsToFavorites201ResponseNotFound](schemas/trakt/docs/AddItemsToFavorites201ResponseNotFound.md)
 - [AddItemsToFavoritesRequest](schemas/trakt/docs/AddItemsToFavoritesRequest.md)
 - [AddItemsToFavoritesRequestShowsInner](schemas/trakt/docs/AddItemsToFavoritesRequestShowsInner.md)
 - [AddItemsToPersonalList201Response](schemas/trakt/docs/AddItemsToPersonalList201Response.md)
 - [AddItemsToPersonalList201ResponseAdded](schemas/trakt/docs/AddItemsToPersonalList201ResponseAdded.md)
 - [AddItemsToPersonalList201ResponseNotFound](schemas/trakt/docs/AddItemsToPersonalList201ResponseNotFound.md)
 - [AddItemsToPersonalListRequest](schemas/trakt/docs/AddItemsToPersonalListRequest.md)
 - [AddItemsToPersonalListRequestMoviesInner](schemas/trakt/docs/AddItemsToPersonalListRequestMoviesInner.md)
 - [AddItemsToPersonalListRequestMoviesInnerIds](schemas/trakt/docs/AddItemsToPersonalListRequestMoviesInnerIds.md)
 - [AddItemsToPersonalListRequestShowsInner](schemas/trakt/docs/AddItemsToPersonalListRequestShowsInner.md)
 - [AddItemsToWatchedHistory201Response](schemas/trakt/docs/AddItemsToWatchedHistory201Response.md)
 - [AddItemsToWatchedHistoryRequest](schemas/trakt/docs/AddItemsToWatchedHistoryRequest.md)
 - [AddItemsToWatchedHistoryRequestEpisodesInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestEpisodesInner.md)
 - [AddItemsToWatchedHistoryRequestMoviesInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestMoviesInner.md)
 - [AddItemsToWatchedHistoryRequestSeasonsInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestSeasonsInner.md)
 - [AddItemsToWatchedHistoryRequestShowsInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestShowsInner.md)
 - [AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestShowsInnerSeasonsInner.md)
 - [AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner](schemas/trakt/docs/AddItemsToWatchedHistoryRequestShowsInnerSeasonsInnerEpisodesInner.md)
 - [AddItemsToWatchlist201Response](schemas/trakt/docs/AddItemsToWatchlist201Response.md)
 - [AddItemsToWatchlist201ResponseList](schemas/trakt/docs/AddItemsToWatchlist201ResponseList.md)
 - [AddItemsToWatchlistRequest](schemas/trakt/docs/AddItemsToWatchlistRequest.md)
 - [AddItemsToWatchlistRequestMoviesInner](schemas/trakt/docs/AddItemsToWatchlistRequestMoviesInner.md)
 - [AddItemsToWatchlistRequestShowsInner](schemas/trakt/docs/AddItemsToWatchlistRequestShowsInner.md)
 - [AddNewRatings201Response](schemas/trakt/docs/AddNewRatings201Response.md)
 - [AddNewRatings201ResponseAdded](schemas/trakt/docs/AddNewRatings201ResponseAdded.md)
 - [AddNewRatings201ResponseNotFound](schemas/trakt/docs/AddNewRatings201ResponseNotFound.md)
 - [AddNewRatings201ResponseNotFoundMoviesInner](schemas/trakt/docs/AddNewRatings201ResponseNotFoundMoviesInner.md)
 - [AddNewRatingsRequest](schemas/trakt/docs/AddNewRatingsRequest.md)
 - [AddNewRatingsRequestEpisodesInner](schemas/trakt/docs/AddNewRatingsRequestEpisodesInner.md)
 - [AddNewRatingsRequestMoviesInner](schemas/trakt/docs/AddNewRatingsRequestMoviesInner.md)
 - [AddNewRatingsRequestSeasonsInner](schemas/trakt/docs/AddNewRatingsRequestSeasonsInner.md)
 - [AddNewRatingsRequestShowsInner](schemas/trakt/docs/AddNewRatingsRequestShowsInner.md)
 - [AddNewRatingsRequestShowsInnerSeasonsInner](schemas/trakt/docs/AddNewRatingsRequestShowsInnerSeasonsInner.md)
 - [AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner](schemas/trakt/docs/AddNewRatingsRequestShowsInnerSeasonsInnerEpisodesInner.md)
 - [AddNotes201Response](schemas/trakt/docs/AddNotes201Response.md)
 - [AddNotesRequest](schemas/trakt/docs/AddNotesRequest.md)
 - [ApproveFollowRequest200Response](schemas/trakt/docs/ApproveFollowRequest200Response.md)
 - [CheckIntoAnItem201Response](schemas/trakt/docs/CheckIntoAnItem201Response.md)
 - [CheckIntoAnItem201ResponseEpisode](schemas/trakt/docs/CheckIntoAnItem201ResponseEpisode.md)
 - [CheckIntoAnItem201ResponseEpisodeIds](schemas/trakt/docs/CheckIntoAnItem201ResponseEpisodeIds.md)
 - [CheckIntoAnItem409Response](schemas/trakt/docs/CheckIntoAnItem409Response.md)
 - [CheckIntoAnItemRequest](schemas/trakt/docs/CheckIntoAnItemRequest.md)
 - [CheckIntoAnItemRequestSharing](schemas/trakt/docs/CheckIntoAnItemRequestSharing.md)
 - [CreatePersonalList201Response](schemas/trakt/docs/CreatePersonalList201Response.md)
 - [CreatePersonalListRequest](schemas/trakt/docs/CreatePersonalListRequest.md)
 - [ExchangeRefreshTokenForAccessToken200Response](schemas/trakt/docs/ExchangeRefreshTokenForAccessToken200Response.md)
 - [ExchangeRefreshTokenForAccessToken401Response](schemas/trakt/docs/ExchangeRefreshTokenForAccessToken401Response.md)
 - [ExchangeRefreshTokenForAccessTokenRequest](schemas/trakt/docs/ExchangeRefreshTokenForAccessTokenRequest.md)
 - [FollowThisUser201Response](schemas/trakt/docs/FollowThisUser201Response.md)
 - [GenerateNewDeviceCodes200Response](schemas/trakt/docs/GenerateNewDeviceCodes200Response.md)
 - [GenerateNewDeviceCodesRequest](schemas/trakt/docs/GenerateNewDeviceCodesRequest.md)
 - [GetACommentOrReply200Response](schemas/trakt/docs/GetACommentOrReply200Response.md)
 - [GetACommentOrReply200ResponseUserStats](schemas/trakt/docs/GetACommentOrReply200ResponseUserStats.md)
 - [GetAMovie200Response](schemas/trakt/docs/GetAMovie200Response.md)
 - [GetANote200Response](schemas/trakt/docs/GetANote200Response.md)
 - [GetASingleEpisodeForAShow200Response](schemas/trakt/docs/GetASingleEpisodeForAShow200Response.md)
 - [GetASinglePerson200Response](schemas/trakt/docs/GetASinglePerson200Response.md)
 - [GetASinglePerson200ResponseSocialIds](schemas/trakt/docs/GetASinglePerson200ResponseSocialIds.md)
 - [GetASingleShow200Response](schemas/trakt/docs/GetASingleShow200Response.md)
 - [GetASingleShow200ResponseAirs](schemas/trakt/docs/GetASingleShow200ResponseAirs.md)
 - [GetAUserSPersonalLists200ResponseInner](schemas/trakt/docs/GetAUserSPersonalLists200ResponseInner.md)
 - [GetAllEpisodesForASingleSeason200ResponseInner](schemas/trakt/docs/GetAllEpisodesForASingleSeason200ResponseInner.md)
 - [GetAllListComments200ResponseInner](schemas/trakt/docs/GetAllListComments200ResponseInner.md)
 - [GetAllListsAUserCanCollaborateOn200ResponseInner](schemas/trakt/docs/GetAllListsAUserCanCollaborateOn200ResponseInner.md)
 - [GetAllMovieAliases200ResponseInner](schemas/trakt/docs/GetAllMovieAliases200ResponseInner.md)
 - [GetAllMovieReleases200ResponseInner](schemas/trakt/docs/GetAllMovieReleases200ResponseInner.md)
 - [GetAllMovieTranslations200ResponseInner](schemas/trakt/docs/GetAllMovieTranslations200ResponseInner.md)
 - [GetAllPeopleForAMovie200Response](schemas/trakt/docs/GetAllPeopleForAMovie200Response.md)
 - [GetAllPeopleForAMovie200ResponseCastInner](schemas/trakt/docs/GetAllPeopleForAMovie200ResponseCastInner.md)
 - [GetAllPeopleForAMovie200ResponseCrew](schemas/trakt/docs/GetAllPeopleForAMovie200ResponseCrew.md)
 - [GetAllPeopleForAMovie200ResponseCrewArtInner](schemas/trakt/docs/GetAllPeopleForAMovie200ResponseCrewArtInner.md)
 - [GetAllPeopleForAMovie200ResponseCrewDirectingInner](schemas/trakt/docs/GetAllPeopleForAMovie200ResponseCrewDirectingInner.md)
 - [GetAllPeopleForAMovie200ResponseCrewProductionInner](schemas/trakt/docs/GetAllPeopleForAMovie200ResponseCrewProductionInner.md)
 - [GetAllPeopleForASeason200Response](schemas/trakt/docs/GetAllPeopleForASeason200Response.md)
 - [GetAllPeopleForASeason200ResponseCrew](schemas/trakt/docs/GetAllPeopleForASeason200ResponseCrew.md)
 - [GetAllPeopleForAShow200Response](schemas/trakt/docs/GetAllPeopleForAShow200Response.md)
 - [GetAllPeopleForAShow200ResponseCastInner](schemas/trakt/docs/GetAllPeopleForAShow200ResponseCastInner.md)
 - [GetAllPeopleForAShow200ResponseCrew](schemas/trakt/docs/GetAllPeopleForAShow200ResponseCrew.md)
 - [GetAllPeopleForAShow200ResponseCrewArtInner](schemas/trakt/docs/GetAllPeopleForAShow200ResponseCrewArtInner.md)
 - [GetAllPeopleForAShow200ResponseCrewVisualEffectsInner](schemas/trakt/docs/GetAllPeopleForAShow200ResponseCrewVisualEffectsInner.md)
 - [GetAllPeopleForAnEpisode200Response](schemas/trakt/docs/GetAllPeopleForAnEpisode200Response.md)
 - [GetAllPeopleForAnEpisode200ResponseCrew](schemas/trakt/docs/GetAllPeopleForAnEpisode200ResponseCrew.md)
 - [GetAllPeopleForAnEpisode200ResponseGuestStarsInner](schemas/trakt/docs/GetAllPeopleForAnEpisode200ResponseGuestStarsInner.md)
 - [GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson](schemas/trakt/docs/GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPerson.md)
 - [GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds](schemas/trakt/docs/GetAllPeopleForAnEpisode200ResponseGuestStarsInnerPersonIds.md)
 - [GetAllSeasonTranslations200ResponseInner](schemas/trakt/docs/GetAllSeasonTranslations200ResponseInner.md)
 - [GetAllSeasonsForAShow200ResponseInner](schemas/trakt/docs/GetAllSeasonsForAShow200ResponseInner.md)
 - [GetAllSeasonsForAShow200ResponseInnerEpisodesInner](schemas/trakt/docs/GetAllSeasonsForAShow200ResponseInnerEpisodesInner.md)
 - [GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds](schemas/trakt/docs/GetAllSeasonsForAShow200ResponseInnerEpisodesInnerIds.md)
 - [GetAllSeasonsForAShow200ResponseInnerIds](schemas/trakt/docs/GetAllSeasonsForAShow200ResponseInnerIds.md)
 - [GetAllShowCertifications200ResponseInner](schemas/trakt/docs/GetAllShowCertifications200ResponseInner.md)
 - [GetAllShowTranslations200ResponseInner](schemas/trakt/docs/GetAllShowTranslations200ResponseInner.md)
 - [GetAllUsersWhoLikedAComment200ResponseInner](schemas/trakt/docs/GetAllUsersWhoLikedAComment200ResponseInner.md)
 - [GetAllVideos200ResponseInner](schemas/trakt/docs/GetAllVideos200ResponseInner.md)
 - [GetCertifications200Response](schemas/trakt/docs/GetCertifications200Response.md)
 - [GetCertifications200ResponseUsInner](schemas/trakt/docs/GetCertifications200ResponseUsInner.md)
 - [GetCollection200ResponseInner](schemas/trakt/docs/GetCollection200ResponseInner.md)
 - [GetCollection200ResponseInnerSeasonsInner](schemas/trakt/docs/GetCollection200ResponseInnerSeasonsInner.md)
 - [GetCollection200ResponseInnerSeasonsInnerEpisodesInner](schemas/trakt/docs/GetCollection200ResponseInnerSeasonsInnerEpisodesInner.md)
 - [GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata](schemas/trakt/docs/GetCollection200ResponseInnerSeasonsInnerEpisodesInnerMetadata.md)
 - [GetCountries200ResponseInner](schemas/trakt/docs/GetCountries200ResponseInner.md)
 - [GetFavorites200ResponseInner](schemas/trakt/docs/GetFavorites200ResponseInner.md)
 - [GetFollowers200ResponseInner](schemas/trakt/docs/GetFollowers200ResponseInner.md)
 - [GetFriends200ResponseInner](schemas/trakt/docs/GetFriends200ResponseInner.md)
 - [GetGenres200ResponseInner](schemas/trakt/docs/GetGenres200ResponseInner.md)
 - [GetGenres200ResponseInnerSubgenresInner](schemas/trakt/docs/GetGenres200ResponseInnerSubgenresInner.md)
 - [GetHiddenItems200ResponseInner](schemas/trakt/docs/GetHiddenItems200ResponseInner.md)
 - [GetIDLookupResults200ResponseInner](schemas/trakt/docs/GetIDLookupResults200ResponseInner.md)
 - [GetItemsOnAList200ResponseInner](schemas/trakt/docs/GetItemsOnAList200ResponseInner.md)
 - [GetItemsOnAList200ResponseInnerEpisode](schemas/trakt/docs/GetItemsOnAList200ResponseInnerEpisode.md)
 - [GetItemsOnAList200ResponseInnerEpisodeIds](schemas/trakt/docs/GetItemsOnAList200ResponseInnerEpisodeIds.md)
 - [GetItemsOnAList200ResponseInnerPerson](schemas/trakt/docs/GetItemsOnAList200ResponseInnerPerson.md)
 - [GetItemsOnAList200ResponseInnerSeason](schemas/trakt/docs/GetItemsOnAList200ResponseInnerSeason.md)
 - [GetItemsOnAList200ResponseInnerSeasonIds](schemas/trakt/docs/GetItemsOnAList200ResponseInnerSeasonIds.md)
 - [GetItemsOnAPersonalList200ResponseInner](schemas/trakt/docs/GetItemsOnAPersonalList200ResponseInner.md)
 - [GetLastActivity200Response](schemas/trakt/docs/GetLastActivity200Response.md)
 - [GetLastActivity200ResponseAccount](schemas/trakt/docs/GetLastActivity200ResponseAccount.md)
 - [GetLastActivity200ResponseComments](schemas/trakt/docs/GetLastActivity200ResponseComments.md)
 - [GetLastActivity200ResponseEpisodes](schemas/trakt/docs/GetLastActivity200ResponseEpisodes.md)
 - [GetLastActivity200ResponseLists](schemas/trakt/docs/GetLastActivity200ResponseLists.md)
 - [GetLastActivity200ResponseMovies](schemas/trakt/docs/GetLastActivity200ResponseMovies.md)
 - [GetLastActivity200ResponseSeasons](schemas/trakt/docs/GetLastActivity200ResponseSeasons.md)
 - [GetLastActivity200ResponseShows](schemas/trakt/docs/GetLastActivity200ResponseShows.md)
 - [GetLastActivity200ResponseWatchlist](schemas/trakt/docs/GetLastActivity200ResponseWatchlist.md)
 - [GetLastEpisode200Response](schemas/trakt/docs/GetLastEpisode200Response.md)
 - [GetLikes200ResponseInner](schemas/trakt/docs/GetLikes200ResponseInner.md)
 - [GetLikes200ResponseInnerList](schemas/trakt/docs/GetLikes200ResponseInnerList.md)
 - [GetList200Response](schemas/trakt/docs/GetList200Response.md)
 - [GetMovieCredits200Response](schemas/trakt/docs/GetMovieCredits200Response.md)
 - [GetMovieCredits200ResponseCastInner](schemas/trakt/docs/GetMovieCredits200ResponseCastInner.md)
 - [GetMovieCredits200ResponseCrew](schemas/trakt/docs/GetMovieCredits200ResponseCrew.md)
 - [GetMovieCredits200ResponseCrewDirectingInner](schemas/trakt/docs/GetMovieCredits200ResponseCrewDirectingInner.md)
 - [GetMovieRatings200Response](schemas/trakt/docs/GetMovieRatings200Response.md)
 - [GetMovieRatings200ResponseDistribution](schemas/trakt/docs/GetMovieRatings200ResponseDistribution.md)
 - [GetMovieRecommendations200ResponseInner](schemas/trakt/docs/GetMovieRecommendations200ResponseInner.md)
 - [GetMovieRecommendations200ResponseInnerFavoritedByInner](schemas/trakt/docs/GetMovieRecommendations200ResponseInnerFavoritedByInner.md)
 - [GetMovieStats200Response](schemas/trakt/docs/GetMovieStats200Response.md)
 - [GetMovieStudios200ResponseInner](schemas/trakt/docs/GetMovieStudios200ResponseInner.md)
 - [GetMovieStudios200ResponseInnerIds](schemas/trakt/docs/GetMovieStudios200ResponseInnerIds.md)
 - [GetMovies200ResponseInner](schemas/trakt/docs/GetMovies200ResponseInner.md)
 - [GetMovies200ResponseInnerMovie](schemas/trakt/docs/GetMovies200ResponseInnerMovie.md)
 - [GetMovies200ResponseInnerMovieIds](schemas/trakt/docs/GetMovies200ResponseInnerMovieIds.md)
 - [GetNetworks200ResponseInner](schemas/trakt/docs/GetNetworks200ResponseInner.md)
 - [GetNetworks200ResponseInnerIds](schemas/trakt/docs/GetNetworks200ResponseInnerIds.md)
 - [GetNewShows200ResponseInner](schemas/trakt/docs/GetNewShows200ResponseInner.md)
 - [GetNewShows200ResponseInnerEpisode](schemas/trakt/docs/GetNewShows200ResponseInnerEpisode.md)
 - [GetNewShows200ResponseInnerEpisodeIds](schemas/trakt/docs/GetNewShows200ResponseInnerEpisodeIds.md)
 - [GetNextEpisode200Response](schemas/trakt/docs/GetNextEpisode200Response.md)
 - [GetNotes200ResponseInner](schemas/trakt/docs/GetNotes200ResponseInner.md)
 - [GetNotes200ResponseInnerAttachedTo](schemas/trakt/docs/GetNotes200ResponseInnerAttachedTo.md)
 - [GetNotes200ResponseInnerNote](schemas/trakt/docs/GetNotes200ResponseInnerNote.md)
 - [GetNotes200ResponseInnerNoteUser](schemas/trakt/docs/GetNotes200ResponseInnerNoteUser.md)
 - [GetNotes200ResponseInnerNoteUserIds](schemas/trakt/docs/GetNotes200ResponseInnerNoteUserIds.md)
 - [GetPendingFollowingRequests200ResponseInner](schemas/trakt/docs/GetPendingFollowingRequests200ResponseInner.md)
 - [GetPlaybackProgress200ResponseInner](schemas/trakt/docs/GetPlaybackProgress200ResponseInner.md)
 - [GetPopularMovies200ResponseInner](schemas/trakt/docs/GetPopularMovies200ResponseInner.md)
 - [GetPopularShows200ResponseInner](schemas/trakt/docs/GetPopularShows200ResponseInner.md)
 - [GetRatings200ResponseInner](schemas/trakt/docs/GetRatings200ResponseInner.md)
 - [GetRecentlyUpdatedMovies200ResponseInner](schemas/trakt/docs/GetRecentlyUpdatedMovies200ResponseInner.md)
 - [GetRecentlyUpdatedPeople200ResponseInner](schemas/trakt/docs/GetRecentlyUpdatedPeople200ResponseInner.md)
 - [GetRecentlyUpdatedShows200ResponseInner](schemas/trakt/docs/GetRecentlyUpdatedShows200ResponseInner.md)
 - [GetRepliesForAComment200ResponseInner](schemas/trakt/docs/GetRepliesForAComment200ResponseInner.md)
 - [GetSavedFilters200ResponseInner](schemas/trakt/docs/GetSavedFilters200ResponseInner.md)
 - [GetSeasonPremieres200ResponseInner](schemas/trakt/docs/GetSeasonPremieres200ResponseInner.md)
 - [GetSeasonRatings200Response](schemas/trakt/docs/GetSeasonRatings200Response.md)
 - [GetSeasonStats200Response](schemas/trakt/docs/GetSeasonStats200Response.md)
 - [GetShowCollectionProgress200Response](schemas/trakt/docs/GetShowCollectionProgress200Response.md)
 - [GetShowCollectionProgress200ResponseSeasonsInner](schemas/trakt/docs/GetShowCollectionProgress200ResponseSeasonsInner.md)
 - [GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner](schemas/trakt/docs/GetShowCollectionProgress200ResponseSeasonsInnerEpisodesInner.md)
 - [GetShowCredits200Response](schemas/trakt/docs/GetShowCredits200Response.md)
 - [GetShowCredits200ResponseCastInner](schemas/trakt/docs/GetShowCredits200ResponseCastInner.md)
 - [GetShowCredits200ResponseCrew](schemas/trakt/docs/GetShowCredits200ResponseCrew.md)
 - [GetShowCredits200ResponseCrewProductionInner](schemas/trakt/docs/GetShowCredits200ResponseCrewProductionInner.md)
 - [GetShowRatings200Response](schemas/trakt/docs/GetShowRatings200Response.md)
 - [GetShowRecommendations200ResponseInner](schemas/trakt/docs/GetShowRecommendations200ResponseInner.md)
 - [GetShowStats200Response](schemas/trakt/docs/GetShowStats200Response.md)
 - [GetShowWatchedProgress200Response](schemas/trakt/docs/GetShowWatchedProgress200Response.md)
 - [GetShowWatchedProgress200ResponseSeasonsInner](schemas/trakt/docs/GetShowWatchedProgress200ResponseSeasonsInner.md)
 - [GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner](schemas/trakt/docs/GetShowWatchedProgress200ResponseSeasonsInnerEpisodesInner.md)
 - [GetShows200ResponseInner](schemas/trakt/docs/GetShows200ResponseInner.md)
 - [GetShows200ResponseInnerEpisode](schemas/trakt/docs/GetShows200ResponseInnerEpisode.md)
 - [GetShows200ResponseInnerEpisodeIds](schemas/trakt/docs/GetShows200ResponseInnerEpisodeIds.md)
 - [GetShows200ResponseInnerShow](schemas/trakt/docs/GetShows200ResponseInnerShow.md)
 - [GetShows200ResponseInnerShowIds](schemas/trakt/docs/GetShows200ResponseInnerShowIds.md)
 - [GetSingleSeasonsForAShow200Response](schemas/trakt/docs/GetSingleSeasonsForAShow200Response.md)
 - [GetStats200Response](schemas/trakt/docs/GetStats200Response.md)
 - [GetStats200ResponseMovies](schemas/trakt/docs/GetStats200ResponseMovies.md)
 - [GetStats200ResponseNetwork](schemas/trakt/docs/GetStats200ResponseNetwork.md)
 - [GetStats200ResponseRatings](schemas/trakt/docs/GetStats200ResponseRatings.md)
 - [GetStats200ResponseSeasons](schemas/trakt/docs/GetStats200ResponseSeasons.md)
 - [GetStats200ResponseShows](schemas/trakt/docs/GetStats200ResponseShows.md)
 - [GetTextQueryResults200ResponseInner](schemas/trakt/docs/GetTextQueryResults200ResponseInner.md)
 - [GetTheAttachedItem200Response](schemas/trakt/docs/GetTheAttachedItem200Response.md)
 - [GetTheAttachedItem200ResponseAttachedTo](schemas/trakt/docs/GetTheAttachedItem200ResponseAttachedTo.md)
 - [GetTheAttachedMediaItem200Response](schemas/trakt/docs/GetTheAttachedMediaItem200Response.md)
 - [GetTheMostAnticipatedMovies200ResponseInner](schemas/trakt/docs/GetTheMostAnticipatedMovies200ResponseInner.md)
 - [GetTheMostAnticipatedShows200ResponseInner](schemas/trakt/docs/GetTheMostAnticipatedShows200ResponseInner.md)
 - [GetTheMostAnticipatedShows200ResponseInnerShow](schemas/trakt/docs/GetTheMostAnticipatedShows200ResponseInnerShow.md)
 - [GetTheMostAnticipatedShows200ResponseInnerShowIds](schemas/trakt/docs/GetTheMostAnticipatedShows200ResponseInnerShowIds.md)
 - [GetTheMostFavoritedMovies200ResponseInner](schemas/trakt/docs/GetTheMostFavoritedMovies200ResponseInner.md)
 - [GetTheMostFavoritedShows200ResponseInner](schemas/trakt/docs/GetTheMostFavoritedShows200ResponseInner.md)
 - [GetTheMostPlayedMovies200ResponseInner](schemas/trakt/docs/GetTheMostPlayedMovies200ResponseInner.md)
 - [GetTheMostPlayedShows200ResponseInner](schemas/trakt/docs/GetTheMostPlayedShows200ResponseInner.md)
 - [GetTheWeekendBoxOffice200ResponseInner](schemas/trakt/docs/GetTheWeekendBoxOffice200ResponseInner.md)
 - [GetTrendingComments200ResponseInner](schemas/trakt/docs/GetTrendingComments200ResponseInner.md)
 - [GetTrendingComments200ResponseInnerComment](schemas/trakt/docs/GetTrendingComments200ResponseInnerComment.md)
 - [GetTrendingComments200ResponseInnerCommentUserStats](schemas/trakt/docs/GetTrendingComments200ResponseInnerCommentUserStats.md)
 - [GetTrendingComments200ResponseInnerList](schemas/trakt/docs/GetTrendingComments200ResponseInnerList.md)
 - [GetTrendingComments200ResponseInnerListIds](schemas/trakt/docs/GetTrendingComments200ResponseInnerListIds.md)
 - [GetTrendingComments200ResponseInnerSeason](schemas/trakt/docs/GetTrendingComments200ResponseInnerSeason.md)
 - [GetTrendingComments200ResponseInnerSeasonIds](schemas/trakt/docs/GetTrendingComments200ResponseInnerSeasonIds.md)
 - [GetTrendingLists200ResponseInner](schemas/trakt/docs/GetTrendingLists200ResponseInner.md)
 - [GetTrendingLists200ResponseInnerList](schemas/trakt/docs/GetTrendingLists200ResponseInnerList.md)
 - [GetTrendingMovies200ResponseInner](schemas/trakt/docs/GetTrendingMovies200ResponseInner.md)
 - [GetTrendingShows200ResponseInner](schemas/trakt/docs/GetTrendingShows200ResponseInner.md)
 - [GetUserProfile200Response](schemas/trakt/docs/GetUserProfile200Response.md)
 - [GetUsersWatchingRightNow200ResponseInner](schemas/trakt/docs/GetUsersWatchingRightNow200ResponseInner.md)
 - [GetWatched200ResponseInner](schemas/trakt/docs/GetWatched200ResponseInner.md)
 - [GetWatchedHistory200ResponseInner](schemas/trakt/docs/GetWatchedHistory200ResponseInner.md)
 - [GetWatching200Response](schemas/trakt/docs/GetWatching200Response.md)
 - [GetWatchlist200ResponseInner](schemas/trakt/docs/GetWatchlist200ResponseInner.md)
 - [PollForTheAccessTokenRequest](schemas/trakt/docs/PollForTheAccessTokenRequest.md)
 - [PostAComment201Response](schemas/trakt/docs/PostAComment201Response.md)
 - [PostAComment201ResponseUser](schemas/trakt/docs/PostAComment201ResponseUser.md)
 - [PostAComment201ResponseUserIds](schemas/trakt/docs/PostAComment201ResponseUserIds.md)
 - [PostAComment201ResponseUserStats](schemas/trakt/docs/PostAComment201ResponseUserStats.md)
 - [PostACommentRequest](schemas/trakt/docs/PostACommentRequest.md)
 - [PostACommentRequestSharing](schemas/trakt/docs/PostACommentRequestSharing.md)
 - [PostAReplyForAComment201Response](schemas/trakt/docs/PostAReplyForAComment201Response.md)
 - [PostAReplyForACommentRequest](schemas/trakt/docs/PostAReplyForACommentRequest.md)
 - [RemoveHiddenItems200Response](schemas/trakt/docs/RemoveHiddenItems200Response.md)
 - [RemoveHiddenItemsRequest](schemas/trakt/docs/RemoveHiddenItemsRequest.md)
 - [RemoveHiddenItemsRequestShowsInner](schemas/trakt/docs/RemoveHiddenItemsRequestShowsInner.md)
 - [RemoveItemsFromCollection200Response](schemas/trakt/docs/RemoveItemsFromCollection200Response.md)
 - [RemoveItemsFromCollectionRequest](schemas/trakt/docs/RemoveItemsFromCollectionRequest.md)
 - [RemoveItemsFromCollectionRequestMoviesInner](schemas/trakt/docs/RemoveItemsFromCollectionRequestMoviesInner.md)
 - [RemoveItemsFromCollectionRequestShowsInner](schemas/trakt/docs/RemoveItemsFromCollectionRequestShowsInner.md)
 - [RemoveItemsFromCollectionRequestShowsInnerSeasonsInner](schemas/trakt/docs/RemoveItemsFromCollectionRequestShowsInnerSeasonsInner.md)
 - [RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner](schemas/trakt/docs/RemoveItemsFromCollectionRequestShowsInnerSeasonsInnerEpisodesInner.md)
 - [RemoveItemsFromFavorites200Response](schemas/trakt/docs/RemoveItemsFromFavorites200Response.md)
 - [RemoveItemsFromFavoritesRequest](schemas/trakt/docs/RemoveItemsFromFavoritesRequest.md)
 - [RemoveItemsFromHistory200Response](schemas/trakt/docs/RemoveItemsFromHistory200Response.md)
 - [RemoveItemsFromHistory200ResponseNotFound](schemas/trakt/docs/RemoveItemsFromHistory200ResponseNotFound.md)
 - [RemoveItemsFromHistoryRequest](schemas/trakt/docs/RemoveItemsFromHistoryRequest.md)
 - [RemoveItemsFromPersonalList200Response](schemas/trakt/docs/RemoveItemsFromPersonalList200Response.md)
 - [RemoveItemsFromPersonalListRequest](schemas/trakt/docs/RemoveItemsFromPersonalListRequest.md)
 - [RemoveItemsFromPersonalListRequestMoviesInner](schemas/trakt/docs/RemoveItemsFromPersonalListRequestMoviesInner.md)
 - [RemoveItemsFromPersonalListRequestShowsInner](schemas/trakt/docs/RemoveItemsFromPersonalListRequestShowsInner.md)
 - [RemoveItemsFromWatchlist200Response](schemas/trakt/docs/RemoveItemsFromWatchlist200Response.md)
 - [RemoveRatings200Response](schemas/trakt/docs/RemoveRatings200Response.md)
 - [ReorderAUserSLists200Response](schemas/trakt/docs/ReorderAUserSLists200Response.md)
 - [ReorderAUserSListsRequest](schemas/trakt/docs/ReorderAUserSListsRequest.md)
 - [ReorderFavoritedItems200Response](schemas/trakt/docs/ReorderFavoritedItems200Response.md)
 - [ReorderItemsOnAList200Response](schemas/trakt/docs/ReorderItemsOnAList200Response.md)
 - [ReorderWatchlistItems200Response](schemas/trakt/docs/ReorderWatchlistItems200Response.md)
 - [ReorderWatchlistItemsRequest](schemas/trakt/docs/ReorderWatchlistItemsRequest.md)
 - [ResetShowProgress200Response](schemas/trakt/docs/ResetShowProgress200Response.md)
 - [RetrieveSettings200Response](schemas/trakt/docs/RetrieveSettings200Response.md)
 - [RetrieveSettings200ResponseAccount](schemas/trakt/docs/RetrieveSettings200ResponseAccount.md)
 - [RetrieveSettings200ResponseConnections](schemas/trakt/docs/RetrieveSettings200ResponseConnections.md)
 - [RetrieveSettings200ResponseLimits](schemas/trakt/docs/RetrieveSettings200ResponseLimits.md)
 - [RetrieveSettings200ResponseLimitsList](schemas/trakt/docs/RetrieveSettings200ResponseLimitsList.md)
 - [RetrieveSettings200ResponseLimitsSearch](schemas/trakt/docs/RetrieveSettings200ResponseLimitsSearch.md)
 - [RetrieveSettings200ResponseLimitsWatchlist](schemas/trakt/docs/RetrieveSettings200ResponseLimitsWatchlist.md)
 - [RetrieveSettings200ResponsePermissions](schemas/trakt/docs/RetrieveSettings200ResponsePermissions.md)
 - [RetrieveSettings200ResponseSharingText](schemas/trakt/docs/RetrieveSettings200ResponseSharingText.md)
 - [RetrieveSettings200ResponseUser](schemas/trakt/docs/RetrieveSettings200ResponseUser.md)
 - [RetrieveSettings200ResponseUserIds](schemas/trakt/docs/RetrieveSettings200ResponseUserIds.md)
 - [RetrieveSettings200ResponseUserImages](schemas/trakt/docs/RetrieveSettings200ResponseUserImages.md)
 - [RetrieveSettings200ResponseUserImagesAvatar](schemas/trakt/docs/RetrieveSettings200ResponseUserImagesAvatar.md)
 - [RevokeAnAccessTokenRequest](schemas/trakt/docs/RevokeAnAccessTokenRequest.md)
 - [StartWatchingInAMediaCenter201Response](schemas/trakt/docs/StartWatchingInAMediaCenter201Response.md)
 - [StartWatchingInAMediaCenterRequest](schemas/trakt/docs/StartWatchingInAMediaCenterRequest.md)
 - [StopOrFinishWatchingInAMediaCenter201Response](schemas/trakt/docs/StopOrFinishWatchingInAMediaCenter201Response.md)
 - [StopOrFinishWatchingInAMediaCenter409Response](schemas/trakt/docs/StopOrFinishWatchingInAMediaCenter409Response.md)
 - [StopOrFinishWatchingInAMediaCenterRequest](schemas/trakt/docs/StopOrFinishWatchingInAMediaCenterRequest.md)
 - [UpdateACommentOrReply200Response](schemas/trakt/docs/UpdateACommentOrReply200Response.md)
 - [UpdateACommentOrReplyRequest](schemas/trakt/docs/UpdateACommentOrReplyRequest.md)
 - [UpdateANote200Response](schemas/trakt/docs/UpdateANote200Response.md)
 - [UpdateANoteRequest](schemas/trakt/docs/UpdateANoteRequest.md)
 - [UpdateAWatchlistItemRequest](schemas/trakt/docs/UpdateAWatchlistItemRequest.md)
 - [UpdateFavorites200Response](schemas/trakt/docs/UpdateFavorites200Response.md)
 - [UpdateFavoritesRequest](schemas/trakt/docs/UpdateFavoritesRequest.md)
 - [UpdatePersonalList200Response](schemas/trakt/docs/UpdatePersonalList200Response.md)
 - [UpdatePersonalListRequest](schemas/trakt/docs/UpdatePersonalListRequest.md)
 - [UpdateWatchlist200Response](schemas/trakt/docs/UpdateWatchlist200Response.md)
 - [UpdateWatchlist200ResponseIds](schemas/trakt/docs/UpdateWatchlist200ResponseIds.md)
 - [UpdateWatchlistRequest](schemas/trakt/docs/UpdateWatchlistRequest.md)


<a id="documentation-for-authorization"></a>
## Documentation For Authorization


Authentication schemes defined for the API:
<a id="oauth2"></a>
### oauth2

- **Type**: OAuth
- **Flow**: accessCode
- **Authorization URL**: /
- **Scopes**: N/A


## Author
