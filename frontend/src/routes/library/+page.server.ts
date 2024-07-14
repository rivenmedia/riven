import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { createQueryString } from '$lib/helpers';
import { env } from '$env/dynamic/private';
const BACKEND_URL = env.BACKEND_URL || 'http://127.0.0.1:8080';

export const load = (async ({ fetch, url }) => {
	const params = {
		limit: Number(url.searchParams.get('limit')) || 100,
		page: Number(url.searchParams.get('page')) || 1,
		type: url.searchParams.get('type') || 'Movie',
		search: url.searchParams.get('search') || '',
		state: url.searchParams.get('state') || ''
	};

	const queryString = createQueryString(params);

	async function getItems() {
		try {
			const res = await fetch(`${BACKEND_URL}/items${queryString}`);
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch items data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch items data. Server error or API is down.');
		}
	}

	return {
		items: await getItems()
	};
}) satisfies PageServerLoad;
