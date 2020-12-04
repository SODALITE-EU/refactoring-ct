class Configuration:
    def __init__(self,
                 containers_manager=None,
                 requests_store=None,
                 min_cores=None,
                 max_cores=None,
                 control_period=None,
                 control_type=None,
                 actuator_port=None,
                 dry_run=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.containers_manager = containers_manager
            self.requests_store = requests_store
            self.min_cores = min_cores
            self.max_cores = max_cores
            self.control_period = control_period
            self.control_type = control_type
            self.actuator_port = actuator_port
            self.dry_run = dry_run

            self.models_endpoint = self.containers_manager + "/models"
            self.containers_endpoint = self.containers_manager + "/containers"
            self.requests_endpoint = self.requests_store
