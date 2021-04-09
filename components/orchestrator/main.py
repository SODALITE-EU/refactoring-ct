import json
import logging
import time
import uuid
import requests
from flask import request
from flask import Flask
from flask_cors import CORS
import yaml
from kubernetes import client as client_k8s_api
from kubernetes import config as config_k8s_api
from configurations_generator import ConfigurationsGenerator
from models.configurations import OrchestratorConfiguration, K8sConfiguration,\
    ContainersManagerConfiguration, RequestsStoreConfiguration, ControllerConfiguration, DispatcherConfiguration
from models.device import Device


app = Flask(__name__)
CORS(app)

status = None
configs = {}
tfs_config = None
k8s_config = None
k8s_containers = None
k8s_deployment = None
k8s_service = None
containers = None
MODELS_DIR = "tfs_models/"


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


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/configuration', methods=['GET'])
def get_configuration():
    if k8s_config:
        return {"configuration": k8s_config.__dict__}, 200
    else:
        return {"error": "configuration not defined"}, 400


@app.route('/configuration/tfs', methods=['GET'])
def get_tfs_configuration():
    if tfs_config:
        return {"configuration": tfs_config}, 200
    else:
        return {"error": "tfs configuration not defined"}, 400


@app.route('/configuration/k8s/deployment', methods=['GET'])
def get_k8s_deployment():
    if k8s_deployment:
        return {"configuration": yaml.dump(clean_empty(k8s_deployment.to_dict()))}, 200
    else:
        return {"error": "k8s deployment not defined"}, 400


@app.route('/configuration/k8s/service', methods=['GET'])
def get_k8s_service():
    if k8s_service:
        return {"configuration": yaml.dump(clean_empty(k8s_service.to_dict()))}, 200
    else:
        return {"error": "k8s service not defined"}, 400


def generate_k8s_deployment_service():
    global tfs_config, k8s_containers, k8s_deployment, k8s_service
    # generate TF serving config file
    logging.info("generating tf serving config...")
    tfs_config = ConfigurationsGenerator.tf_config_generator(configs["k8s_config"].models,
                                                             configs["k8s_config"].tfs_models_path)

    # generate K8s deployment and service
    logging.info("generating k8s deployment and service...")
    k8s_containers, k8s_deployment, k8s_service = ConfigurationsGenerator.k8s_config_generator(
        k8s_config=configs["k8s_config"], logging=logging)

    k8s_deployment_yml, _ = get_k8s_deployment()
    k8s_service_yml, _ = get_k8s_service()
    logging.info(k8s_deployment_yml)
    logging.info(k8s_service_yml)


def append_models_uuid(models):
    logging.info("appending uuid to models names")
    for model in models:
        # append uuid
        model["name"] = model["name"].replace("_", "-") + "-" + str(uuid.uuid4())


