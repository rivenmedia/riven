import re
import PTN
from typing import List
from pydantic import BaseModel
from program.settings.manager import settings_manager
from thefuzz import fuzz


class ParserConfig(BaseModel):
    language: List[str]
    include_4k: bool
    highest_quality: bool
    repack_proper: bool


class Parser:
    def __init__(self):
        self.settings = settings_manager.settings.parser
        self.language = self.settings.language
        self.resolution = self.determine_resolution()

    def determine_resolution(self):
        """Determine the resolution to use based on user settings."""
        if self.settings.highest_quality:
            return ["UHD", "2160p", "4K", "1080p", "720p"]
        if self.settings.include_4k:
            return ["2160p", "4K", "1080p", "720p"]
        return ["1080p", "720p"]

    def parse(self, item, string) -> dict:
        """Parse the given string and return True if it matches the user settings."""
        return self._parse(item, string)

    def _parse(self, item, string) -> dict:
        """Parse the given string and return the parsed data."""
        parse = PTN.parse(string)
        parsed_title = parse.get("title", "")

        # episodes
        episodes = []
        if parse.get("episode", False):
            episode = parse.get("episode")
            if isinstance(episode, list):
                for sub_episode in episode:
                    episodes.append(int(sub_episode))
            else:
                episodes.append(int(episode))

        if item is not None:
            title_match = self.check_for_title_match(item, parsed_title)
        is_4k = parse.get("resolution", False) in ["2160p", "4K", "UHD"]
        is_complete = self._is_complete_series(string)
        is_dual_audio = self._is_dual_audio(string)
        _is_unwanted_quality = self._is_unwanted_quality(string)

        parsed_data = {
            "string": string,
            "parsed_title": parsed_title,
            "fetch": False,
            "is_4k": is_4k,
            "is_dual_audio": is_dual_audio,
            "is_complete": is_complete,
            "is_unwanted_quality": _is_unwanted_quality,
            "year": parse.get("year", False),
            "resolution": parse.get("resolution", []),
            "quality": parse.get("quality", []),
            "season": parse.get("season", []),
            "episodes": episodes,
            "codec": parse.get("codec", []),
            "audio": parse.get("audio", []),
            "hdr": parse.get("hdr", False),
            "upscaled": parse.get("upscaled", False),
            "remastered": parse.get("remastered", False),
            "proper": parse.get("proper", False),
            "repack": parse.get("repack", False),
            "subtitles": parse.get("subtitles") == "Available",
            "language": parse.get("language", []),
            "remux": parse.get("remux", False),
            "extended": parse.get("extended", False),
        }

        if item is not None:
            parsed_data["title_match"] = title_match
        parsed_data["fetch"] = self._should_fetch(parsed_data)
        return parsed_data

    def episodes(self, string) -> List[int]:
        """Return a list of episodes in the given string."""
        parse = self._parse(None, string)
        return parse["episodes"]

    def episodes_in_season(self, season, string) -> List[int]:
        """Return a list of episodes in the given season."""
        parse = self._parse(None, string)
        if parse["season"] == season:
            return parse["episodes"]
        return []

    def _should_fetch(self, parsed_data: dict) -> bool:
        """Determine if the parsed content should be fetched."""
        # This is where we determine if the item should be fetched
        # based on the user settings and predefined rules.
        # Edit with caution. All have to match for the item to be fetched.
        return (
            parsed_data["resolution"] in self.resolution
            and not parsed_data["is_unwanted_quality"]
        )

    def _is_highest_quality(self, parsed_data: dict) -> bool:
        """Check if content is `highest quality`."""
        return any(
            parsed.get("resolution") in ["UHD", "2160p", "4K"]
            or parsed.get("hdr", False)
            or parsed.get("remux", False)
            or parsed.get("upscaled", False)
            for parsed in parsed_data
        )

    def _is_dual_audio(self, string) -> bool:
        """Check if any content in parsed_data has dual audio."""
        dual_audio_patterns = [
            r"\bmulti(?:ple)?[ .-]*(?:lang(?:uages?)?|audio|VF2)?\b",
            r"\btri(?:ple)?[ .-]*(?:audio|dub\w*)\b",
            r"\bdual[ .-]*(?:au?$|[aá]udio|line)\b",
            r"\bdual\b(?![ .-]*sub)",
            r"\b(?:audio|dub(?:bed)?)[ .-]*dual\b",
            r"\bengl?(?:sub[A-Z]*)?\b",
            r"\beng?sub[A-Z]*\b",
            r"\b(?:DUBBED|dublado|dubbing|DUBS?)\b",
        ]
        dual_audio_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in dual_audio_patterns]
        return any(pattern.search(string) for pattern in dual_audio_patterns)

    @staticmethod
    def _is_complete_series(string) -> bool:
        """Check if string is a `complete series`."""
        # Can be used on either movie or show item types
        series_patterns = [
            r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bbox[ .-]?set\b",
            r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bmini[ .-]?series\b",
            r"(?:\bthe\W)?(?:\bcomplete|full|all)\b.*\b(?:series|seasons|collection|episodes|set|pack|movies)\b",
            r"\b(?:series|seasons|movies?)\b.*\b(?:complete|collection)\b",
            r"(?:\bthe\W)?\bultimate\b[ .]\bcollection\b",
            r"\bcollection\b.*\b(?:set|pack|movies)\b",
            r"\bcollection\b",
            r"duology|trilogy|quadr[oi]logy|tetralogy|pentalogy|hexalogy|heptalogy|anthology|saga",
        ]
        series_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in series_patterns]
        return any(pattern.search(string) for pattern in series_patterns)

    @staticmethod
    def _is_unwanted_quality(string) -> bool:
        """Check if string has an 'unwanted' quality. Default to False."""
        unwanted_quality = [
            r"\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b",
            r"\b(?:H[DQ][ .-]*)?S[ .-]*print\b",
            r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b",
            r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b",
            r"\bP(?:re)?DVD(?:Rip)?\b",
            r"\b(?:DVD?|BD|BR)?[ .-]*Scr(?:eener)?\b",
            r"\bVHS\b",
            r"\bHD[ .-]*TV(?:Rip)?\b",
            r"\bDVB[ .-]*(?:Rip)?\b",
            r"\bSAT[ .-]*Rips?\b",
            r"\bTVRips?\b",
            r"\bR5|R6\b",
            r"\b(DivX|XviD)\b",
            r"\b(?:Deleted[ .-]*)?Scene(?:s)?\b",
            r"\bTrailers?\b",
        ]
        unwanted_quality = [re.compile(pattern, re.IGNORECASE) for pattern in unwanted_quality]
        return any(pattern.search(string) for pattern in unwanted_quality)

    def check_for_title_match(self, item, parsed_title, threshold=90) -> bool:
        """Check if the title matches PTN title using fuzzy matching."""
        target_title = item.title
        if item.type == "season":
            target_title = item.parent.title
        elif item.type == "episode":
            target_title = item.parent.parent.title
        return bool(fuzz.ratio(parsed_title.lower(), target_title.lower()) >= threshold)

    def _get_item_language(self, item) -> str:
        """Get the language of the item."""
        # TODO: This is crap. Need to switch to ranked sorting instead.
        if item.type == "season":
            if item.parent.language == "en":
                if item.parent.is_anime:
                    return ["English", "Japanese"]
            return ["English"]
        elif item.type == "episode":
            if item.parent.parent.language == "en":
                if item.parent.parent.is_anime:
                    return ["English", "Japanese"]
            return ["English"]
        if item.language == "en":
            if item.is_anime:
                return ["English", "Japanese"]
            return ["English"]
        if item.is_anime:
            return ["English", "Japanese"]
        return ["English"]


parser = Parser()
