import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
const BACKEND_URL = env.BACKEND_URL || 'http://127.0.0.1:8080';

export const load = (async () => {
	async function getStats() {
		try {
			const res = await fetch(`${BACKEND_URL}/stats`);
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch stats data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch stats data. Server error or API is down.');
		}
	}

	async function getIncompleteItems() {
		try {
			const res = await fetch(`${BACKEND_URL}/items/incomplete`);
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch incomplete items data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch incomplete items data. Server error or API is down.');
		}
	}

	async function getServices() {
		try {
			const res = await fetch(`${BACKEND_URL}/services`);
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch services data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch services data. Server error or API is down.');
		}
	}

	return {
		stats: await getStats(),
		incompleteItems: await getIncompleteItems(),
		services: await getServices()
	};
}) satisfies PageServerLoad;
