import datetime
import math
import time
import requests
import logging
from models.model import Model
from models.container import Container
from models.device import Device
from models.controller import Controller


class ControllerManager:
    MAX_LOG_SIZE = 500

    b_c = 0.21
    d_c = 0.17

    def __init__(self,
                 models_endpoint: str,
                 containers_endpoint: str,
                 requests_endpoint: str,
                 actuator_port: int,
                 window_time: float,
                 min_c: float,
                 max_c: float):
        self.models_endpoint = models_endpoint
        self.containers_endpoint = containers_endpoint
        self.requests_endpoint = requests_endpoint
        self.actuator_port = actuator_port
        self.window_time = window_time

        # min and max core allocation
        self.min_c = min_c
        self.max_c = max_c

        self.models = {}
        self.nodes = ()
        self.containers = []
        self.containers_on_node = {}

        self.logs = []

        self.controllers = {}

    def init(self):
        # get the models
        self.models = {json_model["name"]: Model(json_data=json_model)
                       for json_model in self.get_data(self.models_endpoint)}

        # get the containers
        self.containers = [Container(json_data=json_container)
                           for json_container in self.get_data(self.containers_endpoint)]

        # group containers by nodes
        self.nodes = set(map(lambda c: c.node, self.containers))
        self.containers_on_node = {}
        for node in self.nodes:
            self.containers_on_node[node] = list(
                filter(lambda c: c.node == node, self.containers))

        log = {"type": "init", "models": [model.name for model in self.models.values()],
               "logs": {"containers": [{node: [c.to_json() for c in self.containers_on_node[node]]} for node in self.containers_on_node]},
               "ts": time.time(), "date": str(datetime.datetime.now())}
        self.logs.append(log)

        # init controllers
        self.controllers = []
        for container in list(filter(lambda c: c.device == Device.CPU and c.active, self.containers)):
            self.controllers.append(Controller(container))

    def mean(self, list):
        num_val = 0
        tot = 0
        for v in list:
            if v is not None:
                num_val += 1
                tot += v

        if tot == 0:
            return None
        else:
            return tot / num_val

    def float_round(self, num, places=0, direction=math.ceil):
        return direction(num * (10 ** places)) / float(10 ** places)

    def update(self):
        # update the models data
        self.models = {json_model["name"]: Model(json_data=json_model)
                       for json_model in self.get_data(self.models_endpoint)}
        gpu_containers = list(filter(lambda c: c.device == Device.GPU, self.containers))

        # get the metrics data since from_ts
        from_ts = time.time() - self.window_time
        metrics = self.get_data(self.requests_endpoint + '/metrics/container/model', {'from_ts': from_ts})

        log = {"type": "update",
               "len_metrics": len(metrics),
               "from_ts": str(datetime.datetime.fromtimestamp(from_ts)),
               "nodes": [node for node in self.nodes],
               "ts": time.time(),
               "date": str(datetime.datetime.now()),
               "logs": {}}

        for node in self.nodes:
            controller_for_node = list(filter(lambda c: c.container.node == node, self.controllers))
            log["logs"][node] = {}

            for controller in controller_for_node:
                log["logs"][node][controller.container.model] = {"metrics": {}, "control": {}}

                # compute the requests completed
                cpu_containers = list(filter(lambda c: c.device == Device.CPU and c.model == controller.container.model,
                                             self.containers_on_node[controller.container.node]))

                reqs_gpus = []
                reqs_cpus = []
                for gpu_container in gpu_containers:
                    reqs_gpus.append(metrics[gpu_container.container_id][controller.container.model])
                for cpu_container in cpu_containers:
                    # there should be only one container for CPU for a model
                    reqs_cpus.append(metrics[cpu_container.container_id][controller.container.model])

                reqs_created_gpus = sum(map(lambda m: m["created"], reqs_gpus))
                reqs_created_cpus = sum(map(lambda m: m["created"], reqs_cpus))
                reqs_completed_gpus = sum(map(lambda m: m["completed"], reqs_gpus))
                reqs_completed_cpus = sum(map(lambda m: m["completed"], reqs_cpus))
                reqs_rt_gpus = self.mean(map(lambda m: m["avg"], reqs_gpus))
                reqs_rt_cpus = self.mean(map(lambda m: m["avg"], reqs_cpus))

                # apply control given models and containers
                controller.v_sla = 1 / (self.models[controller.container.model].sla)

                # check if there are requests for the model
                if reqs_completed_cpus + reqs_created_cpus > 0:
                    if reqs_rt_gpus is not None:
                        controller.v_gpu = 1 / reqs_rt_gpus  # reqs_completed_gpus / self.window_time
                    else:
                        # GPUs did not complete reqs in the previous window: v_gpu = 0
                        controller.v_gpu = 0

                    if reqs_rt_cpus is not None:
                        controller.v_cpu = 1 / reqs_rt_cpus  # reqs_completed_cpus / self.window_time
                    else:
                        # CPUs did not complete reqs in the previous window: v_cpu = 0
                        controller.v_cpu = 0

                    # controller.v_o_cpu = max(0, controller.v_sla - controller.v_gpu)
                    # v_tot = (reqs_rt_gpus * reqs_completed_gpus + reqs_rt_cpus * reqs_completed_cpus) / (reqs_completed_gpus + reqs_completed_cpus)
                    controller.v_o_cpu = controller.v_sla
                    controller.gpu_overperforming = True if controller.v_o_cpu <= 0 else False
                    controller.e = float(controller.v_o_cpu - controller.v_cpu)
                    controller.xc = float(controller.xc_prec + self.b_c * controller.e)
                    if controller.v_o_cpu <= 0:
                        controller.nc = self.min_c
                    else:
                        controller.nc = max(self.min_c,
                                            min(self.max_c,
                                                self.float_round(controller.xc + self.d_c * controller.e, 1)))

                else:
                    controller.v_gpu = 0
                    controller.v_cpu = 0
                    controller.v_o_cpu = 0
                    controller.e = 0
                    controller.xc = float(controller.xc_prec + self.b_c * controller.e)
                    controller.nc = self.min_c
                    v_tot = None


                controller_metrics = {"cpu_containers": len(cpu_containers),
                                      "gpu_containers": len(gpu_containers),
                                      "model_sla":  self.models[controller.container.model].sla,
                                      "reqs_com_cpus": reqs_completed_cpus,
                                      "reqs_com_gpus": reqs_completed_gpus,
                                      "reqs_cre_cpus": reqs_created_cpus,
                                      "reqs_cre_gpus": reqs_created_gpus,
                                      "reqs_rt_cpus": reqs_rt_cpus if reqs_rt_cpus is not None else 0,
                                      "reqs_rt_gpus": reqs_rt_gpus if reqs_rt_gpus is not None else 0}
                log["logs"][node][controller.container.model]["metrics"] = controller_metrics

            tot_reqs_cores = sum(map(lambda c: c.nc, controller_for_node))
            log["logs"][node]["cores_before_norm"] = tot_reqs_cores
            log["logs"][node]["max_c"] = self.max_c

            if tot_reqs_cores > self.max_c:
                # norm
                for controller in controller_for_node:
                    controller.nc = self.float_round(
                        (controller.nc * self.max_c / tot_reqs_cores), 1)

            for controller in controller_for_node:
                controller.xc_prec = float(controller.nc - self.b_c * controller.e)

            # log controllers
            for controller in controller_for_node:
                control_model = {"nc": controller.nc,
                                 "v_sla": controller.v_sla,
                                 "v_cpu": controller.v_cpu,
                                 "v_gpu": controller.v_gpu,
                                 "v_o_cpu": controller.v_o_cpu,
                                 "e": controller.e,
                                 "xc": controller.xc}
                log["logs"][node][controller.container.model]["control"] = control_model


            tot_reqs_cores = sum(map(lambda c: c.nc, controller_for_node))
            log["logs"][node]["tot_req_core"] = tot_reqs_cores
            # actuate
            for controller in controller_for_node:
                # update container by node
                # post to actuator
                act_response = requests.post("http://" + node + ":" + str(self.actuator_port) + "/containers/" + controller.container.container_id,
                                             json={"cpu_quota": int(controller.nc * 100000)})
                # post con containers_manager
                cont_response = requests.patch(self.containers_endpoint,
                                               json={"container_id": controller.container.container_id,
                                                     "cpu_quota": int(controller.nc * 100000)})

                log["logs"][node][controller.container.model]["control"]["container_id"] = controller.container.container_id
                log["logs"][node][controller.container.model]["control"]["act_response"] = act_response.json()
                log["logs"][node][controller.container.model]["control"]["cont_response"] = cont_response.json()

        self.logs.append(log)

    def get_logs(self, from_ts=0.0):
        self.logs = list(filter(lambda l: l["ts"] > float(from_ts), self.logs))
        return self.logs

    def get_data(self, url, data=None):
        try:
            response = requests.get(url, params=data)
        except Exception as e:
            logging.warning(e)
            response = []
        if getattr(response, "json", None):
            return response.json()
        else:
            return {}

    def to_json(self):
        pass
