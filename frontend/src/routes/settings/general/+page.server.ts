import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { generalSettingsSchema } from '$lib/schemas/setting';
import { saveSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['symlink', 'real_debrid', 'scraping'];
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${toGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
		host_path: toPassToSchema.data.symlink.host_path,
		container_path: toPassToSchema.data.symlink.container_path,
		realdebrid_api_key: toPassToSchema.data.real_debrid.api_key,
		torrentio_filter: toPassToSchema.data.scraping.torrentio?.filter || '',
		torrentio_enabled: toPassToSchema.data.scraping.torrentio.enabled,
		orionoid_api_key: toPassToSchema.data.scraping.orionoid?.api_key || '',
		orionoid_enabled: toPassToSchema.data.scraping.orionoid.enabled,
		jackett_api_key: toPassToSchema.data.scraping.jackett?.api_key || '',
		jackett_url: toPassToSchema.data.scraping.jackett?.url || '',
		jackett_enabled: toPassToSchema.data.scraping.jackett.enabled
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
		const toSet = [
			{
				key: 'symlink',
				value: {
					host_path: form.data.host_path,
					container_path: form.data.container_path
				}
			},
			{
				key: 'real_debrid',
				value: {
					api_key: form.data.realdebrid_api_key
				}
			},
			{
				key: 'scraping',
				value: {
					torrentio: {
						enabled: form.data.torrentio_enabled,
						filter: form.data.torrentio_filter
					},
					orionoid: {
						enabled: form.data.orionoid_enabled,
						api_key: form.data.orionoid_api_key
					},
					jackett: {
						enabled: form.data.jackett_enabled,
						url: form.data.jackett_url,
						api_key: form.data.jackett_api_key
					}
				}
			}
		];

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
