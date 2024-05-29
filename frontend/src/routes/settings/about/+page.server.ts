import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	async function getAboutInfo() {
		try {
			const toGet = ['version', 'symlink'];
			const results = await fetch(`http://127.0.0.1:8080/settings/get/${toGet.join(',')}`);
			return await results.json();
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch settings data. API is down.');
		}
	}
	async function getContributors() {
		try {
			const results = await fetch('https://api.github.com/repos/dreulavelle/iceburg/contributors');
			const data = await results.json();
			return data
			.filter((contributor: any) => contributor.type !== 'Bot' && contributor.type !== 'Organization')
			.map((contributor: any) => ({
				avatar: contributor.avatar_url,
				name: contributor.login,
				profile: contributor.html_url
			}));
		
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch contributors data. API is down.');
		}
	}

	return { settings: await getAboutInfo(), contributors: await getContributors() };
};
