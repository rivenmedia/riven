import { DateTime } from 'luxon';
import type { IcebergItem } from '$lib/types';

// only works with real-debrid dates because of CET format provided by RD
export function formatRDDate(inputDate: string, format: string = 'long'): string {
	let cetDate = DateTime.fromISO(inputDate, { zone: 'Europe/Paris' });
	cetDate = cetDate.setZone('utc');

	const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	cetDate = cetDate.setZone(userTimeZone);

	let formattedDate;
	if (format === 'short') {
		formattedDate = cetDate.toLocaleString({
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	} else {
		formattedDate = cetDate.toLocaleString(DateTime.DATETIME_FULL);
	}

	return formattedDate;
}

export function formatDate(
	inputDate: string,
	format: string = 'long',
	relative: boolean = false
): string {
	let date = DateTime.fromISO(inputDate);
	date = date.setZone('local');

	let formattedDate;

	if (relative) {
		formattedDate = date.toRelative() || '';
	} else {
		if (format === 'short') {
			formattedDate = date.toLocaleString({
				year: 'numeric',
				month: 'short',
				day: 'numeric'
			});
		} else if (format === 'year') {
			formattedDate = date.toLocaleString({
				year: 'numeric'
			});
		} else {
			formattedDate = date.toLocaleString(DateTime.DATETIME_FULL);
		}
	}

	return formattedDate;
}

export function formatWords(words: string) {
	return words
		.split('_')
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
		.join(' ');
}

export function convertIcebergItemsToObject(items: IcebergItem[]) {
	const result: { [key: string]: IcebergItem[] } = {};

	for (const item of items) {
		if (!result[item.state]) {
			result[item.state] = [];
		}
		result[item.state].push(item);
	}

	return result;
}

export async function saveSettings(fetch: any, toSet: any) {
	const data = await fetch('http://127.0.0.1:8080/settings/set', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(toSet)
	});

	const saveSettings = await fetch('http://127.0.0.1:8080/settings/save', {
		method: 'POST'
	});

	const loadSettings = await fetch('http://127.0.0.1:8080/settings/load', {
		method: 'GET'
	});

	return {
		data,
		saveSettings,
		loadSettings
	};
}
