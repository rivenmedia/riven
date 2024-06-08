import type { PageServerLoad, Actions } from './$types';
import { superValidate, message } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { fail, error, redirect } from '@sveltejs/kit';
import { formatWords } from '$lib/helpers';
import {
	setSettings,
	saveSettings,
	loadSettings,
	scrapersSettingsSchema,
	scrapersSettingsToGet,
	scrapersSettingsServices,
	scrapersSettingsToPass,
	scrapersSettingsToSet
} from '$lib/forms/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(
				`http://127.0.0.1:8080/settings/get/${scrapersSettingsToGet.join(',')}`
			);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	let toPassToSchema = scrapersSettingsToPass(data);

	return {
		form: await superValidate(toPassToSchema, zod(scrapersSettingsSchema))
	};
};

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, zod(scrapersSettingsSchema));

		if (!form.valid) {
			console.log("form not valid")
			return fail(400, {
				form
			});
		}
		const toSet = scrapersSettingsToSet(form);

		try {
			const data = await setSettings(event.fetch, toSet, scrapersSettingsServices);
			if (!data.data.success) {
				return message(
					form,
					`${scrapersSettingsServices.map(formatWords).join(', ')} service(s) failed to initialize. Please check your settings.`,
					{
						status: 400
					}
				);
			}
			const save = await saveSettings(event.fetch);
			const load = await loadSettings(event.fetch);
		} catch (e) {
			console.error(e);
			return message(form, 'Unable to save settings. API is down.', {
				status: 400
			});
		}

		if (event.url.searchParams.get('onboarding') === 'true') {
			redirect(302, '/onboarding/4');
		}

		return message(form, 'Settings saved!');
	}
};
