import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_mount: z.string(),
	container_mount: z.string(),
	realdebrid_api_key: z.string(),
	torrentio_filter: z.string()
});

export type GeneralSettingsSchema = typeof generalSettingsSchema;
