import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { getSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getAboutInfo() {
		try {
			const toGet = ['version', 'host_mount', 'container_mount'];
			const results = await getSettings(fetch, toGet);
			return results;
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	return {
		settings: await getAboutInfo()
	};
};
