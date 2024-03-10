from program.versions.parser import ParsedMediaItem

# Feel free to add more test cases!

def test_multi_audio_patterns():
    test_cases = [
        ("Lucy 2014 Dual-Audio WEBRip 1400Mb", True),
        ("Darkness Falls (2020) HDRip 720p [Hindi-Dub] Dual-Audio x264", True),
        ("The Simpsons - Season 1 Complete [DVDrip ITA ENG] TNT Village", False),
        ("Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE", False),
    ]
    for test_string, expected in test_cases:
        assert ParsedMediaItem.check_multi_audio(test_string) == expected

def test_multi_subtitle_patterns():
    test_cases = [
        ("IP Man And Four Kings 2019 HDRip 1080p x264 AAC Mandarin HC CHS-ENG SUBS Mp4Ba", True),
        ("The Simpsons - Season 1 Complete [DVDrip ITA ENG] TNT Village", True),
        ("The.X-Files.S01.Retail.DKsubs.720p.BluRay.x264-RAPiDCOWS", False),
        ("Hercules (2014) WEBDL DVDRip XviD-MAX", False),
    ]
    for test_string, expected in test_cases:
        assert ParsedMediaItem.check_multi_subtitle(test_string) == expected

def test_complete_series_patterns():
    test_cases = [
        ("The Sopranos - The Complete Series (Season 1, 2, 3, 4, 5 & 6) + Extras", True),
        ("The Inbetweeners Collection", True),
        ("The Simpsons S01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", False),
        ("Two and a Half Men S12E01 HDTV x264 REPACK-LOL [eztv]", False),
    ]
    for test_string, expected in test_cases:
        assert ParsedMediaItem.check_complete_series(test_string) == expected

def test_unwanted_quality_patterns():
    # False means the pattern is unwanted, and won't be fetched.
    test_cases = [
        ("Mission.Impossible.1996.Custom.Audio.1080p.PL-Spedboy", True),
        ("Casino.1995.MULTi.REMUX.2160p.UHD.Blu-ray.HDR.HEVC.DTS-X7.1-DENDA", True),
        ("Guardians of the Galaxy (CamRip / 2014)", False),
        ("Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE", False)
    ]
    for test_string, expected in test_cases:
        assert ParsedMediaItem.check_unwanted_quality(test_string) == expected
