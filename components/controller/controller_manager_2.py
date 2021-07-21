import datetime
import math
import time
import requests
import logging
import statistics as stats
from models.model import Model
from models.container import Container
from models.device import Device
from models.controller import Controller


class ControllerManager2:
    MAX_LOG_SIZE = 500

    Kql = -0.03 #-20 * pow(0.12, 2) / 30 * 5
    Tiql = 8

    def __init__(self,
                 models_endpoint: str,
                 containers_endpoint: str,
                 requests_endpoint: str,
                 actuator_port: int,
                 control_period: float,
                 min_c: float,
                 max_c: float):
        self.models_endpoint = models_endpoint
        self.containers_endpoint = containers_endpoint
        self.requests_endpoint = requests_endpoint
        self.actuator_port = actuator_port
        self.control_period = control_period
        self.window_time = control_period

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
        # update the models data (SLA may be updated)
        self.models = {json_model["name"]: Model(json_data=json_model)
                       for json_model in self.get_data(self.models_endpoint)}

        # get the metrics data since from_ts
        from_ts = time.time() - self.window_time
        metrics_from_ts = self.get_data(self.requests_endpoint + '/metrics/container/model', {'from_ts': from_ts})
        metrics = self.get_data(self.requests_endpoint + '/metrics/container/model/created')

        log = {"type": "update",
               "len_metrics_from_ts": len(metrics_from_ts),
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

                # there should be only one container for CPU for a model
                cpu_container = list(filter(lambda c: c.device == Device.CPU and c.model == controller.container.model,
                                            self.containers_on_node[controller.container.node]))[0]

                # metrics
                reqs_created_cpus = metrics_from_ts[cpu_container.container_id][controller.container.model]["created"]
                reqs_completed_cpus = metrics_from_ts[cpu_container.container_id][controller.container.model]["completed"]
                input_reqs = metrics_from_ts[cpu_container.container_id][controller.container.model]["input_reqs"]
                queue_len = metrics[cpu_container.container_id][controller.container.model]["created"]

                resp_time_sla = self.models[controller.container.model].sla
                Ts = self.control_period

                sp_queue_length = eqlen = None
                # estimated input rate
                #est_input_rate = (reqs_created_cpus + reqs_completed_cpus) / self.window_time
                est_input_rate = input_reqs / self.window_time
                meas_queue_len = queue_len
                # controller.eir_history.append(est_input_rate)
                # controller.mql_history.append(meas_queue_len)
                if est_input_rate > 0:
                    # set point queue length
                    sp_queue_length = resp_time_sla * est_input_rate
                    eqlen = sp_queue_length - meas_queue_len
                    # sp_queue_length = resp_time_sla * stats.mean(controller.eir_history)
                    # eqlen = sp_queue_length - stats.mean(controller.mql_history)
                    # proportional
                    controller.up = self.Kql * eqlen
                    # integral
                    controller.ui = controller.uio + self.Kql * Ts / self.Tiql * eqlen

                    controller.dcores = max(self.min_c, min(self.max_c, controller.up + controller.ui))
                    controller.uio = controller.dcores - controller.up
                else:
                    if meas_queue_len <= 0:
                        controller.dcores = self.min_c
                        controller.uio = self.min_c

                # apply control given models and containers
                controller_metrics = {"model_sla":  self.models[controller.container.model].sla,
                                      "reqs_com_cpus_from_ts": reqs_completed_cpus,
                                      "reqs_cre_cpus_from_ts": reqs_created_cpus,
                                      "meas_queue_len": meas_queue_len,
                                      "est_input_rate": est_input_rate,
                                      "sp_queue_length": sp_queue_length,
                                      "eqlen": eqlen}
                log["logs"][node][controller.container.model]["metrics"] = controller_metrics

            tot_reqs_cores = sum(map(lambda c: c.dcores, controller_for_node))
            log["logs"][node]["cores_before_norm"] = tot_reqs_cores
            log["logs"][node]["max_c"] = self.max_c

            # if tot_reqs_cores > self.max_c:
            #     # norm
            #     for controller in controller_for_node:
            #         controller.nc = self.float_round(
            #             (controller.nc * self.max_c / tot_reqs_cores), 1)

            tot_reqs_cores = sum(map(lambda c: c.dcores, controller_for_node))
            log["logs"][node]["tot_req_core"] = tot_reqs_cores
            # actuate
            for controller in controller_for_node:
                # update container by node
                # post to actuator
                act_response = requests.post("http://" + node + ":" + str(self.actuator_port) + "/containers/" + controller.container.container_id,
                                             json={"cpu_quota": int(controller.dcores * 100000)})
                # post con containers_manager
                cont_response = requests.patch(self.containers_endpoint,
                                               json={"container_id": controller.container.container_id,
                                                     "cpu_quota": int(controller.dcores * 100000)})

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
