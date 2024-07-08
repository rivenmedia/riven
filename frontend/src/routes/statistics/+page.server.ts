import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load = (async () => {
	async function getStats() {
		try {
			const res = await fetch('http://127.0.0.1:8080/stats');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch stats data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch stats data. Server error or API is down.');
		}
	}

	return {
		stats: await getStats()
	};
}) satisfies PageServerLoad;
