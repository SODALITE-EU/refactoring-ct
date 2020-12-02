import argparse
import time
from flask import Flask, jsonify
from flask import request
import logging
import yaml
import json
import requests
from flask_cors import CORS
from models.model import Model
from models.device import Device
from models.container import Container
from kubernetes import client, config
from configurator import Configurator

app = Flask(__name__)
CORS(app)

CONFIG_FILE = "config/config.json"
CONTAINERS_LIST_ENDPOINT = "/containers"

# constants set after configuration
INIT_QUOTA = None
ACTUATOR_PORT = None


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/containers', methods=['GET', 'PATCH'])
def containers():
    if request.method == 'GET':
        return jsonify([container.to_json() for container in containers])
    elif request.method == 'PATCH':
        data = request.get_json()
        app.logger.info("Request: " + str(data))

        app.logger.info("Updating container %s with quota %d",
                        data["container_id"], data["cpu_quota"])

        # search and update the container quota
        for container in containers:
            if container.container_id == data["container_id"] or container.container_id[:12] == data["container_id"]:
                container.quota = data["cpu_quota"]
                app.logger.info("Container %s updated")
                break
        return {"response": "ok"}
    """ elif request.method == 'POST':
    # TODO: add a new container
    data = request.get_json()
    app.logger.info("Adding new container %s", data["model"])
    container = Container(data["model"], data["version"])
    containers.append(container)
    return container.to_json()"""


@app.route('/node/containers', methods=['GET'])
def containers_grouped_by_nodes():
    nodes = set(map(lambda c: c.node, containers))
    containers_in_node = {}
    for node in nodes:
        containers_in_node[node] = [container.to_json() for container in
                                    list(filter(lambda c: c.node == node, containers))]
    return jsonify(containers_in_node)


@app.route('/containers/<node>', methods=['GET'])
def containers_by_node(node):
    return jsonify([container.to_json() for container in list(filter(lambda c: c.node == node, containers))])


@app.route('/models', methods=['GET', 'PATCH'])
def models():
    if request.method == 'GET':
        return jsonify([model.to_json() for model in models])
    elif request.method == 'PATCH':
        data = request.get_json()
        app.logger.info("Request: " + str(data))
        app.logger.info("Updating model %s", data["model"])

        # search and update the model
        for model in models:
            if model.name == data["model"]:
                if data["sla"] is not None:
                    model.sla = float(data["sla"])
                    app.logger.info("Model %s updated", model.name)
                    break
        return {"response": "ok"}


@app.route('/models/<model_name>', methods=['GET'])
def get_model(model_name):
    for model in models:
        if model.name == model_name:
            return model.to_json()


@app.route('/models/<model_name>/containers', methods=['GET'])
def get_container_for_model(model_name):
    return jsonify(list(map(lambda c: c.to_json(), filter(lambda c: c.model == model_name, containers))))


@app.route('/models/<node>', methods=['GET'])
def models_by_node(node):
    models_node = []
    for model in models:
        if model.name in list(map(lambda c: c.model, list((filter(lambda c: c.node == node, containers))))):
            models_node.append(model)
    return jsonify([model.to_json() for model in models_node])


def check_write(res):
    if res > 0:
        logging.info("write ok")
    else:
        logging.error("write error")


def clean_empty(d):
    if not isinstance(d, (dict, list)):
        return d
    if isinstance(d, list):
        return [v for v in (clean_empty(v) for v in d) if v]
    return {k: v for k, v in ((k, clean_empty(v)) for k, v in d.items()) if v}


