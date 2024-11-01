from loguru import logger
from RTN.models import BaseRankingModel, BestRanking, DefaultRanking


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

    custom: BaseRankingModel = BaseRankingModel() # All ranks set to 0 by default
    default: DefaultRanking = DefaultRanking() # Good for 720p/1080p releases
    best: BestRanking = BestRanking() # Good for 4K HDR REMUX releases

    @classmethod
    def get(cls, name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        model = getattr(cls, name, None)
        if model is None:
            logger.warning(f"Ranking model '{name}' not found. Setting to custom model.")
            return cls.custom
        return model


models = RankModels()
