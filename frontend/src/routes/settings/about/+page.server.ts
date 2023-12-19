import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getAboutInfo() {
		try {
			const toGet = ['version', 'host_mount', 'container_mount'];

			// use Promise.all to make all requests at once

			const promises = toGet.map(async (item) => {
				const res = await fetch(`http://127.0.0.1:8080/settings/get/${item}`);
				if (res.ok) {
					return await res.json();
				}
				error(400, `Unable to fetch settings data: ${res.status} ${res.statusText}`);
			});

			const results = (await Promise.all(promises)).reduce((acc, item, index) => {
				acc[toGet[index]] = item;
				return acc;
			}, {});

            return results;
		} catch (e) {
			console.error(e);
			error(500, 'Unable to fetch settings data. API is down.');
		}
	}

	return {
		settings: await getAboutInfo()
	};
};
