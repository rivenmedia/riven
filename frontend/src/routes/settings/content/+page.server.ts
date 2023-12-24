import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { contentSettingsSchema } from '$lib/schemas/setting';
import { getSettings, setSettings } from '$lib/helpers';

export const load = (async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['mdblist', 'overseerr'];
			const results = await getSettings(fetch, toGet);
			return results;
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
        overseerr_url: toPassToSchema.overseerr.data.url,
        overseerr_api_key: toPassToSchema.overseerr.data.api_key,
        mdblist_api_key: toPassToSchema.mdblist.data.api_key,
        mdblist_update_interval: toPassToSchema.mdblist.data.update_interval,
        mdblist_lists: toPassToSchema.mdblist.data.lists
	};

	const form = await superValidate(toPassToSchema, contentSettingsSchema);

	return { form };
}) satisfies PageServerLoad;

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, contentSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}
		console.log(form);

		return {
			form
		};
	}
};
