from pydantic import BaseModel


class BaseRankingModel(BaseModel):
    # resolution
    uhd: int = 0
    fhd: int = 0
    hd: int = 0
    sd: int = 0
    # quality
    bluray: int = 0
    hdr: int = 0
    hdr10: int = 0
    dolby_video: int = 0
    # audio
    dts_x: int = 0
    dts_hd: int = 0
    dts_hd_ma: int = 0
    atmos: int = 0
    truehd: int = 0
    ddplus: int = 0
    ac3: int = 0
    aac: int = 0
    # other
    remux: int = 0
    webdl: int = 0
    repack: int = 5
    proper: int = 4
    # extras
    dubbed: int = 4
    subbed: int = 2
    av1: int =  0


class DefaultRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 90
    hd: int = 80
    sd: int = -20
    dolby_video: int = -20
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
    uhd: int = 1
    fhd: int = 3
    hd: int = 2
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
    """RankModels class for storing all ranking models."""
    default: DefaultRanking = DefaultRanking()
    remux: BestRemuxRanking = BestRemuxRanking()
    web: BestWebRanking = BestWebRanking()
    resolution: BestResolutionRanking = BestResolutionRanking()
    overall: BestOverallRanking = BestOverallRanking()
    anime: AnimeRanking = AnimeRanking()
    all: AllRanking = AllRanking()

    def get(name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        return getattr(RankModels, name, RankModels.default)
