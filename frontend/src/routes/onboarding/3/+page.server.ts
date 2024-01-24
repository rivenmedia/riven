import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { contentSettingsSchema } from '$lib/schemas/setting';
import { saveSettings } from '$lib/helpers';
import {
	contentSettingsToGet,
	contentSettingsToPass,
	contentSettingsToSet
} from '$lib/forms/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(
				`http://127.0.0.1:8080/settings/get/${contentSettingsToGet.join(',')}`
			);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	let toPassToSchema = contentSettingsToPass(data);

	const form = await superValidate(toPassToSchema, contentSettingsSchema, { errors: false });
	return { form };
};
