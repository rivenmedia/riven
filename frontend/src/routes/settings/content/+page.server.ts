import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { contentSettingsSchema } from '$lib/schemas/setting';
import { getSettings, setSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['overseerr', 'mdblist'];
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
};

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, contentSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}

		const toSet = {
			overseerr: {
				url: form.data.overseerr_url,
				api_key: form.data.overseerr_api_key
			},
			mdblist: {
				api_key: form.data.mdblist_api_key,
				update_interval: form.data.mdblist_update_interval,
				lists: form.data.mdblist_lists
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
