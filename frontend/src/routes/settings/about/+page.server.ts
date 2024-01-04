import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getAboutInfo() {
		try {
			const toGet = ['version', 'symlink'];
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${toGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	return { settings: await getAboutInfo() };
};
