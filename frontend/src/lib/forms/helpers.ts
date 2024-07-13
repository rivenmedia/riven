import { type SuperValidated, type Infer } from 'sveltekit-superforms';

import { z } from 'zod';

// TODO: Add toCheck
export async function setSettings(fetch: any, toSet: any) {
	const settings = await fetch('http://127.0.0.1:8080/settings/set', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(toSet)
	});
	const settingsData = await settings.json();

	return {
		data: settingsData
	};
}

export async function saveSettings(fetch: any) {
	const data = await fetch('http://127.0.0.1:8080/settings/save', {
		method: 'POST'
	});
	const response = await data.json();

	return {
		data: response
	};
}

export async function loadSettings(fetch: any) {
	const data = await fetch('http://127.0.0.1:8080/settings/load', {
		method: 'GET'
	});
	const response = await data.json();

	return {
		data: response
	};
}

// General Settings -----------------------------------------------------------------------------------
export const generalSettingsToGet: string[] = ['debug', 'log', 'symlink', 'downloaders'];

export const generalSettingsSchema = z.object({
	debug: z.boolean().default(true),
	log: z.boolean().default(true),
	rclone_path: z.string().min(1),
	library_path: z.string().min(1),
	separate_anime_dirs: z.boolean().default(false),
	movie_filesize_min: z.coerce.number().gte(0).int().optional().default(200),
	movie_filesize_max: z.coerce.number().gte(-1).int().optional().default(-1),
	episode_filesize_min: z.coerce.number().gte(0).int().optional().default(40),
	episode_filesize_max: z.coerce.number().gte(-1).int().optional().default(-1),
	realdebrid_enabled: z.boolean().default(false),
	realdebrid_api_key: z.string().optional().default(''),
	realdebrid_proxy_enabled: z.boolean().default(false),
	realdebrid_proxy_url: z.string().optional().default(''),
	alldebrid_enabled: z.boolean().default(false),
	alldebrid_api_key: z.string().optional().default(''),
	alldebrid_proxy_enabled: z.boolean().default(false),
	alldebrid_proxy_url: z.string().optional().default(''),
	torbox_enabled: z.boolean().default(false),
	torbox_api_key: z.string().optional().default('')
});
export type GeneralSettingsSchema = typeof generalSettingsSchema;

export function generalSettingsToPass(data: any) {
	return {
		debug: data.data.debug,
		log: data.data.log,
		rclone_path: data.data.symlink.rclone_path,
		library_path: data.data.symlink.library_path,
		separate_anime_dirs: data.data.symlink.separate_anime_dirs,
		movie_filesize_min: data.data.downloaders.movie_filesize_min,
		movie_filesize_max: data.data.downloaders.movie_filesize_max,
		episode_filesize_min: data.data.downloaders.episode_filesize_min,
		episode_filesize_max: data.data.downloaders.episode_filesize_max,
		realdebrid_enabled: data.data.downloaders.real_debrid.enabled,
		realdebrid_api_key: data.data.downloaders.real_debrid?.api_key || '',
		realdebrid_proxy_enabled: data.data.downloaders.real_debrid?.proxy_enabled || false,
		realdebrid_proxy_url: data.data.downloaders.real_debrid?.proxy_url || '',
		alldebrid_enabled: data.data.downloaders.all_debrid.enabled,
		alldebrid_api_key: data.data.downloaders.all_debrid?.api_key || '',
		alldebrid_proxy_enabled: data.data.downloaders.all_debrid?.proxy_enabled || false,
		alldebrid_proxy_url: data.data.downloaders.all_debrid?.proxy_url || '',
		torbox_enabled: data.data.downloaders.torbox.enabled,
		torbox_api_key: data.data.downloaders.torbox?.api_key || '',
	};
}

