export interface NavItem {
	name: string;
	path: string;
}

export interface UserResponse {
	id: number;
	username: string;
	email: string;
	points: number;
	locale: string;
	avatar: string;
	type: string;
	premium: number;
	expiration: string;
}

export interface IcebergItem {
	item_id: number;
	title: string;
	type: string;
	imdb_id: string | null;
	tvdb_id: number | null;
	tmdb_id: number | null;
	state: string;
	imdb_link: string;
	aired_at: string;
	genres: string[];
	guid: string | null;
	requested_at: string;
	requested_by: string;
	scraped_at: string | null;
	scraped_times: number | null;
}

export interface StatusInterface {
	text?: string;
	color: string;
	bg: string;
	description: string;
}

export interface StatusInfo {
	[key: string]: StatusInterface;
}
