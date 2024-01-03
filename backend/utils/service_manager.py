from copy import deepcopy
from threading import Thread
from utils.settings import settings_manager


class ServiceManager:
    def __init__(self, media_items=None, *services):
        self.media_items = media_items
        self.services = []
        self.initialize_services(services)
        self.settings = deepcopy(settings_manager.get_all())
        settings_manager.register_observer(self)

    def initialize_services(self, modules=None):
        services = []
        if self.services:
            for index, service in enumerate(self.services):
                if modules and service.key in modules:
                    self.services[index] = service.__class__(self.media_items)
                    services.append(self.services[index])

        elif modules:
            for service in modules:
                new_service = service(self.media_items)
                self.services.append(new_service)
                services.append(new_service)

        # Start the services
        for service in services:
            if Thread in service.__class__.__bases__ and service.initialized and not service.running:
                service.start()

    def update_settings(self, new_settings):
        modules_to_update = []
        for module, values in self.settings.items():
            for new_module, new_values in new_settings.items():
                if module == new_module:
                    if values != new_values:
                        modules_to_update.append(module)
        self.settings = deepcopy(new_settings)
        self.initialize_services(modules_to_update)

    def notify(self):
        self.update_settings(settings_manager.settings)
