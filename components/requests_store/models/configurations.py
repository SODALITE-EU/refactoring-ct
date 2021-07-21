from models.queues_policies import QueuesPolicy


class OrchestratorConfiguration:
    def __init__(self,
                 containers_manager=None,
                 requests_store=None,
                 controller=None,
                 dispatcher=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.containers_manager = containers_manager
            self.requests_store = requests_store
            self.controller = controller
            self.dispatcher = dispatcher
        self.config_endpoint = "/configuration"
        self.start_endpoint = "/start"

    def get(self, key):
        return self.__dict__[key]


class K8sConfiguration:
    def __init__(self,
                 models=None,
                 available_cpus=None,
                 available_gpus=None,
                 actuator_image=None,
                 actuator_port=None,
                 k8s_api_configuration=None,
                 k8s_service_type=None,
                 k8s_image_pull_policy=None,
                 k8s_host_network=None,
                 randomize_model_names=None,
                 tfs_image=None,
                 tfs_init_image=None,
                 tfs_config_endpoint=None,
                 tfs_models_url=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.models = models
            self.available_cpus = available_cpus
            self.available_gpus = available_gpus
            self.actuator_image = actuator_image
            self.actuator_port = actuator_port
            self.k8s_api_configuration = k8s_api_configuration
            self.k8s_service_type = k8s_service_type
            self.k8s_image_pull_policy = k8s_image_pull_policy
            self.k8s_host_network = k8s_host_network
            self.randomize_model_names = randomize_model_names
            self.tfs_image = tfs_image
            self.tfs_models_path = "/home/models/"
            self.tfs_config_file_name = self.tfs_models_path + "tf_serving_models.config"
            self.tfs_init_image = tfs_init_image
            self.tfs_config_endpoint = tfs_config_endpoint
            self.tfs_models_url = tfs_models_url


class ContainersManagerConfiguration:
    def __init__(self,
                 models=None,
                 containers=None,
                 actuator_port=None,
                 init_quota=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.models = models
            self.containers = containers
            self.actuator_port = actuator_port
            self.init_quota = init_quota
        self.container_list_endpoint = "/containers"


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


class ControllerConfiguration:
    def __init__(self,
                 containers_manager=None,
                 requests_store=None,
                 actuator_port=None,
                 min_cores=None,
                 max_cores=None,
                 control_period=None,
                 window_time=None,
                 control_type=None,
                 dry_run=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.containers_manager = containers_manager
            self.requests_store = requests_store
            self.actuator_port = actuator_port
            self.min_cores = min_cores
            self.max_cores = max_cores
            self.control_period = control_period
            self.window_time = window_time
            self.control_type = control_type
            self.dry_run = dry_run

        self.models_endpoint = self.containers_manager + "/models"
        self.containers_endpoint = self.containers_manager + "/containers"
        self.requests_endpoint = self.requests_store + "/requests"


class DispatcherConfiguration:
    def __init__(self,
                 containers_manager=None,
                 requests_store=None,
                 verbose=None,
                 gpu_queues_policy=None,
                 max_log_consumers=None,
                 max_polling_threads=None,
                 max_consumers_cpu=None,
                 max_consumers_gpu=None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.containers_manager = containers_manager
            self.requests_store = requests_store
            self.verbose = verbose
            self.gpu_queues_policy = gpu_queues_policy
            self.cpu_queues_policy = QueuesPolicy.ROUND_ROBIN
            self.max_log_consumers = max_log_consumers
            self.max_polling_threads = max_polling_threads
            self.max_consumers_cpu = max_consumers_cpu
            self.max_consumers_gpu = max_consumers_gpu

        self.models_endpoint = self.containers_manager + "/models"
        self.containers_endpoint = self.containers_manager + "/containers"
        self.requests_store_endpoint = self.requests_store + "/requests"

