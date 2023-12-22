import { z } from 'zod';

export const generalSettingsSchema = z.object({
	host_mount: z.string().min(1),
	container_mount: z.string().min(1),
	realdebrid_api_key: z.string().min(1),
	torrentio_filter: z.string().min(1),
});