@app.route('/deployment', methods=['POST'])
def k8s_apply():
    global status, configs, containers

    # set deployment config
    data = request.get_json()
    logging.info(type(data["models"]))
    # append uuid to model name
    append_models_uuid(data["models"])
    configs["containers_manager"].models = data["models"]
    # take the first initial_replicas
    configs["k8s_config"].initial_replicas = data["models"][0]["initial_replicas"]
    configs["k8s_config"].models = data["models"]
    logging.info("models: " + str(configs["k8s_config"].models))
    configs["k8s_config"].available_gpus = data["available_gpus"]
    configs["k8s_config"].tfs_image = data["tfs_image"]
    if "k8s_api_configuration" in data:
        configs["k8s_config"].k8s_api_configuration = data["k8s_api_configuration"]

    generate_k8s_deployment_service()

    if k8s_deployment and k8s_service and k8s_containers:
        # configure K8s API
        if configs["k8s_config"].k8s_api_configuration:
            logging.info("K8s API using config: " + str(configs["k8s_config"].k8s_api_configuration))
            config_k8s_api.load_kube_config_from_dict(configs["k8s_config"].k8s_api_configuration)
        else:
            logging.info("K8s API using default config")
            config_k8s_api.load_kube_config()

        # apply k8s deployment
        apps_api = client_k8s_api.AppsV1Api()
        try:
            resp = apps_api.create_namespaced_deployment(namespace="default", body=k8s_deployment)
            if resp and resp.metadata and resp.metadata.name:
                logging.info("Service created. status='%s'" % resp.metadata.name)
            else:
                raise client_k8s_api.exceptions.ApiException()
        except client_k8s_api.exceptions.ApiException:
            status = "error K8s deployment"
            logging.info(status)
            return {"result": "error during the creation of the K8s deployment"}, 400

        # apply k8s service
        try:
            apps_api = client_k8s_api.CoreV1Api()
            resp = apps_api.create_namespaced_service(namespace="default", body=k8s_service)
            if resp and resp.metadata and resp.metadata.name:
                logging.info("Service created. status='%s'" % resp.metadata.name)
            else:
                raise client_k8s_api.exceptions.ApiException()
        except client_k8s_api.exceptions.ApiException:
            status = "error K8s service"
            logging.info(status)
            return {"result": "error during the creation of the K8s service"}, 400

        # list node IPs
        # wait until the service is applied in k8s
        sleep_time = 2
        waited_time = 0
        timeout = 100
        service_ok = False
        while not service_ok:
            logging.info("Waiting %ds, total waited %ds/%ds for K8s service..." % (sleep_time, waited_time, timeout))
            time.sleep(sleep_time)
            waited_time += sleep_time
            resp = apps_api.read_namespaced_endpoints(namespace="default", name="nodemanager-svc")
            # check if response
            if resp and resp.subsets and len(resp.subsets) > 0:
                for subset in resp.subsets:
                    # check if subset is ready
                    if not subset.not_ready_addresses:
                        service_ok = True
            sleep_time *= 2
            if waited_time > timeout:
                status = "error K8s service timeout"
                logging.info(status)
                return {"result": "error timeout waiting for K8s service"}, 400

        k8s_nodes = []
        for i, subset in enumerate(resp.subsets):
            if not resp.subsets[i].addresses:
                status = "error K8s service IPs not found"
                logging.info(status)
                return {"result": "error K8s service, node IPs not found, API returned: " + str(resp)}, 400
            if len(resp.subsets[i].addresses) == 0:
                status = "error K8s service IPs empty"
                logging.info(status)
                return {"result": "error K8s service, node IPs empty, API returned: " + str(resp)}, 400
            for j, address in enumerate(resp.subsets[i].addresses):
                k8s_nodes.append(address.ip)
        logging.info("Available node (IPs), node ips=" + str(k8s_nodes))

        # populate the container list
        containers = []
        for node in k8s_nodes:
            for k8s_container in k8s_containers:
                container = k8s_container
                container.active = True
                container.set_node(node)
                containers.append(container)

        logging.info("+ %d CPU containers, not linked yet", len(list(filter(lambda m: m.device == Device.CPU, containers))))
        logging.info("+ %d GPU containers, not linked yet", len(list(filter(lambda m: m.device == Device.GPU, containers))))
        logging.info("containers: " + str([c.to_json() for c in containers]))

        # update containers
        configs["containers_manager"].containers = [c.to_json() for c in containers]

        # configure and start components
        status = "configuring components"
        logging.info(status)
        configured = configure_components()
        if configured:
            status = "starting components"
            logging.info(status)
            started = start_components()
            if started:
                status = "active"
                logging.info(status)
                endpoints = {m["name"][:-37]: configs["orchestrator"].dispatcher + "/predict/" + m["name"]
                             for m in configs["k8s_config"].models}
                return {"endpoints": endpoints}, 200
        return {"result": "error configuration"}, 400
    else:
        return {"result": "not configured yet"}, 400


def configure_components():
    global status

    for component in ["containers_manager", "requests_store", "dispatcher", "controller"]:
        status = "config " + component
        logging.info(status)

        res = configure_component(configs[component],
                                  configs["orchestrator"].get(component) + configs["orchestrator"].config_endpoint)
        if res:
            logging.info(component + " configured")
        else:
            status = "error config " + component
            logging.error(status)
            return res
    return True


