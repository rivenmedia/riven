import type { Handle } from '@sveltejs/kit';
import { redirect, error } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';

const onboarding: Handle = async ({ event, resolve }) => {
	if (!event.url.pathname.startsWith('/onboarding')) {
		const res = await event.fetch('http://127.0.0.1:8080/services');
		const data = await res.json();
		if (!data.success || !data.data) {
			error(500, 'API Error');
		}
		const toCheck = ['content', 'scraping', 'plex', 'real_debrid', 'symlink'];
		const allServicesTrue: boolean = toCheck.every((service) => data.data[service] === true);
		if (!allServicesTrue) {
			redirect(302, '/onboarding');
		}
	}

	return resolve(event);
};

export const handle = sequence(onboarding);
