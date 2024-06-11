import { DateTime } from 'luxon';
import type { RivenItem } from '$lib/types';

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
	} else if (format === 'left') {
		const now = DateTime.now();
		const diff = cetDate.diff(now, 'days').toObject();
		const days = Math.round(diff.days ?? 0);
		if (days > 0) {
			formattedDate = `${days} days left`;
		} else if (days < 0) {
			formattedDate = `${Math.abs(days)} days ago`;
		} else {
			formattedDate = 'Today';
		}
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

export function convertIcebergItemsToObject(items: RivenItem[]) {
	const result: { [key: string]: RivenItem[] } = {};

	for (const item of items) {
		if (!result[item.state]) {
			result[item.state] = [];
		}
		result[item.state].push(item);
	}

	return result;
}
