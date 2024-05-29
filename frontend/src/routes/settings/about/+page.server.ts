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
	async function getSponsors() {
		try {
			// graphql query to get sponsors
			const query = `
			query {
				user(login: "dreulavelle") {
				  ... on Sponsorable {
					sponsors(first: 100) {
					  totalCount
					  nodes {
						... on User { login, avatarUrl, url }
						... on Organization { login, avatarUrl, url }
					  }
					}
				  }
				}
			}
			`
			const results = await fetch('https://api.github.com/graphql', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ query })
			});
			if (results.status !== 200) {
				console.error(results);
				return []
			}
			const data = await results.json();
			return data.data.user.sponsors.nodes.map((sponsor: any) => ({
				avatar: sponsor.avatarUrl,
				name: sponsor.login,
				profile: sponsor.url
			}));
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch sponsors data. API is down.');
		}
	}

	return { settings: await getAboutInfo(), contributors: await getContributors(), sponsors: await getSponsors()};
};
