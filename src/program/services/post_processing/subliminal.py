import os
import pathlib

from babelfish import Language
from loguru import logger
from subliminal import ProviderPool, Video, region, save_subtitles
from subliminal.exceptions import AuthenticationError

from program.media.subtitle import Subtitle
from program.settings.manager import settings_manager
from program.utils import root_dir


class Subliminal:
    def __init__(self):
        self.key = "subliminal"
        self.settings = settings_manager.settings.post_processing.subliminal
        if not self.settings.enabled:
            self.initialized = False
            return
        if not region.is_configured:
            region.configure("dogpile.cache.dbm", arguments={"filename": f"{root_dir}/data/subliminal.dbm"})
        providers = ["gestdown","opensubtitles","opensubtitlescom","podnapisi","tvsubtitles"]
        provider_config = {}
        for provider, value in self.settings.providers.items():
            if value["enabled"]:
                provider_config[provider] = {"username": value["username"], "password": value["password"]}
        self.pool = ProviderPool(providers=providers,provider_configs=provider_config)
        for provider in providers:
            try:
                self.pool[provider].initialize()
                if self.pool.provider_configs.get(provider, False):
                    if provider == "opensubtitlescom":
                        self.pool[provider].login()
                        if not self.pool[provider].check_token():
                            raise AuthenticationError
            except Exception:
                logger.warning(f"Could not initialize provider: {provider}.")
                if provider == "opensubtitlescom":
                    self.pool.initialized_providers.pop(provider)
                    self.pool.provider_configs.pop(provider)
                    self.pool[provider].initialize()
                    logger.warning("Using default opensubtitles.com provider.")
        self.languages = set(create_language_from_string(lang) for lang in self.settings.languages)
        self.initialized = self.enabled

    @property
    def enabled(self):
        return self.settings.enabled

    def scan_files_and_download(self):
        # Do we want this?
        pass
        # videos = _scan_videos(settings_manager.settings.symlink.library_path)
        # subtitles = download_best_subtitles(videos, {Language("eng")})
        # for video, subtitle in subtitles.items():
        #     original_name = video.name
        #     video.name = pathlib.Path(video.symlink)
        #     saved = save_subtitles(video, subtitle)
        #     video.name = original_name
        #     for subtitle in saved:
        #         logger.info(f"Downloaded ({subtitle.language}) subtitle for {pathlib.Path(video.symlink).stem}")

    def get_subtitles(self, item):
        if item.type in ["movie", "episode"]:
            real_name = pathlib.Path(item.symlink_path).resolve().name
            try:
                video = Video.fromname(real_name)
                video.symlink_path = item.symlink_path
                video.subtitle_languages = get_existing_subtitles(pathlib.Path(item.symlink_path).stem, pathlib.Path(item.symlink_path).parent)
                # Get all subtitles for all languages
                all_subtitles = self.pool.list_subtitles(video, self.languages)
                subtitles_to_download = []
                count_per_language = getattr(self.settings, 'count_per_language', 1)
                for language in self.languages:
                    # Filter and sort by score for each language
                    lang_subs = [s for s in all_subtitles if s.language == language]
                    # Compute score for each subtitle
                    scored = [(s, s.get_matches(video)) for s in lang_subs]
                    # Sort by number of matches (descending)
                    scored.sort(key=lambda x: len(x[1]), reverse=True)
                    # Take top N
                    top_subs = [s for s, _ in scored[:count_per_language]]
                    subtitles_to_download.extend(top_subs)
                # Download all selected subtitles
                self.pool.download_subtitles(subtitles_to_download)
                return video, subtitles_to_download
            except ValueError:
                logger.error(f"Could not parse video name: {real_name}")
        return {}, []

    def save_subtitles(self, video, subtitles, item):
        # Save all subtitles, appending an index if more than one per language
        lang_count = {}
        for subtitle in subtitles:
            original_name = video.name
            video.name = pathlib.Path(video.symlink_path)
            lang = str(subtitle.language)
            lang_count.setdefault(lang, 0)
            lang_count[lang] += 1
            # If more than one per language, append index
            if lang_count[lang] > 1:
                # Save with .lang.N.srt
                filename = f"{video.name.stem}.{lang}.{lang_count[lang]}.srt"
                save_subtitles(video, [subtitle], directory=video.name.parent, single=False, encoding=None, filename=filename)
                logger.info(f"Downloaded ({subtitle.language}) subtitle #{lang_count[lang]} for {pathlib.Path(item.symlink_path).stem}")
            else:
                saved = save_subtitles(video, [subtitle])
                for subtitle in saved:
                    logger.info(f"Downloaded ({subtitle.language}) subtitle for {pathlib.Path(item.symlink_path).stem}")
            video.name = original_name


    def run(self, item):
        for language in self.languages:
            key = str(language)
            item.subtitles.append(Subtitle({key: None}))
        try:
            video, subtitles = self.get_subtitles(item)
            self.save_subtitles(video, subtitles, item)
            self.update_item(item)
        except Exception as e:
            logger.error(f"Failed to download subtitles for {item.log_string}: {e}")


    def update_item(self, item):
        folder = pathlib.Path(item.symlink_path).parent
        subs = get_existing_subtitles(pathlib.Path(item.symlink_path).stem, folder)
        for lang in subs:
            key = str(lang)
            for subtitle in item.subtitles:
                if subtitle.language == key:
                    subtitle.file = (folder / lang.file).__str__()
                    break

    def should_submit(item):
        return item.type in ["movie", "episode"] and not any(subtitle.file is not None for subtitle in item.subtitles)

def _scan_videos(directory):
    """
    Scan the given directory recursively for video files.

    :param directory: Path to the directory to scan
    :return: List of Video objects
    """
    videos = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith((".mp4", ".mkv", ".avi", ".mov", ".wmv")):
                video_path = os.path.join(root, file)
                video_name = pathlib.Path(video_path).resolve().name
                video = Video.fromname(video_name)
                video.symlink = pathlib.Path(video_path)

                # Scan for subtitle files
                video.subtitle_languages = get_existing_subtitles(video.symlink.stem, pathlib.Path(root))
                videos.append(video)
    return videos

def create_language_from_string(lang: str) -> Language:
    try:
        if len(lang) == 2:
            return Language.fromcode(lang, "alpha2")
        if len(lang) == 3:
            return Language.fromcode(lang, "alpha3b")
    except ValueError:
        logger.error(f"Invalid language code: {lang}")
        return None

def get_existing_subtitles(filename: str, path: pathlib.Path) -> set[Language]:
    subtitle_languages = set()
    for file in path.iterdir():
        if file.stem.startswith(filename) and file.suffix == ".srt":
                parts = file.name.split(".")
                if len(parts) > 2:
                    lang_code = parts[-2]
                    language = create_language_from_string(lang_code)
                    language.file = file.name
                    subtitle_languages.add(language)
    return subtitle_languages