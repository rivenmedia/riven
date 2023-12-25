import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { plexSettingsSchema } from '$lib/schemas/setting';
import { getSettings, setSettings } from '$lib/helpers';

export const load = (async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['plex'];
			const results = await getSettings(fetch, toGet);
			return results;
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
		user: toPassToSchema.plex.data.user,
		token: toPassToSchema.plex.data.token,
		url: toPassToSchema.plex.data.url,
		watchlist: toPassToSchema.plex.data.watchlist
	};

	const form = await superValidate(toPassToSchema, plexSettingsSchema);

	return { form };
}) satisfies PageServerLoad;

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, plexSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}
		const toSet = {
			plex: {
				user: form.data.user,
				token: form.data.token,
				url: form.data.url,
				watchlist: form.data.watchlist
			}
		};

		try {
			const data = await setSettings(event.fetch, toSet);
		} catch (e) {
			console.error(e);
			return message(form, 'Unable to save settings. API is down.', {
				status: 400
			});
		}

		return message(form, 'Settings saved!');
	}
};