def configure_component(configuration, endpoint):
    logging.info("sending: " + json.dumps(configuration.__dict__) + " to " + endpoint)
    headers = {'content-type': 'application/json'}
    try:
        response = requests.post(endpoint, data=json.dumps(configuration.__dict__), headers=headers)
    except Exception as e:
        logging.error("error configuration " + str(e))
        return False
    if response.status_code == 200:
        return True
    else:
        logging.error("error configuration response " + str(response))
        return False


def start_components():
    global status

    for component in ["containers_manager", "requests_store", "controller"]:
        status = "starting " + component
        logging.info(status)

        res = start_component(configs["orchestrator"].get(component) + configs["orchestrator"].start_endpoint)
        if res:
            logging.info(component + " started")
        else:
            status = "error starting " + component
            logging.error(status)
            return res
    return True


def start_component(endpoint):
    logging.info("send start to: " + endpoint)
    try:
        response = requests.post(endpoint)
    except Exception as e:
        logging.error("error start " + str(e))
        return False
    if response.status_code == 200:
        return True
    else:
        logging.error("error start response " + str(response))
        return False


@app.route('/configuration', methods=['POST'])
def configure():
    global status, configs, tfs_config, k8s_config, k8s_containers, k8s_deployment, k8s_service

    logging.info("configuration started...")
    data = request.get_json()

    configs = {}
    # orchestrator configuration
    configs["orchestrator"] = OrchestratorConfiguration(containers_manager=data["orchestrator"]["containers_manager"],
                                                        requests_store=data["orchestrator"]["requests_store"],
                                                        dispatcher=data["orchestrator"]["dispatcher"],
                                                        controller=data["orchestrator"]["controller"])

    # deployment configuration
    configs["k8s_config"] = K8sConfiguration(actuator_image=data["orchestrator"]["actuator_image"],
                                             actuator_port=data["orchestrator"]["actuator_port"],
                                             k8s_service_type=data["orchestrator"]["k8s_service_type"],
                                             k8s_image_pull_policy=data["orchestrator"]["k8s_image_pull_policy"],
                                             k8s_host_network=data["orchestrator"]["k8s_host_network"],
                                             tfs_init_image=data["orchestrator"]["tfs_init_image"],
                                             tfs_config_endpoint=data["orchestrator"]["tfs_config_endpoint"])

    configs["containers_manager"] = ContainersManagerConfiguration(actuator_port=configs["k8s_config"].actuator_port,
                                                                   init_quota=data["containers_manager"]["init_quota"])

    configs["requests_store"] = RequestsStoreConfiguration(containers_manager=configs["orchestrator"].containers_manager)

    configs["controller"] = ControllerConfiguration(containers_manager=configs["orchestrator"].containers_manager,
                                                    requests_store=configs["orchestrator"].requests_store,
                                                    actuator_port=configs["k8s_config"].actuator_port,
                                                    min_cores=data["controller"]["min_cores"],
                                                    max_cores=data["controller"]["max_cores"],
                                                    control_type=data["controller"]["control_type"],
                                                    control_period=data["controller"]["control_period"],
                                                    dry_run=data["controller"]["dry_run"])

    configs["dispatcher"] = DispatcherConfiguration(containers_manager=configs["orchestrator"].containers_manager,
                                                    requests_store=configs["orchestrator"].requests_store,
                                                    verbose=data["dispatcher"]["verbose"],
                                                    gpu_queues_policy=data["dispatcher"]["gpu_queues_policy"],
                                                    max_log_consumers=data["dispatcher"]["max_log_consumers"],
                                                    max_polling_threads=data["dispatcher"]["max_polling_threads"],
                                                    max_consumers_cpu=data["dispatcher"]["max_consumers_cpu"],
                                                    max_consumers_gpu=data["dispatcher"]["max_consumers_gpu"])

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


if __name__ == "__main__":
    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='DEBUG', format=log_format)

    # start
    status = "inactive"
    logging.info(status)
    app.run(host='0.0.0.0', port=5000)
