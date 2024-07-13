import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ fetch }) => {
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

	async function getTrendingMoviesWeek() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/trending/movie/week');
			if (res.ok) {
				return await res.json();
			}
			error(400, `Unable to fetch trending movies data: ${res.status} ${res.statusText}`);
		} catch (e) {
			console.error(e);
			error(503, 'Unable to fetch trending movies data. Server error or API is down.');
		}
	}

	async function getTrendingShowsWeek() {
		try {
			const res = await fetch('http://127.0.0.1:8080/tmdb/trending/tv/week');
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
		trendingMovies: await getTrendingMoviesWeek(),
		trendingShows: await getTrendingShowsWeek(),
		moviesPopular: await getMoviesPopular(),
		moviesTopRated: await getMoviesTopRated(),
		showsPopular: await getShowsPopular(),
		showsTopRated: await getShowsTopRated()
	};
};
