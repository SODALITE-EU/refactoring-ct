from models.queues_policies import QueuesPolicy


class Configuration:
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

