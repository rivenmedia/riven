import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_path: z.string().min(1),
	container_path: z.string().min(1),
	realdebrid_api_key: z.string().min(1),
	torrentio_filter: z.string().optional().default(''),
	torrentio_enabled: z.boolean().default(false),
	orionoid_api_key: z.string().optional().default(''),
	orionoid_enabled: z.boolean().default(false),
	jackett_api_key: z.string().optional().default(''),
	jackett_url: z.string().url().optional().default('http://localhost:9117'),
	jackett_enabled: z.boolean().default(false)
});

export const mediaServerSettingsSchema = z.object({
	plex_token: z.string().optional().default(''),
	plex_url: z.string().url().optional().default('')
});

export const contentSettingsSchema = z.object({
	overseerr_url: z.string().url().optional().default(''),
	overseerr_api_key: z.string().optional().default(''),
	mdblist_api_key: z.string().optional().default(''),
	mdblist_update_interval: z.number().int().min(1).default(80),
	mdblist_lists: z.string().array().default([''])
});

export type GeneralSettingsSchema = typeof generalSettingsSchema;
export type MediaServerSettingsSchema = typeof mediaServerSettingsSchema;
export type ContentSettingsSchema = typeof contentSettingsSchema;
