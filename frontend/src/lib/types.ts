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

export interface PlexDebridItem {
	item_id: number;
	title: string;
	type: string;
	imdb_id: string;
	state: string;
	imdb_link: string;
	aired_at: string;
	genres: string[];
	guid: string;
	requested_at: string;
	requested_by: string;
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

export interface PlexService {
	user: string;
	token: string;
	url: string;
	watchlist?: string;
}

export interface MdblistService {
	lists: string[];
	api_key: string;
	update_interval: number;
}

export interface OverseerrService {
	url: string;
	api_key: string;
}

export interface TorrentioService {
	filter: string;
}

export interface RealdebridService {
	api_key: string;
}

export interface IcebergServices {
	plex: PlexService;
	mdblist?: MdblistService;
	overseerr?: OverseerrService;
	torrentio?: TorrentioService;
	realdebrid: RealdebridService;
}
