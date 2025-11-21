# coding: utf-8

"""
Trakt API

At Trakt, we collect lots of interesting information about what tv shows and movies everyone is watching. Part of the fun with such data is making it available for anyone to mash up and use on their own site or app. The Trakt API was made just for this purpose. It is very easy to use, you basically call a URL and get some JSON back.  More complex API calls (such as adding a movie or show to your collection) involve sending us data. These are still easy to use, you simply POST some JSON data to a specific URL.  Make sure to check out the [**Required Headers**](#introduction/required-headers) and [**Authentication**](#reference/authentication-oauth) sections for more info on what needs to be sent with each API call. Also check out the [**Terminology**](#introduction/terminology) section insight into the features Trakt supports.  # Create an App  To use the Trakt API, you'll need to [**create a new API app**](https://trakt.tv/oauth/applications/new).  # Stay Connected  API discussion and bugs should be posted in the [**GitHub Developer Forum**](https://github.com/trakt/api-help/issues) and *watch* the repository if you'd like to get notifications. Make sure to follow our [**API Blog**](https://apiblog.trakt.tv) and [**@traktapi on Twitter**](https://twitter.com/traktapi) too.  # API URL  The API should always be accessed over SSL.  ``` https://api.trakt.tv ```  If you would like to use our sandbox environment to not fill production with test data, use this URL over SSL.  ``` https://api-staging.trakt.tv ```  > ### 🅽🅾🆃🅴 > _Staging is a completely separate environment, so you'll need to [**create a new API app on staging**](https://staging.trakt.tv/oauth/applications/new)._  # Verbs  The API uses restful verbs.  | Verb | Description | |---|---| | `GET` | Select one or more items. Success returns `200` status code. | | `POST` | Create a new item. Success returns `201` status code. | | `PUT` | Update an item. Success returns `200` status code. | | `DELETE` | Delete an item. Success returns `200` or `204` status code. |  # Status Codes  The API will respond with one of the following HTTP status codes.  | Code | Description | |---|---| | `200` | Success | `201` | Success - *new resource created (POST)* | `204` | Success - *no content to return (DELETE)* | `400` | Bad Request - *request couldn't be parsed* | `401` | Unauthorized - *OAuth must be provided* | `403` | Forbidden - *invalid API key or unapproved app* | `404` | Not Found - *method exists, but no record found* | `405` | Method Not Found - *method doesn't exist* | `409` | Conflict - *resource already created* | `412` | Precondition Failed - *use application/json content type* | `420` | Account Limit Exceeded - *list count, item count, etc* | `422` | Unprocessable Entity - *validation errors* | `423` | Locked User Account - *have the user contact support* | `426` | VIP Only - *user must upgrade to VIP* | `429` | Rate Limit Exceeded | `500` | Server Error - *please open a support ticket* | `502` | Service Unavailable - *server overloaded (try again in 30s)* | `503` | Service Unavailable - *server overloaded (try again in 30s)* | `504` | Service Unavailable - *server overloaded (try again in 30s)* | `520` | Service Unavailable - *Cloudflare error* | `521` | Service Unavailable - *Cloudflare error* | `522` | Service Unavailable - *Cloudflare error*  # Required Headers  You'll need to send some headers when making API calls to identify your application, set the version and set the content type to JSON.  | Header | Value | |---|---| | `Content-Type` <span style=\"color:red;\">*</a> | `application/json` | | `User-Agent` <span style=\"color:red;\">*</a> | We suggest using your app and version like `MyAppName/1.0.0` | | `trakt-api-key` <span style=\"color:red;\">*</a> | Your `client_id` listed under your Trakt applications. | | `trakt-api-version` <span style=\"color:red;\">*</a> | `2` | API version to use.  All `POST`, `PUT`, and `DELETE` methods require a valid OAuth `access_token`. Some `GET` calls require OAuth and others will return user specific data if OAuth is sent. Methods that &#128274; **require** or have &#128275; **optional** OAuth will be indicated.  Your OAuth library should take care of sending the auth headers for you, but for reference here's how the Bearer token should be sent.  | Header | Value | |---|---| | `Authorization` | `Bearer [access_token]` |  # Rate Limiting  All API methods are rate limited. A `429` HTTP status code is returned when the limit has been exceeded. Check the headers for detailed info, then try your API call in `Retry-After` seconds.  | Header | Value | |---|---| | `X-Ratelimit` | `{\"name\":\"UNAUTHED_API_GET_LIMIT\",\"period\":300,\"limit\":1000,\"remaining\":0,\"until\":\"2020-10-10T00:24:00Z\"}` | | `Retry-After` | `10` |  Here are the current limits. There are separate limits for authed (user level) and unauthed (application level) calls. We'll continue to adjust these limits to optimize API performance for everyone. The goal is to prevent API abuse and poor coding, but allow users to use apps normally.  | Name | Verb | Methods | Limit | |---|---|---|---| | `AUTHED_API_POST_LIMIT` | `POST`, `PUT`, `DELETE` | all | 1 call per second | | `AUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes | | `UNAUTHED_API_GET_LIMIT` | `GET` | all | 1000 calls every 5 minutes |  # Locked User Account  A `423` HTTP status code is returned when the OAuth user has a locked or deactivated user account. Please instruct the user to [**email Trakt support**](mailto:support@trakt.tv) so we can fix their account. API access will be suspended for the user until we fix their account.  | Header | Value | |---|---| | `X-Account-Locked` | `true` or `false` | | `X-Account-Deactivated` | `true` or `false` |  # VIP Methods  Some API methods are tagged 🔥 **VIP Only**. A `426` HTTP status code is returned when the user isn't a VIP, indicating they need to sign up for [**Trakt VIP**](https://trakt.tv/vip) in order to use this method. In your app, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` |  Some API methods are tagged 🔥 **VIP Enhanced**. A `420` HTTP status code is returned when the user has exceeded their account limit. Signing up for [**Trakt VIP**](https://trakt.tv/vip) will increase these limits. If the user isn't a VIP, please open a browser to `X-Upgrade-URL` so the user can sign up for Trakt VIP. If they are already VIP and still exceeded the limit, please display a message indicating this.  | Header | Value | |---|---| | `X-Upgrade-URL` | `https://trakt.tv/vip` | | `X-VIP-User` | `true` or `false` | | `X-Account-Limit` | Limit allowed. |  # Pagination  Some methods are paginated. Methods with &#128196; **Pagination** will load 1 page of 10 items by default. Methods with &#128196; **Pagination Optional** will load all items by default. In either case, append a query string like `?page={page}&limit={limit}` to the URL to influence the results.  | Parameter | Type | Default | Value | |---|---|---|---| | `page` | integer | `1` | Number of page of results to be returned. | | `limit` | integer | `10` | Number of results to return per page. |  All paginated methods will return these HTTP headers.  | Header | Value | |---|---| | `X-Pagination-Page` | Current page. | | `X-Pagination-Limit` | Items per page. | | `X-Pagination-Page-Count` | Total number of pages. | | `X-Pagination-Item-Count` | Total number of items. |  # Extended Info  By default, all methods will return minimal info for movies, shows, episodes, people, and users. Minimal info is typically all you need to match locally cached items and includes the `title`, `year`, and `ids`. However, you can request different extended levels of information by adding `?extended={level}` to the URL. Send a comma separated string to get multiple types of extended info.  > ### 🅽🅾🆃🅴 > _This returns a lot of extra data, so please only use extended parameters if you actually need them!_  | Level | Description | |---|---| | `images` | Minimal info and all images. | | `full` | Complete info for an item. | | `full,images` | Complete info and all images. | | `metadata` | **Collection only.** Additional video and audio info. |  # Filters  Some `movies`, `shows`, `calendars`,  and `search` methods support additional filters and will be tagged with &#127898; **Filters**. Applying these filters refines the results and helps your users to more easily discover new items.  Add a query string (i.e. `?years=2016&genres=action`) with any filters you want to use. Some filters allow multiples which can be sent as comma delimited parameters. For example, `?genres=action,adventure` would match the `action` OR `adventure` genre.  *Please note*, subgenres are currently a technical preview.  We're currently in the process of smoothing this out.  > ### 🅽🅾🆃🅴 > _Make sure to properly URL encode the parameters including spaces and special characters._  #### Common Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `query` | | `batman` | Search titles and descriptions. | | `years` | | `2016` | 4 digit year or range of years. | | `genres` | &#10003; | `action` | [Genre slugs.](#reference/genres) | | `subgenres` | &#10003; | `android` | [Subgenre slugs.](#reference/subgenres) | | `languages` | &#10003; | `en` | [2 character language code.](#reference/languages) | | `countries` | &#10003; | `us` | [2 character country code.](#reference/countries) | | `runtimes` | | `30-90` | Range in minutes. | | `studio_ids` | &#10003; | `42` | Trakt studio ID. |  #### Rating Filters  Trakt, TMDB, and IMDB ratings apply to `movies`, `shows`, and `episodes`. Rotten Tomatoes and Metacritic apply to `movies`.  | Parameter | Multiples | Example | Value | |---|---|---|---| | `ratings` | | `75-100` | Trakt rating range between `0` and `100`. | | `votes` | | `5000-10000` | Trakt vote count between `0` and `100000`. | | `tmdb_ratings` | | `5.5-10.0` | TMDB rating range between `0.0` and `10.0`. | | `tmdb_votes` | | `5000-10000` | TMDB vote count between `0` and `100000`. | | `imdb_ratings` | | `5.5-10.0` | IMDB rating range between `0.0` and `10.0`. | | `imdb_votes` | | `5000-10000` | IMDB vote count between `0` and `3000000`. | | `rt_meters` | | `55-1000` | Rotten Tomatoes tomatometer range between `0` and `100`. | | `rt_user_meters` | | `65-100` | Rotten Tomatoes audience score range between `0` and `100`. | | `metascores` | | `5.5-10.0` | Metacritic score range between `0` and `100`. |  #### Movie Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `pg-13` | US content certification. |  #### Show Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `status` | &#10003; | `ended` | Set to `returning series`, `continuing`, `in production`, `planned`, `upcoming`,  `pilot`, `canceled`, or `ended`. |  #### Episode Filters  | Parameter | Multiples | Example | Value | |---|---|---|---| | `certifications` | &#10003; | `tv-pg` | US content certification. | | `network_ids` | &#10003; | `53` | Trakt network ID. | | `episode_types` | &#10003; | `mid_season_premiere` | Set to `standard`, `series_premiere`, `season_premiere`, `mid_season_finale`, `mid_season_premiere`, `season_finale`,  or `series_finale`. |  # CORS  When creating your API app, specify the JavaScript (CORS) origins you'll be using. We use these origins to return the headers needed for CORS.  # Dates  All dates will be GMT and returned in the ISO 8601 format like `2014-09-01T09:10:11.000Z`. Adjust accordingly in your app for the user's local timezone.  # Emojis  We use short codes for emojis like `:smiley:` and `:raised_hands:` and render them on the Trakt website using [**JoyPixels**](https://www.joypixels.com/) _(verion 6.6.0)_. Methods that support emojis are tagged with &#128513; **Emojis**. For POST methods, you can send standard unicode emojis and we'll automatically convert them to short codes. For GET methods, we'll return the unicode emojis if possible, but some short codes might also be returned. It's up to your app to convert short codes back to unicode emojis.  # Standard Media Objects  All methods will accept or return standard media objects for `movie`, `show`, `season`, `episode`, `person`, and `user` items. Here are examples for all minimal objects.  #### movie  ``` {     \"title\": \"Batman Begins\",     \"year\": 2005,     \"ids\": {         \"trakt\": 1,         \"slug\": \"batman-begins-2005\",         \"imdb\": \"tt0372784\",         \"tmdb\": 272     } } ```  #### show  ``` {     \"title\": \"Breaking Bad\",     \"year\": 2008,     \"ids\": {         \"trakt\": 1,         \"slug\": \"breaking-bad\",         \"tvdb\": 81189,         \"imdb\": \"tt0903747\",         \"tmdb\": 1396     } } ```  #### season  ``` {     \"number\": 0,     \"ids\": {         \"trakt\": 1,         \"tvdb\": 439371,         \"tmdb\": 3577     } } ```  #### episode  ``` {     \"season\": 1,     \"number\": 1,     \"title\": \"Pilot\",     \"ids\": {         \"trakt\": 16,         \"tvdb\": 349232,         \"imdb\": \"tt0959621\",         \"tmdb\": 62085     } } ```  #### person  ``` {     \"name\": \"Bryan Cranston\",     \"ids\": {         \"trakt\": 142,         \"slug\": \"bryan-cranston\",         \"imdb\": \"nm0186505\",         \"tmdb\": 17419     } } ```  #### user  ``` {     \"username\": \"sean\",     \"private\": false,     \"name\": \"Sean Rudford\",     \"vip\": true,     \"vip_ep\": true,     \"ids\": {         \"slug\": \"sean\"     } } ```  # Images  #### Trakt Images  Trakt can return images by appending `?extended=images` to most URLs. This will return all images for a `movie`, `show`, `season`, `episode`, or `person`. Images are returned in a `images` object with keys for each image type. Each image type is an array of image URLs, but only 1 image URL will be returned for now. This is just future proofing.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > **Please cache all images!** All images are required to be cached in your app or server and not loaded directly from our CDN. Hotlinking images is not allowed and will be blocked.  > ### 🅽🅾🆃🅴 > All images are returned in WebP format for reduced file size, at the same image quality. You'll also need to prepend the https:// prefix to all image URLs.  ### Example Images Object  ```json {   \"title\": \"TRON: Legacy\",   \"year\": 2010,   \"ids\": {     \"trakt\": 12601,     \"slug\": \"tron-legacy-2010\",     \"imdb\": \"tt1104001\",     \"tmdb\": 20526   },   \"images\": {     \"fanart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/fanarts/medium/5aab754f58.jpg.webp\"     ],     \"poster\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/posters/thumb/e0d9dd35c5.jpg.webp\"     ],     \"logo\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/logos/medium/dbce70b4aa.png.webp\"     ],     \"clearart\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/cleararts/medium/513a3688d1.png.webp\"     ],     \"banner\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/banners/medium/71dc0c3258.jpg.webp\"     ],     \"thumb\": [       \"walter-r2.trakt.tv/images/movies/000/012/601/thumbs/medium/fcd7d7968c.jpg.webp\"     ]   } } ```  #### External Images  If you want more variety of images, there are several external services you can use. The standard Trakt media objects for all `movie`, `show`, `season`, `episode`, and `person` items include an `ids` object. These `ids` map to other services like [TMDB](https://www.themoviedb.org), [TVDB](https://thetvdb.com), [Fanart.tv](https://fanart.tv), [IMDB](https://www.imdb.com), and [OMDB](https://www.omdbapi.com/).  Most of these services have free APIs you can use to grab lots of great looking images. Here’s a chart to help you find the best artwork for your app. [**We also wrote an article to help with this.**](https://medium.com/api-news/how-to-find-the-best-images-516045bcc3b6)  | Media | Type | [TMDB](https://developers.themoviedb.org/3) | [TVDB](https://api.thetvdb.com/swagger) | [Fanart.tv](http://docs.fanarttv.apiary.io) | [OMDB](https://www.omdbapi.com) | |---|---|---|---|---|---| | `shows` | `poster` | &#10003; | &#10003; | &#10003; | &#10003; | |  | `fanart` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `seasons` | `poster` | &#10003; | &#10003; | &#10003; |  | |  | `banner` |  | &#10003; | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `episodes` | `screenshot` | &#10003; | &#10003; |  |  | | `movies` | `poster` | &#10003; |  | &#10003; | &#10003; | |  | `fanart` | &#10003; |  | &#10003; |  | |  | `banner` |  |  | &#10003; |  | |  | `logo` | &#10003; |  | &#10003; |  | |  | `clearart` |  |  | &#10003; |  | |  | `thumb` |  |  | &#10003; |  | | `person` | `headshot` | &#10003; |  |  |  | |  | `character` |  | &#10003; |  |  |  # Website Media Links  There are several ways to construct direct links to media on the Trakt website. The website itself uses slugs so the URLs are more readable.  | Type | URL | |---|---| | `movie` | `/movies/:id` | | | `/movies/:slug` | | `show` | `/shows/:id` | | | `/shows/:slug` | | `season` | `/shows/:id/seasons/:num` | | | `/shows/:slug/seasons/:num` | | `episode` | `/shows/:id/seasons/:num/episodes/:num` | | | `/shows/:slug/seasons/:num/episodes/:num` | | `person` | `/people/:id` | | | `/people/:slug` | | `comment` | `/comments/:id` | | `list` | `/lists/:id` |  You can also create links using the Trakt, IMDB, TMDB, or TVDB IDs. We recommend using the Trakt ID if possible since that will always have full coverage. If you use the search url without an `id_type` it will return search results if multiple items are found.  | Type | URL | |---|---| | `trakt` | `/search/trakt/:id` | |  | `/search/trakt/:id?id_type=movie` | |  | `/search/trakt/:id?id_type=show` | |  | `/search/trakt/:id?id_type=season` | |  | `/search/trakt/:id?id_type=episode` | |  | `/search/trakt/:id?id_type=person` | | `imdb` | `/search/imdb/:id` | | `tmdb` | `/search/tmdb/:id` | |  | `/search/tmdb/:id?id_type=movie` | |  | `/search/tmdb/:id?id_type=show` | |  | `/search/tmdb/:id?id_type=episode` | |  | `/search/tmdb/:id?id_type=person` | | `tvdb` | `/search/tvdb/:id` | |  | `/search/tvdb/:id?id_type=show` | |  | `/search/tvdb/:id?id_type=episode` |  # Third Party Libraries  All of the libraries listed below are user contributed. If you find a bug or missing feature, please contact the developer directly. These might help give your project a head start, but we can't provide direct support for any of these libraries. Please help us keep this list up to date.  | Language | Name | Repository | |---|---|---| | `C#` | `Trakt.NET` | https://github.com/henrikfroehling/Trakt.NET | |  | `TraktSharp` | https://github.com/wwarby/TraktSharp | | `C++` | `libtraqt` | https://github.com/RobertMe/libtraqt | | `Clojure` | `clj-trakt` | https://github.com/niamu/clj-trakt | | `Java` | `trakt-java` | https://github.com/UweTrottmann/trakt-java | | `Kotlin` | `trakt-api` | https://github.com/MoviebaseApp/trakt-api | | `Node.js` | `Trakt.tv` | https://github.com/vankasteelj/trakt.tv | |  | `TraktApi2` | https://github.com/PatrickE94/traktapi2 | | `Python` | `trakt.py` | https://github.com/fuzeman/trakt.py | |  | `pyTrakt` | https://github.com/moogar0880/PyTrakt | | `R` | `tRakt` | https://github.com/jemus42/tRakt | | `React Native` | `nodeless-trakt` | https://github.com/kdemoya/nodeless-trakt | | `Ruby` | `omniauth-trakt` | https://github.com/wafcio/omniauth-trakt | |  | `omniauth-trakt` | https://github.com/alextakitani/omniauth-trakt | | `Swift` | `TraktKit` | https://github.com/MaxHasADHD/TraktKit | |  | `AKTrakt` | https://github.com/arsonik/AKTrakt |  # Terminology  Trakt has a lot of features and here's a chart to help explain the differences between some of them.  | Term | Description | |---|---| | `scrobble` | Automatic way to track what a user is watching in a media center. | | `checkin` | Manual action used by mobile apps allowing the user to indicate what they are watching right now. | | `history` | All watched items (scrobbles, checkins, watched) for a user. | | `collection` | Items a user has available to watch including Blu-Rays, DVDs, and digital downloads. | | `watchlist` | Items a user wants to watch in the future. Once watched, they are auto removed from this list. | | `list` | Personal list for any purpose. Items are not auto removed from any personal lists. | | `favorites` | A user's top 50 TV shows and movies. |

The version of the OpenAPI document:
Generated by OpenAPI Generator (https://openapi-generator.tech)

Do not edit the class manually.
"""  # noqa: E501

