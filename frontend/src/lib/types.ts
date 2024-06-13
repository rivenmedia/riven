export interface NavItem {
	name: string;
	path: string;
}

export interface RDData {
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

export interface RDUserResponse {
	success: boolean;
	data: RDData;
	downloader: string;
}
interface TorboxData {
	id: number;
	created_at: string;
	updated_at: string;
	email: string;
	plan: number;
	total_downloaded: number;
	customer: string;
	server: number;
	is_subscribed: boolean;
	premium_expires_at: string;
	cooldown_until: string;
	auth_id: string;
	user_referral: string;
	base_email: string;
}

export interface TorboxUserResponse {
	success: boolean;
	detail: string;
	data: TorboxData;
	downloader: string;
}

export interface RivenItem {
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
	is_anime: boolean;
	guid: string | null;
	requested_at: string;
	requested_by: string;
	scraped_at: string | null;
	scraped_times: number | null;
}
