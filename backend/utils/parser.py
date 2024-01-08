import PTN


class Parser:
    def __init__(self):
        self.resolution = ["1080p", "720p"]
        self.language = ["English"]

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

        resolution = parse.get("resolution")
        quality = parse.get("quality")
        language = parse.get("language")
        if not language:
            language = "English"
        extended = parse.get("extended")

        return {
            "episodes": episodes or [],
            "resolution": resolution or [],
            "quality": quality or [],
            "language": language or [],
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

    def parse(self, string):
        parse = self._parse(string)
        return (
            parse["resolution"] in self.resolution
            and parse["language"] in self.language
        )

parser = Parser()