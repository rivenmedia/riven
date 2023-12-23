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
	url: z.string().min(1),
	watchlist: z.string().default('').optional()
});
