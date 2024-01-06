import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_path: z.string().min(1),
	container_path: z.string().min(1),
	realdebrid_api_key: z.string().min(1),
});

export const scrapersSettingsSchema = z.object({
	after_2: z.number().nonnegative().default(0.5),
	after_5: z.number().nonnegative().default(2),
	after_10: z.number().nonnegative().default(24),
	torrentio_enabled: z.boolean().default(false),
	orionoid_enabled: z.boolean().default(false),
	jackett_enabled: z.boolean().default(false),
	torrentio_filter: z.string().optional().default('sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown'),
	orionoid_api_key: z.string().optional().default(''),
	jackett_url: z.string().url().optional().default('http://localhost:9117')
});

export const mediaServerSettingsSchema = z.object({
	plex_token: z.string().optional().default(''),
	plex_url: z.string().url().optional().default('')
});

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
	plex_watchlist_update_interval: z.number().nonnegative().int().optional().default(80)
});

export type GeneralSettingsSchema = typeof generalSettingsSchema;
export type ScrapersSettingsSchema = typeof scrapersSettingsSchema;
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;
export type ContentSettingsSchema = typeof contentSettingsSchema;
