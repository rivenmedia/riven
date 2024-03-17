import re

from program.settings.manager import settings_manager as sm
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
    hdr: int = 0
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
    av1: int = sm.settings.ranking.rank_av1 or 0


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
    dubbed: int = 60
    subbed: int = 40


class AnyRanking(BaseRankingModel):
    uhd: int = 2
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
    any: AnyRanking = AnyRanking()

    def get(name: str) -> BaseRankingModel:
        """Get a ranking model by name."""
        return getattr(RankModels, name, RankModels.default)


def calculate_ranking(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the ranking of a given ParsedMediaItem"""
    rank = calculate_resolution_rank(parsed_data, ranking)
    rank += calculate_quality_rank(parsed_data, ranking)
    rank += calculate_codec_rank(parsed_data, ranking)
    rank += calculate_audio_rank(parsed_data, ranking)
    rank += calculate_other_ranks(parsed_data, ranking)
    if parsed_data.repack:
        rank += ranking.repack
    if parsed_data.proper:
        rank += ranking.proper
    if parsed_data.remux:
        rank += ranking.remux
    if parsed_data.is_multi_audio:
        rank += ranking.dubbed
    if parsed_data.is_multi_subtitle:
        rank += ranking.subbed
    return rank

def calculate_resolution_rank(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the resolution ranking of a given ParsedMediaItem"""
    resolution: str = parsed_data.resolution[0] if parsed_data.resolution else None
    if parsed_data.is_4k and sm.settings.ranking.include_4k:
        return ranking.uhd
    elif parsed_data.is_4k:
        return -1000
    elif resolution == "1080p":
        return ranking.fhd
    elif resolution == "720p":
        return ranking.hd
    elif resolution in ("576p", "480p"):
        return ranking.sd
    return 0

def calculate_quality_rank(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the quality ranking of a given ParsedMediaItem"""
    total_rank = 0
    quality_rank = {
        "WEB-DL": ranking.webdl,
        "Blu-ray": ranking.bluray,
        "WEBCap": -1000,
        "Cam": -1000,
        "Telesync": -1000,
        "Telecine": -1000,
        "Screener": -1000,
        "BRRip": -1000,
        "BDRip": -1000,
        "VODRip": -1000,
        "TVRip": -1000,
        "DVD-R": -1000,
    }
    for quality, rank in quality_rank.items():
        if quality in parsed_data.quality:
            total_rank += rank
    return total_rank

def calculate_codec_rank(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the codec ranking of a given ParsedMediaItem"""
    total_rank = 0
    codec_rank = {
        "Xvid": -1000,
        "AV1": ranking.av1,
        "H.263": -1000,
        "H.264": 3,
        "H.265": 0,
        "H.265 Main 10": 0,
        "HEVC": 0,
        "VC-1": -1000,
        "MPEG-2": -1000
    }
    for codec, rank in codec_rank.items():
        if codec in parsed_data.codec:
            total_rank += rank
    return total_rank

def calculate_audio_rank(parsed_data, ranking: BaseRankingModel) -> int:
    """Calculate the audio ranking of a given ParsedMediaItem"""
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
        "DTS": ranking.dts_hd,
        "DTS-HD": ranking.dts_hd + 5,
        "DTS-HD MA": ranking.dts_hd_ma + 10,
        "DTS-ES": ranking.dts_x + 5,
        "DTS-EX": ranking.dts_x + 5,
        "DTS:X": ranking.dts_x + 10,
        "AAC": ranking.aac,
        "AAC-LC": ranking.aac + 2,
        "HE-AAC": ranking.aac + 5,
        "HE-AAC v2": ranking.aac + 10,
        "AC3": ranking.ac3,
        "FLAC": -1000,
        "OGG": -1000
    }
    for audio, rank in audio_rank.items():
        if audio == audio_format:
            total_rank += rank
    return total_rank

def calculate_other_ranks(parsed_data, ranking: BaseRankingModel) -> int:  # noqa: C901
    """Calculate all the other rankings of a given ParsedMediaItem"""
    total_rank = 0
    if parsed_data.bitDepth and parsed_data.bitDepth[0] > 8:
        total_rank += 10
    if parsed_data.hdr:
        if parsed_data.hdr == "HDR":
            total_rank += ranking.hdr
        elif parsed_data.hdr == "HDR10+":
            total_rank += ranking.hdr + 10
        elif parsed_data.hdr == "DV":
            total_rank += ranking.dolby_video
    if parsed_data.is_complete:
        total_rank += 100
    elif len(parsed_data.season) > 1:
        total_rank += 15 * len(parsed_data.season)
    elif len(parsed_data.episode) > 1:
        total_rank += 10 * len(parsed_data.episode)
    if parsed_data.excess and "Extras" in parsed_data.excess:
        total_rank += -20
    return total_rank
