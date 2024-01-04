import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { mediaServerSettingsSchema } from '$lib/schemas/setting';
import { saveSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['plex'];
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${toGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
		plex_token: toPassToSchema.data.plex.token,
		plex_url: toPassToSchema.data.plex.url
	};

	const form = await superValidate(toPassToSchema, mediaServerSettingsSchema);

	return { form };
};

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, mediaServerSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}
		const toSet = [
			{
				key: 'plex',
				value: {
					token: form.data.plex_token,
					url: form.data.plex_url
				}
			}
		];

		try {
			const data = await saveSettings(event.fetch, toSet);
		} catch (e) {
			console.error(e);
			return message(form, 'Unable to save settings. API is down.', {
				status: 400
			});
		}

		return message(form, 'Settings saved!');
	}
};
