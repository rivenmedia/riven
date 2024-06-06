import { type SuperValidated } from 'sveltekit-superforms';
import { z } from 'zod';

/**
 * Sets the settings in memory in the 
 *
 * @param fetch - The fetch function used to make the request.
 * @param toSet - The settings to be set.
 * @param toCheck - The services to check.
 * @returns An object containing the settings data and a boolean indicating if all the given services are true or not.
 */
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

/**
 * Saves the settings from memory to the json file in the 
 * @param fetch - The fetch function used to make the request.
 * @returns A promise that resolves to an object containing the response data.
 */
export async function saveSettings(fetch: any) {
	const data = await fetch('http://127.0.0.1:8080/settings/save', {
		method: 'POST'
	});
	const response = await data.json();

	return {
		data: response
	};
}

/**
 * Loads settings from the json to memory in 
 * @param fetch - The fetch function used to make the HTTP request.
 * @returns A promise that resolves to an object containing the loaded settings.
 */
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
export const generalSettingsToGet: string[] = ['debug', 'log', 'symlink', 'real_debrid'];
export const generalSettingsServices: string[] = ['symlink', 'real_debrid'];

export const generalSettingsSchema = z.object({
	debug: z.boolean().default(true),
	log: z.boolean().default(true),
	rclone_path: z.string().min(1),
	library_path: z.string().min(1),
	realdebrid_api_key: z.string().min(1)
});
export type GeneralSettingsSchema = typeof generalSettingsSchema;

export function generalSettingsToPass(data: any) {	
	return {
		debug: data.data.debug,
		log: data.data.log,
		rclone_path: data.data.symlink.rclone_path,
		library_path: data.data.symlink.library_path,
		realdebrid_api_key: data.data.real_debrid.api_key,
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
			key: 'real_debrid',
			value: {
				api_key: form.data.realdebrid_api_key
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
	mdblist_enabled: z.boolean().default(false),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.number().nonnegative().int().optional().default(80),
	mdblist_lists: z.string().array().optional().default(['']),
	plex_watchlist_enabled: z.boolean().default(false),
	plex_watchlist_rss: z.string().optional().default(''),
	plex_watchlist_update_interval: z.number().nonnegative().int().optional().default(80),
	listrr_enabled: z.boolean().default(false),
	listrr_api_key: z.string().optional().default(''),
	listrr_update_interval: z.number().nonnegative().int().optional().default(80),
	listrr_movie_lists: z.string().array().optional().default(['']),
	listrr_show_lists: z.string().array().optional().default([''])
});
export type ContentSettingsSchema = typeof contentSettingsSchema;

export function contentSettingsToPass(data: any) {
	return {
		overseerr_enabled: data.data.content.overseerr.enabled,
		overseerr_url: data.data.content.overseerr?.url || '',
		overseerr_api_key: data.data.content.overseerr?.api_key || '',
		mdblist_enabled: data.data.content.mdblist.enabled,
		mdblist_api_key: data.data.content.mdblist?.api_key || '',
		mdblist_update_interval: data.data.content.mdblist?.update_interval || 80,
		mdblist_lists: data.data.content.mdblist?.lists || [''],
		plex_watchlist_enabled: data.data.content.plex_watchlist.enabled,
		plex_watchlist_rss: data.data.content.plex_watchlist?.rss || '',
		plex_watchlist_update_interval: data.data.content.plex_watchlist?.update_interval || 80,
		listrr_enabled: data.data.content.listrr.enabled,
		listrr_api_key: data.data.content.listrr?.api_key || '',
		listrr_update_interval: data.data.content.listrr?.update_interval || 80,
		listrr_movie_lists: data.data.content.listrr?.movie_lists || [''],
		listrr_show_lists: data.data.content.listrr?.show_lists || ['']
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
					api_key: form.data.overseerr_api_key
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
				}
			}
		}
	];
}

// Media Server Settings -----------------------------------------------------------------------------------
export const mediaServerSettingsToGet: string[] = ['plex'];
export const mediaServerSettingsServices: string[] = ['plex'];

export const mediaServerSettingsSchema = z.object({
	update_interval: z.string().optional().default(''),
	plex_token: z.string().optional().default(''),
	plex_url: z.string().optional().default('')
});
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;

export function mediaServerSettingsToPass(data: any) {
	return {
		update_interval: data.data.plex.update_interval,
		plex_token: data.data.plex.token,
		plex_url: data.data.plex.url
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
	jackett_api_key: z.string().optional().default('')
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
		jackett_api_key: data.data.scraping.jackett?.api_key || ''
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
					url: form.data.annatar_url,
				},
				orionoid: {
					enabled: form.data.orionoid_enabled,
					api_key: form.data.orionoid_api_key
				},
				jackett: {
					enabled: form.data.jackett_enabled,
					url: form.data.jackett_url,
				}
			}
		}
	];
}
