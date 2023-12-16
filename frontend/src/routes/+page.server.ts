import type { PageServerLoad } from './$types';
import type { UserResponse } from '$lib/types';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getUserData() {
		const res = await fetch('http://localhost:8080/user');
		if (res.ok) {
			return (await res.json()) as UserResponse;
		}
		return null;
	}

	return {
		user: await getUserData()
	};
};
