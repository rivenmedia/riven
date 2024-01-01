from copy import deepcopy
from utils.settings import settings_manager


class ServiceManager:
    def __init__(self, media_items=None, *services):
        self.media_items = media_items
        self.services = []
        self.services = self.initialize_services(services)
        self.settings = deepcopy(settings_manager.get_all())
        settings_manager.register_observer(self)

    def initialize_services(self, modules=None):
        services = []
        if self.services:
            for index, service in enumerate(self.services):
                if modules:
                    if service.key in modules:
                        self.services[index] = service.__class__(self.media_items)
        else:
            for service in modules:
                if self.media_items != None:
                    services.append(service(self.media_items))
                else:
                    services.append(service())
        return services

    def update_settings(self, new_settings):
        modules_to_update = []
        for module, values in self.settings.items():
            for new_module, new_values in new_settings.items():
                if module == new_module:
                    if values != new_values:
                        modules_to_update.append(module)
        self.initialize_services(modules_to_update)

    def notify(self):
        self.update_settings(settings_manager.settings)
