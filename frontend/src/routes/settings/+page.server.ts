import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getSettings() {
		try {
			const res = await fetch('http://127.0.0.1:8080/settings/get/all');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch settings data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(500, 'Unable to fetch settings data. API is down.');
		}
	}

	return {
		settings: await getSettings()
	};
};
