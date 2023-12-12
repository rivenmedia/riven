from pydantic import BaseModel, validator
from typing import Optional
import re


class PTN(BaseModel):
    '''Parse media information from filename'''
    filename: str
    year: Optional[int] = None
    resolution: Optional[int] = None
    audio: Optional[str] = None
    hdr: Optional[str] = None
    codec: Optional[str] = None
    bit_depth: Optional[str] = None
    source: Optional[str] = None
    edition: Optional[str] = None

    @validator('year', pre=True, always=True)
    def extract_year(cls, _, values, **kwargs) -> Optional[int]:
        filename = values.get('filename', '')
        year_pattern = r'\b(19\d{2}|20[01]\d)\b'
        match = re.search(year_pattern, filename)
        if match:
            return match.group(1)
        return None

    @validator('resolution', pre=True, always=True)
    def extract_resolution(cls, _, values, **kwargs) -> Optional[int]:
        filename = values.get('filename', '')
        resolution_patterns = [
            (r'\b480p\b', 480),
            (r'\b720p\b', 720),
            (r'\b1080p\b', 1080),
            (r'\b4k|2160p\b', 2160),
        ]
        for pattern, res_pattern in resolution_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return res_pattern(match) if callable(res_pattern) else res_pattern
        return None

    @validator('audio', pre=True, always=True)
    def extract_audio(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        audio_patterns = [
            (r'7\.1[. ]?Atmos\b', '7.1 Atmos'),
            (r'\b(?:mp3|Atmos|DTS(?:-HD)?|TrueHD)\b', lambda m: m.group(0).upper()),
            (r'\bFLAC(?:\+?2\.0)?(?:x[2-4])?\b', 'FLAC'),
            (r'\bEAC-?3(?:[. -]?[256]\.[01])?\b', 'EAC3'),
            (r'\bAC-?3(?:[.-]5\.1|x2\.?0?)?\b', 'AC3'),
            (r'\b5\.1(?:x[2-4]+)?\+2\.0(?:x[2-4])?\b', '2.0'),
            (r'\b2\.0(?:x[2-4]|\+5\.1(?:x[2-4])?)\b', '2.0'),
            (r'\b5\.1ch\b', 'AC3'),
            (r'\bDD5[. ]?1\b', 'DD5.1'),
            (r'\bQ?AAC(?:[. ]?2[. ]0|x2)?\b', 'AAC'),
        ]
        for pattern, audio_format in audio_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return audio_format(match).upper() if callable(audio_format) else audio_format
        return None

    @validator('hdr', pre=True, always=True)
    def extract_hdr(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        hdr_patterns = [
            (r'\bDV\b|dolby.?vision|\bDoVi\b', 'DV'),
            (r'HDR10(?:\+|plus)', 'HDR10+'),
            (r'\bHDR(?:10)?\b', 'HDR'),
        ]
        for pattern, hdr_format in hdr_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return hdr_format
        return None

    @validator('codec', pre=True, always=True)
    def extract_codec(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        codec_patterns = [
            (r'\b[xh][-. ]?26[45]', lambda m: m.group(0).replace(" ", "").replace("-", "").replace(".", "").lower()),
            (r'\bhevc(?:\s?10)?\b', 'hevc'),
            (r'\b(?:dvix|mpeg2|divx|xvid|avc)\b', lambda m: m.group(0).lower()),
        ]
        for pattern, codec_format in codec_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return codec_format(match) if callable(codec_format) else codec_format.upper()
        return None

    @validator('bit_depth', pre=True, always=True)
    def extract_bit_depth(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        bit_depth_patterns = [
            (r'(?:8|10|12)[- ]?bit', lambda m: m.group(0).replace(" ", "").replace("-", "").lower()),
            (r'\bhevc\s?10\b', '10bit'),
            (r'\bhdr10\b', '10bit'),
            (r'\bhi10\b', '10bit'),
        ]
        for pattern, depth_format in bit_depth_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return depth_format(match) if callable(depth_format) else depth_format.upper()
        return None

    @validator('source', pre=True, always=True)
    def extract_source(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        source_patterns = [
            (r'\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b', 'CAM'),
            (r'\b(?:H[DQ][ .-]*)?S[ .-]*print', 'CAM'),
            (r'\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b', 'TeleSync'),
            (r'\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b', 'TeleCine'),
            (r'\bBlu[ .-]*Ray\b(?=.*remux)', 'BluRay REMUX'),
            (r'(?:BD|BR|UHD)[- ]?remux', 'BluRay REMUX'),
            (r'(remux.*)\bBlu[ .-]*Ray\b', 'BluRay REMUX'),
            (r'\bBlu[ .-]*Ray\b(?![ .-]*Rip)', 'BluRay'),
            (r'\bUHD[ .-]*Rip\b', 'UHDRip'),
            (r'\bHD[ .-]*Rip\b', 'HDRip'),
            (r'\bMicro[ .-]*HD\b', 'HDRip'),
            (r'\b(?:BR|Blu[ .-]*Ray)[ .-]*Rip\b', 'BRRip'),
            (r'\bBD[ .-]*Rip\b|\bBDR\b|\bBD-RM\b|[[(]BD[\]) .,-]', 'BDRip'),
            (r'\b(?:HD[ .-]*)?DVD[ .-]*Rip\b', 'DVDRip'),
            (r'\bVHS[ .-]*Rip\b', 'DVDRip'),
            (r'\bDVD(?:R\d?)?\b', 'DVD'),
            (r'\bVHS\b', 'DVD'),
            (r'\bHD[ .-]*TV(?:Rip)?\b', 'HDTV'),
            (r'\bDVB[ .-]*(?:Rip)?\b', 'HDTV'),
            (r'\bWEB[ .-]*DL(?:Rip)?\b', 'WEB-DL'),
            (r'\bWEB[ .-]*Rip\b', 'WEBRip'),
        ]
        for pattern, source_type in source_patterns:
            if source_type is None:  # If we just want to remove this from output
                if re.search(pattern, filename, re.IGNORECASE):
                    return None
            else:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    return source_type
        return None

    @validator('edition', pre=True, always=True)
    def extract_edition(cls, _, values, **kwargs) -> Optional[str]:
        filename = values.get('filename', '')
        edition_patterns = [
            (r'\bDiamond\b', 'Diamond Edition'),
            (r'\bRemaster(?:ed)?\b', 'Remastered Edition'),
            (r'\bUltimate.Edition\b', 'Ultimate Edition'),
            (r'\bExtended.Director\'?s\b', 'Director\'s Cut'),
            (r'\bDirector\'?s.Cut\b', 'Director\'s Cut'),
            (r'\bCollector\'?s\b', 'Collector\'s Edition'),
            (r'\bTheatrical\b', 'Theatrical'),
            (r'\b\d{2,3}(th)?.Anniversary.(Edition|Ed)?\b', 'Anniversary Edition'),
            (r'\bUncut\b', 'Uncut'),
            (r'\bIMAX\b', 'IMAX'),
            (r'\b3D\b', '3D'),
            (r'\bExtended\b', 'Extended Edition'),
        ]
        for pattern, edition_type in edition_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return edition_type
        return None

ptn = PTN