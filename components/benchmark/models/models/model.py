import uuid

class Model:

    def __init__(self,
                 name: str = None,
                 version: int = None,
                 sla: float = None,
                 alpha: float = 1,
                 profiled_rt: float = None,
                 tfs_model_url: str = None,
                 required_cpus: int = None,
                 required_gpus: int = None,
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
            self.required_cpus = required_cpus
            self.required_gpus = required_gpus

    def to_json(self):
        return {
            "name": self.name,
            "version": self.version,
            "required_cpus": self.required_cpus,
            "required_gpus": self.required_gpus,
            "sla": self.sla,
            "alpha": self.alpha,
            "profiled_rt": self.profiled_rt
        }
