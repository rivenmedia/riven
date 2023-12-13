import type { PageLoad } from './$types';
import type { UserResponse } from '$lib/types';

export const load: PageLoad = async ({ fetch }) => {
	const getUserData = async () => {
		const res = await fetch('http://${HOSTIP}:8080/user');
		if (res.ok) {
            return await res.json() as UserResponse;
        }
        return null;
	};

	return {
		user: getUserData()
	};
};
