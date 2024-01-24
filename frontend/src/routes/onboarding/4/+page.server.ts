import type { PageServerLoad, Actions } from './$types';
import { error } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms/server';
import { scrapersSettingsSchema } from '$lib/forms/helpers';
import {
	scrapersSettingsToGet,
	scrapersSettingsToPass,
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

	const form = await superValidate(toPassToSchema, scrapersSettingsSchema, { errors: false });
	return { form };
};
