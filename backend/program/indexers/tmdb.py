from utils.logger import logger
from utils.request import get

TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105

# TODO: Maybe remove the else condition ? It's not necessary since exception is raised 400-450, 500-511, 408, 460, 504, 520, 524, 522, 598 and 599


class TMDB:
    def __init__(self):
        self.API_URL = "https://api.themoviedb.org/3"
        self.HEADERS = {
            "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}",
        }

    def getMoviesNowPlaying(self, params: str):
        url = f"{self.API_URL}/movie/now_playing?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get movies now playing: {response.text}")
                return None
        except Exception as e:
            logger.error(
                f"An error occurred while getting movies now playing: {str(e)}"
            )
            return None

    def getMoviesPopular(self, params: str):
        url = f"{self.API_URL}/movie/popular?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get popular movies: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting popular movies: {str(e)}")
            return None

    def getMoviesTopRated(self, params: str):
        url = f"{self.API_URL}/movie/top_rated?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get top rated movies: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting top rated movies: {str(e)}")
            return None

    def getMoviesUpcoming(self, params: str):
        url = f"{self.API_URL}/movie/upcoming?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get upcoming movies: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting upcoming movies: {str(e)}")
            return None

    def getTrending(self, params: str, type: str, window: str):
        url = f"{self.API_URL}/trending/{type}/{window}?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get trending {type}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting trending {type}: {str(e)}")
            return None

    def getTVAiringToday(self, params: str):
        url = f"{self.API_URL}/tv/airing_today?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV airing today: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV airing today: {str(e)}")
            return None

    def getTVOnTheAir(self, params: str):
        url = f"{self.API_URL}/tv/on_the_air?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV on the air: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV on the air: {str(e)}")
            return None

    def getTVPopular(self, params: str):
        url = f"{self.API_URL}/tv/popular?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get popular TV shows: {response.text}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting popular TV shows: {str(e)}")
            return None

    def getTVTopRated(self, params: str):
        url = f"{self.API_URL}/tv/top_rated?{params}"
        try:
            response = get(url, additional_headers=self.HEADERS)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get top rated TV shows: {response.text}")
                return None
        except Exception as e:
            logger.error(
                f"An error occurred while getting top rated TV shows: {str(e)}"
            )
            return None
