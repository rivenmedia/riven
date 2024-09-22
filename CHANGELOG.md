# Changelog

## [0.13.3](https://github.com/rivenmedia/riven/compare/v0.13.2...v0.13.3) (2024-09-22)


### Bug Fixes

* mdblist error on imdb_id as NoneType ([048cd71](https://github.com/rivenmedia/riven/commit/048cd718af36538eb2a4443ee5a9e0f57fe3d130))

## [0.13.2](https://github.com/rivenmedia/riven/compare/v0.13.1...v0.13.2) (2024-09-22)


### Features

* add jellyfin & emby support. ([b600b6c](https://github.com/rivenmedia/riven/commit/b600b6ccb0cd50ad15e7a36465151793c766270e))


### Bug Fixes

* forgot to add updater files..... ([805182a](https://github.com/rivenmedia/riven/commit/805182a8648191f8b34b85697e897b6e2ef5c57b))


### Miscellaneous Chores

* release 0.13.2 ([76ccbf3](https://github.com/rivenmedia/riven/commit/76ccbf3080c6cc5af267d5e8a8b59860cd26c97c))

## [0.13.1](https://github.com/rivenmedia/riven/compare/v0.13.0...v0.13.1) (2024-09-22)


### Bug Fixes

* jackett isinstance using list instead of tuple ([c925a5b](https://github.com/rivenmedia/riven/commit/c925a5b75a4b90af16c1ff5b04c5f2869c232b0a))

## [0.13.0](https://github.com/rivenmedia/riven/compare/v0.12.8...v0.13.0) (2024-09-22)


### Features

* add jellyfin & emby support. ([375302e](https://github.com/rivenmedia/riven/commit/375302ea761b157178de4383fb6ad9a61e07f1d6))


### Bug Fixes

* mdblist nonetype on imdb_id ([10f1044](https://github.com/rivenmedia/riven/commit/10f1044792356a982c6aa3b07682c418d2fa8550))

## [0.12.8](https://github.com/rivenmedia/riven/compare/v0.12.7...v0.12.8) (2024-09-22)


### Bug Fixes

* fixed type on env var for symlink workers ([5c50cc6](https://github.com/rivenmedia/riven/commit/5c50cc60a086f22bc0bc07dfc54ecb4447e7712d))

## [0.12.7](https://github.com/rivenmedia/riven/compare/v0.12.6...v0.12.7) (2024-09-22)


### Bug Fixes

* lowered symlink max workers to 4 on db init ([0481b98](https://github.com/rivenmedia/riven/commit/0481b982a2c70a1130c66c4d7e01b71dbe7649aa))

## [0.12.6](https://github.com/rivenmedia/riven/compare/v0.12.5...v0.12.6) (2024-09-21)


### Bug Fixes

* remove missing attr ([5625307](https://github.com/rivenmedia/riven/commit/5625307a029bf0d59b6615958dbad2e020afb52e))

## [0.12.5](https://github.com/rivenmedia/riven/compare/v0.12.4...v0.12.5) (2024-09-21)


### Bug Fixes

* corrected rate limit for Torrentio ([540ba52](https://github.com/rivenmedia/riven/commit/540ba528797637e77accb9f66f7e38c58869b9d1))

## [0.12.4](https://github.com/rivenmedia/riven/compare/v0.12.3...v0.12.4) (2024-09-21)


### Bug Fixes

* plex rss startswith error ([9a2a0c1](https://github.com/rivenmedia/riven/commit/9a2a0c14211f68af523af4cdb3c8f742496a7722))
* revert schema validation, this is causing issues. ([12f4a1a](https://github.com/rivenmedia/riven/commit/12f4a1aa7d55210e1e65744c4ee8d8e082f3d68a))

## [0.12.3](https://github.com/rivenmedia/riven/compare/v0.12.2...v0.12.3) (2024-09-21)


### Bug Fixes

* mdblist list item validation fixed ([63fc95b](https://github.com/rivenmedia/riven/commit/63fc95b7ef69cb8ffb6aeadcfa20988d834ca65a))

## [0.12.2](https://github.com/rivenmedia/riven/compare/v0.12.1...v0.12.2) (2024-09-21)


### Bug Fixes

* update api with json schema ([1b7365c](https://github.com/rivenmedia/riven/commit/1b7365c77d3d121b6e7dccea2bd011fabb408aa6))

## [0.12.1](https://github.com/rivenmedia/riven/compare/v0.12.0...v0.12.1) (2024-09-21)


### Bug Fixes

* tweak db reset. fixed issue with mdblist. ([652924e](https://github.com/rivenmedia/riven/commit/652924eb8cf6d82aec90eb514628b3c51849ab98))

## [0.12.0](https://github.com/rivenmedia/riven/compare/v0.11.1...v0.12.0) (2024-09-20)


### Features

* add alias support in parsing when scraping torrents. several other tweaks. ([365f022](https://github.com/rivenmedia/riven/commit/365f02239cbed0f3e441a2e60abee31e78a05553))
* improvements to reset/retry/remove endpoints ([98f9e49](https://github.com/rivenmedia/riven/commit/98f9e49581bf43e3602d8dcb74f14a5bed1d529d))
* move symlink db init to progress bar. added threading to speed it up. needs testing! ([71fb859](https://github.com/rivenmedia/riven/commit/71fb8592528c9b1a60856ed5cedc069a3faf8b2c))
* update RTN to latest ([bbc5ce7](https://github.com/rivenmedia/riven/commit/bbc5ce75487ed87a989253b444f53c71d757f7db))


### Bug Fixes

* add infohash to scraped log msg. added exclude for unreleased to retry lib. ([9491e53](https://github.com/rivenmedia/riven/commit/9491e53045d97585afd57d73523bebe1997a3509))
* add sleep between event retries ([01e71f0](https://github.com/rivenmedia/riven/commit/01e71f021643348dc7dddc4b172cf0ecb548342d))
* add torrent name and infohash to download log. update deps to resolve parsing bugs. ([aecaf37](https://github.com/rivenmedia/riven/commit/aecaf3725075879c16651434fa6add10ef56fcff))
* anime movies not showing in correct dir ([44e0161](https://github.com/rivenmedia/riven/commit/44e0161c3234da3b6d26ce41ecaa50d557b1ff99))
* content services now only output new items that arent in the db. tidied some initial startup logging. ([797778c](https://github.com/rivenmedia/riven/commit/797778ca36095b350ec336900e283a2a70b0a95f))
* fixed bug with upscaled in parsett. update dep ([f3974ef](https://github.com/rivenmedia/riven/commit/f3974efc702fc351ddabfbbb8efa91d57d6b3d2c))
* fixed completed items being added to queue on startup ([d45882f](https://github.com/rivenmedia/riven/commit/d45882f9ec405e9f3ee8423183e0ef38e6e63dd5))
* moved log cleaning to scheduled func. fixed bug with new furiosa movie ([475f934](https://github.com/rivenmedia/riven/commit/475f9345ad40adbbb8e8b2a453cede253f86d2c0))
* movie obj trying to index as show type ([c0e1e2c](https://github.com/rivenmedia/riven/commit/c0e1e2c4a1b1c068a1fe04bfc300a10dea927000))
* ranking wasnt followed by downloader ([578ae8f](https://github.com/rivenmedia/riven/commit/578ae8f88b3865222e6ab6cca6e53ff73273ef12))
* resetting a item would make it unresettable again ([f5c849f](https://github.com/rivenmedia/riven/commit/f5c849f0ccbb7028609221c397991e0f64380df5))
* revert back to old way of retry library ([46a6510](https://github.com/rivenmedia/riven/commit/46a651043a65e5d42ecb8d104dcf7ac477985d18))
* revert item in db check during state processing ([18f22c1](https://github.com/rivenmedia/riven/commit/18f22c1d1cb68ed1d8f8748bba9a63d122cf499d))
* select biggest file for movie caches ([c6f9337](https://github.com/rivenmedia/riven/commit/c6f93375222dc32cc8b06060459be607e17758ba))
* slow api calls due to calculating state for every item ([f5e08f8](https://github.com/rivenmedia/riven/commit/f5e08f8fd506eae2f6f693347e774929edbb24fe))
* throw exception instead of error on plex validation ([17a579e](https://github.com/rivenmedia/riven/commit/17a579e1f129533e337e31990970978976bc7b91))
* tweak logging for db init from symlinks. ([2f15fbd](https://github.com/rivenmedia/riven/commit/2f15fbd938dc70e8c1eb709a4d8debf281d9e2b0))
* unhardcode orionoid limitcount. whoops! ([f7668c6](https://github.com/rivenmedia/riven/commit/f7668c68bd7b787145ce212fb0479705608db191))

## [0.11.1](https://github.com/rivenmedia/riven/compare/v0.11.0...v0.11.1) (2024-08-30)


### Miscellaneous Chores

* release 0.11.1 ([4453a15](https://github.com/rivenmedia/riven/commit/4453a15d7d82edadbac8d9a96941217d09467798))

## [0.11.0](https://github.com/rivenmedia/riven/compare/v0.10.5...v0.11.0) (2024-08-30)


### Features

* "Ongoing" and "Unreleased" states for shows ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* Removal of Symlinks and Overseerr requests on removal of item from riven. ([276ed79](https://github.com/rivenmedia/riven/commit/276ed79f4374a0812300f78c1de42bae3a019bfd))


### Bug Fixes

* event updates for frontend ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* get all content from content services (previously only one item was picked) ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* remove local updater and stop possibility of looping with symlinked state ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* trakt indexer not picking up shows ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* trakt indexing was not copying correct item attributes in previous release ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))
* updated settings.json variables for opensubtitles ([71012ef](https://github.com/rivenmedia/riven/commit/71012efe405ad2a26420ed331ceeb27ca49e580e))
* validate subtitle providers on init, remove addic7ed and napiprojekt providers ([6ee4742](https://github.com/rivenmedia/riven/commit/6ee47424fa5878bda99c0b4c57701ff24832af00))

## [0.10.5](https://github.com/rivenmedia/riven/compare/v0.10.4...v0.10.5) (2024-08-19)


### Features

* add a subtitle provider (subliminal) ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))


### Bug Fixes

* address high memory usage ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))
* various small bug fixes ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))


### Miscellaneous Chores

* bump version to 0.10.5 ([5c3c39f](https://github.com/rivenmedia/riven/commit/5c3c39f1eafd66e9a20b21a2cdb8215d7f2aebbb))
* release 0.10.4 ([cacbc46](https://github.com/rivenmedia/riven/commit/cacbc46f35096956aab1f77d794942d68d76de16))

## [0.10.4](https://github.com/rivenmedia/riven/compare/v0.10.4...v0.10.4) (2024-08-19)


### Features

* add a subtitle provider (subliminal) ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))


### Bug Fixes

* address high memory usage ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))
* various small bug fixes ([f96fe54](https://github.com/rivenmedia/riven/commit/f96fe54aa1ff6efe8ffcef161a173b74a7ca81c4))


### Miscellaneous Chores

* release 0.10.4 ([cacbc46](https://github.com/rivenmedia/riven/commit/cacbc46f35096956aab1f77d794942d68d76de16))

## [0.10.3](https://github.com/rivenmedia/riven/compare/v0.10.2...v0.10.3) (2024-08-17)


### Bug Fixes

* address memory leak by closing SQLAlchemy sessions and add connection pool options ([0ebd38f](https://github.com/rivenmedia/riven/commit/0ebd38fb3802d143b1bd9266f248d34c532d78e7))

## [0.10.2](https://github.com/rivenmedia/riven/compare/v0.10.1...v0.10.2) (2024-08-15)


### Bug Fixes

* correct attribute names in zilean scraper ([6e26304](https://github.com/rivenmedia/riven/commit/6e26304f89cfb5456714d424cf8e6b75c8a4a3bc))

## [0.10.1](https://github.com/rivenmedia/riven/compare/v0.10.0...v0.10.1) (2024-08-11)


### Bug Fixes

* add cascade drop on alembic table ([b110cac](https://github.com/rivenmedia/riven/commit/b110cac68b24a92ee196317b7a4df3a5718d475e))

## [0.10.0](https://github.com/rivenmedia/riven/compare/v0.9.2...v0.10.0) (2024-08-11)


### Features

* release 0.9.3 ([a072821](https://github.com/rivenmedia/riven/commit/a072821c3d1ee82e8580494906881338f30d8691))

## [0.9.2](https://github.com/rivenmedia/riven/compare/v0.9.1...v0.9.2) (2024-07-31)


### Features

* add ignore hash feature ([d8e565f](https://github.com/rivenmedia/riven/commit/d8e565f946e4bb75c6f4fa9736b36c59d3c8aef1))


### Bug Fixes

* moved blacklisting to an attr of item ([989bf8b](https://github.com/rivenmedia/riven/commit/989bf8bc56c0bc7271aa000de454ecaf784b6e3a))
* removed lazy from mapped_column on blacklisted_streams ([aca5a0f](https://github.com/rivenmedia/riven/commit/aca5a0f07e9bea50583efb9fc8f4d093372dbd83))

## [0.9.1](https://github.com/rivenmedia/riven/compare/v0.9.0...v0.9.1) (2024-07-31)


### Bug Fixes

* add libtorrent to docker image ([af88478](https://github.com/rivenmedia/riven/commit/af88478add731a351420595aafb2577bf721d7c0))
* merged changes with db fixes ([f3103b6](https://github.com/rivenmedia/riven/commit/f3103b6f9dda4d078be32ccd5fad09f5d041bbce))


### Documentation

* Update ElfHosted details in README ([#578](https://github.com/rivenmedia/riven/issues/578)) ([6047b96](https://github.com/rivenmedia/riven/commit/6047b96edcbbdd5fcaf2f73ecdba9c6c6f0c93a2))

## [0.9.0](https://github.com/rivenmedia/riven/compare/v0.8.4...v0.9.0) (2024-07-27)


### Features

* add automatic dev builds in pipeline ([d55e061](https://github.com/rivenmedia/riven/commit/d55e06173b3a35de6c0b586fd9aee0216e9455da))


### Bug Fixes

* add alembic reinit to hard reset ([91ba58b](https://github.com/rivenmedia/riven/commit/91ba58bfa24a50759115cd9e7190f81b7ddb58fe))
* add extra logging to track issue. added mutex to add_to_running ([87c3241](https://github.com/rivenmedia/riven/commit/87c324189a1dd78fed0b06e502e10eba4ae1db58))
* add hard reset to cli ([e3366a6](https://github.com/rivenmedia/riven/commit/e3366a630e0b2774cded15e7197187712e9561a4))
* add parent object into stream ([16c1ceb](https://github.com/rivenmedia/riven/commit/16c1ceb3bd071be501d4436ba29e8ba90820c588))
* include stream in db, rework blacklisting ([03c6023](https://github.com/rivenmedia/riven/commit/03c602362ac07122cd5e0153226a7136b1eb330a))
* plex watchlist updated to work with new api changes. added db guards. improved trakt id detection. changed rd blacklisting to only blacklist on movie/episode items or on empty rd cache ([ce074b3](https://github.com/rivenmedia/riven/commit/ce074b3268f075365ad406af4cf629d1715458ec))
* remove state logging where state is not available ([76fdd89](https://github.com/rivenmedia/riven/commit/76fdd8949f0c9620ad421c8b870e518823fcff04))
* tidied push_event_queue. this func has been causing looping issues we're seeing. ([5c7943d](https://github.com/rivenmedia/riven/commit/5c7943d8b9255f49da01834c39cc901c401507c9))
* update rollback ([e57d06c](https://github.com/rivenmedia/riven/commit/e57d06c4966b3e0178a56bfdce848872abf8b81a))
* wrong symlink count at startup. corrected post symlink handling ([cbe9012](https://github.com/rivenmedia/riven/commit/cbe901260eeaa2465b93708134e715297ee0d998))

## [0.8.4](https://github.com/rivenmedia/riven/compare/v0.8.3...v0.8.4) (2024-07-25)


### Bug Fixes

* Release 0.8.4 ([266cf0c](https://github.com/rivenmedia/riven/commit/266cf0cb455354d54edcb2e47ffc632f6c8e6b7b))
* tweaked comet scraper. removed poetry venv from entrypoint. ([32be8fc](https://github.com/rivenmedia/riven/commit/32be8fc174eca148c2577a3941005da41e7f8513))

## [0.8.3](https://github.com/rivenmedia/riven/compare/v0.8.2...v0.8.3) (2024-07-25)


### Miscellaneous Chores

* release 0.8.3 ([66085da](https://github.com/rivenmedia/riven/commit/66085da71a86f507d09cf21df121a24a2b2a0537))

## [0.8.2](https://github.com/rivenmedia/riven/compare/v0.8.1...v0.8.2) (2024-07-24)


### Bug Fixes

* api port back to 8080 ([6a7cf4f](https://github.com/rivenmedia/riven/commit/6a7cf4fb16fc39142ab613afa05afca64908bfca))

## [0.8.1](https://github.com/rivenmedia/riven/compare/v0.8.0...v0.8.1) (2024-07-24)


### Bug Fixes

* moved poetry files to root workdir ([a0eb41b](https://github.com/rivenmedia/riven/commit/a0eb41b7aa93a635deaf04a56f57a0201c91d418))
* revert appendleft on push_event_queue ([8becb59](https://github.com/rivenmedia/riven/commit/8becb5923b1ef103ddd4cb76f59778b7c1f2269f))

## 0.8.0 (2024-07-24)


### ⚠ BREAKING CHANGES

* add BACKEND_URL environment variable to support for custom backend URL ([#518](https://github.com/rivenmedia/riven/issues/518))

### Features

* add BACKEND_URL environment variable to support for custom backend URL ([#518](https://github.com/rivenmedia/riven/issues/518)) ([e48ee93](https://github.com/rivenmedia/riven/commit/e48ee932823ad38732533ebaeb3de6937d416354))
* add changelog. add version.txt ([#562](https://github.com/rivenmedia/riven/issues/562)) ([14eff8d](https://github.com/rivenmedia/riven/commit/14eff8d7c01f57f2659eddf4c619d30690b23001))
* Add endpoint to manually request items ([#551](https://github.com/rivenmedia/riven/issues/551)) ([652671e](https://github.com/rivenmedia/riven/commit/652671e15379846700ec1f1c86651a6c1463f5b9))
* add lazy loading for images in statistics and home pages ([#502](https://github.com/rivenmedia/riven/issues/502)) ([fadab73](https://github.com/rivenmedia/riven/commit/fadab73b6e8b3d9e6453f64e25a480b0f299a24a))
* add support for mdblist urls ([#402](https://github.com/rivenmedia/riven/issues/402)) ([282eb35](https://github.com/rivenmedia/riven/commit/282eb3565b213c52aea66a597092e998e27708fa))
* add top rated section ([#505](https://github.com/rivenmedia/riven/issues/505)) ([5ef689b](https://github.com/rivenmedia/riven/commit/5ef689bebc70d2fbe71485f876698a37a09083be))
* added content settings and other minor improvements ([#88](https://github.com/rivenmedia/riven/issues/88)) ([f3444cc](https://github.com/rivenmedia/riven/commit/f3444ccfadeb5e0375f9331968d81bf079a0fcd3))
* added tmdb api support ([#410](https://github.com/rivenmedia/riven/issues/410)) ([adc4e9a](https://github.com/rivenmedia/riven/commit/adc4e9a0622b2cf4deff5dc8daed56e4b03c0d5f))
* enforce conventional commits ([5ffddc1](https://github.com/rivenmedia/riven/commit/5ffddc106a42dea5d406f7ae1a6bcd887cddcab0))
* finish up trakt integration ([#333](https://github.com/rivenmedia/riven/issues/333)) ([5ca02a4](https://github.com/rivenmedia/riven/commit/5ca02a48fd22daff35230e5ed49cba5f7ee88efe))
* fixed size of command palette on large device ([#98](https://github.com/rivenmedia/riven/issues/98)) ([c3326dd](https://github.com/rivenmedia/riven/commit/c3326dd92da82c196416ce6e8d45a53601b05a3d))
* formatted using black & prettier (in frontend) and moved to crlf ([#51](https://github.com/rivenmedia/riven/issues/51)) ([315f310](https://github.com/rivenmedia/riven/commit/315f31096569e72e6cc3080f32b3e1e63bc26817))
* frontend and backend improvements ([#197](https://github.com/rivenmedia/riven/issues/197)) ([080d02c](https://github.com/rivenmedia/riven/commit/080d02cf465456d230528b0b9b2aef94f071595e))
* frontend backend and ui improvements ([#358](https://github.com/rivenmedia/riven/issues/358)) ([8a9e941](https://github.com/rivenmedia/riven/commit/8a9e941f4fd92e80c1093a74e562e46c80201a3e))
* frontend fixes and improvements ([#29](https://github.com/rivenmedia/riven/issues/29)) ([fd19f8a](https://github.com/rivenmedia/riven/commit/fd19f8a8c599d5f0ddc50704b01d926255a5b1ca))
* frontend improvements ([#158](https://github.com/rivenmedia/riven/issues/158)) ([1e714bf](https://github.com/rivenmedia/riven/commit/1e714bfcddb3fc97133d47060be31df2f5bff00e))
* frontend improvements ([#159](https://github.com/rivenmedia/riven/issues/159)) ([b6c2699](https://github.com/rivenmedia/riven/commit/b6c269999e2883c50630a2c1690c93b323045156))
* frontend improvements ([#16](https://github.com/rivenmedia/riven/issues/16)) ([d958a4b](https://github.com/rivenmedia/riven/commit/d958a4bae419d9245d1f983f9566375e5e1983a0))
* frontend improvements ([#50](https://github.com/rivenmedia/riven/issues/50)) ([ffec1c4](https://github.com/rivenmedia/riven/commit/ffec1c4766f423392910830bf0c7be9962eb9530))
* frontend improvements,, added settings! ([#86](https://github.com/rivenmedia/riven/issues/86)) ([2641de0](https://github.com/rivenmedia/riven/commit/2641de0f39eab2debe0b5fb998545f153280a24d))
* frontend rewrite to sveltekit with basic features ([#13](https://github.com/rivenmedia/riven/issues/13)) ([8c519d7](https://github.com/rivenmedia/riven/commit/8c519d7b2a39af4cceb0352c46024475d90d645e))
* improved frontend ui ([#195](https://github.com/rivenmedia/riven/issues/195)) ([77e7ad7](https://github.com/rivenmedia/riven/commit/77e7ad7309f4775f24aad49b6a904e8c7f08e38e))
* improved ui ([#422](https://github.com/rivenmedia/riven/issues/422)) ([71e6365](https://github.com/rivenmedia/riven/commit/71e6365d1c96d224e2e946040f41901f13abb4c0))
* Listrr Support Added ([#136](https://github.com/rivenmedia/riven/issues/136)) ([943b098](https://github.com/rivenmedia/riven/commit/943b098f396426c67848f28f2ad226e8f055fb8b))


### Bug Fixes

* add BACKEND_URL arg to avoid build error ([#519](https://github.com/rivenmedia/riven/issues/519)) ([b7309c4](https://github.com/rivenmedia/riven/commit/b7309c4916a330356d429afb6a1e20cff56eebcc))
* add BACKEND_URL arg to avoid build error ([#520](https://github.com/rivenmedia/riven/issues/520)) ([ffad7e3](https://github.com/rivenmedia/riven/commit/ffad7e31d493f4306d4d8f33bb7afd1d780a76d9))
* add new settings changes to frontend ([#416](https://github.com/rivenmedia/riven/issues/416)) ([38c1b75](https://github.com/rivenmedia/riven/commit/38c1b751eae37cec489c18bcf0a531ec23ee2a05))
* add try-catch to submit_job for runtime errors ([d09f512](https://github.com/rivenmedia/riven/commit/d09f512a1667a73cb63193eb29d7a4bf9fc1fed5))
* change mdblist str to int ([#382](https://github.com/rivenmedia/riven/issues/382)) ([b88c475](https://github.com/rivenmedia/riven/commit/b88c475459c140bd9b5ae95cdd1583c41dee94f9))
* change Path objs to str ([#389](https://github.com/rivenmedia/riven/issues/389)) ([41bc74e](https://github.com/rivenmedia/riven/commit/41bc74e4fdb1f03dd988923b82dec19985c9b1e1))
* change version filename in dockerfile ([5bf802d](https://github.com/rivenmedia/riven/commit/5bf802d399516633ec4683f4940ad3b649038386))
* comet validation needed is_ok on response instead of ok ([#557](https://github.com/rivenmedia/riven/issues/557)) ([5f8d8c4](https://github.com/rivenmedia/riven/commit/5f8d8c42a8d02f586121da072697d40c8e5313ad))
* continue instead of exit on failed to enhance metadata ([#560](https://github.com/rivenmedia/riven/issues/560)) ([657068f](https://github.com/rivenmedia/riven/commit/657068f8e1c4e241d096eaadd52e850eafb27aba))
* convert str to path first ([#388](https://github.com/rivenmedia/riven/issues/388)) ([2944bf0](https://github.com/rivenmedia/riven/commit/2944bf07398972e3271e98cabcb64febd828addc))
* correct parsing of external id's ([#163](https://github.com/rivenmedia/riven/issues/163)) ([b155e60](https://github.com/rivenmedia/riven/commit/b155e606ffbb130b1df4ad15246ca74bad490699))
* crash on failed metadata enhancement ([88b7f0b](https://github.com/rivenmedia/riven/commit/88b7f0b98c1df574a06fd43cdbaaed50a69a0dc9))
* disable ruff in ci ([5ffddc1](https://github.com/rivenmedia/riven/commit/5ffddc106a42dea5d406f7ae1a6bcd887cddcab0))
* docker metadata from release please ([08b7144](https://github.com/rivenmedia/riven/commit/08b7144bb319986185d3cb1975dbef77a9945690))
* docker metadata from release please ([e48659f](https://github.com/rivenmedia/riven/commit/e48659ff574f7caf6ab37c7d2a035c4bbe4edf01))
* episode attr error when checking Show type ([#387](https://github.com/rivenmedia/riven/issues/387)) ([3e0a575](https://github.com/rivenmedia/riven/commit/3e0a5758910adc4b02d90bb2839f77ec3e6f6d3f))
* fix around 200 ruff errors ([d30679d](https://github.com/rivenmedia/riven/commit/d30679d9adcfd41f751349328f658187a8285072))
* fix around 200 ruff errors ([a73fbfd](https://github.com/rivenmedia/riven/commit/a73fbfd6a6f0e1464cf05e55492c3b69876363c0))
* fixed about page github errors and other minor improvements ([#347](https://github.com/rivenmedia/riven/issues/347)) ([0c87f47](https://github.com/rivenmedia/riven/commit/0c87f47bbbe69de33c7bab9bdecc61d845f597fa))
* fixed the errors in frontend to make it working, still some changes and rewrite needed for improvements ([#346](https://github.com/rivenmedia/riven/issues/346)) ([03cd45c](https://github.com/rivenmedia/riven/commit/03cd45c2cfe4f04d49f2bea754a5a641c68ba9f2))
* handle bad quality manually in parser ([#145](https://github.com/rivenmedia/riven/issues/145)) ([6101511](https://github.com/rivenmedia/riven/commit/6101511b2589b7731025052db403b2c0adfd0376))
* lower the z index and increase z index of header ([#504](https://github.com/rivenmedia/riven/issues/504)) ([41e2c71](https://github.com/rivenmedia/riven/commit/41e2c716db8e0ead3291e7f71fca9f20dd99ca94))
* min/max filesize being returned undefined ([fadab73](https://github.com/rivenmedia/riven/commit/fadab73b6e8b3d9e6453f64e25a480b0f299a24a))
* minor fix to hooks.server.ts ([#355](https://github.com/rivenmedia/riven/issues/355)) ([8edb0ce](https://github.com/rivenmedia/riven/commit/8edb0ce766dc5079b0f6ede269e7e2b2461f1d0d))
* minor ui improvements ([#503](https://github.com/rivenmedia/riven/issues/503)) ([8085f15](https://github.com/rivenmedia/riven/commit/8085f15d424ca671b1f0293fbda70559682c5923))
* remove frontend ci ([#552](https://github.com/rivenmedia/riven/issues/552)) ([eeb2d00](https://github.com/rivenmedia/riven/commit/eeb2d00610e2f4f7f3c1cfeb3922600fb645739a))
* revert trakt/item modules back to 0.7.4 ([864535b](https://github.com/rivenmedia/riven/commit/864535b01dc790142e21284d24f71335dd116e38))
* RTN import incorrect after updating package ([#415](https://github.com/rivenmedia/riven/issues/415)) ([f2b86e0](https://github.com/rivenmedia/riven/commit/f2b86e08d73479addf7bada77b23c8cfd72752a3))
* switch to dynamic private env ([#522](https://github.com/rivenmedia/riven/issues/522)) ([eb8d3d0](https://github.com/rivenmedia/riven/commit/eb8d3d0a9010a9389d68dff8c4dd9cbdd6b71944))
* switch to dynamic private env ([#523](https://github.com/rivenmedia/riven/issues/523)) ([0355e64](https://github.com/rivenmedia/riven/commit/0355e6485c6e43f66a04165a85a890aaf1d8c0c3))
* text color on light theme ([#506](https://github.com/rivenmedia/riven/issues/506)) ([5379784](https://github.com/rivenmedia/riven/commit/5379784e7f84f97955fc4728cdb3301919c6f0ac))
* tidy parser. add lint/test to makefile. ([#241](https://github.com/rivenmedia/riven/issues/241)) ([bd82b23](https://github.com/rivenmedia/riven/commit/bd82b2392330da31e443e66e780b01bc26f3a60d))
* update packages ([15df41d](https://github.com/rivenmedia/riven/commit/15df41d3d30a03f9371bf90f99eedc96b32f41c7))
* validate rd user data and updater settings on startup ([6016c54](https://github.com/rivenmedia/riven/commit/6016c54e1518a850102b6d09c6b51b3cef721a2d))
* versioning to come from pyproject.toml ([d30679d](https://github.com/rivenmedia/riven/commit/d30679d9adcfd41f751349328f658187a8285072))


### Documentation

* minor improvements ([#160](https://github.com/rivenmedia/riven/issues/160)) ([0d0a12f](https://github.com/rivenmedia/riven/commit/0d0a12f5516254acd8be81fb97cd7694e9010d21))
* minor improvements ([#161](https://github.com/rivenmedia/riven/issues/161)) ([2ad7986](https://github.com/rivenmedia/riven/commit/2ad79866e93336f2977fa1d6762bc867a26a1571))
* minor improvements ([#162](https://github.com/rivenmedia/riven/issues/162)) ([bac8284](https://github.com/rivenmedia/riven/commit/bac8284f38f1cbe7e1d1b05dd486ba7eae68d5b2))


### Miscellaneous Chores

* release 0.8.0 ([091d0bc](https://github.com/rivenmedia/riven/commit/091d0bc13dad19dbbf4b3e8d870458e3cddcf246))
