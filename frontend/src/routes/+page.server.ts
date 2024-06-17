import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
	// async function getAppData() {
	// 	try {
	// 		const serviceRes = await fetch('http://127.0.0.1:8080/services');
	// 		if (serviceRes.ok) {
	// 			const services = await serviceRes.json();

	// 			if (services.data.torbox) {
	// 				const userRes = await fetch('http://127.0.0.1:8080/torbox');
	// 				if (userRes.ok) {
	// 					return {
	// 						services,
	// 						user: await userRes.json(),
	// 						downloader: 'torbox'
	// 					};
	// 				}
	// 			} else {
	// 				const userRes = await fetch('http://127.0.0.1:8080/rd');
	// 				if (userRes.ok) {
	// 					return {
	// 						services,
	// 						user: await userRes.json(),
	// 						downloader: 'rd'
	// 					};
	// 				}
	// 			}
	// 		}
	// 		error(400, `Unable to fetch services data: ${serviceRes.status} ${serviceRes.statusText}`);
	// 	} catch (e) {
	// 		console.error(e);
	// 		error(503, 'Unable to fetch services data. Server error or API is down.');
	// 	}
	// }

	// async function getVersion() {
	// 	try {
	// 		const res = await fetch('http://127.0.0.1:8080/settings/get/version');
	// 		if (res.ok) {
	// 			return await res.json();
	// 		}
	// 		error(400, `Unable to fetch version data: ${res.status} ${res.statusText}`);
	// 	} catch (e) {
	// 		console.error(e);
	// 		error(503, 'Unable to fetch version data. Server error or API is down.');
	// 	}
	// }

	async function getNowPlaying() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/movie/now_playing');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch now playing data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch now playing data. Server error or API is down.');
		}
	}

	async function getTrendingAll() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/trending/all/day');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch trending data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch trending data. Server error or API is down.');
		}
	}

	async function getTrendingMovies() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/trending/movie/day');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch trending movies data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch trending movies data. Server error or API is down.');
		}
	}

	async function getTrendingShows() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/trending/tv/day');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch trending shows data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch trending shows data. Server error or API is down.');
		}
	}

	async function getMoviesPopular() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/movie/popular');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch popular movies data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch popular movies data. Server error or API is down.');
		}
	}

	async function getMoviesTopRated() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/movie/top_rated');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch top rated movies data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch top rated movies data. Server error or API is down.');
		}
	}

	async function getShowsPopular() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/tv/popular');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch popular shows data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch popular shows data. Server error or API is down.');
		}
	}

	async function getShowsTopRated() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/tv/top_rated');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch top rated shows data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch top rated shows data. Server error or API is down.');
		}
	}

	return {
		nowPlaying: await getNowPlaying(),
		trendingAll: await getTrendingAll(),
		trendingMovies: await getTrendingMovies(),
		trendingShows: await getTrendingShows(),
		moviesPopular: await getMoviesPopular(),
		moviesTopRated: await getMoviesTopRated(),
		showsPopular: await getShowsPopular(),
		showsTopRated: await getShowsTopRated()
	};
};
