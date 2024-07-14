import type { Handle } from '@sveltejs/kit';
import { redirect, error } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { env } from '$env/dynamic/private';

const onboarding: Handle = async ({ event, resolve }) => {
	if (!event.url.pathname.startsWith('/onboarding') && event.request.method === 'GET') {
		const BACKEND_URL = env.BACKEND_URL || 'http://127.0.0.1:8080';
		const res = await event.fetch(`${env.BACKEND_URL}/services`);
		const data = await res.json();
		if (!data.success || !data.data) {
			error(500, 'API Error');
		}
		const toCheck = ['symlink', 'symlinklibrary'];
		const allServicesTrue: boolean = toCheck.every((service) => data.data[service] === true);
		if (!allServicesTrue) {
			redirect(302, '/onboarding');
		}
	}

	return resolve(event);
};

export const handle = sequence(onboarding);
