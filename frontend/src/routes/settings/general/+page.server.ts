import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { generalSettingsSchema } from '$lib/schemas/setting';
import { getSettings, setSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['version', 'host_mount', 'container_mount', 'realdebrid', 'torrentio'];
			const results = await getSettings(fetch, toGet);
			return results;
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
		host_mount: toPassToSchema.host_mount.data,
		container_mount: toPassToSchema.container_mount.data,
		realdebrid_api_key: toPassToSchema.realdebrid.data.api_key,
		torrentio_filter: toPassToSchema.torrentio.data.filter
	};

	const form = await superValidate(toPassToSchema, generalSettingsSchema);

	return { form };
};

export const actions: Actions = {
	default: async (event) => {
		const form = await superValidate(event, generalSettingsSchema);
		if (!form.valid) {
			return fail(400, {
				form
			});
		}
		console.log(form);

		const toSet = {
			host_mount: form.data.host_mount,
			container_mount: form.data.container_mount,
			realdebrid: {
				api_key: form.data.realdebrid_api_key
			},
			torrentio: {
				filter: form.data.torrentio_filter
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
