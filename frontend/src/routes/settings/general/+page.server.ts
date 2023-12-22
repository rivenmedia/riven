import type { PageServerLoad, Actions } from './$types';
import { fail } from '@sveltejs/kit';
import { error } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms/server';
import { generalSettingsSchema } from '$lib/schemas/setting';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getSettings() {
		try {
			const toGet = ['version', 'host_mount', 'container_mount', 'realdebrid', 'torrentio'];
			const promises = toGet.map(async (item) => {
				const res = await fetch(`http://127.0.0.1:8080/settings/get/${item}`);
				if (res.ok) {
					return await res.json();
				}
				error(400, `Unable to fetch settings data: ${res.status} ${res.statusText}`);
			});

			const results = (await Promise.all(promises)).reduce((acc, item, index) => {
				acc[toGet[index]] = item;
				return acc;
			}, {});

			return results;
		} catch (e) {
			console.error(e);
			error(500, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getSettings();
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
		return {
			form
		};
	}
};
