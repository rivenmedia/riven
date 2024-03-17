import re

from pydantic import BaseModel


class BaseRankingModel(BaseModel):
    # resolution
    uhd: int = 0   # 4K
    fhd: int = 0   # 1080p
    hd: int = 0    # 720p
    sd: int = 0    # 480p
    # quality
    bluray: int = 0
    dolby_video: int = 0
    hdr10_plus: int = 0
    hdr10: int = 0
    # audio
    dts_x: int = 0
    dts_hd: int = 0
    dts_hd_ma: int = 0
    atmos: int = 0
    truehd: int = 0
    dolby_digital_plus: int = 0
    ddplus: int = 0
    ac3: int = 0
    aac: int = 0
    # other
    remux: int = 0
    webdl: int = 0
    repack: int = 5
    proper: int = 4
    # extras
    dubbed: int = 7
    subbed: int = 4
    x264: int = 3


class DefaultRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 90
    hd: int = 80
    sd: int = -20
    aac: int = 70
    ac3: int = 50
    remux: int = -1000
    webdl: int = 100


class BestRemuxRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 60
    hd: int = 40
    sd: int = 20
    dolby_video: int = 100
    hdr10_plus: int = 90
    hdr10: int = 80
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
    hdr10_plus: int = 90
    hdr10: int = 80
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
    hdr10_plus: int = 90
    hdr10: int = 80
    dts_x: int = 100
    dts_hd: int = 80
    dts_hd_ma: int = 90
    atmos: int = 90
    truehd: int = 60
    dolby_digital_plus: int = 100
    ddplus: int = 90
    aac: int = 30
    ac3: int = 20
    remux: int = 150
    webdl: int = -1000
    

class BestOverallRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 90
    hd: int = 80
    sd: int = 70
    dolby_video: int = 100
    hdr10_plus: int = 90
    hdr10: int = 80
    dts_x: int = 100
    dts_hd: int = 80
    dts_hd_ma: int = 90
    atmos: int = 90
    truehd: int = 60
    dolby_digital_plus: int = 50
    ddplus: int = 40
    aac: int = 30
    ac3: int = 20
    remux: int = 150
    webdl: int = 90


class AnimeRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 90
    hd: int = 80
    sd: int = 20
    ac3: int = 50
    remux: int = -1000
    webdl: int = 100
    dubbed: int = 60
    subbed: int = 40


class AnyRanking(BaseRankingModel):
    uhd: int = 1
    fhd: int = 1
    hd: int = 1
    sd: int = 1
    dolby_video: int = 1
    hdr10_plus: int = 1
    hdr10: int = 1
    dts_x: int = 1
    dts_hd: int = 1
    dts_hd_ma: int = 1
    atmos: int = 1
    truehd: int = 1
    dolby_digital_plus: int = 1
    ddplus: int = 1
    ac3: int = 1
    remux: int = 1
    webdl: int = 1
    repack: int = 1
    proper: int = 1


class RankModels:
    """RankModels class for storing all ranking models."""
    default: DefaultRanking = DefaultRanking()
    remux: BestRemuxRanking = BestRemuxRanking()
    web: BestWebRanking = BestWebRanking()
    resolution: BestResolutionRanking = BestResolutionRanking()
    overall: BestOverallRanking = BestOverallRanking()
    anime: AnimeRanking = AnimeRanking()
    any: AnyRanking = AnyRanking()

    def get(name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        return getattr(RankModels, name, RankModels.default)


def calculate_ranking(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the ranking of a given ParsedMediaItem"""
    rank = calculate_resolution_rank(parsed_data, ranking)
    rank += calculate_quality_rank(parsed_data, ranking)
    rank += calculate_audio_rank(parsed_data, ranking)
    rank += calculate_other_ranks(parsed_data, ranking)
    return rank

def calculate_resolution_rank(parsed_data, ranking: BaseRankingModel) -> int:
    if parsed_data.is_4k:
        return ranking.uhd
    for resolution in parsed_data.resolution:
        if resolution == "1080p":
            return ranking.fhd
        if resolution == "720p":
            return ranking.hd
        if resolution == "480p":
            return ranking.sd
    return 0

def calculate_quality_rank(parsed_data, ranking: BaseRankingModel) -> int:
    total_rank = 0
    quality_rank = {
        "WEB-DL": ranking.webdl,
        "Dolby Vision": ranking.dolby_video,
        "HDR10+": ranking.hdr10_plus,
        "HDR10": ranking.hdr10
    }
    for quality, rank in quality_rank.items():
        if quality in parsed_data.quality:
            total_rank += rank
    return total_rank

def calculate_audio_rank(parsed_data, ranking: BaseRankingModel) -> int:
    total_rank = 0
    audio_format: str = parsed_data.audio[0] if parsed_data.audio else None
    if not audio_format:
        return total_rank
    
    # Remove any unwanted audio formats. We dont support surround sound formats yet.
    # These also make it harder to compare audio formats.
    audio_format = re.sub(r"7.1|5.1|Dual|Mono|Original|LiNE", "", audio_format).strip()
    
    audio_rank = {
        "Dolby TrueHD": ranking.truehd,
        "Dolby Atmos": ranking.atmos,
        "Dolby Digital": ranking.ac3,
        "Dolby Digital EX": ranking.dts_x,
        "Dolby Digital Plus": ranking.ddplus,
        "DTS-HD": ranking.dts_hd,
        "DTS-HD MA": ranking.dts_hd_ma,
        "DTS-ES": ranking.dts_x,
        "DTS-EX": ranking.dts_x,
        "DTS:X": ranking.dts_x,
        "DTS": ranking.dts_hd,
        "AC3": ranking.ac3,
        "Custom": ranking.dubbed,
        "Dual": ranking.dubbed
    }
    for audio, rank in audio_rank.items():
        if audio == audio_format:
            total_rank += rank
    return total_rank

def calculate_other_ranks(parsed_data, ranking: BaseRankingModel) -> int:
    total_rank = 0
    if parsed_data.repack:
        total_rank += ranking.repack
    if parsed_data.proper:
        total_rank += ranking.proper
    if parsed_data.remux:
        total_rank += ranking.remux
    if parsed_data.is_multi_audio:
        total_rank += ranking.dubbed
    if parsed_data.is_multi_subtitle:
        total_rank += ranking.subbed
    if parsed_data.bitDepth and parsed_data.bitDepth[0] > 8:
        total_rank += 10
    return total_rank
