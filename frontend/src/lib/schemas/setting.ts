import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_mount: z.string().min(1),
	container_mount: z.string().min(1),
	realdebrid_api_key: z.string().min(1),
	torrentio_filter: z.string().min(1)
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
	mdblist_lists: z.array(z.string()).optional().default([""]),
})

type GeneralSettings = z.infer<typeof generalSettingsSchema>;
type PlexSettings = z.infer<typeof plexSettingsSchema>;
type ContentSettings = z.infer<typeof contentSettingsSchema>;