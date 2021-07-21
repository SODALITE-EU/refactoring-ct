from enum import IntEnum
from .device import Device
import statistics as stat
import time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()


class ReqState(IntEnum):
    CREATED = 0
    WAITING = 1
    COMPLETED = 2
    ERROR = 3


class Request(Base):
    __tablename__ = 'requests'

    id = Column(UUID, primary_key=True)
    model = Column(String)
    version = Column(Integer)
    ts_in = Column(Float)
    ts_wait = Column(Float)
    ts_out = Column(Float)
    process_time = Column(Float)
    resp_time = Column(Float)
    node = Column(String)
    container = Column(String)
    container_id = Column(String)
    device = Column(Integer)
    endpoint = Column(String)
    state = Column(Integer, default=int(ReqState.CREATED))

    def set_waiting(self):
        self.ts_wait = time.time()
        self.state = int(ReqState.WAITING)

    def set_completed(self, response):
        self.ts_out = time.time()
        self.resp_time = self.ts_out - self.ts_in
        self.process_time = self.ts_out - self.ts_wait
        # self.response = response
        self.state = int(ReqState.COMPLETED)

    def set_error(self, response):
        self.response = response
        self.state = int(ReqState.ERROR)

    def to_json(self):
        req_json = {
            "id": str(self.id),
            "model": self.model,
            "version": self.version,
            "node": self.node,
            "container": self.container,
            "container_id": self.container_id,
            "device": self.device,
            "endpoint": self.endpoint,
            "ts_in": self.ts_in,
            "ts_wait": self.ts_wait,
            "ts_out": self.ts_out,
            "process_time": self.process_time,
            "resp_time": self.resp_time,
            "state": self.state
        }
        return req_json

    @staticmethod
    def metrics(reqs, from_ts=0):
        created = completed = input_reqs = 0
        on_cpu = on_gpu = 0
        resp_times = process_time = []
        for r in reqs:
            if r.ts_out is None and r.ts_in >= float(from_ts):
                created += 1
            if r.ts_out is not None and r.ts_out >= float(from_ts):
                completed += 1
                resp_times.append(r.resp_time)
                process_time.append(r.process_time)
            if r.ts_wait is not None and r.ts_wait >= float(from_ts):
                input_reqs += 1
            if r.device == Device.GPU:
                on_gpu += 1
            elif r.device == Device.CPU:
                on_cpu += 1

        mean_resp_time = mean_process_time = min_t = max_t = dev_t = None
        if completed > 0:
            mean_resp_time = stat.mean(resp_times)
            mean_process_time = stat.mean(process_time)
            min_t = min(resp_times)
            max_t = max(resp_times)

            if completed > 1:
                dev_t = stat.variance(resp_times)

        return {
            "completed": completed,
            "created": created,
            "input_reqs": input_reqs,
            "on_gpu": on_gpu,
            "on_cpu": on_cpu,
            "avg": mean_resp_time,
            "avg_process": mean_process_time,
            "dev": dev_t,
            "min": min_t,
            "max": max_t
        }
