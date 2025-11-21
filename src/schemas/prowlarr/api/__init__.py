# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.prowlarr.api.api_info_api import ApiInfoApi
    from schemas.prowlarr.api.app_profile_api import AppProfileApi
    from schemas.prowlarr.api.application_api import ApplicationApi
    from schemas.prowlarr.api.authentication_api import AuthenticationApi
    from schemas.prowlarr.api.backup_api import BackupApi
    from schemas.prowlarr.api.command_api import CommandApi
    from schemas.prowlarr.api.custom_filter_api import CustomFilterApi
    from schemas.prowlarr.api.development_config_api import DevelopmentConfigApi
    from schemas.prowlarr.api.download_client_api import DownloadClientApi
    from schemas.prowlarr.api.download_client_config_api import DownloadClientConfigApi
    from schemas.prowlarr.api.file_system_api import FileSystemApi
    from schemas.prowlarr.api.health_api import HealthApi
    from schemas.prowlarr.api.history_api import HistoryApi
    from schemas.prowlarr.api.host_config_api import HostConfigApi
    from schemas.prowlarr.api.indexer_api import IndexerApi
    from schemas.prowlarr.api.indexer_default_categories_api import (
        IndexerDefaultCategoriesApi,
    )
    from schemas.prowlarr.api.indexer_proxy_api import IndexerProxyApi
    from schemas.prowlarr.api.indexer_stats_api import IndexerStatsApi
    from schemas.prowlarr.api.indexer_status_api import IndexerStatusApi
    from schemas.prowlarr.api.localization_api import LocalizationApi
    from schemas.prowlarr.api.log_api import LogApi
    from schemas.prowlarr.api.log_file_api import LogFileApi
    from schemas.prowlarr.api.newznab_api import NewznabApi
    from schemas.prowlarr.api.notification_api import NotificationApi
    from schemas.prowlarr.api.ping_api import PingApi
    from schemas.prowlarr.api.search_api import SearchApi
    from schemas.prowlarr.api.static_resource_api import StaticResourceApi
    from schemas.prowlarr.api.system_api import SystemApi
    from schemas.prowlarr.api.tag_api import TagApi
    from schemas.prowlarr.api.tag_details_api import TagDetailsApi
    from schemas.prowlarr.api.task_api import TaskApi
    from schemas.prowlarr.api.ui_config_api import UiConfigApi
    from schemas.prowlarr.api.update_api import UpdateApi
    from schemas.prowlarr.api.update_log_file_api import UpdateLogFileApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.prowlarr.api.api_info_api import ApiInfoApi
from schemas.prowlarr.api.app_profile_api import AppProfileApi
from schemas.prowlarr.api.application_api import ApplicationApi
from schemas.prowlarr.api.authentication_api import AuthenticationApi
from schemas.prowlarr.api.backup_api import BackupApi
from schemas.prowlarr.api.command_api import CommandApi
from schemas.prowlarr.api.custom_filter_api import CustomFilterApi
from schemas.prowlarr.api.development_config_api import DevelopmentConfigApi
from schemas.prowlarr.api.download_client_api import DownloadClientApi
from schemas.prowlarr.api.download_client_config_api import DownloadClientConfigApi
from schemas.prowlarr.api.file_system_api import FileSystemApi
from schemas.prowlarr.api.health_api import HealthApi
from schemas.prowlarr.api.history_api import HistoryApi
from schemas.prowlarr.api.host_config_api import HostConfigApi
from schemas.prowlarr.api.indexer_api import IndexerApi
from schemas.prowlarr.api.indexer_default_categories_api import IndexerDefaultCategoriesApi
from schemas.prowlarr.api.indexer_proxy_api import IndexerProxyApi
from schemas.prowlarr.api.indexer_stats_api import IndexerStatsApi
from schemas.prowlarr.api.indexer_status_api import IndexerStatusApi
from schemas.prowlarr.api.localization_api import LocalizationApi
from schemas.prowlarr.api.log_api import LogApi
from schemas.prowlarr.api.log_file_api import LogFileApi
from schemas.prowlarr.api.newznab_api import NewznabApi
from schemas.prowlarr.api.notification_api import NotificationApi
from schemas.prowlarr.api.ping_api import PingApi
from schemas.prowlarr.api.search_api import SearchApi
from schemas.prowlarr.api.static_resource_api import StaticResourceApi
from schemas.prowlarr.api.system_api import SystemApi
from schemas.prowlarr.api.tag_api import TagApi
from schemas.prowlarr.api.tag_details_api import TagDetailsApi
from schemas.prowlarr.api.task_api import TaskApi
from schemas.prowlarr.api.ui_config_api import UiConfigApi
from schemas.prowlarr.api.update_api import UpdateApi
from schemas.prowlarr.api.update_log_file_api import UpdateLogFileApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
