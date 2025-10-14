import json
import uuid
from datetime import datetime
from typing import Literal

from loguru import logger
from RTN.models import BaseRankingModel, BestRanking, DefaultRanking, SettingsModel


class VersionProfile(SettingsModel):
    """
    A class representing a version profile for the application.

    This represents a single JSON version configuration for a user.
    For example, it could be a 'movies-4k.json' that would be in charge of getting 4K movies.
    """

    id: str = ""
    media_type: Literal["movie", "show"] = "movie"
    symlink_path: str = "movies"
    anime_type: bool = False
    enable_upgrades: bool = False
    upgrade_resolution_to: Literal["4k", "2160p", "1080p", "720p"] = "1080p"
    upgrade_at: datetime
    upgrade_interval: float = 168.0  # 7 days (in hours)

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.media_type = "movie"
        self.anime_type = False
        self.symlink_path = ""
        self.upgrade_resolution_to = "1080p"
        self.enable_upgrades = False
        self.upgrade_at = datetime.now()
        self.upgrade_interval = 168.0
        super().__init__()


class VersionHandler:
    def __init__(self, config_directory: str):
        self.config_directory = config_directory
        self.current_profile = None

    def load_profile(self, profile_name: str):
        """Load a ranking profile from a JSON file."""
        try:
            with open(f"{self.config_directory}/{profile_name}.json", "r") as file:
                profile_data = json.load(file)
                self.apply_profile(profile_data)
                self.current_profile = profile_name
                logger.info(f"Loaded profile '{profile_name}' successfully.")
        except FileNotFoundError:
            logger.error(
                f"Profile '{profile_name}' not found in directory '{self.config_directory}'."
            )
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON file for profile '{profile_name}': {e}")

    def apply_profile(self, profile_data: dict):
        """Apply the profile settings to the ranking model."""
        # Assuming profile_data contains settings that can be directly applied to the ranking model
        # You might need to adjust this based on the actual structure of your profile data
        ranking_settings = models.get(profile_data.get("ranking_model", "default"))
        # Update the ranking settings with the profile data
        # This is a placeholder; adjust based on your actual settings structure
        for key, value in profile_data.items():
            if hasattr(ranking_settings, key):
                setattr(ranking_settings, key, value)
            else:
                logger.warning(f"Unknown setting '{key}' in profile data.")

    def get_current_profile(self):
        """Get the name of the currently loaded profile."""
        return self.current_profile


class RankModels:
    """
    The `RankModels` class represents a collection of ranking models for different categories.
    Each ranking model is a subclass of the `BaseRankingModel` class.

    Attributes:
        `default` (DefaultRanking): The default ranking model for getting best results for non-transcoded releases.
        `custom` (BaseRankingModel): Uses a base ranking model for all categories with all ranks set to 0.
        `best` (BestRanking): The best ranking model for getting the highest quality releases.

    Methods:
        `get(name: str)` -> `BaseRankingModel`: Returns a ranking model based on the given name.

    Note:
        If the name is not found, use the `custom` model which uses a base ranking model for all categories with all ranks set to 0.
    """

    custom: BaseRankingModel = BaseRankingModel()  # All ranks set to 0 by default
    default: DefaultRanking = DefaultRanking()  # Good for 720p/1080p releases
    best: BestRanking = BestRanking()  # Good for 4K HDR REMUX releases

    @classmethod
    def get(cls, name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        model = getattr(cls, name, None)
        if model is None:
            logger.warning(
                f"Ranking model '{name}' not found. Setting to custom model."
            )
            return cls.custom
        return model


models = RankModels()
