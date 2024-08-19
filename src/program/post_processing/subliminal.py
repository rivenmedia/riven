import os
import pathlib
from subliminal import region, Video, save_subtitles, ProviderPool
from babelfish import Language
from program.media.subtitle import Subtitle
from program.settings.manager import settings_manager
from utils import root_dir
from loguru import logger

class Subliminal:
    def __init__(self):
        self.key = "subliminal"
        self.settings = settings_manager.settings.post_processing.subliminal
        if not self.settings.enabled:
            self.initialized = False
            return
        providers = ['gestdown','opensubtitles','opensubtitlescom','podnapisi','tvsubtitles']
        provider_config = {}
        for provider in self.settings.providers.keys():
            if self.settings.providers[provider]["enabled"]:
                value = self.settings.providers[provider]
                provider_config[provider] = {"username": value["username"], "password": value["password"]}
                providers.append(provider)
        self.pool = ProviderPool(providers=providers,provider_configs=provider_config)
        for provider in self.pool.providers:
            try:
                self.pool[provider].initialize()
            except:
                logger.warning(f"Could not initialize provider: {provider}")
        if not region.is_configured:
            region.configure('dogpile.cache.dbm', arguments={'filename': f'{root_dir}/data/subliminal.dbm'})
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
                return video, self.pool.download_best_subtitles(self.pool.list_subtitles(video, self.languages), video, self.languages)
            except ValueError:
                logger.error(f"Could not parse video name: {real_name}")
        return {}

    def save_subtitles(self, video, subtitles, item):
        for subtitle in subtitles:
            original_name = video.name
            video.name = pathlib.Path(video.symlink_path)
            saved = save_subtitles(video, [subtitle])
            for subtitle in saved:
                logger.info(f"Downloaded ({subtitle.language}) subtitle for {pathlib.Path(item.symlink_path).stem}")
            video.name = original_name
            

    def run(self, item):
        video, subtitles = self.get_subtitles(item)
        for language in self.languages:
            key = str(language)
            item.subtitles.append(Subtitle({key: None}))
        self.save_subtitles(video, subtitles, item)
        self.update_item(item)
        
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
            if file.endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv')):
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
        if file.stem.startswith(filename) and file.suffix == '.srt':
                parts = file.name.split('.')
                if len(parts) > 2:
                    lang_code = parts[-2]
                    language = create_language_from_string(lang_code)
                    language.file = file.name
                    subtitle_languages.add(language)
    return subtitle_languages