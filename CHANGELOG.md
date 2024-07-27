# Changelog

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
