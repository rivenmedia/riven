from RTN.models import BaseRankingModel
from utils.logger import logger


class DefaultRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 100
    hd: int = 50
    sd: int = -100
    dolby_video: int = -100
    aac: int = 70
    ac3: int = 50
    remux: int = -1000
    webdl: int = 90
    bluray: int = 80


class BestRemuxRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 60
    hd: int = 40
    sd: int = 20
    dolby_video: int = 100
    hdr: int = 80
    hdr10: int = 90
    dts_x: int = 100
    dts_hd: int = 80
    dts_hd_ma: int = 90
    atmos: int = 90
    truehd: int = 60
    aac: int = 30
    ac3: int = 20
    remux: int = 150
    webdl: int = -1000


class BestWebRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 90
    hd: int = 80
    sd: int = 20
    dolby_video: int = 100
    hdr: int = 80
    hdr10: int = 90
    aac: int = 50
    ac3: int = 40
    remux: int = -1000
    webdl: int = 100


class BestResolutionRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 90
    hd: int = 80
    sd: int = 70
    dolby_video: int = 100
    hdr: int = 80
    hdr10: int = 90
    dts_x: int = 100
    dts_hd: int = 80
    dts_hd_ma: int = 90
    atmos: int = 90
    truehd: int = 60
    ddplus: int = 90
    aac: int = 30
    ac3: int = 20
    remux: int = 150
    bluray: int = 120
    webdl: int = -1000


class BestOverallRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 90
    hd: int = 80
    sd: int = 70
    dolby_video: int = 100
    hdr: int = 80
    hdr10: int = 90
    dts_x: int = 100
    dts_hd: int = 80
    dts_hd_ma: int = 90
    atmos: int = 90
    truehd: int = 60
    ddplus: int = 40
    aac: int = 30
    ac3: int = 20
    remux: int = 150
    bluray: int = 120
    webdl: int = 90


class AnimeRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 90
    hd: int = 80
    sd: int = 20
    aac: int = 70
    ac3: int = 50
    remux: int = -1000
    webdl: int = 90
    bluray: int = 50
    dubbed: int = 100
    subbed: int = 100


class AllRanking(BaseRankingModel):
    uhd: int = 2
    fhd: int = 3
    hd: int = 1
    sd: int = 1
    dolby_video: int = 1
    hdr: int = 1
    dts_x: int = 1
    dts_hd: int = 1
    dts_hd_ma: int = 1
    atmos: int = 1
    truehd: int = 1
    ddplus: int = 1
    aac: int = 2
    ac3: int = 1
    remux: int = 1
    webdl: int = 1
    bluray: int = 1


class RankModels:
    """
    The `RankModels` class represents a collection of ranking models for different categories.
    Each ranking model is a subclass of the `BaseRankingModel` class.

    Attributes:
        `default` (DefaultRanking): The default ranking model.
        `remux` (BestRemuxRanking): The ranking model for the best remux.
        `web` (BestWebRanking): The ranking model for the best web release.
        `resolution` (BestResolutionRanking): The ranking model for the best resolution.
        `overall` (BestOverallRanking): The ranking model for the best overall quality.
        `anime` (AnimeRanking): The ranking model for anime releases.
        `all` (AllRanking): The ranking model for all releases.

    Methods:
        `get(name: str)` -> `BaseRankingModel`: Returns a ranking model based on the given name.
        If the name is not found, the default ranking model is returned.
    """

    default: DefaultRanking = DefaultRanking()
    custom: BaseRankingModel = BaseRankingModel()
    remux: BestRemuxRanking = BestRemuxRanking()
    web: BestWebRanking = BestWebRanking()
    resolution: BestResolutionRanking = BestResolutionRanking()
    overall: BestOverallRanking = BestOverallRanking()
    anime: AnimeRanking = AnimeRanking()
    all: AllRanking = AllRanking()

    @classmethod
    def get(cls, name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        model = getattr(cls, name, None)
        if model is None:
            logger.warning(f"Ranking model '{name}' not found. Setting to custom model.")
            return cls.custom
        return model


models = RankModels()
