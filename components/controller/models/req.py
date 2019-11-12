import statistics as stat
import uuid
import time
from .device import Device
from enum import IntEnum


class ReqState(IntEnum):
    CREATED = 0
    WAITING = 1
    COMPLETED = 2
    ERROR = 3


class Req:

    def __init__(self,
                 model: str = None,
                 version: int = None,
                 instances: list = None,
                 json_data=None) -> None:
        if json_data:
            self.__dict__ = json_data
        else:
            self.id = uuid.uuid4()
            self.model = model
            self.version = version
            self.instances = instances
            self.ts_in = time.time()
            self.ts_out = None
            self.resp_time = None
            self.node = None
            self.container = None
            self.container_id = None
            self.device = None
            self.response = None
            self.state = ReqState.CREATED

    def set_completed(self, response):
        self.ts_out = time.time()
        self.resp_time = self.ts_out - self.ts_in
        self.response = response
        self.state = ReqState.COMPLETED

    def set_error(self, response):
        self.response = response
        self.state = ReqState.ERROR

    def to_json(self, verbose=False):
        req_json = {
            "id": str(self.id),
            "model": self.model,
            "version": self.version,
            "node": self.node,
            "container": self.container,
            "container_id": self.container_id,
            "device": self.device,
            "ts_in": self.ts_in,
            "ts_out": self.ts_out,
            "resp_time": self.resp_time,
            "state": self.state
        }

        if verbose:
            req_json["instances"] = self.instances
            req_json["response"] = self.response

        return req_json

    @staticmethod
    def metrics(reqs):
        completed = list(filter(lambda r: r.state == ReqState.COMPLETED, reqs))
        resp_times = list(map(lambda r: r.resp_time, completed))
        on_gpu = list(filter(lambda r: r.device == Device.GPU, completed))
        on_cpu = list(filter(lambda r: r.device == Device.CPU, completed))

        mean_t = min_t = max_t = dev_t = None
        if len(completed) > 0:
            mean_t = stat.mean(resp_times)
            min_t = min(resp_times)
            max_t = max(resp_times)

            if len(completed) > 1:
                dev_t = stat.variance(resp_times)

        return {
            "completed": len(completed),
            "created": len(reqs) - len(completed),
            "on_gpu": len(on_gpu),
            "on_cpu": len(on_cpu),
            "avg": mean_t,
            "dev": dev_t,
            "min": min_t,
            "max": max_t
        }
