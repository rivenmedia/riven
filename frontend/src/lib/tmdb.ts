// Todo

class TmdbApi {
	private apiKey: string;
	private baseUrl: string;

	constructor(apiKey: string) {
		this.apiKey = apiKey;
		this.baseUrl = 'https://api.themoviedb.org/3';
	}

	async getPopularMovies() {
		const response = await fetch(`${this.baseUrl}/movie/popular?api_key=${this.apiKey}`);
		const data = await response.json();
		return data.results;
	}

	async getMovieDetails(id: number) {
		const response = await fetch(`${this.baseUrl}/movie/${id}?api_key=${this.apiKey}`);
		return response.json();
	}
}

export default TmdbApi;
