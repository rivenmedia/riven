import { type SuperValidated } from 'sveltekit-superforms';
import type {
	GeneralSettingsSchema,
	ContentSettingsSchema,
	MediaServerSettingsSchema,
	ScrapersSettingsSchema
} from '$lib/schemas/setting';

// General Settings -----------------------------------------------------------------------------------
export const generalSettingsToGet: string[] = ['debug', 'log', 'symlink', 'real_debrid'];

export function generalSettingsToPass(data: any) {
	return {
		debug: data.data.debug,
		log: data.data.log,
		host_path: data.data.symlink.host_path,
		container_path: data.data.symlink.container_path,
		realdebrid_api_key: data.data.real_debrid.api_key
	}
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

export function contentSettingsToPass(data:any) {
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
		plex_watchlist_update_interval:
			data.data.content.plex_watchlist?.update_interval || 80
	}
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
				}
			}
		}
	];
}

// Media Server Settings -----------------------------------------------------------------------------------
export const mediaServerSettingsToGet: string[] = ['plex'];

export function mediaServerSettingsToPass(data: any) {
	return {
		plex_token: data.data.plex.token,
		plex_url: data.data.plex.url
	}
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

export function scrapersSettingsToPass(data: any) {
	return {
		after_2: data.data.scraping.after_2,
		after_5: data.data.scraping.after_5,
		after_10: data.data.scraping.after_10,
		torrentio_enabled: data.data.scraping.torrentio.enabled,
		orionoid_enabled: data.data.scraping.orionoid.enabled,
		jackett_enabled: data.data.scraping.jackett.enabled,
		torrentio_filter: data.data.scraping.torrentio?.filter || '',
		orionoid_api_key: data.data.scraping.orionoid?.api_key || '',
		jackett_url: data.data.scraping.jackett?.url || ''
	}
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
					filter: form.data.torrentio_filter
				},
				orionoid: {
					enabled: form.data.orionoid_enabled,
					api_key: form.data.orionoid_api_key
				},
				jackett: {
					enabled: form.data.jackett_enabled,
					url: form.data.jackett_url
				}
			}
		}
	];
}
