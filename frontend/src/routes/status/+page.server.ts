import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getItems() {
		const res = await fetch('http://localhost:8080/items/');
		if (res.ok) {
			return await res.json();
		}
		return null;
	}

	async function getStates() {
		const res = await fetch('http://localhost:8080/items/states');
		if (res.ok) {
			return await res.json();
		}
		return null;
	}

	return {
		streamed: {
			items: getItems()
		},
		states: await getStates()
	};
};