import warnings
from pydantic import validate_call, Field, StrictFloat, StrictStr, StrictInt
from typing import Any, Dict, List, Optional, Tuple, Union
from typing_extensions import Annotated

from pydantic import Field, StrictInt, StrictStr, field_validator
from typing import List, Optional
from typing_extensions import Annotated
from schemas.trakt.models.add_hidden_items201_response import AddHiddenItems201Response
from schemas.trakt.models.add_hidden_items_request import AddHiddenItemsRequest
from schemas.trakt.models.add_items_to_personal_list201_response import (
    AddItemsToPersonalList201Response,
)
from schemas.trakt.models.add_items_to_personal_list_request import (
    AddItemsToPersonalListRequest,
)
from schemas.trakt.models.approve_follow_request200_response import (
    ApproveFollowRequest200Response,
)
from schemas.trakt.models.create_personal_list201_response import (
    CreatePersonalList201Response,
)
from schemas.trakt.models.create_personal_list_request import CreatePersonalListRequest
from schemas.trakt.models.follow_this_user201_response import FollowThisUser201Response
from schemas.trakt.models.get_a_user_s_personal_lists200_response_inner import (
    GetAUserSPersonalLists200ResponseInner,
)
from schemas.trakt.models.get_all_list_comments200_response_inner import (
    GetAllListComments200ResponseInner,
)
from schemas.trakt.models.get_all_lists_a_user_can_collaborate_on200_response_inner import (
    GetAllListsAUserCanCollaborateOn200ResponseInner,
)
from schemas.trakt.models.get_all_users_who_liked_a_comment200_response_inner import (
    GetAllUsersWhoLikedAComment200ResponseInner,
)
from schemas.trakt.models.get_collection200_response_inner import (
    GetCollection200ResponseInner,
)
from schemas.trakt.models.get_favorites200_response_inner import (
    GetFavorites200ResponseInner,
)
from schemas.trakt.models.get_followers200_response_inner import (
    GetFollowers200ResponseInner,
)
from schemas.trakt.models.get_friends200_response_inner import (
    GetFriends200ResponseInner,
)
from schemas.trakt.models.get_hidden_items200_response_inner import (
    GetHiddenItems200ResponseInner,
)
from schemas.trakt.models.get_items_on_a_personal_list200_response_inner import (
    GetItemsOnAPersonalList200ResponseInner,
)
from schemas.trakt.models.get_likes200_response_inner import GetLikes200ResponseInner
from schemas.trakt.models.get_list200_response import GetList200Response
from schemas.trakt.models.get_notes200_response_inner import GetNotes200ResponseInner
from schemas.trakt.models.get_pending_following_requests200_response_inner import (
    GetPendingFollowingRequests200ResponseInner,
)
from schemas.trakt.models.get_ratings200_response_inner import (
    GetRatings200ResponseInner,
)
from schemas.trakt.models.get_saved_filters200_response_inner import (
    GetSavedFilters200ResponseInner,
)
from schemas.trakt.models.get_stats200_response import GetStats200Response
from schemas.trakt.models.get_trending_comments200_response_inner import (
    GetTrendingComments200ResponseInner,
)
from schemas.trakt.models.get_user_profile200_response import GetUserProfile200Response
from schemas.trakt.models.get_watched200_response_inner import (
    GetWatched200ResponseInner,
)
from schemas.trakt.models.get_watched_history200_response_inner import (
    GetWatchedHistory200ResponseInner,
)
from schemas.trakt.models.get_watching200_response import GetWatching200Response
from schemas.trakt.models.get_watchlist200_response_inner import (
    GetWatchlist200ResponseInner,
)
from schemas.trakt.models.remove_hidden_items200_response import (
    RemoveHiddenItems200Response,
)
from schemas.trakt.models.remove_hidden_items_request import RemoveHiddenItemsRequest
from schemas.trakt.models.remove_items_from_personal_list200_response import (
    RemoveItemsFromPersonalList200Response,
)
from schemas.trakt.models.remove_items_from_personal_list_request import (
    RemoveItemsFromPersonalListRequest,
)
from schemas.trakt.models.reorder_a_user_s_lists200_response import (
    ReorderAUserSLists200Response,
)
from schemas.trakt.models.reorder_a_user_s_lists_request import (
    ReorderAUserSListsRequest,
)
from schemas.trakt.models.reorder_items_on_a_list200_response import (
    ReorderItemsOnAList200Response,
)
from schemas.trakt.models.reorder_watchlist_items_request import (
    ReorderWatchlistItemsRequest,
)
from schemas.trakt.models.retrieve_settings200_response import (
    RetrieveSettings200Response,
)
from schemas.trakt.models.update_a_watchlist_item_request import (
    UpdateAWatchlistItemRequest,
)
from schemas.trakt.models.update_personal_list200_response import (
    UpdatePersonalList200Response,
)
from schemas.trakt.models.update_personal_list_request import UpdatePersonalListRequest

