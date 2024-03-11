from pydantic import BaseModel


class BaseRankingModel(BaseModel):
    uhd: int = 0   # 4K
    fhd: int = 0   # 1080p
    hd: int = 0    # 720p
    sd: int = 0    # 480p
    dolby_video: int = 0
    hdr10_plus: int = 0
    hdr10: int = 0
    dts_x: int = 0
    dts_hd: int = 0
    truehd_atmos: int = 0
    truehd: int = 0
    ddp_atmos: int = 0
    ddplus: int = 0
    ac3: int = 0
    remux: int = 0
    webdl: int = 0
    repack: int = 0
    proper: int = 0


class DefaultRanking(BaseRankingModel):
    uhd: int = -1000
    fhd: int = 90
    hd: int = 80
    sd: int = 20
    dolby_video: int = 0
    hdr10_plus: int = 0
    hdr10: int = 0
    dts_x: int = 0
    dts_hd: int = 0
    truehd_atmos: int = 0
    truehd: int = 0
    ddp_atmos: int = 0
    ddplus: int = 0
    ac3: int = 50
    remux: int = -1000
    webdl: int = 100
    repack: int = 4
    proper: int = 5


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
    truehd_atmos: int = 90
    truehd: int = 60
    ddp_atmos: int = 0
    ddplus: int = 0
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    repack: int = 4
    proper: int = 5


class BestWebRanking(BaseRankingModel):
    uhd: int = 100
    fhd: int = 90
    hd: int = 80
    sd: int = 20
    dolby_video: int = 100
    hdr10_plus: int = 90
    hdr10: int = 80
    dts_x: int = 0
    dts_hd: int = 0
    truehd_atmos: int = 0
    truehd: int = 0
    ddp_atmos: int = 0
    ddplus: int = 0
    ac3: int = 50
    remux: int = -1000
    webdl: int = 100
    repack: int = 4
    proper: int = 5


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
    truehd_atmos: int = 90
    truehd: int = 60
    ddp_atmos: int = 100
    ddplus: int = 90
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    repack: int = 4
    proper: int = 5
    

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
    truehd_atmos: int = 90
    truehd: int = 60
    ddp_atmos: int = 50
    ddplus: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = 90
    repack: int = 4
    proper: int = 5


class WhateverRanking(BaseRankingModel):
    uhd: int = 1
    fhd: int = 1
    hd: int = 1
    sd: int = 1
    dolby_video: int = 1
    hdr10_plus: int = 1
    hdr10: int = 1
    dts_x: int = 1
    dts_hd: int = 1
    truehd_atmos: int = 1
    truehd: int = 1
    ddp_atmos: int = 1
    ddplus: int = 1
    ac3: int = 1
    remux: int = 1
    webdl: int = 1
    repack: int = 1
    proper: int = 1


def calculate_ranking(item, ranking: BaseRankingModel) -> int:
    """Calculate the ranking of a given ParsedMediaItem"""
    rank = 0
    rank += calculate_resolution_rank(item, ranking)
    rank += calculate_quality_rank(item, ranking)
    rank += calculate_audio_rank(item, ranking)
    rank += calculate_other_ranks(item, ranking)
    return rank

def calculate_resolution_rank(item, ranking: BaseRankingModel) -> int:
    for resolution in item.resolution:
        if resolution in ("2160p", "4K", "UHD"):
            return ranking.uhd
        if resolution == "1080p":
            return ranking.fhd
        if resolution == "720p":
            return ranking.hd
        if resolution == "480p":
            return ranking.sd
    return 0

def calculate_quality_rank(item, ranking: BaseRankingModel) -> int:
    quality_rank = {
        "Dolby Vision": ranking.dolby_video,
        "HDR10+": ranking.hdr10_plus,
        "HDR10": ranking.hdr10
    }
    for quality, rank in quality_rank.items():
        if quality in item.quality:
            return rank
    return 0

def calculate_audio_rank(item, ranking: BaseRankingModel) -> int:
    audio_rank = {
        "DTS:X": ranking.dts_x,
        "DTS-HD": ranking.dts_hd,
        "TrueHD Atmos": ranking.truehd_atmos,
        "TrueHD": ranking.truehd,
        "DD+ Atmos": ranking.ddp_atmos,
        "DD+": ranking.ddplus,
        "AC3": ranking.ac3
    }
    for audio, rank in audio_rank.items():
        if audio in item.audio:
            return rank
    return 0

def calculate_other_ranks(item, ranking: BaseRankingModel) -> int:
    other_ranks = {
        "WEBDL": ranking.webdl
    }
    rank = 0
    if item.repack:
        rank += ranking.repack
    if item.proper:
        rank += ranking.proper
    if item.remux:
        rank += ranking.remux
    if "WEBDL" in item.quality:
        rank += other_ranks["WEBDL"]
    return rank
