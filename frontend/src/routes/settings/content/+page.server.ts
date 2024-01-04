import type { PageServerLoad, Actions } from './$types';
import { fail, error } from '@sveltejs/kit';
import { message, superValidate } from 'sveltekit-superforms/server';
import { contentSettingsSchema } from '$lib/schemas/setting';
import { saveSettings } from '$lib/helpers';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getPartialSettings() {
		try {
			const toGet = ['content'];
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${toGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}

	let toPassToSchema: any = await getPartialSettings();
	toPassToSchema = {
		overseerr_enabled: toPassToSchema.data.content.overseerr.enabled,
		overseerr_url: toPassToSchema.data.content.overseerr?.url || '',
		overseerr_api_key: toPassToSchema.data.content.overseerr?.api_key || '',
		mdblist_enabled: toPassToSchema.data.content.mdblist.enabled,
		mdblist_api_key: toPassToSchema.data.content.mdblist?.api_key || '',
		mdblist_update_interval: toPassToSchema.data.content.mdblist?.update_interval || 80,
		mdblist_lists: toPassToSchema.data.content.mdblist?.lists || [''],
		plex_watchlist_enabled: toPassToSchema.data.content.plex_watchlist.enabled,
		plex_watchlist_rss: toPassToSchema.data.content.plex_watchlist?.watchlist || '',
		plex_watchlist_update_interval:
			toPassToSchema.data.content.plex_watchlist?.update_interval || 80
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
		const toSet = [
			{
				key: 'content',
				value: {
					overseerr: {
						enabled: form.data.overseerr_enabled,
						url: form.data.overseerr_url,
						api_key: form.data.overseerr_api_key
					},
					mdblist: {
						enabled: form.data.mdblist_enabled,
						api_key: form.data.mdblist_api_key,
						update_interval: form.data.mdblist_update_interval,
						lists: form.data.mdblist_lists
					},
					plex_watchlist: {
						enabled: form.data.plex_watchlist_enabled,
						watchlist: form.data.plex_watchlist_rss,
						update_interval: form.data.plex_watchlist_update_interval
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
