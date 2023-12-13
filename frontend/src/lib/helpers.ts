import { DateTime, Settings } from 'luxon';
import type { PlexDebridItem } from '$lib/types';

// only works with real-debrid dates because of CET format provided by RD
export function formatDate(inputDate: string, format: string = 'long'): string {
	let cetDate = DateTime.fromISO(inputDate, { zone: 'Europe/Paris' }); // Parse date as CET
	cetDate = cetDate.setZone('utc'); // Convert to UTC

	const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone; // Get user's timezone
	cetDate = cetDate.setZone(userTimeZone); // Convert to user's timezone

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

export function formatState(state: string) {
	return state
		.split('_')
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
		.join(' ');
}

export function convertPlexDebridItemsToObject(items: PlexDebridItem[]) {
	const result: { [key: string]: PlexDebridItem[] } = {};

	for (const item of items) {
		if (!result[item.state]) {
			result[item.state] = [];
		}
		result[item.state].push(item);
	}

	return result;
}