export function generalSettingsToSet(form: SuperValidated<Infer<GeneralSettingsSchema>>) {
	return [
		{
			key: 'debug',
			value: form.data.debug
		},
		{
			key: 'log',
			value: form.data.log
		},
		{
			key: 'symlink',
			value: {
				rclone_path: form.data.rclone_path,
				library_path: form.data.library_path,
				separate_anime_dirs: form.data.separate_anime_dirs
			}
		},
		{
			key: 'downloaders',
			value: {
				movie_filesize_min: form.data.movie_filesize_min,
				movie_filesize_max: form.data.movie_filesize_max,
				episode_filesize_min: form.data.episode_filesize_min,
				episode_filesize_max: form.data.episode_filesize_max,
				real_debrid: {
					enabled: form.data.realdebrid_enabled,
					api_key: form.data.realdebrid_api_key,
					proxy_enabled: form.data.realdebrid_proxy_enabled,
					proxy_url: form.data.realdebrid_proxy_url
				},
				all_debrid: {
					enabled: form.data.alldebrid_enabled,
					api_key: form.data.alldebrid_api_key,
					proxy_enabled: form.data.alldebrid_proxy_enabled,
					proxy_url: form.data.alldebrid_proxy_url
				},
				torbox: {
					enabled: form.data.torbox_enabled,
					api_key: form.data.torbox_api_key
				}
			}
		}
	];
}

// Media Server Settings -----------------------------------------------------------------------------------

export const mediaServerSettingsToGet: string[] = ['updaters'];

export const mediaServerSettingsSchema = z.object({
	// update_interval: z.number().nonnegative().int().optional().default(120), // Moved to coerce due to https://github.com/huntabyte/shadcn-svelte/issues/574
	update_interval: z.coerce.number().gte(0).int().optional().default(120),
	local_enabled: z.boolean().default(false),
	plex_enabled: z.boolean().default(false),
	plex_token: z.string().optional().default(''),
	plex_url: z.string().optional().default('')
});
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;

export function mediaServerSettingsToPass(data: any) {
	return {
		update_interval: data.data.updaters.update_interval,
		plex_token: data.data.updaters.plex.token,
		plex_url: data.data.updaters.plex.url,
		plex_enabled: data.data.updaters.plex.enabled,
		local_enabled: data.data.updaters.local.enabled
	};
}

export function mediaServerSettingsToSet(form: SuperValidated<Infer<MediaServerSettingsSchema>>) {
	return [
		{
			key: 'updaters',
			value: {
				update_interval: form.data.update_interval,
				local: {
					enabled: form.data.local_enabled
				},
				plex: {
					enabled: form.data.plex_enabled,
					token: form.data.plex_token,
					url: form.data.plex_url
				}
			}
		}
	];
}

// Scrapers Settings -----------------------------------------------------------------------------------

export const scrapersSettingsToGet: string[] = ['scraping'];

export const scrapersSettingsSchema = z.object({
	after_2: z.coerce.number().gte(0).int().default(0.5),
	after_5: z.coerce.number().gte(0).int().default(2),
	after_10: z.coerce.number().gte(0).int().default(24),
	torrentio_enabled: z.boolean().default(false),
	torrentio_url: z.string().optional().default('https://torrentio.strem.fun'),
	torrentio_timeout: z.coerce.number().gte(0).int().optional().default(30),
	torrentio_ratelimit: z.boolean().default(true),
	torrentio_filter: z
		.string()
		.optional()
		.default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	knightcrawler_enabled: z.boolean().default(false),
	knightcrawler_url: z.string().optional().default('https://knightcrawler.elfhosted.com/'),
	knightcrawler_timeout: z.coerce.number().gte(0).int().optional().default(30),
	knightcrawler_ratelimit: z.boolean().default(true),
	knightcrawler_filter: z
		.string()
		.optional()
		.default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	annatar_enabled: z.boolean().default(false),
	annatar_url: z.string().optional().default('https://annatar.elfhosted.com'),
	annatar_timeout: z.coerce.number().gte(0).int().optional().default(10),
	annatar_ratelimit: z.boolean().default(true),
	annatar_limit: z.coerce.number().gte(0).int().optional().default(2000),
	orionoid_enabled: z.boolean().default(false),
	orionoid_api_key: z.string().optional().default(''),
	orionoid_timeout: z.coerce.number().gte(0).int().optional().default(10),
	orionoid_ratelimit: z.boolean().default(true),
	orionoid_limitcount: z.coerce.number().gte(0).int().optional().default(5),
	jackett_enabled: z.boolean().default(false),
	jackett_url: z.string().optional().default('http://localhost:9117'),
	jackett_timeout: z.coerce.number().gte(0).int().optional().default(10),
	jackett_ratelimit: z.boolean().default(true),
	jackett_api_key: z.string().optional().default(''),
	mediafusion_enabled: z.boolean().default(false),
	mediafusion_url: z.string().optional().default('https://mediafusion.elfhosted.com'),
	mediafusion_timeout: z.coerce.number().gte(0).int().optional().default(10),
	mediafusion_ratelimit: z.boolean().default(true),
	mediafusion_catalogs: z.array(z.string()).optional().default([]),
	prowlarr_enabled: z.boolean().default(false),
	prowlarr_url: z.string().optional().default('http://localhost:9696'),
	prowlarr_timeout: z.coerce.number().gte(0).int().optional().default(10),
	prowlarr_ratelimit: z.boolean().default(true),
	prowlarr_limiter_seconds: z.coerce.number().gte(0).int().optional().default(60),
	prowlarr_api_key: z.string().optional().default(''),
	torbox_scraper_enabled: z.boolean().default(false),
	torbox_scraper_timeout: z.coerce.number().gte(0).int().optional().default(30),
	torbox_scraper_ratelimit: z.boolean().default(true),
	zilean_enabled: z.boolean().default(false),
	zilean_url: z.string().optional().default('http://localhost:8181'),
	zilean_timeout: z.coerce.number().gte(0).int().optional().default(30),
	zilean_ratelimit: z.boolean().default(true)
});
export type ScrapersSettingsSchema = typeof scrapersSettingsSchema;

