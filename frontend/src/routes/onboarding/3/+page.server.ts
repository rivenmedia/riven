import type { PageServerLoad } from './$types';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { error } from '@sveltejs/kit';
import {
	contentSettingsSchema,
	contentSettingsToGet,
	contentSettingsToPass
} from '$lib/forms/helpers';
import { BACKEND_URL } from '$env/static/private';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const results = await fetch(
				`${BACKEND_URL}/settings/get/${contentSettingsToGet.join(',')}`
			);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let data: any = await getPartialSettings();
	let toPassToSchema = contentSettingsToPass(data);

	return {
		form: await superValidate(toPassToSchema, zod(contentSettingsSchema))
	};
};
