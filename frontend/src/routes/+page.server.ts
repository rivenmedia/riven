import type { PageServerLoad } from './$types';
import type { RDUserResponse, TorboxUserResponse } from '$lib/types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	// async function getUserData() {
	// 	try {
	// 		const res = await fetch('http://127.0.0.1:8080/user');
	// 		if (res.ok) {
	// 			return (await res.json()) as UserResponse;
	// 		}
	// 		error(400, `Unable to fetch user data: ${res.status} ${res.statusText}`);
	// 	} catch (e) {
	// 		console.error(e);
	// 		error(503, 'Unable to fetch user data. Server error or API is down.');
	// 	}
	// }

	// async function getServices() {
	// 	try {
	// 		const res = await fetch('http://127.0.0.1:8080/services');
	// 		if (res.ok) {
	// 			return await res.json();
	// 		}
	// 		error(400, `Unable to fetch services data: ${res.status} ${res.statusText}`);
	// 	} catch (e) {
	// 		console.error(e);
	// 		error(503, 'Unable to fetch services data. Server error or API is down.');
	// 	}
	// }

	async function getAppData() {
		try {
			const serviceRes = await fetch('http://127.0.0.1:8080/services');
			if (serviceRes.ok) {
				const services = await serviceRes.json();

				if (services.data.torbox) {
					const userRes = await fetch('http://127.0.0.1:8080/torbox');
					if (userRes.ok) {
						return {
							services,
							user: (await userRes.json()),
							downloader: "torbox"
						};
					}
				} else {
					const userRes = await fetch('http://127.0.0.1:8080/rd');
					if (userRes.ok) {
						return {
							services,
							user: (await userRes.json()),
							downloader: "rd"
						};
					}
				}
			}
			error(400, `Unable to fetch services data: ${serviceRes.status} ${serviceRes.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch services data. Server error or API is down.');
		}
	}

	async function getVersion() {
		try {
			const res = await fetch('http://127.0.0.1:8080/settings/get/version');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch version data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch version data. Server error or API is down.');
		}
	}

	return {
		version: await getVersion(),
		appData: await getAppData()
	};
};