export function scrapersSettingsToPass(data: any) {
	return {
		after_2: data.data.scraping.after_2,
		after_5: data.data.scraping.after_5,
		after_10: data.data.scraping.after_10,
		torrentio_url: data.data.scraping.torrentio?.url || 'https://torrentio.strem.fun',
		torrentio_enabled: data.data.scraping.torrentio.enabled,
		torrentio_filter: data.data.scraping.torrentio?.filter || '',
		torrentio_timeout: data.data.scraping.torrentio?.timeout || 30,
		torrentio_ratelimit: data.data.scraping.torrentio?.ratelimit || true,
		knightcrawler_url:
			data.data.scraping.knightcrawler?.url || 'https://knightcrawler.elfhosted.com/',
		knightcrawler_enabled: data.data.scraping.knightcrawler.enabled,
		knightcrawler_filter: data.data.scraping.knightcrawler?.filter || '',
		knightcrawler_timeout: data.data.scraping.knightcrawler?.timeout || 30,
		knightcrawler_ratelimit: data.data.scraping.knightcrawler?.ratelimit || true,
		annatar_url: data.data.scraping.annatar?.url || 'https://annatar.elfhosted.com',
		annatar_enabled: data.data.scraping.annatar.enabled,
		annatar_limit: data.data.scraping.annatar?.limit || 2000,
		annatar_timeout: data.data.scraping.annatar?.timeout || 10,
		annatar_ratelimit: data.data.scraping.annatar?.ratelimit || true,
		orionoid_enabled: data.data.scraping.orionoid.enabled,
		orionoid_api_key: data.data.scraping.orionoid?.api_key || '',
		orionoid_limitcount: data.data.scraping.orionoid?.limitcount || 5,
		orionoid_timeout: data.data.scraping.orionoid?.timeout || 10,
		orionoid_ratelimit: data.data.scraping.orionoid?.ratelimit || true,
		jackett_enabled: data.data.scraping.jackett.enabled,
		jackett_url: data.data.scraping.jackett?.url || '',
		jackett_api_key: data.data.scraping.jackett?.api_key || '',
		jackett_timeout: data.data.scraping.jackett?.timeout || 10,
		jackett_ratelimit: data.data.scraping.jackett?.ratelimit || true,
		mediafusion_url: data.data.scraping.mediafusion?.url || 'https://mediafusion.elfhosted.com/',
		mediafusion_enabled: data.data.scraping.mediafusion.enabled,
		mediafusion_catalogs: data.data.scraping.mediafusion.catalogs || [
			'prowlarr_streams',
			'torrentio_streams'
		],
		mediafusion_timeout: data.data.scraping.mediafusion?.timeout || 10,
		mediafusion_ratelimit: data.data.scraping.mediafusion?.ratelimit || true,
		prowlarr_enabled: data.data.scraping.prowlarr?.enabled || false,
		prowlarr_url: data.data.scraping.prowlarr?.url || 'http://localhost:9696',
		prowlarr_api_key: data.data.scraping.prowlarr?.api_key || '',
		prowlarr_timeout: data.data.scraping.prowlarr?.timeout || 10,
		prowlarr_ratelimit: data.data.scraping.prowlarr?.ratelimit || true,
		prowlarr_limiter_seconds: data.data.scraping.prowlarr?.limiter_seconds || 60,
		torbox_scraper_enabled: data.data.scraping.torbox_scraper?.enabled || false,
		torbox_scraper_timeout: data.data.scraping.torbox_scraper?.timeout || 30,
		torbox_scraper_ratelimit: data.data.scraping.torbox_scraper?.ratelimit || true,
		zilean_enabled: data.data.scraping.zilean?.enabled || false,
		zilean_url: data.data.scraping.zilean?.url || 'http://localhost:8181',
		zilean_timeout: data.data.scraping.zilean?.timeout || 30,
		zilean_ratelimit: data.data.scraping.zilean?.ratelimit || true
	};
}

