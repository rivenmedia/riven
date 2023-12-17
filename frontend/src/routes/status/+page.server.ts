import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getStates() {
		try {
			const res = await fetch('http://127.0.0.1:8080/items/states');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch states data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(500, 'Unable to fetch states data. API is down.');
		}
	}

	async function getItems() {
		try {
			const res = await fetch('http://127.0.0.1:8080/items/');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch items data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(500, 'Unable to fetch items data. API is down.');
		}
	}

	return {
		streamed: {
			items: getItems()
		},
		states: await getStates()
	};
};
