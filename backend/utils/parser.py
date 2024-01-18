import re
import PTN
from typing import List
from pydantic import BaseModel
from utils.settings import settings_manager
from thefuzz import fuzz


class ParserConfig(BaseModel):
    language: List[str]
    include_4k: bool
    highest_quality: bool
    repack_proper: bool


class Parser:
    
    def __init__(self):
        self.settings = ParserConfig(**settings_manager.get("parser"))
        self.language = self.settings.language or ["English"]
        self.resolution = ["1080p", "720p"]
        self.unwanted_codec = ["H.263", "Xvid"]  # Bad for transcoding
        self.quality = [None, "Blu-ray", "WEB-DL", "WEBRip", "HDRip", 
                        "HDTVRip", "BDRip", "Pay-Per-View Rip"]
        self.validate_settings()

    def validate_settings(self):
        if self.settings.highest_quality:
            self.resolution = ["UHD", "2160p", "4K", "1080p", "720p"]
        elif self.settings.include_4k:
            self.resolution = ["2160p", "4K", "1080p", "720p"]
        else:
            self.resolution = ["1080p", "720p"]

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

        title = parse.get("title")
        season = parse.get("season")
        audio = parse.get("audio")
        codec = parse.get("codec")
        resolution = parse.get("resolution")
        quality = parse.get("quality")
        subtitles = parse.get("subtitles")
        language = parse.get("language")
        hdr = parse.get("hdr")
        upscaled = parse.get("upscaled")
        remastered = parse.get("remastered")
        proper = parse.get("proper")
        repack = parse.get("repack")
        remux = parse.get("remux")
        if not language:
            language = "English"
        extended = parse.get("extended")

        return {
            "title": title,
            "resolution": resolution or [],
            "quality": quality or [],
            "season": season,
            "episodes": episodes or [],
            "codec": codec or [],
            "audio": audio or [],
            "hdr": hdr or False,
            "upscaled": upscaled or False,
            "remastered": remastered or False,
            "proper": proper or False,
            "repack": repack or False,
            "subtitles": True if subtitles == "Available" else False,
            "language": language or [],
            "remux": remux or False,
            "extended": extended,
        }

    def episodes(self, string) -> List[int]:
        parse = self._parse(string)
        return parse["episodes"]

    def episodes_in_season(self, season, string) -> List[int]:
        parse = self._parse(string)
        if parse["season"] == season:
            return parse["episodes"]
        return []

    def _is_4k(self, string) -> bool:
        """Check if content is `4k`."""
        if self.settings.include_4k:
            parsed = self._parse(string)
            return parsed.get("resolution", False) in ["2160p", "4K"]

    def _is_highest_quality(self, string) -> bool:
        """Check if content is `highest quality`."""
        if self.settings.highest_quality:
            parsed = self._parse(string)
            return any([
                parsed.get("hdr", False),
                parsed.get("remux", False),
                parsed.get("resolution", False) in ["UHD", "2160p", "4K"],
                parsed.get("upscaled", False)
            ])

    def _is_repack_or_proper(self, string) -> bool:
        """Check if content is `repack` or `proper`."""
        if self.settings.repack_proper:
            parsed = self._parse(string)
            return any([
                parsed.get("proper", False),
                parsed.get("repack", False),
            ])

    def _is_dual_audio(self, string) -> bool:
        """Check if content is `dual audio`."""
        parsed = self._parse(string)
        return parsed.get("audio") == "Dual" or \
                re.search(r"((dual.audio)|(english|eng)\W+(dub|audio))", string, flags=re.IGNORECASE) is not None

    def _is_network(self, string) -> bool:
        """Check if content is from a `network`."""
        parsed = self._parse(string)
        network = ["Apple TV+", "Amazon Studios", "Netflix", 
                "Nickelodeon", "YouTube Premium", "Disney Plus", 
                "DisneyNOW", "HBO Max", "HBO", "Hulu Networks", 
                "DC Universe", "Adult Swim", "Comedy Central", 
                "Peacock", "AMC", "PBS", "Crunchyroll", 
                "Syndication", "Hallmark", "BBC", "VICE",
                "MSNBC", "Crave"]  # Will probably be used later in `Versions`
        return (parsed.get("network", False)) in network

    def _is_unwanted_quality(string) -> bool:
        """Check if string has an `unwanted` quality."""
        patterns = [
            re.compile(r"(?:HD)?CAM(?:-?Rip)?", re.IGNORECASE),
            re.compile(r"(?:HD)?TS|TELESYNC|PDVD|PreDVDRip", re.IGNORECASE),
            re.compile(r"(?:HD)?TC|TELECINE", re.IGNORECASE),
            re.compile(r"WEB[ -]?Cap", re.IGNORECASE),
            re.compile(r"WP|WORKPRINT", re.IGNORECASE),
            re.compile(r"(?:DVD)?SCR(?:EENER)?|BDSCR", re.IGNORECASE),
            re.compile(r"DVD-?(?:Rip|Mux)", re.IGNORECASE),
            re.compile(r"DVDR|DVD-Full|Full-rip", re.IGNORECASE),
            re.compile(r"D?TVRip|DVBRip", re.IGNORECASE),
            re.compile(r"VODR(?:ip)?", re.IGNORECASE)
        ]
        return any(pattern.search(string) for pattern in patterns)

    def sort_streams(self, streams: dict) -> dict:
        """Sorts streams based on user preferences."""
        def sorting_key(item):
            _, stream = item
            title = stream['name']
            return (
                self._is_dual_audio(title),
                self._is_repack_or_proper(title),
                self._is_highest_quality(title),
                self._is_4k(title),
                self._is_network(title)
            )
        sorted_streams = sorted(streams.items(), key=sorting_key, reverse=True)
        return dict(sorted_streams)

    def parse(self, string) -> bool:
        """Parse the given string and return True if it matches the user settings."""
        parse = self._parse(string)
        return (
            parse["resolution"] in self.resolution
            and parse["language"] in self.language
            and not parse["quality"] in self.unwanted_quality
            and not self._is_unwanted_quality(string)
        )

    def get_title(self, string) -> str:
        """Get the `title` from the given string."""
        parse = self._parse(string)
        return parse["title"]

    def check_for_title_match(self, item, string, threshold=94) -> bool:
        """Check if the title matches PTN title using fuzzy matching."""
        # TODO1: remove special chars from parsed_title and target_title. Could improve matching.
        # TODO2: We should be checking aliases as well for titles. Anime only probably?
        parsed_title = self.get_title(string)
        if item.type == "movie":
            target_title = item.title
        elif item.type == "season":
            target_title = item.parent.title
        elif item.type == "episode":
            target_title = item.parent.parent.title
        else:
            return False
        return fuzz.ratio(parsed_title.lower(), target_title.lower()) >= threshold

parser = Parser()