export function scrapersSettingsToSet(form: SuperValidated<Infer<ScrapersSettingsSchema>>) {
	return [
		{
			key: 'scraping',
			value: {
				after_2: form.data.after_2,
				after_5: form.data.after_5,
				after_10: form.data.after_10,
				torrentio: {
					enabled: form.data.torrentio_enabled,
					url: form.data.torrentio_url,
					filter: form.data.torrentio_filter,
					timeout: form.data.torrentio_timeout,
					ratelimit: form.data.torrentio_ratelimit
				},
				knightcrawler: {
					enabled: form.data.knightcrawler_enabled,
					url: form.data.knightcrawler_url,
					filter: form.data.knightcrawler_filter,
					timeout: form.data.knightcrawler_timeout,
					ratelimit: form.data.knightcrawler_ratelimit
				},
				annatar: {
					enabled: form.data.annatar_enabled,
					url: form.data.annatar_url,
					limit: form.data.annatar_limit,
					timeout: form.data.annatar_timeout,
					ratelimit: form.data.annatar_ratelimit
				},
				orionoid: {
					enabled: form.data.orionoid_enabled,
					api_key: form.data.orionoid_api_key,
					limitcount: form.data.orionoid_limitcount,
					timeout: form.data.orionoid_timeout,
					ratelimit: form.data.orionoid_ratelimit
				},
				jackett: {
					enabled: form.data.jackett_enabled,
					url: form.data.jackett_url,
					api_key: form.data.jackett_api_key,
					timeout: form.data.jackett_timeout,
					ratelimit: form.data.jackett_ratelimit
				},
				mediafusion: {
					enabled: form.data.mediafusion_enabled,
					url: form.data.mediafusion_url,
					catalogs: form.data.mediafusion_catalogs,
					timeout: form.data.mediafusion_timeout,
					ratelimit: form.data.mediafusion_ratelimit
				},
				prowlarr: {
					enabled: form.data.prowlarr_enabled,
					url: form.data.prowlarr_url,
					api_key: form.data.prowlarr_api_key,
					timeout: form.data.prowlarr_timeout,
					ratelimit: form.data.prowlarr_ratelimit,
					limiter_seconds: form.data.prowlarr_limiter_seconds
				},
				torbox_scraper: {
					enabled: form.data.torbox_scraper_enabled,
					timeout: form.data.torbox_scraper_timeout,
					ratelimit: form.data.torbox_scraper_ratelimit
				},
				zilean: {
					enabled: form.data.zilean_enabled,
					url: form.data.zilean_url,
					timeout: form.data.zilean_timeout,
					ratelimit: form.data.zilean_ratelimit
				}
			}
		}
	];
}

// Content Settings -----------------------------------------------------------------------------------

export const contentSettingsToGet: string[] = ['content'];

export const contentSettingsSchema = z.object({
	overseerr_enabled: z.boolean().default(false),
	overseerr_url: z.string().optional().default(''),
	overseerr_api_key: z.string().optional().default(''),
	overseerr_update_interval: z.coerce.number().gte(0).int().optional().default(30),
	overseerr_use_webhook: z.boolean().optional().default(false),
	mdblist_enabled: z.boolean().default(false),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.coerce.number().gte(0).int().optional().default(300),
	mdblist_lists: z.string().array().optional().default([]),
	plex_watchlist_enabled: z.boolean().default(false),
	plex_watchlist_rss: z.array(z.string()).optional().default([]),
	plex_watchlist_update_interval: z.coerce.number().gte(0).int().optional().default(60),
	listrr_enabled: z.boolean().default(false),
	listrr_api_key: z.string().optional().default(''),
	listrr_update_interval: z.coerce.number().gte(0).int().optional().default(300),
	listrr_movie_lists: z.string().array().optional().default([]),
	listrr_show_lists: z.string().array().optional().default([]),
	trakt_enabled: z.boolean().default(false),
	trakt_api_key: z.string().optional().default(''),
	trakt_update_interval: z.coerce.number().gte(0).int().optional().default(300),
	trakt_watchlist: z.array(z.string()).optional().default([]),
	trakt_user_lists: z.array(z.string()).optional().default([]),
	trakt_collection: z.array(z.string()).optional().default([]),
	trakt_fetch_trending: z.boolean().default(false),
	trakt_fetch_popular: z.boolean().default(false),
	trakt_trending_count: z.coerce.number().gte(0).int().optional().default(10),
	trakt_popular_count: z.coerce.number().gte(0).int().optional().default(10)
});
export type ContentSettingsSchema = typeof contentSettingsSchema;

