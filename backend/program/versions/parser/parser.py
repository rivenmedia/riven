from thefuzz import fuzz
from .models import ParsedMediaItem


class Parser:
    """Parser class for parsing media items."""
    
    def parse(self, query: str) -> ParsedMediaItem:
        """Parse the given string using the ParsedMediaItem model."""
        return ParsedMediaItem(raw_title=query)

    @staticmethod
    def check_title_match(item, raw_title: str, threshold: int = 90) -> bool:
        """Check if the title matches PTN title using fuzzy matching."""
        target_title = item.title
        if item.type == "season":
            target_title = item.parent.title
        elif item.type == "episode":
            target_title = item.parent.parent.title
        return fuzz.ratio(raw_title.lower(), target_title.lower()) >= threshold


parser = Parser()
