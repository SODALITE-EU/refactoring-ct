import uuid

class Model:

    def __init__(self,
                 name: str = None,
                 version: int = None,
                 sla: float = None,
                 alpha: float = 1,
                 profiled_rt: float = None,
                 tfs_model_url: str = None,
                 initial_replicas: int = None,
                 json_data=None):
        if json_data:
            self.__dict__ = json_data
        else:
            self.name = name
            self.version = version
            self.sla = sla
            self.alpha = alpha
            self.profiled_rt = profiled_rt
            self.tfs_model_url = tfs_model_url
            self.initial_replicas = initial_replicas

    def to_json(self):
        return {
            "name": self.name,
            "version": self.version,
            "sla": self.sla,
            "alpha": self.alpha,
            "profiled_rt": self.profiled_rt
        }