export function contentSettingsToPass(data: any) {
	return {
		overseerr_enabled: data.data.content.overseerr.enabled,
		overseerr_url: data.data.content.overseerr?.url || '',
		overseerr_api_key: data.data.content.overseerr?.api_key || '',
		overseerr_update_interval: data.data.content.overseerr?.update_interval || 30,
		overseerr_use_webhook: data.data.content.overseerr?.use_webhook || false,
		mdblist_enabled: data.data.content.mdblist.enabled,
		mdblist_api_key: data.data.content.mdblist?.api_key || '',
		mdblist_update_interval: data.data.content.mdblist?.update_interval || 300,
		mdblist_lists: data.data.content.mdblist?.lists || [],
		plex_watchlist_enabled: data.data.content.plex_watchlist.enabled,
		plex_watchlist_rss: data.data.content.plex_watchlist?.rss || [],
		plex_watchlist_update_interval: data.data.content.plex_watchlist?.update_interval || 60,
		listrr_enabled: data.data.content.listrr.enabled,
		listrr_api_key: data.data.content.listrr?.api_key || '',
		listrr_update_interval: data.data.content.listrr?.update_interval || 300,
		listrr_movie_lists: data.data.content.listrr?.movie_lists || [],
		listrr_show_lists: data.data.content.listrr?.show_lists || [],
		trakt_enabled: data.data.content.trakt.enabled,
		trakt_api_key: data.data.content.trakt?.api_key || '',
		trakt_update_interval: data.data.content.trakt?.update_interval || 300,
		trakt_watchlist: data.data.content.trakt?.watchlist || [],
		trakt_user_lists: data.data.content.trakt?.user_lists || [],
		trakt_collection: data.data.content.trakt?.collection || [],
		trakt_fetch_trending: data.data.content.trakt?.fetch_trending || false,
		trakt_fetch_popular: data.data.content.trakt?.fetch_popular || false,
		trakt_trending_count: data.data.content.trakt?.fetch_trending_count || 10,
		trakt_popular_count: data.data.content.trakt?.fetch_popular_count || 10
	};
}

export function contentSettingsToSet(form: SuperValidated<Infer<ContentSettingsSchema>>) {
	return [
		{
			key: 'content',
			value: {
				overseerr: {
					enabled: form.data.overseerr_enabled,
					url: form.data.overseerr_url,
					api_key: form.data.overseerr_api_key,
					update_interval: form.data.overseerr_update_interval,
					use_webhook: form.data.overseerr_use_webhook
				},
				mdblist: {
					enabled: form.data.mdblist_enabled,
					api_key: form.data.mdblist_api_key,
					update_interval: form.data.mdblist_update_interval,
					lists: form.data.mdblist_lists
				},
				plex_watchlist: {
					enabled: form.data.plex_watchlist_enabled,
					rss: form.data.plex_watchlist_rss,
					update_interval: form.data.plex_watchlist_update_interval
				},
				listrr: {
					enabled: form.data.listrr_enabled,
					api_key: form.data.listrr_api_key,
					update_interval: form.data.listrr_update_interval,
					movie_lists: form.data.listrr_movie_lists,
					show_lists: form.data.listrr_show_lists
				},
				trakt: {
					enabled: form.data.trakt_enabled,
					api_key: form.data.trakt_api_key,
					update_interval: form.data.trakt_update_interval,
					watchlist: form.data.trakt_watchlist,
					user_lists: form.data.trakt_user_lists,
					collection: form.data.trakt_collection,
					fetch_trending: form.data.trakt_fetch_trending,
					fetch_popular: form.data.trakt_fetch_popular,
					trending_count: form.data.trakt_trending_count,
					popular_count: form.data.trakt_popular_count
				}
			}
		}
	];
}