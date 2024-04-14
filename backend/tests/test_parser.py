import pytest
from RTN import RTN, Torrent, parse
from RTN.exceptions import GarbageTorrent
from RTN.models import CustomRank, DefaultRanking, SettingsModel


@pytest.fixture
def settings_model():
    return SettingsModel()

@pytest.fixture
def ranking_model():
    return DefaultRanking()

@pytest.fixture
def rtn(settings_model, ranking_model):
    return RTN(settings_model, ranking_model)

@pytest.fixture
def multiple_test_strings():
    return [
    "Another [BDRip 1920x1080 x264 FLAC] [Exp]",
    "A.Place.Further.Than.the.Universe.S01.1080p.BluRay.10-Bit.FLAC2.0.x265-YURASUKA",
    "Arifureta - From Commonplace to World's Strongest S02 [BDRip 1080p x264 AAC-FLAC] [Dual-Audio]",
    "[Believe] Naruto Shippuuden the Movie 1 (BD 1080p x264 10-bit FLAC) [AFF09B88].mkv",
    "[Believe] Naruto Shippuuden the Movie 2 - Bonds (BD 1080p x264 10-bit FLAC) [AC44FC01].mkv",
    "Black.Lagoon.S01E01.1080p.BluRay.FLAC.DTS-HD.x264-LegionV3.mkv",
    "Charlotte.S01.1080p.Blu-Ray.10-Bit.Dual-Audio.FLAC.x265-iAHD",
    "Classroom.of.the.Elite.S01.1080p.BluRay.10-Bit.Dual-Audio.FLAC5.1.x265-YURASUKA",
    "Classroom.of.the.Elite.S02.1080p.BluRay.10-Bit.Dual-Audio.FLAC5.1.x265-YURASUKA",
    "Claymore.S01.720p-Hi10p.BluRay.FLAC5.1.x264-CTR-Kametsu",
    "Dororo (2019) [BD 1080p HEVC FLAC] [Dual-Audio] [OZR]",
    "Dr. Stone S02 1080p Dual Audio BD Remux FLAC-TTGA",
    "[ElFamosoBD] Kakegurui S01 & S02 - VOSTFR (BD x264 1080p FLAC)",
    "FLCL.S01.Bluray.1080p-Hi10p.x264.FLAC2.0.Dual.[SRLS].mkv",
    "Goblin.Slayer.Goblins.Crown.2020.1080p.ITA.BluRay.REMUX.AVC.FLAC.2.0-Meakes.mkv",
    "Kaguya-sama.Love.Is.War.S03.BluRay.Remux.FLAC2.0.H.264-LYS1TH3A",
    "Kill.la.Kill.S01.1080p.BluRay.Remux.AVC.FLAC.2.0-ZeroBuild",
    "Kill.la.Kill.S01.1080p-Hi10p.BluRay.FLAC2.0.x264-CTR",
    "[Legion]Black.Lagoon.S01+02.1080p-.Bluray.FLAC.DTS-HD.x264(Dual Audio)V3",
    "Money Heist (2017) Season 01 S01 (1080p BluRay x265 HEVC 10bit FLAC 2.0 Qman) [UTR]",
    "My Dress-Up Darling S01 1080p Dual Audio BD Remux FLAC-TTGA",
    "My.Hero.Academia.S02.1080p-Hi10p.BluRay.FLAC5.1.x264-ITH",
    "My.Neighbor.Totoro.1988.PROPER.BluRay.1080p.FLAC.2.0.AVC.REMUX-FraMeSToR.mkv",
    "No.Game.No.Life.S01.1080p-Hi10p.BluRay.FLAC2.0.x264-CTR",
    "Overlord.S01.1080p.BluRay.10-Bit.Dual-Audio.FLAC5.1.x265-YURASUKA",
    "[RUDY] Mushoku Tensei S02 [BD Remux Dual Audio 1080p AVC FLAC AAC]",
    "[ShadyCrab] The Devil Is a Part Timer! [BD 1080p Hi10 FLAC][Dual-Audio]",
    "The Devil is a Part-Timer! S01 [BD 1080p HEVC 10bit FLAC] [Dual-Audio]",
    "The Rising of the Shield Hero - S02 [BD 1080p HEVC 10bit AAC-FLAC] [Dual-Audio]",
    "[The_Wyandotte] Fairy Tail (2009) 1-175 (h.265 BD 1080p Dual-Audio FLAC)",
    "[The_Wyandotte] Fairy Tail (2014) (h.264 BD 1080p Dual-Audio FLAC)",
    "Tokyo.Ghoul.S02.Hybrid.BluRay.Remux.1080p.AVC.FLAC.2.0-RiMJOB",
    "Tokyo.Ghoul.S03.Hybrid.BluRay.Remux.1080p.AVC.FLAC.2.0-RiMJOB",
    "Tsukimichi S01 1080p Dual Audio BD Remux FLAC-TTGA",
    "[UDF] Sword Art Online S1 & S2 (BDRip 1080p x264 FLACx2) [dual-audio]",
    "[Vodes] Tensei Shitara Slime Datta Ken [BD 1080p HEVC 10bit FLAC] [Dual-Audio]"
]

def test_rtn(rtn):
    assert isinstance(rtn, RTN)
