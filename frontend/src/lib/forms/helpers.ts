import { type SuperValidated } from 'sveltekit-superforms';
import { z } from 'zod';

export async function setSettings(fetch: any, toSet: any, toCheck: string[]) {
	const settings = await fetch('http://127.0.0.1:8080/settings/set', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(toSet)
	});
	const settingsData = await settings.json();

	const services = await fetch('http://127.0.0.1:8080/services');
	const data = await services.json();
	const allServicesTrue: boolean = toCheck.every((service) => data.data[service] === true);

	return {
		data: settingsData,
		allServicesTrue: allServicesTrue
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
export const generalSettingsServices: string[] = [
	'symlinklibrary',
	'symlink',
	'realdebrid',
	'torbox',
	'torbox_downloader'
];

export const generalSettingsSchema = z.object({
	debug: z.boolean().default(true),
	log: z.boolean().default(true),
	rclone_path: z.string().min(1),
	library_path: z.string().min(1),
	realdebrid_enabled: z.boolean().default(false),
	realdebrid_api_key: z.string().optional().default(''),
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
		realdebrid_enabled: data.data.downloaders.real_debrid.enabled,
		realdebrid_api_key: data.data.downloaders.real_debrid?.api_key || '',
		torbox_enabled: data.data.downloaders.torbox.enabled,
		torbox_api_key: data.data.downloaders.torbox?.api_key || ''
	};
}

export function generalSettingsToSet(form: SuperValidated<GeneralSettingsSchema>) {
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
				library_path: form.data.library_path
			}
		},
		{
			key: 'downloaders',
			value: {
				real_debrid: {
					enabled: form.data.realdebrid_enabled,
					api_key: form.data.realdebrid_api_key
				},
				torbox: {
					enabled: form.data.torbox_enabled,
					api_key: form.data.torbox_api_key
				}
			}
		}
	];
}

// Content Settings -----------------------------------------------------------------------------------
export const contentSettingsToGet: string[] = ['content'];
export const contentSettingsServices: string[] = ['content'];

export const contentSettingsSchema = z.object({
	overseerr_enabled: z.boolean().default(false),
	overseerr_url: z.string().optional().default(''),
	overseerr_api_key: z.string().optional().default(''),
	overseerr_update_interval: z.number().nonnegative().int().optional().default(30),
	overseerr_use_webhook: z.boolean().optional().default(false),
	mdblist_enabled: z.boolean().default(false),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.number().nonnegative().int().optional().default(300),
	mdblist_lists: z.string().array().optional().default(['']),
	plex_watchlist_enabled: z.boolean().default(false),
	plex_watchlist_rss: z.string().optional().default(''),
	plex_watchlist_update_interval: z.number().nonnegative().int().optional().default(60),
	listrr_enabled: z.boolean().default(false),
	listrr_api_key: z.string().optional().default(''),
	listrr_update_interval: z.number().nonnegative().int().optional().default(300),
	listrr_movie_lists: z.string().array().optional().default(['']),
	listrr_show_lists: z.string().array().optional().default(['']),
	trakt_enabled: z.boolean().default(false),
	trakt_api_key: z.string().optional().default(''),
	trakt_update_interval: z.number().nonnegative().int().optional().default(300),
	trakt_watchlist: z.string().array().optional().default(['']),
	trakt_user_lists: z.string().array().optional().default(['']),
	trakt_fetch_trending: z.boolean().default(false),
	trakt_fetch_popular: z.boolean().default(false),
	trakt_trending_count: z.number().nonnegative().int().optional().default(10),
	trakt_popular_count: z.number().nonnegative().int().optional().default(10)
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
		mdblist_lists: data.data.content.mdblist?.lists || [''],
		plex_watchlist_enabled: data.data.content.plex_watchlist.enabled,
		plex_watchlist_rss: data.data.content.plex_watchlist?.rss || '',
		plex_watchlist_update_interval: data.data.content.plex_watchlist?.update_interval || 60,
		listrr_enabled: data.data.content.listrr.enabled,
		listrr_api_key: data.data.content.listrr?.api_key || '',
		listrr_update_interval: data.data.content.listrr?.update_interval || 300,
		listrr_movie_lists: data.data.content.listrr?.movie_lists || [''],
		listrr_show_lists: data.data.content.listrr?.show_lists || [''],
		trakt_enabled: data.data.content.trakt.enabled,
		trakt_api_key: data.data.content.trakt?.api_key || '',
		trakt_update_interval: data.data.content.trakt?.update_interval || 300,
		trakt_watchlist: data.data.content.trakt?.watchlist || [''],
		trakt_user_lists: data.data.content.trakt?.user_lists || [''],
		trakt_fetch_trending: data.data.content.trakt?.fetch_trending || false,
		trakt_fetch_popular: data.data.content.trakt?.fetch_popular || false,
		trakt_trending_count: data.data.content.trakt?.fetch_trending_count || 10,
		trakt_popular_count: data.data.content.trakt?.fetch_popular_count || 10
	};
}

