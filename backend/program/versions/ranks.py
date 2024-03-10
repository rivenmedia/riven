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
    ddplus_atmos: int = 0
    ddplus: int = 0
    dts: int = 0
    ac3: int = 0
    remux: int = 0
    webdl: int = 0
    Other_video: int = 0
    Other_audio: int = 0
    repack: int = 0
    proper: int = 0


class DefaultRanking(BaseRankingModel):
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
    dd_atmos: int = 100
    ddplus: int = 90
    dts: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    Other_video: int = -100
    Other_audio: int = -100
    repack: int = 4
    proper: int = 5


class BestRemuxRanking(BaseRankingModel):
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
    dd_atmos: int = 100
    ddplus: int = 90
    dts: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    Other_video: int = -100
    Other_audio: int = -100
    repack: int = 4
    proper: int = 5


class BestWebRanking(BaseRankingModel):
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
    dd_atmos: int = 100
    ddplus: int = 90
    dts: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    Other_video: int = -100
    Other_audio: int = -100
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
    dd_atmos: int = 100
    ddplus: int = 90
    dts: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    Other_video: int = -100
    Other_audio: int = -100
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
    dd_atmos: int = 100
    ddplus: int = 90
    dts: int = 40
    ac3: int = 30
    remux: int = 150
    webdl: int = -1000
    Other_video: int = -100
    Other_audio: int = -100
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
    dd_atmos: int = 1
    ddplus: int = 1
    dts: int = 1
    ac3: int = 1
    remux: int = 1
    webdl: int = 1
    Other_video: int = 0
    Other_audio: int = 0
    repack: int = 1
    proper: int = 1