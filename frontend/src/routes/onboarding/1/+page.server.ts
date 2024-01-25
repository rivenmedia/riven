import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms/server';
import { generalSettingsSchema } from '$lib/forms/helpers';
import { generalSettingsToGet, generalSettingsToPass } from '$lib/forms/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(
				`http://127.0.0.1:8080/settings/get/${generalSettingsToGet.join(',')}`
			);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	let toPassToSchema = generalSettingsToPass(data);

	const form = await superValidate(toPassToSchema, generalSettingsSchema, { errors: false });
	return { form };
};
