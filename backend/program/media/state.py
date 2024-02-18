from enum import Enum

class States(Enum):
    Unknown = "Unknown"
    Content = "Content"
    Scrape = "Scrape"
    Download = "Download"    
    Symlink = "Symlink"
    Library = "Library"    
    LibraryPartial = "LibraryPartial"