from schemas.trakt.api_client import ApiClient, RequestSerialized
from schemas.trakt.api_response import ApiResponse
from schemas.trakt.rest import RESTResponseType


class UsersApi:
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None) -> None:
        if api_client is None:
            api_client = ApiClient.get_default()
        self.api_client = api_client

    @validate_call
    def add_hidden_items(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_hidden_items_request: Optional[AddHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> AddHiddenItems201Response:
        """Add hidden items

        #### &#128274; OAuth Required  Hide items for a specific section. Here's what type of items can hidden for each section. You can optionally specify the `hidden_at` date for each item.  #### Hideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_hidden_items_request:
        :type add_hidden_items_request: AddHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_hidden_items_request=add_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddHiddenItems201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def add_hidden_items_with_http_info(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_hidden_items_request: Optional[AddHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[AddHiddenItems201Response]:
        """Add hidden items

        #### &#128274; OAuth Required  Hide items for a specific section. Here's what type of items can hidden for each section. You can optionally specify the `hidden_at` date for each item.  #### Hideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_hidden_items_request:
        :type add_hidden_items_request: AddHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_hidden_items_request=add_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddHiddenItems201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def add_hidden_items_without_preload_content(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_hidden_items_request: Optional[AddHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Add hidden items

        #### &#128274; OAuth Required  Hide items for a specific section. Here's what type of items can hidden for each section. You can optionally specify the `hidden_at` date for each item.  #### Hideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_hidden_items_request:
        :type add_hidden_items_request: AddHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_hidden_items_request=add_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddHiddenItems201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _add_hidden_items_serialize(
        self,
        section,
        trakt_api_version,
        trakt_api_key,
        add_hidden_items_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if section is not None:
            _path_params["section"] = section
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if add_hidden_items_request is not None:
            _body_params = add_hidden_items_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/hidden/{section}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def add_items_to_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_items_to_personal_list_request: Optional[
            AddItemsToPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> AddItemsToPersonalList201Response:
        """Add items to personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required &#128513; Emojis  Add one or more items to a personal list. Items can be movies, shows, seasons, episodes, or people.  #### Notes  Each list item can optionally accept a `notes` *(500 maximum characters)* field with custom text. The user must be a [**Trakt VIP**](https://trakt.tv/vip) to send `notes`.  #### Limits  If the user's list item limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_items_to_personal_list_request:
        :type add_items_to_personal_list_request: AddItemsToPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_items_to_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_items_to_personal_list_request=add_items_to_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddItemsToPersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def add_items_to_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_items_to_personal_list_request: Optional[
            AddItemsToPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[AddItemsToPersonalList201Response]:
        """Add items to personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required &#128513; Emojis  Add one or more items to a personal list. Items can be movies, shows, seasons, episodes, or people.  #### Notes  Each list item can optionally accept a `notes` *(500 maximum characters)* field with custom text. The user must be a [**Trakt VIP**](https://trakt.tv/vip) to send `notes`.  #### Limits  If the user's list item limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_items_to_personal_list_request:
        :type add_items_to_personal_list_request: AddItemsToPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_items_to_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_items_to_personal_list_request=add_items_to_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddItemsToPersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def add_items_to_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        add_items_to_personal_list_request: Optional[
            AddItemsToPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Add items to personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required &#128513; Emojis  Add one or more items to a personal list. Items can be movies, shows, seasons, episodes, or people.  #### Notes  Each list item can optionally accept a `notes` *(500 maximum characters)* field with custom text. The user must be a [**Trakt VIP**](https://trakt.tv/vip) to send `notes`.  #### Limits  If the user's list item limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param add_items_to_personal_list_request:
        :type add_items_to_personal_list_request: AddItemsToPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._add_items_to_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            add_items_to_personal_list_request=add_items_to_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "AddItemsToPersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _add_items_to_personal_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        add_items_to_personal_list_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if add_items_to_personal_list_request is not None:
            _body_params = add_items_to_personal_list_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists/{list_id}/items",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def approve_follow_request(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApproveFollowRequest200Response:
        """Approve follow request

        #### &#128274; OAuth Required  Approve a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._approve_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ApproveFollowRequest200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def approve_follow_request_with_http_info(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ApproveFollowRequest200Response]:
        """Approve follow request

        #### &#128274; OAuth Required  Approve a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._approve_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ApproveFollowRequest200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def approve_follow_request_without_preload_content(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Approve follow request

        #### &#128274; OAuth Required  Approve a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._approve_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ApproveFollowRequest200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _approve_follow_request_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/requests/{id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def create_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        create_personal_list_request: Optional[CreatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> CreatePersonalList201Response:
        """Create personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required  Create a new personal list. The `name` is the only required field, but the other info is recommended to ask for.  #### Limits  If the user's list limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Default | Value | |---|---|---|---| | `name` <span style=\"color:red;\">*</a> | string |  | Name of the list. | | `description` | string |  | Description for this list. | | `privacy` | string | `private` | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | `false` | Should each item be numbered? | | `allow_comments` | boolean | `true` | Are comments allowed? | | `sort_by` | string | `rank` | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc` | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param create_personal_list_request:
        :type create_personal_list_request: CreatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._create_personal_list_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            create_personal_list_request=create_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "CreatePersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def create_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        create_personal_list_request: Optional[CreatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[CreatePersonalList201Response]:
        """Create personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required  Create a new personal list. The `name` is the only required field, but the other info is recommended to ask for.  #### Limits  If the user's list limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Default | Value | |---|---|---|---| | `name` <span style=\"color:red;\">*</a> | string |  | Name of the list. | | `description` | string |  | Description for this list. | | `privacy` | string | `private` | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | `false` | Should each item be numbered? | | `allow_comments` | boolean | `true` | Are comments allowed? | | `sort_by` | string | `rank` | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc` | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param create_personal_list_request:
        :type create_personal_list_request: CreatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._create_personal_list_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            create_personal_list_request=create_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "CreatePersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def create_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        create_personal_list_request: Optional[CreatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Create personal list

        #### 🔥 VIP Enhanced &#128274; OAuth Required  Create a new personal list. The `name` is the only required field, but the other info is recommended to ask for.  #### Limits  If the user's list limit is exceeded, a `420` HTTP error code is returned. Use the [**/users/settings**](/reference/users/settings) method to get all limits for a user account. In most cases, upgrading to [**Trakt VIP**](https://trakt.tv/vip) will increase the limits.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Default | Value | |---|---|---|---| | `name` <span style=\"color:red;\">*</a> | string |  | Name of the list. | | `description` | string |  | Description for this list. | | `privacy` | string | `private` | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | `false` | Should each item be numbered? | | `allow_comments` | boolean | `true` | Are comments allowed? | | `sort_by` | string | `rank` | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc` | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param create_personal_list_request:
        :type create_personal_list_request: CreatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._create_personal_list_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            create_personal_list_request=create_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "CreatePersonalList201Response",
            "420": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _create_personal_list_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        create_personal_list_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if create_personal_list_request is not None:
            _body_params = create_personal_list_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def delete_a_users_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Delete a user's personal list

        #### &#128274; OAuth Required  Remove a personal list and all items it contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._delete_a_users_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def delete_a_users_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Delete a user's personal list

        #### &#128274; OAuth Required  Remove a personal list and all items it contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._delete_a_users_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def delete_a_users_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Delete a user's personal list

        #### &#128274; OAuth Required  Remove a personal list and all items it contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._delete_a_users_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _delete_a_users_personal_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="DELETE",
            resource_path="/users/{id}/lists/{list_id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def deny_follow_request(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Deny follow request

        #### &#128274; OAuth Required  Deny a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._deny_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def deny_follow_request_with_http_info(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Deny follow request

        #### &#128274; OAuth Required  Deny a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._deny_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def deny_follow_request_without_preload_content(
        self,
        id: Annotated[StrictInt, Field(description="ID of the follower request.")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Deny follow request

        #### &#128274; OAuth Required  Deny a follower using the `id` of the request. If the `id` is not found, was already approved, or was already denied, a `404` error will be returned.

        :param id: ID of the follower request. (required)
        :type id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._deny_follow_request_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _deny_follow_request_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="DELETE",
            resource_path="/users/requests/{id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def follow_this_user(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> FollowThisUser201Response:
        """Follow this user

        #### &#128274; OAuth Required  If the user has a private profile, the follow request will require approval (`approved_at` will be null). If a user is public, they will be followed immediately (`approved_at` will have a date).  > ### 🅽🅾🆃🅴 > _If this user is already being followed or there is a pending follow request, a `409` HTTP status code will returned._

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._follow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "FollowThisUser201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def follow_this_user_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[FollowThisUser201Response]:
        """Follow this user

        #### &#128274; OAuth Required  If the user has a private profile, the follow request will require approval (`approved_at` will be null). If a user is public, they will be followed immediately (`approved_at` will have a date).  > ### 🅽🅾🆃🅴 > _If this user is already being followed or there is a pending follow request, a `409` HTTP status code will returned._

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._follow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "FollowThisUser201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def follow_this_user_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Follow this user

        #### &#128274; OAuth Required  If the user has a private profile, the follow request will require approval (`approved_at` will be null). If a user is public, they will be followed immediately (`approved_at` will have a date).  > ### 🅽🅾🆃🅴 > _If this user is already being followed or there is a pending follow request, a `409` HTTP status code will returned._

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._follow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "201": "FollowThisUser201Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _follow_this_user_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/follow",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_a_users_personal_lists(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAUserSPersonalLists200ResponseInner]:
        """Get a user's personal lists

        #### &#128275; OAuth Optional &#128513; Emojis  Returns all personal lists for a user. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items a specific list contains.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_a_users_personal_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAUserSPersonalLists200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_a_users_personal_lists_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAUserSPersonalLists200ResponseInner]]:
        """Get a user's personal lists

        #### &#128275; OAuth Optional &#128513; Emojis  Returns all personal lists for a user. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items a specific list contains.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_a_users_personal_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAUserSPersonalLists200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_a_users_personal_lists_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get a user's personal lists

        #### &#128275; OAuth Optional &#128513; Emojis  Returns all personal lists for a user. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items a specific list contains.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_a_users_personal_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAUserSPersonalLists200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_a_users_personal_lists_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_all_favorites_comments(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAllListComments200ResponseInner]:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the watchlist. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_all_favorites_comments_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAllListComments200ResponseInner]]:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the watchlist. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_all_favorites_comments_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the watchlist. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_all_favorites_comments_serialize(
        self,
        id,
        sort,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if sort is not None:
            _path_params["sort"] = sort
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/watchlist/comments/{sort}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_all_favorites_comments_0(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAllListComments200ResponseInner]:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the favorites. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_0_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_all_favorites_comments_0_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAllListComments200ResponseInner]]:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the favorites. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_0_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_all_favorites_comments_0_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get all favorites comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for the favorites. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_favorites_comments_0_serialize(
            id=id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_all_favorites_comments_0_serialize(
        self,
        id,
        sort,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if sort is not None:
            _path_params["sort"] = sort
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/favorites/comments/{sort}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_all_list_comments(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAllListComments200ResponseInner]:
        """Get all list comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for a list. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_list_comments_serialize(
            id=id,
            list_id=list_id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_all_list_comments_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAllListComments200ResponseInner]]:
        """Get all list comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for a list. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_list_comments_serialize(
            id=id,
            list_id=list_id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_all_list_comments_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        sort: Annotated[StrictStr, Field(description="how to sort")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get all list comments

        #### &#128275; OAuth Optional &#128196; Pagination &#128513; Emojis  Returns all top level comments for a list. By default, the `newest` comments are returned first. Other sorting options include `oldest`, most `likes`, and most `replies`.  > ### 🅽🅾🆃🅴 > _If you send OAuth, comments from blocked users will be automatically filtered out._

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param sort: how to sort (required)
        :type sort: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_list_comments_serialize(
            id=id,
            list_id=list_id,
            sort=sort,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_all_list_comments_serialize(
        self,
        id,
        list_id,
        sort,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        if sort is not None:
            _path_params["sort"] = sort
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists/{list_id}/comments/{sort}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_all_lists_a_user_can_collaborate_on(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAllListsAUserCanCollaborateOn200ResponseInner]:
        """Get all lists a user can collaborate on

        #### &#128275; OAuth Optional  Returns all lists a user can collaborate on. This gives full access to add, remove, and re-order list items. It essentially works just like a list owned by the user, just make sure to use the correct list owner `user` when building the API URLs.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_lists_a_user_can_collaborate_on_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListsAUserCanCollaborateOn200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_all_lists_a_user_can_collaborate_on_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAllListsAUserCanCollaborateOn200ResponseInner]]:
        """Get all lists a user can collaborate on

        #### &#128275; OAuth Optional  Returns all lists a user can collaborate on. This gives full access to add, remove, and re-order list items. It essentially works just like a list owned by the user, just make sure to use the correct list owner `user` when building the API URLs.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_lists_a_user_can_collaborate_on_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListsAUserCanCollaborateOn200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_all_lists_a_user_can_collaborate_on_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get all lists a user can collaborate on

        #### &#128275; OAuth Optional  Returns all lists a user can collaborate on. This gives full access to add, remove, and re-order list items. It essentially works just like a list owned by the user, just make sure to use the correct list owner `user` when building the API URLs.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_lists_a_user_can_collaborate_on_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllListsAUserCanCollaborateOn200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_all_lists_a_user_can_collaborate_on_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists/collaborations",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_all_users_who_liked_a_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetAllUsersWhoLikedAComment200ResponseInner]:
        """Get all users who liked a list

        #### &#128275; OAuth Optional &#128196; Pagination  Returns all users who liked a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_users_who_liked_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllUsersWhoLikedAComment200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_all_users_who_liked_a_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetAllUsersWhoLikedAComment200ResponseInner]]:
        """Get all users who liked a list

        #### &#128275; OAuth Optional &#128196; Pagination  Returns all users who liked a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_users_who_liked_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllUsersWhoLikedAComment200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_all_users_who_liked_a_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get all users who liked a list

        #### &#128275; OAuth Optional &#128196; Pagination  Returns all users who liked a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_all_users_who_liked_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetAllUsersWhoLikedAComment200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_all_users_who_liked_a_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists/{list_id}/likes",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_collection(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetCollection200ResponseInner]:
        """Get collection

        #### &#128275; OAuth Optional &#10024; Extended Info  Get all collected items in a user's collection. A collected item indicates availability to watch digitally or on physical media.  Each `movie` object contains `collected_at` and `updated_at` timestamps. Since users can set custom dates when they collected movies, it is possible for `collected_at` to be in the past. We also include `updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movie if you see a newer timestamp.  Each `show` object contains `last_collected_at` and `last_updated_at` timestamps. Since users can set custom dates when they collected episodes, it is possible for `last_collected_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the show if you see a newer timestamp.  If you add `?extended=metadata` to the URL, it will return the additional `media_type`, `resolution`, `hdr`, `audio`, `audio_channels` and '3d' metadata. It will use `null` if the metadata isn't set for an item.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_collection_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetCollection200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_collection_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetCollection200ResponseInner]]:
        """Get collection

        #### &#128275; OAuth Optional &#10024; Extended Info  Get all collected items in a user's collection. A collected item indicates availability to watch digitally or on physical media.  Each `movie` object contains `collected_at` and `updated_at` timestamps. Since users can set custom dates when they collected movies, it is possible for `collected_at` to be in the past. We also include `updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movie if you see a newer timestamp.  Each `show` object contains `last_collected_at` and `last_updated_at` timestamps. Since users can set custom dates when they collected episodes, it is possible for `last_collected_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the show if you see a newer timestamp.  If you add `?extended=metadata` to the URL, it will return the additional `media_type`, `resolution`, `hdr`, `audio`, `audio_channels` and '3d' metadata. It will use `null` if the metadata isn't set for an item.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_collection_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetCollection200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_collection_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get collection

        #### &#128275; OAuth Optional &#10024; Extended Info  Get all collected items in a user's collection. A collected item indicates availability to watch digitally or on physical media.  Each `movie` object contains `collected_at` and `updated_at` timestamps. Since users can set custom dates when they collected movies, it is possible for `collected_at` to be in the past. We also include `updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movie if you see a newer timestamp.  Each `show` object contains `last_collected_at` and `last_updated_at` timestamps. Since users can set custom dates when they collected episodes, it is possible for `last_collected_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the show if you see a newer timestamp.  If you add `?extended=metadata` to the URL, it will return the additional `media_type`, `resolution`, `hdr`, `audio`, `audio_channels` and '3d' metadata. It will use `null` if the metadata isn't set for an item.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_collection_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetCollection200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_collection_serialize(
        self,
        id,
        type,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/collection/{type}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_comments(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        comment_type: StrictStr,
        type: StrictStr,
        include_replies: Annotated[
            Optional[StrictStr], Field(description="include comment replies")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetTrendingComments200ResponseInner]:
        """Get comments

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently written comments for the user. You can optionally filter by the `comment_type` and media `type` to limit what gets returned.  By default, only top level comments are returned. Set `?include_replies=true` to return replies in addition to top level comments. Set `?include_replies=only` to return only replies and no top level comments.

        :param id: User slug (required)
        :type id: str
        :param comment_type:  (required)
        :type comment_type: str
        :param type:  (required)
        :type type: str
        :param include_replies: include comment replies
        :type include_replies: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_comments_serialize(
            id=id,
            comment_type=comment_type,
            type=type,
            include_replies=include_replies,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetTrendingComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_comments_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        comment_type: StrictStr,
        type: StrictStr,
        include_replies: Annotated[
            Optional[StrictStr], Field(description="include comment replies")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetTrendingComments200ResponseInner]]:
        """Get comments

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently written comments for the user. You can optionally filter by the `comment_type` and media `type` to limit what gets returned.  By default, only top level comments are returned. Set `?include_replies=true` to return replies in addition to top level comments. Set `?include_replies=only` to return only replies and no top level comments.

        :param id: User slug (required)
        :type id: str
        :param comment_type:  (required)
        :type comment_type: str
        :param type:  (required)
        :type type: str
        :param include_replies: include comment replies
        :type include_replies: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_comments_serialize(
            id=id,
            comment_type=comment_type,
            type=type,
            include_replies=include_replies,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetTrendingComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_comments_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        comment_type: StrictStr,
        type: StrictStr,
        include_replies: Annotated[
            Optional[StrictStr], Field(description="include comment replies")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get comments

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently written comments for the user. You can optionally filter by the `comment_type` and media `type` to limit what gets returned.  By default, only top level comments are returned. Set `?include_replies=true` to return replies in addition to top level comments. Set `?include_replies=only` to return only replies and no top level comments.

        :param id: User slug (required)
        :type id: str
        :param comment_type:  (required)
        :type comment_type: str
        :param type:  (required)
        :type type: str
        :param include_replies: include comment replies
        :type include_replies: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_comments_serialize(
            id=id,
            comment_type=comment_type,
            type=type,
            include_replies=include_replies,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetTrendingComments200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_comments_serialize(
        self,
        id,
        comment_type,
        type,
        include_replies,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if comment_type is not None:
            _path_params["comment_type"] = comment_type
        if type is not None:
            _path_params["type"] = type
        # process the query parameters
        if include_replies is not None:

            _query_params.append(("include_replies", include_replies))

        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/comments/{comment_type}/{type}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_favorites(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetFavorites200ResponseInner]:
        """Get favorites

        #### 🔥 **VIP Enhanced** &#128274; OAuth Required &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns the top 100 shows and movies a user has favorited. Apps should encourage user's to add favorites so the algorithm keeps getting better.  #### Notes  Each favorite contains a `notes` field explaining why the user favorited the item.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_favorites_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFavorites200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_favorites_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetFavorites200ResponseInner]]:
        """Get favorites

        #### 🔥 **VIP Enhanced** &#128274; OAuth Required &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns the top 100 shows and movies a user has favorited. Apps should encourage user's to add favorites so the algorithm keeps getting better.  #### Notes  Each favorite contains a `notes` field explaining why the user favorited the item.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_favorites_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFavorites200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_favorites_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get favorites

        #### 🔥 **VIP Enhanced** &#128274; OAuth Required &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns the top 100 shows and movies a user has favorited. Apps should encourage user's to add favorites so the algorithm keeps getting better.  #### Notes  Each favorite contains a `notes` field explaining why the user favorited the item.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_favorites_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFavorites200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_favorites_serialize(
        self,
        id,
        type,
        sort_by,
        sort_how,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        if sort_by is not None:
            _path_params["sort_by"] = sort_by
        if sort_how is not None:
            _path_params["sort_how"] = sort_how
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/favorites/{type}/{sort_by}/{sort_how}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_follow_requests(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetPendingFollowingRequests200ResponseInner]:
        """Get follow requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending follow requests so they can either approve or deny them.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_follow_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_follow_requests_with_http_info(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetPendingFollowingRequests200ResponseInner]]:
        """Get follow requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending follow requests so they can either approve or deny them.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_follow_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_follow_requests_without_preload_content(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get follow requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending follow requests so they can either approve or deny them.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_follow_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_follow_requests_serialize(
        self,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/requests",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_followers(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetFollowers200ResponseInner]:
        """Get followers

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all followers including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_followers_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_followers_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetFollowers200ResponseInner]]:
        """Get followers

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all followers including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_followers_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_followers_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get followers

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all followers including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_followers_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_followers_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/followers",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_following(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetFollowers200ResponseInner]:
        """Get following

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all user's they follow including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_following_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_following_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetFollowers200ResponseInner]]:
        """Get following

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all user's they follow including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_following_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_following_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get following

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all user's they follow including when the relationship began.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_following_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFollowers200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_following_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/following",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_friends(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetFriends200ResponseInner]:
        """Get friends

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all friends for a user including when the relationship began. Friendship is a 2 way relationship where each user follows the other.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_friends_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFriends200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_friends_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetFriends200ResponseInner]]:
        """Get friends

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all friends for a user including when the relationship began. Friendship is a 2 way relationship where each user follows the other.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_friends_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFriends200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_friends_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get friends

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all friends for a user including when the relationship began. Friendship is a 2 way relationship where each user follows the other.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_friends_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetFriends200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_friends_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/friends",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_hidden_items(
        self,
        section: StrictStr,
        type: Annotated[
            Optional[StrictStr], Field(description="Narrow down by element type.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetHiddenItems200ResponseInner]:
        """Get hidden items

        #### &#128274; OAuth Required &#128196; Pagination &#10024; Extended Info  Get hidden items for a section. This will return an array of standard media objects. You can optionally limit the `type` of results to return.

        :param section:  (required)
        :type section: str
        :param type: Narrow down by element type.
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_hidden_items_serialize(
            section=section,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetHiddenItems200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_hidden_items_with_http_info(
        self,
        section: StrictStr,
        type: Annotated[
            Optional[StrictStr], Field(description="Narrow down by element type.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetHiddenItems200ResponseInner]]:
        """Get hidden items

        #### &#128274; OAuth Required &#128196; Pagination &#10024; Extended Info  Get hidden items for a section. This will return an array of standard media objects. You can optionally limit the `type` of results to return.

        :param section:  (required)
        :type section: str
        :param type: Narrow down by element type.
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_hidden_items_serialize(
            section=section,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetHiddenItems200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_hidden_items_without_preload_content(
        self,
        section: StrictStr,
        type: Annotated[
            Optional[StrictStr], Field(description="Narrow down by element type.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get hidden items

        #### &#128274; OAuth Required &#128196; Pagination &#10024; Extended Info  Get hidden items for a section. This will return an array of standard media objects. You can optionally limit the `type` of results to return.

        :param section:  (required)
        :type section: str
        :param type: Narrow down by element type.
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_hidden_items_serialize(
            section=section,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetHiddenItems200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_hidden_items_serialize(
        self,
        section,
        type,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if section is not None:
            _path_params["section"] = section
        # process the query parameters
        if type is not None:

            _query_params.append(("type", type))

        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/hidden/{section}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_items_on_a_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetItemsOnAPersonalList200ResponseInner]:
        """Get items on a personal list

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Get all items on a personal list. Items can be a `movie`, `show`, `season`, `episode`, or `person`. You can optionally specify the `type` parameter with a single value or comma delimited string for multiple item types.  #### Notes  Each list item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_items_on_a_personal_list_serialize(
            id=id,
            list_id=list_id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetItemsOnAPersonalList200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_items_on_a_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetItemsOnAPersonalList200ResponseInner]]:
        """Get items on a personal list

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Get all items on a personal list. Items can be a `movie`, `show`, `season`, `episode`, or `person`. You can optionally specify the `type` parameter with a single value or comma delimited string for multiple item types.  #### Notes  Each list item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_items_on_a_personal_list_serialize(
            id=id,
            list_id=list_id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetItemsOnAPersonalList200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_items_on_a_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get items on a personal list

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Get all items on a personal list. Items can be a `movie`, `show`, `season`, `episode`, or `person`. You can optionally specify the `type` parameter with a single value or comma delimited string for multiple item types.  #### Notes  Each list item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_items_on_a_personal_list_serialize(
            id=id,
            list_id=list_id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetItemsOnAPersonalList200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_items_on_a_personal_list_serialize(
        self,
        id,
        list_id,
        type,
        sort_by,
        sort_how,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        if type is not None:
            _path_params["type"] = type
        if sort_by is not None:
            _path_params["sort_by"] = sort_by
        if sort_how is not None:
            _path_params["sort_how"] = sort_how
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists/{list_id}/items/{type}/{sort_by}/{sort_how}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_likes(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetLikes200ResponseInner]:
        """Get likes

        #### &#128274; OAuth Optional &#128196; Pagination  Get items a user likes. This will return an array of standard media objects. You can optionally limit the `type` of results to return.  #### Comment Media Objects  If you add `?extended=comments` to the URL, it will return media objects for each comment like.  > ### 🅽🅾🆃🅴 > _This returns a lot of data, so please only use this extended parameter if you actually need it!_

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_likes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetLikes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_likes_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetLikes200ResponseInner]]:
        """Get likes

        #### &#128274; OAuth Optional &#128196; Pagination  Get items a user likes. This will return an array of standard media objects. You can optionally limit the `type` of results to return.  #### Comment Media Objects  If you add `?extended=comments` to the URL, it will return media objects for each comment like.  > ### 🅽🅾🆃🅴 > _This returns a lot of data, so please only use this extended parameter if you actually need it!_

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_likes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetLikes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_likes_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get likes

        #### &#128274; OAuth Optional &#128196; Pagination  Get items a user likes. This will return an array of standard media objects. You can optionally limit the `type` of results to return.  #### Comment Media Objects  If you add `?extended=comments` to the URL, it will return media objects for each comment like.  > ### 🅽🅾🆃🅴 > _This returns a lot of data, so please only use this extended parameter if you actually need it!_

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_likes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetLikes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_likes_serialize(
        self,
        id,
        type,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/likes/{type}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_notes(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetNotes200ResponseInner]:
        """Get notes

        #### 🔥 VIP Enhanced &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently notes for the user. You can optionally filter by media `type` to limit what gets returned. Use the `attached_to` info to know what the note is actually added to. Media items like `movie`, `show`, `season`, `episode`, or `person` are straightforward, but `history` will need to be mapped to that specific play in their watched history since they might have multiple plays. Since `collection` and `rating` is a 1:1 association, you can assume the note is attached to the media item in the `type` field that has been collected or rated.  #### Limits  Standard accounts are allowed a limited amount of notes, upgrading to [**Trakt VIP**](https://trakt.tv/vip) allows unlimited notes.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_notes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetNotes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_notes_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetNotes200ResponseInner]]:
        """Get notes

        #### 🔥 VIP Enhanced &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently notes for the user. You can optionally filter by media `type` to limit what gets returned. Use the `attached_to` info to know what the note is actually added to. Media items like `movie`, `show`, `season`, `episode`, or `person` are straightforward, but `history` will need to be mapped to that specific play in their watched history since they might have multiple plays. Since `collection` and `rating` is a 1:1 association, you can assume the note is attached to the media item in the `type` field that has been collected or rated.  #### Limits  Standard accounts are allowed a limited amount of notes, upgrading to [**Trakt VIP**](https://trakt.tv/vip) allows unlimited notes.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_notes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetNotes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_notes_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get notes

        #### 🔥 VIP Enhanced &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns the most recently notes for the user. You can optionally filter by media `type` to limit what gets returned. Use the `attached_to` info to know what the note is actually added to. Media items like `movie`, `show`, `season`, `episode`, or `person` are straightforward, but `history` will need to be mapped to that specific play in their watched history since they might have multiple plays. Since `collection` and `rating` is a 1:1 association, you can assume the note is attached to the media item in the `type` field that has been collected or rated.  #### Limits  Standard accounts are allowed a limited amount of notes, upgrading to [**Trakt VIP**](https://trakt.tv/vip) allows unlimited notes.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_notes_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetNotes200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_notes_serialize(
        self,
        id,
        type,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/notes/{type}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_pending_following_requests(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetPendingFollowingRequests200ResponseInner]:
        """Get pending following requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending following requests that they're waiting for the other user's to approve.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_pending_following_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_pending_following_requests_with_http_info(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetPendingFollowingRequests200ResponseInner]]:
        """Get pending following requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending following requests that they're waiting for the other user's to approve.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_pending_following_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_pending_following_requests_without_preload_content(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get pending following requests

        #### &#128274; OAuth Required &#10024; Extended Info  List a user's pending following requests that they're waiting for the other user's to approve.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_pending_following_requests_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetPendingFollowingRequests200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_pending_following_requests_serialize(
        self,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/requests/following",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> GetList200Response:
        """Get personal list

        #### &#128275; OAuth Optional &#128513; Emojis  Returns a single personal list. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items this list contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[GetList200Response]:
        """Get personal list

        #### &#128275; OAuth Optional &#128513; Emojis  Returns a single personal list. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items this list contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get personal list

        #### &#128275; OAuth Optional &#128513; Emojis  Returns a single personal list. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get the actual items this list contains.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_personal_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/lists/{list_id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_ratings(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        rating: Annotated[
            StrictInt, Field(description="Filter for a specific rating.")
        ],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetRatings200ResponseInner]:
        """Get ratings

        #### &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info  Get a user's ratings filtered by `type`. You can optionally filter for a specific `rating` between 1 and 10. Send a comma separated string for `rating` if you need multiple ratings.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param rating: Filter for a specific rating. (required)
        :type rating: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_ratings_serialize(
            id=id,
            type=type,
            rating=rating,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetRatings200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_ratings_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        rating: Annotated[
            StrictInt, Field(description="Filter for a specific rating.")
        ],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetRatings200ResponseInner]]:
        """Get ratings

        #### &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info  Get a user's ratings filtered by `type`. You can optionally filter for a specific `rating` between 1 and 10. Send a comma separated string for `rating` if you need multiple ratings.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param rating: Filter for a specific rating. (required)
        :type rating: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_ratings_serialize(
            id=id,
            type=type,
            rating=rating,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetRatings200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_ratings_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        rating: Annotated[
            StrictInt, Field(description="Filter for a specific rating.")
        ],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get ratings

        #### &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info  Get a user's ratings filtered by `type`. You can optionally filter for a specific `rating` between 1 and 10. Send a comma separated string for `rating` if you need multiple ratings.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param rating: Filter for a specific rating. (required)
        :type rating: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_ratings_serialize(
            id=id,
            type=type,
            rating=rating,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetRatings200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_ratings_serialize(
        self,
        id,
        type,
        rating,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        if rating is not None:
            _path_params["rating"] = rating
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/ratings/{type}/{rating}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_saved_filters(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetSavedFilters200ResponseInner]:
        """Get saved filters

        #### 🔥 VIP Only &#128274; OAuth Required &#128196; Pagination  Get all saved filters a user has created. The `path` and `query` can be used to construct an API path to retrieve the saved data. Think of this like a dynamically updated list.

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_saved_filters_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetSavedFilters200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_saved_filters_with_http_info(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetSavedFilters200ResponseInner]]:
        """Get saved filters

        #### 🔥 VIP Only &#128274; OAuth Required &#128196; Pagination  Get all saved filters a user has created. The `path` and `query` can be used to construct an API path to retrieve the saved data. Think of this like a dynamically updated list.

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_saved_filters_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetSavedFilters200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_saved_filters_without_preload_content(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get saved filters

        #### 🔥 VIP Only &#128274; OAuth Required &#128196; Pagination  Get all saved filters a user has created. The `path` and `query` can be used to construct an API path to retrieve the saved data. Think of this like a dynamically updated list.

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_saved_filters_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetSavedFilters200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_saved_filters_serialize(
        self,
        section,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if section is not None:
            _path_params["section"] = section
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/saved_filters/{section}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_stats(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> GetStats200Response:
        """Get stats

        #### &#128275; OAuth Optional  Returns stats about the movies, shows, and episodes a user has watched, collected, and rated.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_stats_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetStats200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_stats_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[GetStats200Response]:
        """Get stats

        #### &#128275; OAuth Optional  Returns stats about the movies, shows, and episodes a user has watched, collected, and rated.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_stats_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetStats200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_stats_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get stats

        #### &#128275; OAuth Optional  Returns stats about the movies, shows, and episodes a user has watched, collected, and rated.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_stats_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetStats200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_stats_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/stats",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_user_profile(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> GetUserProfile200Response:
        """Get user profile

        #### &#128275; OAuth Optional &#10024; Extended Info  Get a user's profile information. If the user is private, info will only be returned if you send OAuth and are either that user or an approved follower. Adding `?extended=vip` will return some additional VIP related fields so you can display the user's Trakt VIP status and year count.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_user_profile_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetUserProfile200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_user_profile_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[GetUserProfile200Response]:
        """Get user profile

        #### &#128275; OAuth Optional &#10024; Extended Info  Get a user's profile information. If the user is private, info will only be returned if you send OAuth and are either that user or an approved follower. Adding `?extended=vip` will return some additional VIP related fields so you can display the user's Trakt VIP status and year count.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_user_profile_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetUserProfile200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_user_profile_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get user profile

        #### &#128275; OAuth Optional &#10024; Extended Info  Get a user's profile information. If the user is private, info will only be returned if you send OAuth and are either that user or an approved follower. Adding `?extended=vip` will return some additional VIP related fields so you can display the user's Trakt VIP status and year count.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_user_profile_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetUserProfile200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_user_profile_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_watched(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetWatched200ResponseInner]:
        """Get watched

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all movies or shows a user has watched sorted by most plays.  If `type` is set to _shows_ and you add `?extended=noseasons` to the URL, it won't return season or episode info.  Each `movie` and `show` object contains `last_watched_at` and `last_updated_at` timestamps. Since users can set custom dates when they watched movies and episodes, it is possible for `last_watched_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movies and shows if you see a newer timestamp.  Each `show` object contains a `reset_at` timestamp. If not `null`, this is when the user started re-watching the show. Your app can adjust the progress by ignoring episodes with a `last_watched_at` prior to the `reset_at`.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatched200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_watched_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetWatched200ResponseInner]]:
        """Get watched

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all movies or shows a user has watched sorted by most plays.  If `type` is set to _shows_ and you add `?extended=noseasons` to the URL, it won't return season or episode info.  Each `movie` and `show` object contains `last_watched_at` and `last_updated_at` timestamps. Since users can set custom dates when they watched movies and episodes, it is possible for `last_watched_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movies and shows if you see a newer timestamp.  Each `show` object contains a `reset_at` timestamp. If not `null`, this is when the user started re-watching the show. Your app can adjust the progress by ignoring episodes with a `last_watched_at` prior to the `reset_at`.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatched200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_watched_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get watched

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns all movies or shows a user has watched sorted by most plays.  If `type` is set to _shows_ and you add `?extended=noseasons` to the URL, it won't return season or episode info.  Each `movie` and `show` object contains `last_watched_at` and `last_updated_at` timestamps. Since users can set custom dates when they watched movies and episodes, it is possible for `last_watched_at` to be in the past. We also include `last_updated_at` to help sync Trakt data with your app. Cache this timestamp locally and only re-process the movies and shows if you see a newer timestamp.  Each `show` object contains a `reset_at` timestamp. If not `null`, this is when the user started re-watching the show. Your app can adjust the progress by ignoring episodes with a `last_watched_at` prior to the `reset_at`.

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_serialize(
            id=id,
            type=type,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatched200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_watched_serialize(
        self,
        id,
        type,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/watched/{type}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_watched_history(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        item_id: Annotated[
            StrictInt, Field(description="Trakt ID for a specific item.")
        ],
        start_at: Annotated[
            Optional[StrictStr], Field(description="Starting date.")
        ] = None,
        end_at: Annotated[
            Optional[StrictStr], Field(description="Ending date.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetWatchedHistory200ResponseInner]:
        """Get watched history

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns movies and episodes that a user has watched, sorted by most recent. You can optionally limit the `type` to `movies` or `episodes`. The `id` _(64-bit integer)_ in each history item uniquely identifies the event and can be used to remove individual events by using the [**/sync/history/remove**](#reference/sync/remove-from-history/get-watched-history) method. The `action` will be set to `scrobble`, `checkin`, or `watch`.  Specify a `type` and trakt `item_id` to limit the history for just that item. If the `item_id` is valid, but there is no history, an empty array will be returned.  | Example URL | Returns watches for... | |---|---| | `/history/movies/12601` | TRON: Legacy | | `/history/shows/1388` | All episodes of Breaking Bad | | `/history/seasons/3950` | All episodes of Breaking Bad: Season 1 | | `/history/episodes/73482` | Only episode 1 for Breaking Bad: Season 1 |

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param item_id: Trakt ID for a specific item. (required)
        :type item_id: int
        :param start_at: Starting date.
        :type start_at: str
        :param end_at: Ending date.
        :type end_at: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_history_serialize(
            id=id,
            type=type,
            item_id=item_id,
            start_at=start_at,
            end_at=end_at,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchedHistory200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_watched_history_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        item_id: Annotated[
            StrictInt, Field(description="Trakt ID for a specific item.")
        ],
        start_at: Annotated[
            Optional[StrictStr], Field(description="Starting date.")
        ] = None,
        end_at: Annotated[
            Optional[StrictStr], Field(description="Ending date.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetWatchedHistory200ResponseInner]]:
        """Get watched history

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns movies and episodes that a user has watched, sorted by most recent. You can optionally limit the `type` to `movies` or `episodes`. The `id` _(64-bit integer)_ in each history item uniquely identifies the event and can be used to remove individual events by using the [**/sync/history/remove**](#reference/sync/remove-from-history/get-watched-history) method. The `action` will be set to `scrobble`, `checkin`, or `watch`.  Specify a `type` and trakt `item_id` to limit the history for just that item. If the `item_id` is valid, but there is no history, an empty array will be returned.  | Example URL | Returns watches for... | |---|---| | `/history/movies/12601` | TRON: Legacy | | `/history/shows/1388` | All episodes of Breaking Bad | | `/history/seasons/3950` | All episodes of Breaking Bad: Season 1 | | `/history/episodes/73482` | Only episode 1 for Breaking Bad: Season 1 |

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param item_id: Trakt ID for a specific item. (required)
        :type item_id: int
        :param start_at: Starting date.
        :type start_at: str
        :param end_at: Ending date.
        :type end_at: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_history_serialize(
            id=id,
            type=type,
            item_id=item_id,
            start_at=start_at,
            end_at=end_at,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchedHistory200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_watched_history_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: StrictStr,
        item_id: Annotated[
            StrictInt, Field(description="Trakt ID for a specific item.")
        ],
        start_at: Annotated[
            Optional[StrictStr], Field(description="Starting date.")
        ] = None,
        end_at: Annotated[
            Optional[StrictStr], Field(description="Ending date.")
        ] = None,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get watched history

        #### &#128275; OAuth Optional &#128196; Pagination &#10024; Extended Info  Returns movies and episodes that a user has watched, sorted by most recent. You can optionally limit the `type` to `movies` or `episodes`. The `id` _(64-bit integer)_ in each history item uniquely identifies the event and can be used to remove individual events by using the [**/sync/history/remove**](#reference/sync/remove-from-history/get-watched-history) method. The `action` will be set to `scrobble`, `checkin`, or `watch`.  Specify a `type` and trakt `item_id` to limit the history for just that item. If the `item_id` is valid, but there is no history, an empty array will be returned.  | Example URL | Returns watches for... | |---|---| | `/history/movies/12601` | TRON: Legacy | | `/history/shows/1388` | All episodes of Breaking Bad | | `/history/seasons/3950` | All episodes of Breaking Bad: Season 1 | | `/history/episodes/73482` | Only episode 1 for Breaking Bad: Season 1 |

        :param id: User slug (required)
        :type id: str
        :param type:  (required)
        :type type: str
        :param item_id: Trakt ID for a specific item. (required)
        :type item_id: int
        :param start_at: Starting date.
        :type start_at: str
        :param end_at: Ending date.
        :type end_at: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watched_history_serialize(
            id=id,
            type=type,
            item_id=item_id,
            start_at=start_at,
            end_at=end_at,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchedHistory200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_watched_history_serialize(
        self,
        id,
        type,
        item_id,
        start_at,
        end_at,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        if item_id is not None:
            _path_params["item_id"] = item_id
        # process the query parameters
        if start_at is not None:

            _query_params.append(("start_at", start_at))

        if end_at is not None:

            _query_params.append(("end_at", end_at))

        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/history/{type}/{item_id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_watching(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> GetWatching200Response:
        """Get watching

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns a movie or episode if the user is currently watching something.  If they are not, it returns no data and a `204` HTTP status code.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watching_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetWatching200Response",
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_watching_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[GetWatching200Response]:
        """Get watching

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns a movie or episode if the user is currently watching something.  If they are not, it returns no data and a `204` HTTP status code.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watching_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetWatching200Response",
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_watching_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get watching

        #### &#128275; OAuth Optional &#10024; Extended Info  Returns a movie or episode if the user is currently watching something.  If they are not, it returns no data and a `204` HTTP status code.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watching_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "GetWatching200Response",
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_watching_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/watching",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def get_watchlist(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> List[GetWatchlist200ResponseInner]:
        """Get watchlist

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns all items in a user's watchlist filtered by type.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > The watchlist should not be used as a list of what the user is actively watching. Use a combination of the [**/sync/watched**](/reference/sync/get-watched) and [**/shows/:id/progress**](/reference/shows/watched-progress) methods to get what the user is actively watching.  #### Notes  Each watchlist item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.  #### Auto Removal  When an item is watched, it will be automatically removed from the watchlist. For shows and seasons, watching 1 episode will remove the entire show or season.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watchlist_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchlist200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def get_watchlist_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[List[GetWatchlist200ResponseInner]]:
        """Get watchlist

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns all items in a user's watchlist filtered by type.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > The watchlist should not be used as a list of what the user is actively watching. Use a combination of the [**/sync/watched**](/reference/sync/get-watched) and [**/shows/:id/progress**](/reference/shows/watched-progress) methods to get what the user is actively watching.  #### Notes  Each watchlist item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.  #### Auto Removal  When an item is watched, it will be automatically removed from the watchlist. For shows and seasons, watching 1 episode will remove the entire show or season.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watchlist_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchlist200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def get_watchlist_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        type: Annotated[
            StrictStr, Field(description="Filter for a specific item type")
        ],
        sort_by: Annotated[StrictStr, Field(description="Sort by a specific property")],
        sort_how: Annotated[StrictStr, Field(description="Sort direction")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Get watchlist

        #### 🔥 **VIP Enhanced** &#128275; OAuth Optional &#128196; Pagination Optional &#10024; Extended Info &#128513; Emojis  Returns all items in a user's watchlist filtered by type.  > ### ☣️ 🅸🅼🅿🅾🆁🆃🅰🅽🆃 > The watchlist should not be used as a list of what the user is actively watching. Use a combination of the [**/sync/watched**](/reference/sync/get-watched) and [**/shows/:id/progress**](/reference/shows/watched-progress) methods to get what the user is actively watching.  #### Notes  Each watchlist item contains a `notes` field with text entered by the user.  #### Sorting  Default sorting is based on the list defaults and sent in the `X-Sort-By` and `X-Sort-How` headers. If you specify the `sort_by` and `sort_how` parameters, the response will be sorted based on those values and sent in the `X-Applied-Sort-By` and `X-Applied-Sort-How` headers.  Some `sort_by` options are 🔥 **VIP Only** including `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, and `tmdb_votes`. If sent for a non VIP, the items will fall back to  `rank`.  #### Auto Removal  When an item is watched, it will be automatically removed from the watchlist. For shows and seasons, watching 1 episode will remove the entire show or season.

        :param id: User slug (required)
        :type id: str
        :param type: Filter for a specific item type (required)
        :type type: str
        :param sort_by: Sort by a specific property (required)
        :type sort_by: str
        :param sort_how: Sort direction (required)
        :type sort_how: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._get_watchlist_serialize(
            id=id,
            type=type,
            sort_by=sort_by,
            sort_how=sort_how,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "List[GetWatchlist200ResponseInner]",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _get_watchlist_serialize(
        self,
        id,
        type,
        sort_by,
        sort_how,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if type is not None:
            _path_params["type"] = type
        if sort_by is not None:
            _path_params["sort_by"] = sort_by
        if sort_how is not None:
            _path_params["sort_how"] = sort_how
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = []

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/{id}/watchlist/{type}/{sort_by}/{sort_how}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def like_a_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Like a list

        #### &#128274; OAuth Required  Votes help determine popular lists. Only one like is allowed per list per user.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._like_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def like_a_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Like a list

        #### &#128274; OAuth Required  Votes help determine popular lists. Only one like is allowed per list per user.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._like_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def like_a_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Like a list

        #### &#128274; OAuth Required  Votes help determine popular lists. Only one like is allowed per list per user.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._like_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _like_a_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists/{list_id}/like",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def remove_hidden_items(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_hidden_items_request: Optional[RemoveHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RemoveHiddenItems200Response:
        """Remove hidden items

        #### &#128274; OAuth Required  Unhide items for a specific section. Here's what type of items can unhidden for each section.  #### Unhideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_hidden_items_request:
        :type remove_hidden_items_request: RemoveHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_hidden_items_request=remove_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveHiddenItems200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def remove_hidden_items_with_http_info(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_hidden_items_request: Optional[RemoveHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[RemoveHiddenItems200Response]:
        """Remove hidden items

        #### &#128274; OAuth Required  Unhide items for a specific section. Here's what type of items can unhidden for each section.  #### Unhideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_hidden_items_request:
        :type remove_hidden_items_request: RemoveHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_hidden_items_request=remove_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveHiddenItems200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def remove_hidden_items_without_preload_content(
        self,
        section: StrictStr,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_hidden_items_request: Optional[RemoveHiddenItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Remove hidden items

        #### &#128274; OAuth Required  Unhide items for a specific section. Here's what type of items can unhidden for each section.  #### Unhideable Media Objects  | Section | Objects | |---|---|---| | `calendar` | `movie`, `show` | | `progress_watched` | `show`, `season` | | `progress_collected` | `show`, `season` | | `recommendations` | `movie`, `show` | | `comments` | `user` | | `dropped` | `show` |  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `users` | array | Array of `user` objects. |

        :param section:  (required)
        :type section: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_hidden_items_request:
        :type remove_hidden_items_request: RemoveHiddenItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_hidden_items_serialize(
            section=section,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_hidden_items_request=remove_hidden_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveHiddenItems200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _remove_hidden_items_serialize(
        self,
        section,
        trakt_api_version,
        trakt_api_key,
        remove_hidden_items_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if section is not None:
            _path_params["section"] = section
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if remove_hidden_items_request is not None:
            _body_params = remove_hidden_items_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/hidden/{section}/remove",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def remove_items_from_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_items_from_personal_list_request: Optional[
            RemoveItemsFromPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RemoveItemsFromPersonalList200Response:
        """Remove items from personal list

        #### &#128274; OAuth Required  Remove one or more items from a personal list.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_items_from_personal_list_request:
        :type remove_items_from_personal_list_request: RemoveItemsFromPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_items_from_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_items_from_personal_list_request=remove_items_from_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveItemsFromPersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def remove_items_from_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_items_from_personal_list_request: Optional[
            RemoveItemsFromPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[RemoveItemsFromPersonalList200Response]:
        """Remove items from personal list

        #### &#128274; OAuth Required  Remove one or more items from a personal list.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_items_from_personal_list_request:
        :type remove_items_from_personal_list_request: RemoveItemsFromPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_items_from_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_items_from_personal_list_request=remove_items_from_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveItemsFromPersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def remove_items_from_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        remove_items_from_personal_list_request: Optional[
            RemoveItemsFromPersonalListRequest
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Remove items from personal list

        #### &#128274; OAuth Required  Remove one or more items from a personal list.  #### JSON POST Data  | Key | Type | Value | |---|---|---| | `movies` | array | Array of `movie` objects. (see examples &#8594;) | | `shows` | array | Array of `show` objects. | | `seasons` | array | Array of `season` objects. | | `episodes` | array | Array of `episode` objects. | | `people` | array | Array of `person` objects. |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param remove_items_from_personal_list_request:
        :type remove_items_from_personal_list_request: RemoveItemsFromPersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_items_from_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            remove_items_from_personal_list_request=remove_items_from_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RemoveItemsFromPersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _remove_items_from_personal_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        remove_items_from_personal_list_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if remove_items_from_personal_list_request is not None:
            _body_params = remove_items_from_personal_list_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists/{list_id}/items/remove",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def remove_like_on_a_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Remove like on a list

        #### &#128274; OAuth Required  Remove a like on a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_like_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def remove_like_on_a_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Remove like on a list

        #### &#128274; OAuth Required  Remove a like on a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_like_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def remove_like_on_a_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Remove like on a list

        #### &#128274; OAuth Required  Remove a like on a list.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._remove_like_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _remove_like_on_a_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="DELETE",
            resource_path="/users/{id}/lists/{list_id}/like",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def reorder_a_users_lists(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_a_user_s_lists_request: Optional[ReorderAUserSListsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ReorderAUserSLists200Response:
        """Reorder a user's lists

        #### &#128274; OAuth Required  Reorder all lists by sending the updated `rank` of list ids. Use the [**/users/:id/lists**](#reference/users/lists) method to get all list ids.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_a_user_s_lists_request:
        :type reorder_a_user_s_lists_request: ReorderAUserSListsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_a_users_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_a_user_s_lists_request=reorder_a_user_s_lists_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderAUserSLists200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def reorder_a_users_lists_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_a_user_s_lists_request: Optional[ReorderAUserSListsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ReorderAUserSLists200Response]:
        """Reorder a user's lists

        #### &#128274; OAuth Required  Reorder all lists by sending the updated `rank` of list ids. Use the [**/users/:id/lists**](#reference/users/lists) method to get all list ids.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_a_user_s_lists_request:
        :type reorder_a_user_s_lists_request: ReorderAUserSListsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_a_users_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_a_user_s_lists_request=reorder_a_user_s_lists_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderAUserSLists200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def reorder_a_users_lists_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_a_user_s_lists_request: Optional[ReorderAUserSListsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Reorder a user's lists

        #### &#128274; OAuth Required  Reorder all lists by sending the updated `rank` of list ids. Use the [**/users/:id/lists**](#reference/users/lists) method to get all list ids.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_a_user_s_lists_request:
        :type reorder_a_user_s_lists_request: ReorderAUserSListsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_a_users_lists_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_a_user_s_lists_request=reorder_a_user_s_lists_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderAUserSLists200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _reorder_a_users_lists_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        reorder_a_user_s_lists_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if reorder_a_user_s_lists_request is not None:
            _body_params = reorder_a_user_s_lists_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists/reorder",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def reorder_items_on_a_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_watchlist_items_request: Optional[ReorderWatchlistItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ReorderItemsOnAList200Response:
        """Reorder items on a list

        #### &#128274; OAuth Required  Reorder all items on a list by sending the updated `rank` of list item ids. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get all list item ids.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_watchlist_items_request:
        :type reorder_watchlist_items_request: ReorderWatchlistItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_items_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_watchlist_items_request=reorder_watchlist_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderItemsOnAList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def reorder_items_on_a_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_watchlist_items_request: Optional[ReorderWatchlistItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ReorderItemsOnAList200Response]:
        """Reorder items on a list

        #### &#128274; OAuth Required  Reorder all items on a list by sending the updated `rank` of list item ids. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get all list item ids.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_watchlist_items_request:
        :type reorder_watchlist_items_request: ReorderWatchlistItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_items_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_watchlist_items_request=reorder_watchlist_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderItemsOnAList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def reorder_items_on_a_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        reorder_watchlist_items_request: Optional[ReorderWatchlistItemsRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Reorder items on a list

        #### &#128274; OAuth Required  Reorder all items on a list by sending the updated `rank` of list item ids. Use the [**/users/:id/lists/:list_id/items**](#reference/users/list-items) method to get all list item ids.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param reorder_watchlist_items_request:
        :type reorder_watchlist_items_request: ReorderWatchlistItemsRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._reorder_items_on_a_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            reorder_watchlist_items_request=reorder_watchlist_items_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "ReorderItemsOnAList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _reorder_items_on_a_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        reorder_watchlist_items_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if reorder_watchlist_items_request is not None:
            _body_params = reorder_watchlist_items_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="POST",
            resource_path="/users/{id}/lists/{list_id}/items/reorder",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def retrieve_settings(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RetrieveSettings200Response:
        """Retrieve settings

        #### &#128274; OAuth Required  Get the user's settings so you can align your app's experience with what they're used to on the trakt website. A globally unique `uuid` is also returned, which can be used to identify the user locally in your app if needed. However, the `uuid` can't be used to retrieve data from the Trakt API.  #### Limits  The `limits` object is useful to customize your user experience. For example, if the user has a `list` limit of `2`, you might want to show a message to the user that they need to upgrade to [**Trakt VIP**](https://trakt.tv/vip) to add more lists.  #### Permissions  The `permissions` object is also useful to customize your user experience. In general, an account will have permissions to do everything. However, we'll temporarily set a permission to `false` if the user triggers spam protections.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._retrieve_settings_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RetrieveSettings200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def retrieve_settings_with_http_info(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[RetrieveSettings200Response]:
        """Retrieve settings

        #### &#128274; OAuth Required  Get the user's settings so you can align your app's experience with what they're used to on the trakt website. A globally unique `uuid` is also returned, which can be used to identify the user locally in your app if needed. However, the `uuid` can't be used to retrieve data from the Trakt API.  #### Limits  The `limits` object is useful to customize your user experience. For example, if the user has a `list` limit of `2`, you might want to show a message to the user that they need to upgrade to [**Trakt VIP**](https://trakt.tv/vip) to add more lists.  #### Permissions  The `permissions` object is also useful to customize your user experience. In general, an account will have permissions to do everything. However, we'll temporarily set a permission to `false` if the user triggers spam protections.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._retrieve_settings_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RetrieveSettings200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def retrieve_settings_without_preload_content(
        self,
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Retrieve settings

        #### &#128274; OAuth Required  Get the user's settings so you can align your app's experience with what they're used to on the trakt website. A globally unique `uuid` is also returned, which can be used to identify the user locally in your app if needed. However, the `uuid` can't be used to retrieve data from the Trakt API.  #### Limits  The `limits` object is useful to customize your user experience. For example, if the user has a `list` limit of `2`, you might want to show a message to the user that they need to upgrade to [**Trakt VIP**](https://trakt.tv/vip) to add more lists.  #### Permissions  The `permissions` object is also useful to customize your user experience. In general, an account will have permissions to do everything. However, we'll temporarily set a permission to `false` if the user triggers spam protections.

        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._retrieve_settings_serialize(
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "RetrieveSettings200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _retrieve_settings_serialize(
        self,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="GET",
            resource_path="/users/settings",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def unfollow_this_user(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Unfollow this user

        #### &#128274; OAuth Required  Unfollow someone you already follow.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._unfollow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def unfollow_this_user_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Unfollow this user

        #### &#128274; OAuth Required  Unfollow someone you already follow.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._unfollow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def unfollow_this_user_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Unfollow this user

        #### &#128274; OAuth Required  Unfollow someone you already follow.

        :param id: User slug (required)
        :type id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._unfollow_this_user_serialize(
            id=id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _unfollow_this_user_serialize(
        self,
        id,
        trakt_api_version,
        trakt_api_key,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="DELETE",
            resource_path="/users/{id}/follow",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def update_a_list_item(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        list_item_id: Annotated[StrictInt, Field(description="List Item ID")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_a_watchlist_item_request: Optional[UpdateAWatchlistItemRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> None:
        """Update a list item

        #### 🔥 VIP Only &#128274; OAuth Required &#128513; Emojis  Update the `notes` on a single list item.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param list_item_id: List Item ID (required)
        :type list_item_id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_a_watchlist_item_request:
        :type update_a_watchlist_item_request: UpdateAWatchlistItemRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_a_list_item_serialize(
            id=id,
            list_id=list_id,
            list_item_id=list_item_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_a_watchlist_item_request=update_a_watchlist_item_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def update_a_list_item_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        list_item_id: Annotated[StrictInt, Field(description="List Item ID")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_a_watchlist_item_request: Optional[UpdateAWatchlistItemRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[None]:
        """Update a list item

        #### 🔥 VIP Only &#128274; OAuth Required &#128513; Emojis  Update the `notes` on a single list item.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param list_item_id: List Item ID (required)
        :type list_item_id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_a_watchlist_item_request:
        :type update_a_watchlist_item_request: UpdateAWatchlistItemRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_a_list_item_serialize(
            id=id,
            list_id=list_id,
            list_item_id=list_item_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_a_watchlist_item_request=update_a_watchlist_item_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def update_a_list_item_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        list_item_id: Annotated[StrictInt, Field(description="List Item ID")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_a_watchlist_item_request: Optional[UpdateAWatchlistItemRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Update a list item

        #### 🔥 VIP Only &#128274; OAuth Required &#128513; Emojis  Update the `notes` on a single list item.

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param list_item_id: List Item ID (required)
        :type list_item_id: int
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_a_watchlist_item_request:
        :type update_a_watchlist_item_request: UpdateAWatchlistItemRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_a_list_item_serialize(
            id=id,
            list_id=list_id,
            list_item_id=list_item_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_a_watchlist_item_request=update_a_watchlist_item_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "204": None,
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _update_a_list_item_serialize(
        self,
        id,
        list_id,
        list_item_id,
        trakt_api_version,
        trakt_api_key,
        update_a_watchlist_item_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        if list_item_id is not None:
            _path_params["list_item_id"] = list_item_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if update_a_watchlist_item_request is not None:
            _body_params = update_a_watchlist_item_request

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="PUT",
            resource_path="/users/{id}/lists/{list_id}/items/{list_item_id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )

    @validate_call
    def update_personal_list(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_personal_list_request: Optional[UpdatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> UpdatePersonalList200Response:
        """Update personal list

        #### &#128274; OAuth Required  Update a personal list by sending 1 or more parameters. If you update the list name, the original slug will still be retained so existing references to this list won't break.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Value | |---|---|---|---| | `name` | string | Name of the list. | | `description` | string | Description for this list. | | `privacy` | string | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | Should each item be numbered? | | `allow_comments` | boolean | Are comments allowed? | | `sort_by` | string | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_personal_list_request:
        :type update_personal_list_request: UpdatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_personal_list_request=update_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "UpdatePersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data

    @validate_call
    def update_personal_list_with_http_info(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_personal_list_request: Optional[UpdatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[UpdatePersonalList200Response]:
        """Update personal list

        #### &#128274; OAuth Required  Update a personal list by sending 1 or more parameters. If you update the list name, the original slug will still be retained so existing references to this list won't break.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Value | |---|---|---|---| | `name` | string | Name of the list. | | `description` | string | Description for this list. | | `privacy` | string | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | Should each item be numbered? | | `allow_comments` | boolean | Are comments allowed? | | `sort_by` | string | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_personal_list_request:
        :type update_personal_list_request: UpdatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_personal_list_request=update_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "UpdatePersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )

    @validate_call
    def update_personal_list_without_preload_content(
        self,
        id: Annotated[StrictStr, Field(description="User slug")],
        list_id: Annotated[StrictStr, Field(description="Trakt ID or Trakt slug")],
        trakt_api_version: Annotated[
            Optional[StrictStr], Field(description="e.g. 2")
        ] = None,
        trakt_api_key: Annotated[
            Optional[StrictStr], Field(description="e.g. [client_id]")
        ] = None,
        update_personal_list_request: Optional[UpdatePersonalListRequest] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)], Annotated[StrictFloat, Field(gt=0)]
            ],
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Update personal list

        #### &#128274; OAuth Required  Update a personal list by sending 1 or more parameters. If you update the list name, the original slug will still be retained so existing references to this list won't break.  #### Privacy  Lists will be `private` by default. Here is what each value means.  | Value | Privacy impact... | |---|---| | `private` | Only you can see the list. | | `link` | Anyone with the `share_link` can see the list. | | `friends` | Only your friends can see the list. | | `public` | Anyone can see the list. |  #### JSON POST Data  | Key | Type | Value | |---|---|---|---| | `name` | string | Name of the list. | | `description` | string | Description for this list. | | `privacy` | string | `private`, `link`, `friends`, `public` | | `display_numbers` | boolean | Should each item be numbered? | | `allow_comments` | boolean | Are comments allowed? | | `sort_by` | string | `rank`, `added`, `title`, `released`, `runtime`, `popularity`, `random`, `percentage`, `imdb_rating`, `tmdb_rating`, `rt_tomatometer`, `rt_audience`, `metascore`, `votes`, `imdb_votes`, `tmdb_votes`, `my_rating`, `watched`, `collected` | | `sort_how` | string | `asc`, `desc` |

        :param id: User slug (required)
        :type id: str
        :param list_id: Trakt ID or Trakt slug (required)
        :type list_id: str
        :param trakt_api_version: e.g. 2
        :type trakt_api_version: str
        :param trakt_api_key: e.g. [client_id]
        :type trakt_api_key: str
        :param update_personal_list_request:
        :type update_personal_list_request: UpdatePersonalListRequest
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """  # noqa: E501

        _param = self._update_personal_list_serialize(
            id=id,
            list_id=list_id,
            trakt_api_version=trakt_api_version,
            trakt_api_key=trakt_api_key,
            update_personal_list_request=update_personal_list_request,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index,
        )

        _response_types_map: Dict[str, Optional[str]] = {
            "200": "UpdatePersonalList200Response",
        }
        response_data = self.api_client.call_api(
            *_param, _request_timeout=_request_timeout
        )
        return response_data.response

    def _update_personal_list_serialize(
        self,
        id,
        list_id,
        trakt_api_version,
        trakt_api_key,
        update_personal_list_request,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {}

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        if id is not None:
            _path_params["id"] = id
        if list_id is not None:
            _path_params["list_id"] = list_id
        # process the query parameters
        # process the header parameters
        if trakt_api_version is not None:
            _header_params["trakt-api-version"] = trakt_api_version
        if trakt_api_key is not None:
            _header_params["trakt-api-key"] = trakt_api_key
        # process the form parameters
        # process the body parameter
        if update_personal_list_request is not None:
            _body_params = update_personal_list_request

        # set the HTTP header `Accept`
        if "Accept" not in _header_params:
            _header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

        # set the HTTP header `Content-Type`
        if _content_type:
            _header_params["Content-Type"] = _content_type
        else:
            _default_content_type = self.api_client.select_header_content_type(
                ["application/json"]
            )
            if _default_content_type is not None:
                _header_params["Content-Type"] = _default_content_type

        # authentication setting
        _auth_settings: List[str] = ["oauth2"]

        return self.api_client.param_serialize(
            method="PUT",
            resource_path="/users/{id}/lists/{list_id}",
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth,
        )
