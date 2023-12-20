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

	return {
		settings: await getSettings(),
		form: superValidate(generalSettingsSchema)
	};
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
