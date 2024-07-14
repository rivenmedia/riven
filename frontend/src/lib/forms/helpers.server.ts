import { BACKEND_URL } from '$env/static/private';

// TODO: Add toCheck
export async function setSettings(fetch: any, toSet: any) {
	const settings = await fetch(`${BACKEND_URL}/settings/set`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(toSet)
	});
	const settingsData = await settings.json();

	return {
		data: settingsData
	};
}

export async function saveSettings(fetch: any) {
	const data = await fetch(`${BACKEND_URL}/settings/save`, {
		method: 'POST'
	});
	const response = await data.json();

	return {
		data: response
	};
}

export async function loadSettings(fetch: any) {
	const data = await fetch(`${BACKEND_URL}/settings/load`, {
		method: 'GET'
	});
	const response = await data.json();

	return {
		data: response
	};
}
