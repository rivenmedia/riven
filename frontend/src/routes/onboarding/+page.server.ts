import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getHealth() {
		try {
			const res = await fetch('http://127.0.0.1:8080/health');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch user data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch user data. API is down.');
		}
	}

	return {
		health: await getHealth()
	};
};
