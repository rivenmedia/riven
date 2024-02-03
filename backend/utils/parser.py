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
            if type(episode) == list:
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
            "extended": parse.get("extended", False)
        }

        # bandaid for now, this needs to be refactored to make less calls to _parse
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
        # item_language = self._get_item_language(item)
        return (
            parsed_data["resolution"] in self.resolution and
            # any(lang in parsed_data.get("language", item_language) for lang in self.language) and
            not parsed_data["is_unwanted_quality"]
        )

    def _is_highest_quality(self, parsed_data: dict) -> bool:
        """Check if content is `highest quality`."""
        return any(
            parsed.get("resolution") in ["UHD", "2160p", "4K"] or
            parsed.get("hdr", False) or
            parsed.get("remux", False) or
            parsed.get("upscaled", False)
            for parsed in parsed_data
        )

    def _is_dual_audio(self, string) -> bool:
        """Check if any content in parsed_data has dual audio."""
        dual_audio_patterns = [
            re.compile(r"\bmulti(?:ple)?[ .-]*(?:lang(?:uages?)?|audio|VF2)?\b", re.IGNORECASE),
            re.compile(r"\btri(?:ple)?[ .-]*(?:audio|dub\w*)\b", re.IGNORECASE),
            re.compile(r"\bdual[ .-]*(?:au?$|[aá]udio|line)\b", re.IGNORECASE),
            re.compile(r"\bdual\b(?![ .-]*sub)", re.IGNORECASE),
            re.compile(r"\b(?:audio|dub(?:bed)?)[ .-]*dual\b", re.IGNORECASE),
            re.compile(r"\bengl?(?:sub[A-Z]*)?\b", re.IGNORECASE),
            re.compile(r"\beng?sub[A-Z]*\b", re.IGNORECASE),
            re.compile(r"\b(?:DUBBED|dublado|dubbing|DUBS?)\b", re.IGNORECASE),
        ]
        return any(pattern.search(string) for pattern in dual_audio_patterns)

    @staticmethod
    def _is_complete_series(string) -> bool:
        """Check if string is a `complete series`."""
        # Can be used on either movie or show item types
        series_patterns = [
            re.compile(r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bbox[ .-]?set\b", re.IGNORECASE),
            re.compile(r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bmini[ .-]?series\b", re.IGNORECASE),
            re.compile(r"(?:\bthe\W)?(?:\bcomplete|full|all)\b.*\b(?:series|seasons|collection|episodes|set|pack|movies)\b", re.IGNORECASE),
            re.compile(r"\b(?:series|seasons|movies?)\b.*\b(?:complete|collection)\b", re.IGNORECASE),
            re.compile(r"(?:\bthe\W)?\bultimate\b[ .]\bcollection\b", re.IGNORECASE),
            re.compile(r"\bcollection\b.*\b(?:set|pack|movies)\b", re.IGNORECASE),
            re.compile(r"\bcollection\b", re.IGNORECASE),
            re.compile(r"duology|trilogy|quadr[oi]logy|tetralogy|pentalogy|hexalogy|heptalogy|anthology|saga", re.IGNORECASE)
        ]
        return any(pattern.search(string) for pattern in series_patterns)

    @staticmethod
    def _is_unwanted_quality(string) -> bool:
        """Check if string has an 'unwanted' quality. Default to False."""
        unwanted_patterns = [
            re.compile(r"\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b", re.IGNORECASE),
            re.compile(r"\b(?:H[DQ][ .-]*)?S[ .-]*print\b", re.IGNORECASE),
            re.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b", re.IGNORECASE),
            re.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b", re.IGNORECASE),
            re.compile(r"\bP(?:re)?DVD(?:Rip)?\b", re.IGNORECASE),
            re.compile(r"\b(?:DVD?|BD|BR)?[ .-]*Scr(?:eener)?\b", re.IGNORECASE),
            re.compile(r"\bVHS\b", re.IGNORECASE),
            re.compile(r"\bHD[ .-]*TV(?:Rip)?\b", re.IGNORECASE),
            re.compile(r"\bDVB[ .-]*(?:Rip)?\b", re.IGNORECASE),
            re.compile(r"\bSAT[ .-]*Rips?\b", re.IGNORECASE),
            re.compile(r"\bTVRips?\b", re.IGNORECASE),
            re.compile(r"\bR5\b", re.IGNORECASE),
            re.compile(r"\b(DivX|XviD)\b", re.IGNORECASE),
        ]
        return any(pattern.search(string) for pattern in unwanted_patterns)

    def check_for_title_match(self, item, parsed_title, threshold=90) -> bool:
        """Check if the title matches PTN title using fuzzy matching."""
        target_title = item.title
        if item.type == "season":
            target_title = item.parent.title
        elif item.type == "episode":
            target_title = item.parent.parent.title
        match_score = fuzz.ratio(parsed_title.lower(), target_title.lower())
        if match_score >= threshold:
            return True
        return False

    def _get_item_language(self, item) -> str:
        """Get the language of the item."""
        # This is crap. Need to switch to using a dict instead.
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


# def sort_streams(streams: dict, parser: Parser) -> dict:
#     """Sorts streams based on user preferences."""
#     def sorting_key(item):
#         _, stream = item
#         parsed_data = stream.get('parsed_data', {})

#         points = 0
#         if parser._is_dual_audio(parsed_data.get("string", "")):
#             points += 5
#         if parser._is_repack_or_proper(parsed_data):
#             points += 3
#         if parsed_data.get("is_4k", False) and (parser.settings.highest_quality or parser.settings.include_4k):
#             points += 7
#         if not parsed_data.get("is_unwanted", False):
#             points -= 10  # Unwanted content should be pushed to the bottom
#         return points
#     sorted_streams = sorted(streams.items(), key=sorting_key, reverse=True)
#     return dict(sorted_streams)


parser = Parser()