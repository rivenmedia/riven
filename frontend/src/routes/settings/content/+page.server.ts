import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { contentSettingsSchema } from '$lib/schemas/setting';
import { saveSettings } from '$lib/helpers';
import { contentSettingsToGet, contentSettingsToPass, contentSettingsToSet } from '$lib/forms/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${contentSettingsToGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	const toPassToSchema = contentSettingsToPass(data);

	const form = await superValidate(toPassToSchema, contentSettingsSchema);
	return { form };
};

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, contentSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}
		const toSet = contentSettingsToSet(form);

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