export function contentSettingsToSet(form: SuperValidated<ContentSettingsSchema>) {
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
					fetch_trending: form.data.trakt_fetch_trending,
					fetch_popular: form.data.trakt_fetch_popular,
					trending_count: form.data.trakt_trending_count,
					popular_count: form.data.trakt_popular_count
				}
			}
		}
	];
}

// Media Server Settings -----------------------------------------------------------------------------------
export const mediaServerSettingsToGet: string[] = ['plex'];
export const mediaServerSettingsServices: string[] = ['plex'];

export const mediaServerSettingsSchema = z.object({
	update_interval: z.number().nonnegative().int().optional().default(120),
	plex_token: z.string().optional().default(''),
	plex_url: z.string().optional().default('')
});
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;

export function mediaServerSettingsToPass(data: any) {
	return {
		update_interval: data.data.plex.update_interval,
		plex_token: data.data.plex.token,
		plex_url: data.data.plex.url // TODO: Maybe rename it to url only?
	};
}

export function mediaServerSettingsToSet(form: SuperValidated<MediaServerSettingsSchema>) {
	return [
		{
			key: 'plex',
			value: {
				update_interval: form.data.update_interval,
				token: form.data.plex_token,
				url: form.data.plex_url
			}
		}
	];
}

// Scrapers Settings -----------------------------------------------------------------------------------
export const scrapersSettingsToGet: string[] = ['scraping'];
export const scrapersSettingsServices: string[] = ['scraping'];

export const scrapersSettingsSchema = z.object({
	after_2: z.number().nonnegative().default(0.5),
	after_5: z.number().nonnegative().default(2),
	after_10: z.number().nonnegative().default(24),
	torrentio_enabled: z.boolean().default(false),
	knightcrawler_enabled: z.boolean().default(false),
	annatar_enabled: z.boolean().default(false),
	orionoid_enabled: z.boolean().default(false),
	jackett_enabled: z.boolean().default(false),
	mediafusion_enabled: z.boolean().default(false),
	torrentio_url: z.string().optional().default('https://torrentio.strem.fun'),
	torrentio_filter: z
		.string()
		.optional()
		.default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	knightcrawler_url: z.string().optional().default('https://knightcrawler.elfhosted.com/'),
	knightcrawler_filter: z
		.string()
		.optional()
		.default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	annatar_url: z.string().optional().default('https://annatar.elfhosted.com'),
	orionoid_api_key: z.string().optional().default(''),
	jackett_url: z.string().optional().default('http://localhost:9117'),
	jackett_api_key: z.string().optional().default(''),
	mediafusion_url: z.string().optional().default('https://mediafusion.elfhosted.com'),
	mediafusion_catalogs: z.string().array().optional().default([]),
});
export type ScrapersSettingsSchema = typeof scrapersSettingsSchema;

export function scrapersSettingsToPass(data: any) {
	return {
		after_2: data.data.scraping.after_2,
		after_5: data.data.scraping.after_5,
		after_10: data.data.scraping.after_10,
		torrentio_url: data.data.scraping.torrentio?.url || 'https://torrentio.strem.fun',
		torrentio_enabled: data.data.scraping.torrentio.enabled,
		knightcrawler_url: data.data.scraping.knightcrawler?.url || 'https://knightcrawler.elfhosted.com/',
		knightcrawler_enabled: data.data.scraping.knightcrawler.enabled,
		annatar_url: data.data.scraping.annatar?.url || 'https://annatar.elfhosted.com',
		annatar_enabled: data.data.scraping.annatar.enabled,
		orionoid_enabled: data.data.scraping.orionoid.enabled,
		jackett_enabled: data.data.scraping.jackett.enabled,
		torrentio_filter: data.data.scraping.torrentio?.filter || '',
		knightcrawler_filter: data.data.scraping.knightcrawler?.filter || '',
		orionoid_api_key: data.data.scraping.orionoid?.api_key || '',
		jackett_url: data.data.scraping.jackett?.url || '',
		jackett_api_key: data.data.scraping.jackett?.api_key || '',
		mediafusion_url: data.data.scraping.mediafusion?.url || 'https://mediafusion.elfhosted.com/',
		mediafusion_enabled: data.data.scraping.mediafusion.enabled,
		mediafusion_catalogs: data.data.scraping.mediafusion.catalogs || ["prowlarr_streams", "torrentio_streams"]
	};
}

export function scrapersSettingsToSet(form: SuperValidated<ScrapersSettingsSchema>) {
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
					filter: form.data.torrentio_filter
				},
				knightcrawler: {
					enabled: form.data.knightcrawler_enabled,
					url: form.data.knightcrawler_url,
					filter: form.data.knightcrawler_filter
				},
				annatar: {
					enabled: form.data.annatar_enabled,
					url: form.data.annatar_url
				},
				orionoid: {
					enabled: form.data.orionoid_enabled,
					api_key: form.data.orionoid_api_key
				},
				jackett: {
					enabled: form.data.jackett_enabled,
					url: form.data.jackett_url
				},
				mediafusion: {
					enabled: form.data.mediafusion_enabled,
					url: form.data.mediafusion_url,
					catalogs: form.data.mediafusion_catalogs
				}
			}
		}
	];
}