@app.route('/configure', methods=['POST'])
def configure():
    global models
    global containers
    global status
    global INIT_QUOTA
    global ACTUATOR_PORT
    models = []

    logging.info("configuration started...")

    # read from configuration
    data = request.get_json()
    if not all(d in data for d in ["models", "quota", "actuator_port", "workers", "tf_serving_models_path",
                                   "available_gpus", "actuator_image", "k8s_service_type"]):
        return {"error": "config data missing"}, 404
    for model in data["models"]:
        if "profiled_rt" in model:
            models.append(
                Model(model["name"], model["version"], model["sla"], model["alpha"], model["profiled_rt"]))
        else:
            models.append(
                Model(model["name"], model["version"], model["sla"], model["alpha"]))

    # read other params
    INIT_QUOTA = data["quota"]
    ACTUATOR_PORT = data["actuator_port"]
    workers = data["workers"]
    tf_serving_models_path = data["tf_serving_models_path"]
    available_gpus = data["available_gpus"]
    actuator_image = data["actuator_image"]
    k8s_service_type = data["k8s_service_type"]

    # generate TF serving config file
    logging.info("generating tf serving config...")
    tf_serving_config_file_content = Configurator.tf_config_generator(models, tf_serving_models_path)
    tf_serving_config_file_name = tf_serving_models_path + "tf_serving_models.config"

    logging.info("writing tf serving config to file...")
    with open(tf_serving_config_file_name, 'w') as file:
        res = file.write(tf_serving_config_file_content)
    check_write(res)

    # generate K8s deployment and service
    logging.info("generating k8s deployment and service...")
    k8s_containers, k8s_deployment, k8s_service = Configurator.k8s_config_generator(workers,
                                                                                    models,
                                                                                    available_gpus,
                                                                                    actuator_image,
                                                                                    ACTUATOR_PORT,
                                                                                    k8s_service_type,
                                                                                    tf_serving_models_path,
                                                                                    tf_serving_config_file_name)

    k8s_deployment_yml = yaml.dump(clean_empty(k8s_deployment.to_dict()))
    k8s_service_yml = yaml.dump(clean_empty(k8s_service.to_dict()))
    logging.info(k8s_deployment_yml)
    logging.info(k8s_service_yml)
    if "k8s_output_config_path" in data:
        k8s_deployment_file_name = data["k8s_output_config_path"] + "k8s_deployment.yml"
        k8s_service_file_name = data["k8s_output_config_path"] + "k8s_service.yml"
        logging.info("writing k8s deployment to file...")
        with open(k8s_deployment_file_name, 'w') as file:
            res = file.write(k8s_deployment_yml)
            check_write(res)
        logging.info("writing k8s service to file...")
        with open(k8s_service_file_name, 'w') as file:
            res = file.write(k8s_service_yml)
            check_write(res)

    # apply k8s deployment
    config.load_kube_config()
    apps_api = client.AppsV1Api()
    resp = apps_api.create_namespaced_deployment(namespace="default", body=k8s_deployment)
    if resp and resp.metadata and resp.metadata.name:
        logging.info("Service created. status='%s'" % resp.metadata.name)
    else:
        return {"result": "error during the creation of the K8s deployment"}, 400

    # apply k8s service
    apps_api = client.CoreV1Api()
    resp = apps_api.create_namespaced_service(namespace="default", body=k8s_service)
    if resp and resp.metadata and resp.metadata.name:
        logging.info("Service created. status='%s'" % resp.metadata.name)
    else:
        return {"result": "error during the creation of the K8s service"}, 400

    # list node IPs
    # wait until the service is applied in k8s
    sleep_time = 1
    waited_time = 0
    timeout = 100
    service_ok = False
    while not service_ok:
        logging.info("Waiting %ds, total waited %ds/%ds for K8s service..." % (sleep_time, waited_time, timeout))
        time.sleep(sleep_time)
        waited_time += sleep_time
        resp = apps_api.read_namespaced_endpoints(namespace="default", name="nodemanager-svc")
        if resp and resp.subsets:
            service_ok = True
        sleep_time *= 2
        if waited_time > timeout:
            return {"result": "error timeout waiting for K8s service"}, 400

    k8s_nodes = []
    for i, subset in enumerate(resp.subsets):
        if not resp.subsets[i].addresses:
            return {"result": "error K8s service, node IPs not found, api returned: " + str(resp)}, 400
        for j, address in enumerate(resp.subsets[i].addresses):
            k8s_nodes.append(address.ip)
    logging.info("Available node (IPs), node ips=" + str(k8s_nodes))

    # populate the container list
    for node in k8s_nodes:
        for k8s_container in k8s_containers:
            container = k8s_container
            container.set_node(node)
            containers.append(container)

    logging.info("+ %d CPU containers, not linked yet",
                 len(list(filter(lambda m: m.device == Device.CPU, containers))))
    logging.info("+ %d GPU containers, not linked yet",
                 len(list(filter(lambda m: m.device == Device.GPU, containers))))
    logging.info([c.to_json() for c in containers])

    # link containers (get containers IDs)
    containers_linking(ACTUATOR_PORT)

    # set initial CPU quota
    # quota_reset(ACTUATOR_PORT, INIT_QUOTA)

    status = "active"
    logging.info(status)

    return {"result": "ok"}, 200


def containers_linking(actuator_port):
    """
    Link containers with ids
    """
    # get the set of nodes
    nodes = set(map(lambda c: c.node, containers))
    logging.info("Nodes: %s", nodes)

    # get the list of running containers for every node
    for node in nodes:
        containers_on_node = list(filter(lambda c: c.node == node, containers))

        try:
            response = requests.get(
                "http://" + node + ":" + str(actuator_port) + CONTAINERS_LIST_ENDPOINT)
            logging.info("Response: %d %s",
                         response.status_code, response.text)

            if response.ok:
                # get the containers from the response
                running_containers = response.json()
                logging.info("Found %d containers on node %s",
                             len(running_containers), node)

                # set the containers id
                linked_containers = 0
                for container in containers_on_node:
                    for running_container in running_containers:
                        if container.container == running_container["container_name"]:
                            container.container_id = running_container["id"]
                            logging.info("+ link: %s <-> %s",
                                         container.model, container.container_id)
                            linked_containers = linked_containers + 1
                            break
                logging.info("Linked %d containers on node %s",
                             linked_containers, node)
            else:
                # disable model if actuator_controller response status is not 200
                logging.info(
                    "No containers found on node %s, (response not ok)", node)
                for container in containers_on_node:
                    container.active = False

        except Exception as e:
            logging.warning(
                "Disabling containers for node: %s because %s", node, e)

            # disable containers if actuator_controller not reachable
            for container in containers_on_node:
                container.active = False

            break


def quota_reset(actuator_port, quota):
    """
    Set a default number of cores for all the containers
    """
    logging.info("Setting default cores for all containers to: %d", quota)
    for container in containers:
        if container.device == Device.CPU:
            response = requests.post(
                "http://" + container.node + ":" + str(
                    actuator_port) + CONTAINERS_LIST_ENDPOINT + "/" + container.container_id,
                json={"cpu_quota": int(quota * 100000)})
            logging.info("Actuator response: %s", response.text)
            container.quota = int(quota * 100000)


if __name__ == "__main__":
    models = []
    containers = []

    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='DEBUG', format=log_format)

    # start
    status = "inactive"
    logging.info(status)
    app.run(host='0.0.0.0', port=5001)
