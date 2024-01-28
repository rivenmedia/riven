import { type SuperValidated } from 'sveltekit-superforms';
import { z } from 'zod';

// General Settings -----------------------------------------------------------------------------------
export const generalSettingsToGet: string[] = ['debug', 'log', 'symlink', 'real_debrid'];

export const generalSettingsSchema = z.object({
	debug: z.boolean().default(true),
	log: z.boolean().default(true),
	host_path: z.string().min(1),
	container_path: z.string().min(1),
	realdebrid_api_key: z.string().min(1)
});
export type GeneralSettingsSchema = typeof generalSettingsSchema;

export function generalSettingsToPass(data: any) {
	return {
		debug: data.data.debug,
		log: data.data.log,
		host_path: data.data.symlink.host_path,
		container_path: data.data.symlink.container_path,
		realdebrid_api_key: data.data.real_debrid.api_key
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
				host_path: form.data.host_path,
				container_path: form.data.container_path
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

export const contentSettingsSchema = z.object({
	overseerr_enabled: z.boolean().default(false),
	overseerr_url: z.string().url().optional().default(''),
	overseerr_api_key: z.string().optional().default(''),
	mdblist_enabled: z.boolean().default(false),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.number().nonnegative().int().optional().default(80),
	mdblist_lists: z.string().array().optional().default(['']),
	plex_watchlist_enabled: z.boolean().default(false),
	plex_watchlist_rss: z.union([z.string().url(), z.string().optional()]).optional().default(''),
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

export const mediaServerSettingsSchema = z.object({
	plex_token: z.string().optional().default(''),
	plex_url: z.string().url().optional().default('')
});
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;

export function mediaServerSettingsToPass(data: any) {
	return {
		plex_token: data.data.plex.token,
		plex_url: data.data.plex.url
	};
}

export function mediaServerSettingsToSet(form: SuperValidated<MediaServerSettingsSchema>) {
	return [
		{
			key: 'plex',
			value: {
				token: form.data.plex_token,
				url: form.data.plex_url
			}
		}
	];
}

// Scrapers Settings -----------------------------------------------------------------------------------
export const scrapersSettingsToGet: string[] = ['scraping'];

export const scrapersSettingsSchema = z.object({
	after_2: z.number().nonnegative().default(0.5),
	after_5: z.number().nonnegative().default(2),
	after_10: z.number().nonnegative().default(24),
	torrentio_enabled: z.boolean().default(false),
	orionoid_enabled: z.boolean().default(false),
	jackett_enabled: z.boolean().default(false),
	torrentio_url: z.string().optional().default('https://torrentio.strem.fun'),
	torrentio_filter: z
		.string()
		.optional()
		.default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	orionoid_api_key: z.string().optional().default(''),
	jackett_url: z.string().url().optional().default('http://localhost:9117'),
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
		orionoid_enabled: data.data.scraping.orionoid.enabled,
		jackett_enabled: data.data.scraping.jackett.enabled,
		torrentio_filter: data.data.scraping.torrentio?.filter || '',
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
				orionoid: {
					enabled: form.data.orionoid_enabled,
					api_key: form.data.orionoid_api_key
				},
				jackett: {
					enabled: form.data.jackett_enabled,
					url: form.data.jackett_url,
					api_key: form.data.jackett_api_key
				}
			}
		}
	];
}
