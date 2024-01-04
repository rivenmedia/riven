import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_path: z.string().min(1),
	container_path: z.string().min(1),
	realdebrid_api_key: z.string().min(1),
	torrentio_filter: z.string().optional().default(''),
	torrentio_enabled: z.boolean(),
	orionoid_api_key: z.string().optional().default(''),
	orionoid_enabled: z.boolean(),
	jackett_api_key: z.string().optional().default(''),
	jackett_url: z.string().url().optional().default('http://localhost:9117'),
	jackett_enabled: z.boolean()
});

export const plexSettingsSchema = z.object({
	user: z.string().min(1),
	token: z.string().min(1),
	url: z.string().url().min(1),
	watchlist: z.string().optional().default('')
});

export const contentSettingsSchema = z.object({
	overseerr_url: z.string().url().optional().default(''),
	overseerr_api_key: z.string().optional().default(''),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.number().int().min(1).default(80),
	mdblist_lists: z.string().array().default([''])
});

export type GeneralSettingsSchema = typeof generalSettingsSchema;
export type PlexSettingsSchema = typeof plexSettingsSchema;
export type ContentSettingsSchema = typeof contentSettingsSchema;
