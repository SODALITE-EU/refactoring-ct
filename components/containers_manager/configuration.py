class Configuration:
    def __init__(self,
                 init_quota=None,
                 actuator_port=None,
                 actuator_image=None,
                 workers=None,
                 available_gpus=None,
                 tfs_models_path=None,
                 k8s_service_type=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.init_quota = init_quota
            self.actuator_port = actuator_port
            self.actuator_image = actuator_image
            self.workers = workers
            self.available_gpus = available_gpus
            self.tfs_models_path = tfs_models_path
            self.k8s_service_type = k8s_service_type
            self.container_list_endpoint = "/containers"
