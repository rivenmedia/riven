# Changelog

## [0.23.7](https://github.com/rivenmedia/riven/compare/v0.23.6...v0.23.7) (2025-09-02)


### Bug Fixes

* fixed incompleted items from reinit db ([add17ed](https://github.com/rivenmedia/riven/commit/add17ed5f219c2cd338501be00e7f64b71c3f7bd))

## [0.23.6](https://github.com/rivenmedia/riven/compare/v0.23.5...v0.23.6) (2025-08-24)


### Bug Fixes

* revert max_delay in limiter back to 0 ([dc7ef05](https://github.com/rivenmedia/riven/commit/dc7ef05922ac4423ad8d0ad296af2d2366fcdcd3))

## [0.23.5](https://github.com/rivenmedia/riven/compare/v0.23.4...v0.23.5) (2025-08-20)


### Bug Fixes

* temporarily use fixed plexapi dependency from fork ([#1135](https://github.com/rivenmedia/riven/issues/1135)) ([e1fcb49](https://github.com/rivenmedia/riven/commit/e1fcb495f1e38c73c043c2416f932b834e391936))

## [0.23.4](https://github.com/rivenmedia/riven/compare/v0.23.3...v0.23.4) (2025-08-15)


### Bug Fixes

* check for valid symlink video types on db reinit ([c61074f](https://github.com/rivenmedia/riven/commit/c61074f36a39418ac6f73fe2f7684d90115e31d3))

## [0.23.3](https://github.com/rivenmedia/riven/compare/v0.23.2...v0.23.3) (2025-08-15)


### Bug Fixes

* add more parent item data ([25e6810](https://github.com/rivenmedia/riven/commit/25e681055c255d50421cad762d2a3c5fae9100c3))

## [0.23.2](https://github.com/rivenmedia/riven/compare/v0.23.1...v0.23.2) (2025-08-14)


### Bug Fixes

* add proxy_url setting for trakt ([44fb11b](https://github.com/rivenmedia/riven/commit/44fb11b28a9a0782b40941f47ddaf228e2539e4e))
* added default 10s max delay limit to fix hanging in RD requests ([50a1714](https://github.com/rivenmedia/riven/commit/50a1714a059afa8140a6c00b01b66a5f0c6a65c7))

## [0.23.1](https://github.com/rivenmedia/riven/compare/v0.23.0...v0.23.1) (2025-08-10)


### Bug Fixes

* fixed notadirectoryerror on re-init symlinks ([ff97b5c](https://github.com/rivenmedia/riven/commit/ff97b5c4806be568f62a08fb014f035aa0a719bc))

## [0.23.0](https://github.com/rivenmedia/riven/compare/v0.22.0...v0.23.0) (2025-08-06)


### Features

* **api:** added reindex api route to manually reindex items ([ed80503](https://github.com/rivenmedia/riven/commit/ed80503d106e510966040915742e16dfeb7603e7))


### Bug Fixes

* swapped to use trakt indexer directly on reindex route ([315fc29](https://github.com/rivenmedia/riven/commit/315fc29461a435dd4710657ecd1231bf0da8b2bf))

## [0.22.0](https://github.com/rivenmedia/riven/compare/v0.21.21...v0.22.0) (2025-08-05)


### Features

* Add TorBox downloader to Riven ([#1074](https://github.com/rivenmedia/riven/issues/1074)) ([9875109](https://github.com/rivenmedia/riven/commit/9875109e25c3c67cc3cdcd2cd450547dce365854))
* add TRAKT_API_CLIENT_ID env to override the default trakt client id used by trakt indexer ([7fd087f](https://github.com/rivenmedia/riven/commit/7fd087f7b46cde4b6542f1d57ca394a1b4bf28ca))
* set the media type when performing search ([#1110](https://github.com/rivenmedia/riven/issues/1110)) ([16ada64](https://github.com/rivenmedia/riven/commit/16ada643305024ac3e1b3b7f8defc1faef6aa77e))


### Bug Fixes

* fixed hanging on downloader. improved logging. ([#1116](https://github.com/rivenmedia/riven/issues/1116)) ([422db78](https://github.com/rivenmedia/riven/commit/422db783e1a3f07262601478841d9576d70cb332))
* handle create_item_from_imdb_id response exception ([d91dd25](https://github.com/rivenmedia/riven/commit/d91dd254c08fbb410706d4fc6cb97f3691ebc67c))
* readtimeout issue with rd, updated timeout to 25s instead of 15s. added exception handling for this as well. ([45105db](https://github.com/rivenmedia/riven/commit/45105dbd70854d70c56f4ebec3d6ca6ea7ef1504))

## [0.21.21](https://github.com/rivenmedia/riven/compare/v0.21.20...v0.21.21) (2025-05-12)


### Bug Fixes

* anime fix for non-anime related content ([a19e09e](https://github.com/rivenmedia/riven/commit/a19e09e91ca3a31c39563f25e9d8cbc4eca98319))
* copy attrs down to episode as well ([0372ad5](https://github.com/rivenmedia/riven/commit/0372ad5c6c35815d882a5f915d0f3fc3331aa403))
* fixed bug on failing to lowercase during anime check ([9c0ea94](https://github.com/rivenmedia/riven/commit/9c0ea94fe928ffc68417a93eb5439a2c70b05b0c))
* further improvements to validations ([f0f1a3b](https://github.com/rivenmedia/riven/commit/f0f1a3ba17129406dd0dc4ea4e008ddfc35183e9))
* im going back to bed.. ([853586f](https://github.com/rivenmedia/riven/commit/853586f9c6181cfdae763bd6b19db3444499f31c))
* restrict usage of comet from elfhosted instances ([77117db](https://github.com/rivenmedia/riven/commit/77117db99c2c8a78fc814aac4c42e57790744500))
* restrict usage of mediafusion from elfhosted instances ([38fc68b](https://github.com/rivenmedia/riven/commit/38fc68bc3bebd6d38cf56d713a94c7013d3d6929))

## [0.21.20](https://github.com/rivenmedia/riven/compare/v0.21.19...v0.21.20) (2025-04-26)


### Bug Fixes

* improve skipping special episodes/seasons ([2d3f927](https://github.com/rivenmedia/riven/commit/2d3f9274a5f4cea7bd6c8924363e6df306d8a977))
* improved logging on retry_library and update_ongoing for clarity ([01554a5](https://github.com/rivenmedia/riven/commit/01554a5e3b93d1f8a02b7e5630e0e358ea8fb1e0))
* notifications simplified. fixed anime type check on chinese and korean anime. ([7a98d75](https://github.com/rivenmedia/riven/commit/7a98d7512fe3416de7d8d940527a1459a1fdef4f))
* update parsett from 1.6.7 to 1.6.11 (latest) ([e8e16cb](https://github.com/rivenmedia/riven/commit/e8e16cbeb415a867ef08eea047cda4d34cc885e7))

## [0.21.19](https://github.com/rivenmedia/riven/compare/v0.21.18...v0.21.19) (2025-04-10)


### Bug Fixes

* duplicate notifications being sent when using multiple service urls ([#1059](https://github.com/rivenmedia/riven/issues/1059)) ([5408d55](https://github.com/rivenmedia/riven/commit/5408d55a8c152e7ff0d61a00866b186059ab1eb4))

## [0.21.18](https://github.com/rivenmedia/riven/compare/v0.21.17...v0.21.18) (2025-04-03)


### Bug Fixes

* add ffprobe endpoint. fixed trakt id getattr on item. ([a1b23ad](https://github.com/rivenmedia/riven/commit/a1b23ad69338cf48c43f9ef4fa2a0121babd026c))

## [0.21.17](https://github.com/rivenmedia/riven/compare/v0.21.16...v0.21.17) (2025-04-01)


### Bug Fixes

* switch scrape endpoint to list input ([9ef5751](https://github.com/rivenmedia/riven/commit/9ef5751e3caa2022eeb0400de4ee80069e55abbd))

## [0.21.16](https://github.com/rivenmedia/riven/compare/v0.21.15...v0.21.16) (2025-04-01)


### Bug Fixes

* add calendar and parse endpoints ([78445af](https://github.com/rivenmedia/riven/commit/78445af572152a0f45e68efedefd33b9b436fbf6))

## [0.21.15](https://github.com/rivenmedia/riven/compare/v0.21.14...v0.21.15) (2025-03-30)


### Bug Fixes

* get your shit together goldyy ([19522df](https://github.com/rivenmedia/riven/commit/19522df4b967aae144895043024a86d4785eb2eb))

## [0.21.14](https://github.com/rivenmedia/riven/compare/v0.21.13...v0.21.14) (2025-03-30)


### Bug Fixes

* add summary and operation ID to abort manual scraping session endpoint ([28be3d7](https://github.com/rivenmedia/riven/commit/28be3d79f0ef3bd10b253afe94fc955900e647f5))
* fixed resume button in frontend, notifications for shows, and alldebrid missing path attr bug ([7fa60f1](https://github.com/rivenmedia/riven/commit/7fa60f1588797c5b28a3ce573cff31347e9cd362))
* jellyfin updating using wrong endpoint ([07e2b84](https://github.com/rivenmedia/riven/commit/07e2b8483acd48c1525030920d9f2b3c23a06766))
* missing stream for completed item. ([11379dd](https://github.com/rivenmedia/riven/commit/11379dd6e863ce97139f64f422ac95f2b751f30a))
* raise instead of return on remove api endpoint ([1fb4574](https://github.com/rivenmedia/riven/commit/1fb45746f39c4db2b8d029f285a5b9c7798935a6))
* rewrite prowlarr ([b13a52f](https://github.com/rivenmedia/riven/commit/b13a52ff70b034bcb36d3dacdb9c78acd63fa6e3))
* season attr bug in prowlarr ([f253cd4](https://github.com/rivenmedia/riven/commit/f253cd457f4777563437748877a0a8118859da23))
* update comet scraper ([9163c43](https://github.com/rivenmedia/riven/commit/9163c43a98c080898623d7f1b26acac890ad7046))
* use temp request handler on fetching indexers ([343bc55](https://github.com/rivenmedia/riven/commit/343bc553439188aeaa2bbb3de136c5dd30487a76))
* wrong attr in prowlar scraper ([b23339a](https://github.com/rivenmedia/riven/commit/b23339a3a862ed0392437ff0823b501be77bb449))

## [0.21.13](https://github.com/rivenmedia/riven/compare/v0.21.12...v0.21.13) (2025-03-18)


### Bug Fixes

* updated parsett to 1.6.2. made cached status false by default in api ([b9ae02e](https://github.com/rivenmedia/riven/commit/b9ae02e0cd9072691e1fd7eba8413fd54f359b85))

## [0.21.12](https://github.com/rivenmedia/riven/compare/v0.21.11...v0.21.12) (2025-03-18)


### Bug Fixes

* add cache status on manual scrape (revert) ([26b85d8](https://github.com/rivenmedia/riven/commit/26b85d862aab7109bc8eaf9e3cccaa1e76109c80))

## [0.21.11](https://github.com/rivenmedia/riven/compare/v0.21.10...v0.21.11) (2025-03-18)


### Bug Fixes

* fixed duplicate imdb endpoint. better handling of indexing bad items during scraping ([f6595fc](https://github.com/rivenmedia/riven/commit/f6595fceb5a200beb5fe09d3a46f618e40666695))

## [0.21.10](https://github.com/rivenmedia/riven/compare/v0.21.9...v0.21.10) (2025-03-18)


### Bug Fixes

* fixed api endpoints. tidied logging. fixed show/season not black… ([#1036](https://github.com/rivenmedia/riven/issues/1036)) ([0b84cca](https://github.com/rivenmedia/riven/commit/0b84ccaa7ad09a1bb178c09e8c57847b72422577))

## [0.21.9](https://github.com/rivenmedia/riven/compare/v0.21.8...v0.21.9) (2025-03-13)


### Bug Fixes

* improve episode validation on manual scrape ([1f866d6](https://github.com/rivenmedia/riven/commit/1f866d62b82383b240c8f7adb149c3e6ff17ae86))

## [0.21.8](https://github.com/rivenmedia/riven/compare/v0.21.7...v0.21.8) (2025-03-13)


### Bug Fixes

* fixed season and episode manual scrape session handling ([59f1e75](https://github.com/rivenmedia/riven/commit/59f1e751f87f912bfd2fc87c647bdf2f7fd54ee7))

## [0.21.7](https://github.com/rivenmedia/riven/compare/v0.21.6...v0.21.7) (2025-03-13)


### Bug Fixes

* reorder stream addition to item on manual scrape ([7c351cf](https://github.com/rivenmedia/riven/commit/7c351cfd1770767dc112000fb7f4a397ce26000c))

## [0.21.6](https://github.com/rivenmedia/riven/compare/v0.21.5...v0.21.6) (2025-03-13)


### Bug Fixes

* improved episode handling on manual scraping ([#1025](https://github.com/rivenmedia/riven/issues/1025)) ([a949d94](https://github.com/rivenmedia/riven/commit/a949d94eed3af6308915c01596861da3b9782fcc))

## [0.21.5](https://github.com/rivenmedia/riven/compare/v0.21.4...v0.21.5) (2025-03-12)


### Bug Fixes

* added reset streams endpoint ([0f22105](https://github.com/rivenmedia/riven/commit/0f221058d9689c8ddc44fd68a257bf66315f454e))
* fixed blacklist loop on symlink failure. improved scrape on non anime show packs. ([4f29e97](https://github.com/rivenmedia/riven/commit/4f29e9797ddd45f208a902b004fd781d3eb028d8))
* fixed rd downloading issue. added symlink repair api endpoint. ([0354889](https://github.com/rivenmedia/riven/commit/0354889b9f5db7b64ac5e252437ef0d88f669939))
* fixed symlink repair. added update_ongoing and retry_library as api endpoints. ([b7c3c97](https://github.com/rivenmedia/riven/commit/b7c3c970ba7ae583c1fe71d7f45fbfca81be178c))
* increased episode check on show/season packs from 1 to 7 ([fb24ab4](https://github.com/rivenmedia/riven/commit/fb24ab4bd58c5551cd0abf3bc8f8eefbfe2766a9))
* revert trakt cache checking in api ([5778217](https://github.com/rivenmedia/riven/commit/5778217f370bf1c30bb5a07b1f2bf9d48194d528))
* symlink repair error due to missing import ([c01bbff](https://github.com/rivenmedia/riven/commit/c01bbffcb9e7f1381f09070b3efab87e125b6cc7))
* update instance availability logic for the scrape endpoint ([#1023](https://github.com/rivenmedia/riven/issues/1023)) ([486bbff](https://github.com/rivenmedia/riven/commit/486bbfffdfbb5f3afc3196af56019c8eee681655))
* update instance availibility logic for the scrape endpoint ([486bbff](https://github.com/rivenmedia/riven/commit/486bbfffdfbb5f3afc3196af56019c8eee681655))
* various fixes. improved scraping and downloading. ([#1024](https://github.com/rivenmedia/riven/issues/1024)) ([ba57f75](https://github.com/rivenmedia/riven/commit/ba57f75bee691e25cd37bd78e918703fd75094ae))

## [0.21.4](https://github.com/rivenmedia/riven/compare/v0.21.3...v0.21.4) (2025-02-28)


### Bug Fixes

* frontend missing buttons. updated PTT. ([31b29f7](https://github.com/rivenmedia/riven/commit/31b29f7114f4ea6944332c2670afc8c0816d9da1))

## [0.21.3](https://github.com/rivenmedia/riven/compare/v0.21.2...v0.21.3) (2025-02-28)


### Bug Fixes

* multiple logging improvements and various other fixes ([#1015](https://github.com/rivenmedia/riven/issues/1015)) ([5185dbd](https://github.com/rivenmedia/riven/commit/5185dbd8ab62953c55aba2e958d098b828d56174))

## [0.21.2](https://github.com/rivenmedia/riven/compare/v0.21.1...v0.21.2) (2025-02-26)


### Bug Fixes

* reverted postprocessing to patch subliminal issue ([ebc7fc9](https://github.com/rivenmedia/riven/commit/ebc7fc970cea37480db51ece2c670056c2da5239))

## [0.21.1](https://github.com/rivenmedia/riven/compare/v0.21.0...v0.21.1) (2025-02-25)


### Bug Fixes

* correct cache usage logic in TraktAPI ([6405dd6](https://github.com/rivenmedia/riven/commit/6405dd6b88e725af03e3a9d4a4737f03164a4017))
* ensure item retrieval returns a valid result in get_item function ([2523993](https://github.com/rivenmedia/riven/commit/25239939a5916f6d3d3fd3018ce58be3033f9b9d))
* minor tweaks and validation handling ([#1009](https://github.com/rivenmedia/riven/issues/1009)) ([41509ba](https://github.com/rivenmedia/riven/commit/41509bacfc6b712316d57dfba6529c55707c1b7f))

## [0.21.0](https://github.com/rivenmedia/riven/compare/v0.20.1...v0.21.0) (2025-02-20)


### ⚠ BREAKING CHANGES

* Torbox Removal ([#971](https://github.com/rivenmedia/riven/issues/971))

### Features

* Add 6th retry attempt to symlinker ([#926](https://github.com/rivenmedia/riven/issues/926)) ([6d43d7f](https://github.com/rivenmedia/riven/commit/6d43d7f34bacb82ad8e2cca08f6ab15c6b3a2e2c))
* add extended websocket support ([#1007](https://github.com/rivenmedia/riven/issues/1007)) ([16ac0e4](https://github.com/rivenmedia/riven/commit/16ac0e482b3f64edca4f02e9bd224c90c9c255ec))
* add pause and failed states. fixed mediafusion. added more logging to parsing. ([#977](https://github.com/rivenmedia/riven/issues/977)) ([2dc1498](https://github.com/rivenmedia/riven/commit/2dc14984dc467d5c800fc7060cf97163441e5d90))
* add proxy_url to torrentio ([#994](https://github.com/rivenmedia/riven/issues/994)) ([d1ad6fd](https://github.com/rivenmedia/riven/commit/d1ad6fdab429ac24ddf8d309e33a5696e88bd9ac))
* add RIVEN_SETTINGS_FILENAME env ([#993](https://github.com/rivenmedia/riven/issues/993)) ([2eb98ca](https://github.com/rivenmedia/riven/commit/2eb98cad97190650fddd8cfb54ff4353641312f2))


### Bug Fixes

* add alldebrid as option in mediafusion ([42829a2](https://github.com/rivenmedia/riven/commit/42829a2e245169443187ca581bf2dce190f1c7c9))
* add strong typed response to scrape api endpoint ([44f047e](https://github.com/rivenmedia/riven/commit/44f047e7e00c58628fa0669f1630b80f8bbe936e))
* api manual scraping fixes. wip ([7fb50f8](https://github.com/rivenmedia/riven/commit/7fb50f856d2395d2cbdc977a35e0a5ae152eecc0))
* correct route formatting for unblacklist_stream endpoint ([4b64e0f](https://github.com/rivenmedia/riven/commit/4b64e0f1ae405504f72bac5984bb6d280bea78a9))
* enable conditional caching for Trakt API session ([#978](https://github.com/rivenmedia/riven/issues/978)) ([6b295f6](https://github.com/rivenmedia/riven/commit/6b295f6e4d2696dbaf13b121bd635c7df6287821))
* fixed alldebrid instantavail file processing ([#916](https://github.com/rivenmedia/riven/issues/916)) ([d2a6b5b](https://github.com/rivenmedia/riven/commit/d2a6b5bbf0e2c83e3f6f4899e8a367af72d05ae7))
* listrr response being treated as a dict ([#979](https://github.com/rivenmedia/riven/issues/979)) ([d42fb35](https://github.com/rivenmedia/riven/commit/d42fb35d873428f8e0e3bdf27e03b978f3ffc8a4))
* manual scraping updated for downloader rework ([346b352](https://github.com/rivenmedia/riven/commit/346b352c3c6dfcf857b04d65a396ce06e1d70263))
* no streams found or filtered streams from adult content throws e… ([#976](https://github.com/rivenmedia/riven/issues/976)) ([a18a66c](https://github.com/rivenmedia/riven/commit/a18a66ce8747bd1d81e119acbc320f30d03a8557))
* no streams found or filtered streams from adult content throws error ([a18a66c](https://github.com/rivenmedia/riven/commit/a18a66ce8747bd1d81e119acbc320f30d03a8557))
* remove catalog configuration from Mediafusion settings and scraper ([#919](https://github.com/rivenmedia/riven/issues/919)) ([fc7ed05](https://github.com/rivenmedia/riven/commit/fc7ed053dbd9c39df869c61a147bfbf8890a6503))
* resolve trakt data fetch error ([#987](https://github.com/rivenmedia/riven/issues/987)) ([ffc630e](https://github.com/rivenmedia/riven/commit/ffc630e9a198cb1d6eff178f35624de63c2d85ea))
* Torbox Removal ([#971](https://github.com/rivenmedia/riven/issues/971)) ([5d49499](https://github.com/rivenmedia/riven/commit/5d49499ddfc2582945048f1444a3d3445bb58cef))
* update .env names and fix SKIP_TRAKT_CACHE ([#1001](https://github.com/rivenmedia/riven/issues/1001)) ([3504754](https://github.com/rivenmedia/riven/commit/3504754f40b9dbeb923bd160ff1148707846ebd9))
* update ListrrAPI validate method to use correct path ([#906](https://github.com/rivenmedia/riven/issues/906)) ([7659a37](https://github.com/rivenmedia/riven/commit/7659a37d30704b46107b6441e7a40f386ec82101))
* updated sample handling for allowed video files ([8a5e849](https://github.com/rivenmedia/riven/commit/8a5e849aca371c28c418270bdbb863770389f2b7))


### Miscellaneous Chores

* release 0.21.0 ([c9cc836](https://github.com/rivenmedia/riven/commit/c9cc836b5033396175e960ee8f93ab78bfc8e453))

## [0.20.1](https://github.com/rivenmedia/riven/compare/v0.20.0...v0.20.1) (2024-11-27)


### Bug Fixes

* add User-Agent header to torrentio request ([bb799b5](https://github.com/rivenmedia/riven/commit/bb799b57fe6ddfbc5871a87f926d211898776351))
* consolidate User-Agent header usage in Torrentio scraper ([83418d6](https://github.com/rivenmedia/riven/commit/83418d6f8095a0c74c16f20c7598d63e5841237c))
* fixed RD, TB and AD support ([f945d25](https://github.com/rivenmedia/riven/commit/f945d25fe0bff83e60f6fde43c0fc27ea6314c32))
* improve mediafusion validation on startup ([3511e6c](https://github.com/rivenmedia/riven/commit/3511e6cfda6fcf6045cbf9014e1e454ae4937d73))
* moved downloader proxy settings to parent instead of per debrid ([50d9d6e](https://github.com/rivenmedia/riven/commit/50d9d6eb5e37912beff765f7bf753cf08486216b))

## [0.20.0](https://github.com/rivenmedia/riven/compare/v0.19.0...v0.20.0) (2024-11-20)


### Features

* add denied reasoning when trashing torrents and added adult parsing ([#888](https://github.com/rivenmedia/riven/issues/888)) ([d3b5293](https://github.com/rivenmedia/riven/commit/d3b5293dfdb07c7466ff77f7dba16754fbfa7d79))

## [0.19.0](https://github.com/rivenmedia/riven/compare/v0.18.0...v0.19.0) (2024-11-14)


### Features

* add reindexing of movie/shows in unreleased or ongoing state ([139d936](https://github.com/rivenmedia/riven/commit/139d936442de4d5a37e32fb482beb2e65557464c))
* added upload logs endpoint to be used by frontend ([3ad6cae](https://github.com/rivenmedia/riven/commit/3ad6caeb6b0299cf60314ca2f87a76e30eba57be))
* implement filesize validation for movies and episodes ([#869](https://github.com/rivenmedia/riven/issues/869)) ([d1041db](https://github.com/rivenmedia/riven/commit/d1041db78c295873f8f5cf572d9f296704c85506))


### Bug Fixes

* added cleaner directory log when rebuilding symlinks ([bb85517](https://github.com/rivenmedia/riven/commit/bb85517197bf10e855c1cfaa41e0d765dfd298e1))
* chunk initial symlinks on re-ingest ([#882](https://github.com/rivenmedia/riven/issues/882)) ([21cd393](https://github.com/rivenmedia/riven/commit/21cd393913253678f4f580330aa4e28e114fc16f))
* correct Prowlarr capabilities ([#879](https://github.com/rivenmedia/riven/issues/879)) ([f2636e4](https://github.com/rivenmedia/riven/commit/f2636e408f66a730915cfb2f49f56e38b1faf8c9))
* detecting multiple episodes in symlink library ([#862](https://github.com/rivenmedia/riven/issues/862)) ([ebd11fd](https://github.com/rivenmedia/riven/commit/ebd11fd7d94a7763f0869bde6ed9b545d499e14e))
* disable reindexing. wip. change get items endpoint to use id instead of imdbid. ([5123567](https://github.com/rivenmedia/riven/commit/5123567d4fe9ce8ef65d4fc09fa130d19a714ef7))
* more tweaks for scrapers and fine tuning. ([b25658d](https://github.com/rivenmedia/riven/commit/b25658d21a43d2e0a097abf608c7a96216ed90ec))
* re-check ongoing/unreleased items ([#880](https://github.com/rivenmedia/riven/issues/880)) ([47f23fa](https://github.com/rivenmedia/riven/commit/47f23fa0d78c41473445140801f5c6a6a6e076aa))
* skip unindexable items when resetting db ([98cb2c1](https://github.com/rivenmedia/riven/commit/98cb2c12acc40fd2f2c12f79af247f89aa5638fa))
* update state filtering logic to allow 'All' as a valid state ([#870](https://github.com/rivenmedia/riven/issues/870)) ([4430d2d](https://github.com/rivenmedia/riven/commit/4430d2daf682f26b9141a3130fa869524840a2d9))
* updated mediafusion and tweaked scrape func to be cleaner ([73c0bcc](https://github.com/rivenmedia/riven/commit/73c0bcc91eb99c4825764775e986057951c713ae))
* updated torbox scraper to use api key. refactored scrapers slightly. added more logging to scrapers. ([afdb9f6](https://github.com/rivenmedia/riven/commit/afdb9f6f202690dae9b04e7d2c8ce5e078b94d0c))

## [0.18.0](https://github.com/rivenmedia/riven/compare/v0.17.0...v0.18.0) (2024-11-06)


### Features

* add retry policy and connection pool configuration to request utils ([#864](https://github.com/rivenmedia/riven/issues/864)) ([1713a51](https://github.com/rivenmedia/riven/commit/1713a5169805cabcc828b3f82204c05f796a9aa6))


### Bug Fixes

* add HTTP adapter configuration for Jackett and Prowlarr scrapers to manage connection pool size ([0c8057a](https://github.com/rivenmedia/riven/commit/0c8057aef45fcccd2c855a8413729b39020439db))
* add HTTP adapter configuration for Jackett and Prowlarr scrapers… ([#865](https://github.com/rivenmedia/riven/issues/865)) ([0c8057a](https://github.com/rivenmedia/riven/commit/0c8057aef45fcccd2c855a8413729b39020439db))
* fixed log for downloaded message ([656506f](https://github.com/rivenmedia/riven/commit/656506ffba7ed34256291a31eb882dee3b5f4de6))
* remove orionoid sub check ([d2cb0d9](https://github.com/rivenmedia/riven/commit/d2cb0d9baa4be3421e5c56cafdbb6d5c024ca675))
* removed unused functions relating to resolving duplicates ([5aec8fb](https://github.com/rivenmedia/riven/commit/5aec8fb036b9b549477304f46b6ff0548a72d7f7))
* wrong headers attr and added orionoid sub check ([91d3f7d](https://github.com/rivenmedia/riven/commit/91d3f7d87c56a2cb4cb6898b57c480d1b4df94e9))

## [0.17.0](https://github.com/rivenmedia/riven/compare/v0.16.2...v0.17.0) (2024-11-05)


### Features

* add manual torrent adding ([#785](https://github.com/rivenmedia/riven/issues/785)) ([acb22ce](https://github.com/rivenmedia/riven/commit/acb22ce9bb54a09a542e1a587181eb731700243e))
* Add Most Wanted items from Trakt ([#777](https://github.com/rivenmedia/riven/issues/777)) ([325df42](https://github.com/rivenmedia/riven/commit/325df42989e8d6d841ab625284c54d78b9dc02d1))
* add rate limiting tests and update dependencies ([#857](https://github.com/rivenmedia/riven/issues/857)) ([27c8534](https://github.com/rivenmedia/riven/commit/27c8534f3084404f80e6bf8fc01b1be0b9d98ad8))
* auth bearer authentication ([0de32fd](https://github.com/rivenmedia/riven/commit/0de32fd9e7255c8c91aae4cecb428cabe180aea9))
* database migrations, so long db resets ([#858](https://github.com/rivenmedia/riven/issues/858)) ([14e818f](https://github.com/rivenmedia/riven/commit/14e818f1b84870ce7cd0af62319685a62cc32c1a))
* enhance session management and event processing ([#842](https://github.com/rivenmedia/riven/issues/842)) ([13aa94e](https://github.com/rivenmedia/riven/commit/13aa94e5587661770d385d634fa1a3cef9b0d882))
* filesize filter ([d2f8374](https://github.com/rivenmedia/riven/commit/d2f8374ae95fc763842750a67d1d9b9f3c545a8d))
* integrate dependency injection with kink library ([#859](https://github.com/rivenmedia/riven/issues/859)) ([ed5fb2c](https://github.com/rivenmedia/riven/commit/ed5fb2cb1a33ad00fa332c11bbbcd67017fe9695))
* requests second pass ([#848](https://github.com/rivenmedia/riven/issues/848)) ([d41c2ff](https://github.com/rivenmedia/riven/commit/d41c2ff33cc1e88325da6c8f9e10c24199eeb291))
* stream management endpoints ([d75149e](https://github.com/rivenmedia/riven/commit/d75149eb5b246bf7312ddb3d3fac85417e2cb215))
* we now server sse via /stream ([efbc471](https://github.com/rivenmedia/riven/commit/efbc471e4f4429c098df2a601b3f3c42b98afbb7))


### Bug Fixes

* add default value for API_KEY ([bc6ff28](https://github.com/rivenmedia/riven/commit/bc6ff28ff5b1d1632f2dd2ca64743c4012ccc396))
* add python-dotenv to load .env variables ([65a4aec](https://github.com/rivenmedia/riven/commit/65a4aec275a1f7768a77ef0227d6fb402f9a8612))
* correct type hint for incomplete_retries in StatsResponse ([#839](https://github.com/rivenmedia/riven/issues/839)) ([f91ffec](https://github.com/rivenmedia/riven/commit/f91ffece2a70af71967903847068642e58a4f51c))
* duplicate item after scraping for media that isn't in the database already ([#834](https://github.com/rivenmedia/riven/issues/834)) ([4d7ac8d](https://github.com/rivenmedia/riven/commit/4d7ac8d62a22bf2453ed6e433f43f8ebdb969e5f))
* ensure selected files are stored in session during manual selection ([#841](https://github.com/rivenmedia/riven/issues/841)) ([86e6fd0](https://github.com/rivenmedia/riven/commit/86e6fd0f1ddd5f89800d96569288a85238ba8c80))
* files sometimes not found in mount ([02b7a81](https://github.com/rivenmedia/riven/commit/02b7a81f4b6f93d06e59f06791e99e1860e3ebe9))
* future cancellation resulted in reset, retry endpoints fialing ([#817](https://github.com/rivenmedia/riven/issues/817)) ([19cedc8](https://github.com/rivenmedia/riven/commit/19cedc843382acb837c9cd23ddec522d342ed9f5))
* handle removal of nested media items in remove_item function ([#840](https://github.com/rivenmedia/riven/issues/840)) ([2096a4e](https://github.com/rivenmedia/riven/commit/2096a4e85bd613136d9dfe353cdbd7ed0d765e3f))
* hotfix blacklist active stream ([8631008](https://github.com/rivenmedia/riven/commit/86310082d77de6550d5277ffc21c7f0a28167502))
* invalid rd instant availibility call if no infohashes should be checked ([#843](https://github.com/rivenmedia/riven/issues/843)) ([19cf38f](https://github.com/rivenmedia/riven/commit/19cf38fe0d8fefe1de341654401d0e8801b27bb1))
* jackett again - my bad ([#860](https://github.com/rivenmedia/riven/issues/860)) ([703ad33](https://github.com/rivenmedia/riven/commit/703ad334c06671ecf3336beaf328e8a738bf0d87))
* MediaFusion scraper. ([#850](https://github.com/rivenmedia/riven/issues/850)) ([0bbde7d](https://github.com/rivenmedia/riven/commit/0bbde7d3c0e817321b7603f4e5acc1ae80ca9f58))
* mediafusion sometimes throwing error when parsing response ([#844](https://github.com/rivenmedia/riven/issues/844)) ([9c093ac](https://github.com/rivenmedia/riven/commit/9c093ac817ba541aecc552c3e1a6170cf767d58d))
* misleading message when manually adding a torrent ([#822](https://github.com/rivenmedia/riven/issues/822)) ([18cfa3b](https://github.com/rivenmedia/riven/commit/18cfa3b441dba2dc1040157b39b228db35693118))
* overseerr outputting items without imdbid's ([45528a9](https://github.com/rivenmedia/riven/commit/45528a9ee6701190dcc7c5358b2ea22365afcd60))
* remove accidental cache enablement ([877ffec](https://github.com/rivenmedia/riven/commit/877ffec4c9cbcd54906f9bb86a45467c2c3974c7))
* retry api now resets scraped_at ([#816](https://github.com/rivenmedia/riven/issues/816)) ([2676fe8](https://github.com/rivenmedia/riven/commit/2676fe801fe2522b8558daaa0fbbd899c0df5dbe))

## [0.16.2](https://github.com/rivenmedia/riven/compare/v0.16.1...v0.16.2) (2024-10-20)


### Bug Fixes

* fixed replace torrents ([8db6541](https://github.com/rivenmedia/riven/commit/8db6541f5820f52ebb8550b81010e28bf9be589a))

## [0.16.1](https://github.com/rivenmedia/riven/compare/v0.16.0...v0.16.1) (2024-10-19)


### Bug Fixes

* check item instance before add from content services ([7aa48ed](https://github.com/rivenmedia/riven/commit/7aa48ede46dc553beb424d2c9d765a293e6cc7d2))
* listrr outputting imdbids instead of items. solves [#802](https://github.com/rivenmedia/riven/issues/802) ([502e52b](https://github.com/rivenmedia/riven/commit/502e52b5ecff8ac869de28654963fdfad3a2aa13))

## [0.16.0](https://github.com/rivenmedia/riven/compare/v0.15.3...v0.16.0) (2024-10-18)


### Features

* Add debugpy as optional to entrypoint script if DEBUG env variable is set to anything. ([24904fc](https://github.com/rivenmedia/riven/commit/24904fcc27ccba96dfa13245f8eb3add096b36dd))
* Types for the FastAPI API and API refactor ([#748](https://github.com/rivenmedia/riven/issues/748)) ([9eec02d](https://github.com/rivenmedia/riven/commit/9eec02dd65ace8598edc8822f1c1d69c5a5b1537))


### Bug Fixes

* address memory usage ([#787](https://github.com/rivenmedia/riven/issues/787)) ([612964e](https://github.com/rivenmedia/riven/commit/612964ee77395e99610db46febb14bd273aecc30))
* changed default update interval from 5m to 24h on content list services ([7074fb0](https://github.com/rivenmedia/riven/commit/7074fb0e11ec16a34980bf9242bdb4cacd050760))
* delete the movie relation before deleting the mediaitem ([#788](https://github.com/rivenmedia/riven/issues/788)) ([5bfe63a](https://github.com/rivenmedia/riven/commit/5bfe63aa31e78d418bb5df9a962b0ff4fe467bfe))
* fix state filter in items endpoint ([#791](https://github.com/rivenmedia/riven/issues/791)) ([1f24e4f](https://github.com/rivenmedia/riven/commit/1f24e4fe787e174a366c4e1e20f94fef263db76e))
* fixed wrongful checking of bad dirs and images when rebuilding symlink library ([8501c36](https://github.com/rivenmedia/riven/commit/8501c3634ff03b75b7fcc4419db1e4908580b360))
* improved removing items from database ([e4b6e2b](https://github.com/rivenmedia/riven/commit/e4b6e2b61893517c01a35a272806a319c845dd77))
* lower max events added to queue ([197713a](https://github.com/rivenmedia/riven/commit/197713ae9da78eb1d674e313489f0a378c29d03a))
* minor fixes post merge ([01a506f](https://github.com/rivenmedia/riven/commit/01a506faabc675226d6a1412cb2cd3065e3437ca))
* plex watchlist not returning any items ([bf34db5](https://github.com/rivenmedia/riven/commit/bf34db52bc1fc184597e1c6721968d7a33a5b15c))
* remove add to recurring on plex watchlist ([943433c](https://github.com/rivenmedia/riven/commit/943433cba70dd9a3e51d7c51b4eb1e23d098345e))
* reset the scraped time when replacing magnets ([82fe92d](https://github.com/rivenmedia/riven/commit/82fe92d952642408b98ea6a3f1fad51c86adffcb))
* respect orm when removing items ([d6722fa](https://github.com/rivenmedia/riven/commit/d6722fa41e33bcfcb9ceaac32f4be4985af40b15))
* serialize subtitles for api response ([0dd561a](https://github.com/rivenmedia/riven/commit/0dd561a11880ab4cfce4b6631b385b414b953f93))
* service endpoint response for downloaders ([#782](https://github.com/rivenmedia/riven/issues/782)) ([f2020ed](https://github.com/rivenmedia/riven/commit/f2020ed8c0007e125871329e5cd3e821a9522494))
* state filter in items endpoint ([1f24e4f](https://github.com/rivenmedia/riven/commit/1f24e4fe787e174a366c4e1e20f94fef263db76e))
* stream results on stats endpoint ([ff14f85](https://github.com/rivenmedia/riven/commit/ff14f85532221997215e1a1f246a5b8041183e05))
* switch to batched streaming stats endpoint for inc items ([a8a6aa9](https://github.com/rivenmedia/riven/commit/a8a6aa9f0670098441839042ab2ed3d4990860cd))
* switch to generator for reset/retry endpoints ([bf4fc0e](https://github.com/rivenmedia/riven/commit/bf4fc0e79a31f2c4d8701e09ae662ebf3c5e2b3f))
* update full compose with latest zilean changes ([d3ca7a4](https://github.com/rivenmedia/riven/commit/d3ca7a4abd2e0bc7cbef34ab5bbde201986acf55))


### Documentation

* remove duplicate service from readme ([8a9942a](https://github.com/rivenmedia/riven/commit/8a9942a20039281b00b2ddb261f75a543af13ac9))

## [0.15.3](https://github.com/rivenmedia/riven/compare/v0.15.2...v0.15.3) (2024-10-03)


### Bug Fixes

* fixed comet unpack issue ([6ae2a68](https://github.com/rivenmedia/riven/commit/6ae2a686456c3c60390d635fcd6ddb24bdcd6a78))

## [0.15.2](https://github.com/rivenmedia/riven/compare/v0.15.1...v0.15.2) (2024-10-01)


### Bug Fixes

* add log back to orion ([5a81a0c](https://github.com/rivenmedia/riven/commit/5a81a0c14b76f6b90b2d4224b53948707d867040))
* changed to speed mode by default for downloaders ([7aeca0b](https://github.com/rivenmedia/riven/commit/7aeca0bf4fe38ec6ebe7d513ca8e305ef8223b08))
* orionoid and mediafusion fixed ([52f466e](https://github.com/rivenmedia/riven/commit/52f466e35e2d2d3e2cfc9ce81f903a8c0df5e9f4))
* prevent error when more than two streams with the same hash in set_torrent_rd ([c9b8010](https://github.com/rivenmedia/riven/commit/c9b80109c598a2083929214006114d3abe9d6b49))
* refactor and re-enable alldebrid ([4ca9ca2](https://github.com/rivenmedia/riven/commit/4ca9ca2c27203e3ed5b7b9285a77b683db542a85))
* refactor and re-enable alldebrid ([61bc680](https://github.com/rivenmedia/riven/commit/61bc6803eed86d138dd46836a1f271c1c53102c1))
* support files in rclone root ([6ad6d4d](https://github.com/rivenmedia/riven/commit/6ad6d4ddbf01593453c12b39773c07cd028bd261))

## [0.15.1](https://github.com/rivenmedia/riven/compare/v0.15.0...v0.15.1) (2024-09-29)


### Bug Fixes

* prevent error when more than two streams with the same hash in set_torrent_rd ([eaefd63](https://github.com/rivenmedia/riven/commit/eaefd631bf87cbdcd209204f36b716285a9c3046))

## [0.15.0](https://github.com/rivenmedia/riven/compare/v0.14.2...v0.15.0) (2024-09-26)


### Features

* add magnets for use in frontend ([7fc5b1b](https://github.com/rivenmedia/riven/commit/7fc5b1b9be4b662a7ac3c2056cedab80e675a447))
* added magnet handling for use in frontend ([40636dc](https://github.com/rivenmedia/riven/commit/40636dc35e5545ee5c3669145f40f1915c36b212))


### Bug Fixes

* housekeeping ([2308ce5](https://github.com/rivenmedia/riven/commit/2308ce5d2c1462f8dec2b5a0ebbd674d466cbf08))

## [0.14.2](https://github.com/rivenmedia/riven/compare/v0.14.1...v0.14.2) (2024-09-26)


### Bug Fixes

* lower worker count on symlink repair from 8 to 4 workers ([8380b7c](https://github.com/rivenmedia/riven/commit/8380b7cecb47484730335946f8a2e0d8758c1ab3))
* remove reverse on event sort ([13a278f](https://github.com/rivenmedia/riven/commit/13a278f3b76c9b28ef9fe43742c5f7d99f896fad))

## [0.14.1](https://github.com/rivenmedia/riven/compare/v0.14.0...v0.14.1) (2024-09-24)


### Bug Fixes

* update notification workflow ([d768eb8](https://github.com/rivenmedia/riven/commit/d768eb8b845b771058f46216e8de267772f99394))

## [0.14.0](https://github.com/rivenmedia/riven/compare/v0.13.3...v0.14.0) (2024-09-24)


### Features

* add manual scrape endpoint. fixed mdblist empty list issue. other small tweaks. ([57f23d6](https://github.com/rivenmedia/riven/commit/57f23d63ffeb575b32d6fe050fa72ea1ca21cc85))


### Bug Fixes

* torbox scraper missing setting issue fixed. ([f4619c4](https://github.com/rivenmedia/riven/commit/f4619c437786cb1f8761b2f4b1210207e8fb72aa))

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
