import type { PageServerLoad, Actions } from './$types';
import { fail, error, redirect } from '@sveltejs/kit';
import { fail, error, redirect } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { saveSettings } from '$lib/helpers';
import {
	mediaServerSettingsSchema,
	mediaServerSettingsToGet,
	mediaServerSettingsToPass,
	mediaServerSettingsToSet
} from '$lib/forms/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(
				`http://127.0.0.1:8080/settings/get/${mediaServerSettingsToGet.join(',')}`
			);
			const results = await fetch(
				`http://127.0.0.1:8080/settings/get/${mediaServerSettingsToGet.join(',')}`
			);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	let toPassToSchema = mediaServerSettingsToPass(data);
	let data: any = await getPartialSettings();
	let toPassToSchema = mediaServerSettingsToPass(data);

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
		const toSet = mediaServerSettingsToSet(form);
		const toSet = mediaServerSettingsToSet(form);

		try {
			const data = await saveSettings(event.fetch, toSet);
		} catch (e) {
			console.error(e);
			return message(form, 'Unable to save settings. API is down.', {
				status: 400
			});
		}

		if (event.url.searchParams.get('onboarding') === 'true') {
			redirect(302, '/onboarding/3');
		}

		if (event.url.searchParams.get('onboarding') === 'true') {
			redirect(302, '/onboarding/3');
		}

		return message(form, 'Settings saved!');
	}
};
