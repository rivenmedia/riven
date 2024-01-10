import re
import PTN
from typing import List
from pydantic import BaseModel
from utils.settings import settings_manager


class ParserConfig(BaseModel):
    language: List[str]
    include_4k: bool
    highest_quality: bool
    dual_audio: bool   # This sometimes doesnt work depending on if other audio is in the title
    av1_audio: bool

class Parser:
    
    def __init__(self):
        self.settings = ParserConfig(**settings_manager.get("parser"))
        self.language = self.settings.language
        self.resolution = ["1080p", "720p"]
        self.unwanted_codec = ["H.265 Main 10", "H.265", "H.263", "Xvid"]  # Bad for transcoding
        self.quality = [None, "Blu-ray", "WEB-DL", "WEBRip", "HDRip", 
                        "HDTVRip", "BDRip", "Pay-Per-View Rip"]
        self.unwanted_quality = ["Cam", "Telesync", "Telecine", "Screener", 
                                 "DVDSCR", "Workprint", "DVD-Rip", "TVRip", 
                                 "VODRip", "DVD-R", "DSRip", "BRRip"]
        self.audio = [None, "AAC", "AAC 2.0", "FLAC", "Custom"]
        self.network = ["Apple TV+", "Amazon Studios", "Netflix", 
                        "Nickelodeon", "YouTube Premium", "Disney Plus", 
                        "DisneyNOW", "HBO Max", "HBO", "Hulu Networks", 
                        "DC Universe", "Adult Swim", "Comedy Central", 
                        "Peacock", "AMC", "PBS", "Crunchyroll"]  # Will probably be used later in `Versions`
        self.validate_settings()

    def validate_settings(self):
        if self.settings.include_4k or self.settings.highest_quality:
            self.resolution += ["2160p", "4K"]
        if self.settings.highest_quality:
            self.resolution += ["UHD"]
            self.audio += ["Dolby TrueHD", "Dolby Atmos",
                          "Dolby Digital EX", "Dolby Digital Plus",
                          "Dolby Digital Plus 5.1", "Dolby Digital Plus 7.1"
                          "DTS-HD MA", "DTS-HD MA", "DTS-HD",
                          "DTS-EX", "DTS:X", "DTS", "5.1", "7.1"]
            self.unwanted_codec -= ["H.265 Main 10", "H.265"]
        if self.settings.dual_audio:
            self.audio += ["Dual"]
        if not self.settings.av1_audio:
            self.unwanted_codec += ["AV1"]  # Not all devices support this
        # if self.settings.low_resolution:
        #     self.resolution += ["480p", "360p"]  # This needs work. Should check item.year as well?

    def _parse(self, string):
        parse = PTN.parse(string)

        # episodes
        episodes = []
        if parse.get("episode", False):
            episode = parse.get("episode")
            if type(episode) == list:
                for sub_episode in episode:
                    episodes.append(int(sub_episode))
            else:
                episodes.append(int(episode))

        season = parse.get("season")
        audio = parse.get("audio")
        resolution = parse.get("resolution")
        quality = parse.get("quality")
        subtitles = parse.get("subtitles")
        language = parse.get("language")
        hdr = parse.get("hdr")
        remastered = parse.get("remastered")
        proper = parse.get("proper")
        repack = parse.get("repack")
        remux = parse.get("remux")
        if not language:
            language = "English"
        extended = parse.get("extended")

        return {
            "episodes": episodes or [],
            "resolution": resolution or [],
            "quality": quality or [],
            "audio": audio or None,
            "hdr": hdr or None,
            "remastered": remastered or None,
            "proper": proper or None,
            "repack": repack or None,
            "subtitles": subtitles or [],
            "language": language or [],
            "remux": remux or None,
            "extended": extended,
            "season": season,
        }

    def episodes(self, string):
        parse = self._parse(string)
        return parse["episodes"]

    def episodes_in_season(self, season, string):
        parse = self._parse(string)
        if parse["season"] == season:
            return parse["episodes"]
        return []

    def sort_dual_audio(self, string):
        """Check if content has dual audio."""
        # TODO: This could use improvement.. untested.
        parse = self._parse(string)
        if parse["audio"] == "Dual":
            return True
        elif re.search(r"((dual.audio)|(english|eng)\W+(dub|audio))", string, flags=re.IGNORECASE):
            return True
        else:
            return False

    def remove_unwanted(self, string):
        """Filter out unwanted content."""
        # TODO: This could use improvement.. untested.
        parse = self._parse(string)
        return not any([
            parse["quality"] in self.unwanted_quality,
            parse["codec"] in self.unwanted_codec
        ])

    def sort_and_filter_streams(self, streams: dict) -> dict:
        """Sorts and filters streams based on user preferences"""
        # TODO: Sort scraped data based on user preferences
        # instead of scraping one item at a time.
        filtered_sorted_streams = []
        for info_hash, filename in streams.items():
            title = filename.get("name", "")
            if self.remove_unwanted(title):
                filtered_sorted_streams.append((info_hash, filename, self.has_dual_audio(title)))
        filtered_sorted_streams.sort(key=lambda x: x[2], reverse=True)
        sorted_data = {info_hash: name for info_hash, name, _ in filtered_sorted_streams}
        return sorted_data

    def parse(self, string):
        parse = self._parse(string)
        return (
            parse["resolution"] in self.resolution
            and parse["language"] in self.language
            and not parse["quality"] in self.unwanted_quality
        )

parser = Parser()