class RequestsStoreConfiguration:
    def __init__(self,
                 containers_manager=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.containers_manager = containers_manager
            self.models_endpoint = self.containers_manager + "/models"
            self.containers_endpoint = self.containers_manager + "/containers"
