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
from models.configurations import OrchestratorConfiguration, K8sConfiguration, \
    ContainersManagerConfiguration, RequestsStoreConfiguration, ControllerConfiguration, DispatcherConfiguration
from models.device import Device
from models.container import Container

app = Flask(__name__)
CORS(app)

status = None
configs = {}
tfs_configs = []
k8s_config = None
k8s_actuator_daemonset = None
k8s_actuator_service = None
k8s_models_cpu_dpl = []
k8s_models_cpu_svc = []
k8s_models_gpu_dpl = []
k8s_models_gpu_svc = []
models = []
containers = None
tfs_model_enpoint = "/v1/models/"
tfs_protocol = "http://"
gpu_models = []


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


@app.route('/configuration/tfs/<gpu_index>', methods=['GET'])
def get_tfs_configuration(gpu_index):
    gpu_index = int(gpu_index)
    if tfs_configs[gpu_index]:
        return {"configuration": tfs_configs[gpu_index]}, 200
    else:
        return {"error": "tfs configuration not defined"}, 400


@app.route('/configuration/k8s/deployment', methods=['GET'])
def get_k8s_deployment():
    if k8s_models_cpu_dpl or k8s_models_gpu_dpl:
        return {"configuration": [yaml.dump(k8s_deployment) for k8s_deployment in [k8s_models_cpu_dpl, k8s_models_gpu_dpl]]}, 200
    else:
        return {"error": "k8s deployment not defined"}, 400


@app.route('/configuration/k8s/service', methods=['GET'])
def get_k8s_service():
    if k8s_models_cpu_svc or k8s_models_gpu_svc:
        return {"configuration": [yaml.dump(k8s_service) for k8s_service in [k8s_models_cpu_svc, k8s_models_gpu_svc]]}, 200
    else:
        return {"error": "k8s service not defined"}, 400


def generate_k8s_deployments_services():
    global logging, tfs_configs, models, k8s_actuator_daemonset, k8s_actuator_service, \
        k8s_models_cpu_dpl, k8s_models_cpu_svc, k8s_models_gpu_dpl, k8s_models_gpu_svc, gpu_models

    logging.info("generating deployments for " + str(len(models)) + " models")
    logging.info("generating deployments for " + str(len(gpu_models)) + " GPUs")

    # generate K8s deployments and services
    k8s_actuator_daemonset, k8s_actuator_service = ConfigurationsGenerator.k8s_actuator_config_generator(k8s_config=configs["k8s_config"], logging=logging)
    k8s_models_cpu_dpl, k8s_models_cpu_svc = ConfigurationsGenerator.k8s_models_cpu_config_generator(models=models, k8s_config=configs["k8s_config"], logging=logging)
    k8s_models_gpu_dpl, k8s_models_gpu_svc = ConfigurationsGenerator.k8s_models_gpu_config_generator(gpu_models=gpu_models, k8s_config=configs["k8s_config"], logging=logging)

    logging.info("generated " + str(len(k8s_models_cpu_dpl)) + " deployments for CPU models")
    logging.info("generated " + str(len(k8s_models_gpu_dpl)) + " deployments for GPU models")
    # k8s_deployment_yml, _ = get_k8s_deployment()
    # k8s_service_yml, _ = get_k8s_service()
    return True


def fix_models_name(models):
    logging.info("fixing models names")
    for model in models:
        model["name"] = model["name"].replace("_", "-")


def append_models_uuid(models):
    logging.info("appending uuid to models names")
    for model in models:
        # append uuid
        model["name"] = model["name"] + "-" + str(uuid.uuid4())[:8]


# apply k8s daemonset
def apply_k8s_daemonset(k8s_api, daemonset, namespace="default"):
    resp = k8s_api.create_namespaced_daemon_set(namespace=namespace, body=daemonset)
    if resp and resp.metadata and resp.metadata.name:
        logging.info("daemonset created. name='%s'" % resp.metadata.name)
    else:
        raise client_k8s_api.exceptions.ApiException()


def distribute_models_on_gpus():
    global gpu_models
    logging.info("distributing models on gpus...")

    # init gpu_models
    for gpu in range(configs["k8s_config"].available_gpus):
        gpu_models.append([])

    gpu_index = 0
    for model in models:
        # check that required GPU is <= than available ones, otherwise req = avail
        if model.required_gpus > configs["k8s_config"].available_gpus:
            logging.info("for model " + model.name + " required GPUs are > available ones, falling back to available ones")
            model.required_gpus = configs["k8s_config"].available_gpus
        for req_gpu in range(model.required_gpus):
            gpu_models[gpu_index].append(model)
            gpu_index = (gpu_index + 1) % configs["k8s_config"].available_gpus

    for i, g_models in enumerate(gpu_models):
        logging.info("gpu " + str(i) + ", scheduled models: " + str([model.name for model in g_models]))


def generate_tfs_config_files():
    global tfs_configs
    distribute_models_on_gpus()

    # generate TF serving config file
    for i, g_models in enumerate(gpu_models):
        logging.info("generating tf serving config for GPU " + str(i))
        tfs_config = ConfigurationsGenerator.tf_config_generator(g_models, configs["k8s_config"].tfs_models_path)
        tfs_configs.append(tfs_config)

    for i, tfs_config in enumerate(tfs_configs):
        logging.info("gpu " + str(i) + ", TFS config file: " + str(tfs_config))

    return True


# apply k8s service
def apply_k8s_service(k8s_api, service, namespace="default"):
    resp = k8s_api.create_namespaced_service(namespace=namespace, body=service)
    if resp and resp.metadata and resp.metadata.name:
        logging.info("service created. name='%s'" % resp.metadata.name)
    else:
        raise client_k8s_api.exceptions.ApiException()


# apply k8s deployment
def apply_k8s_deployment(k8s_api, deployment, namespace="default"):
    resp = k8s_api.create_namespaced_deployment(namespace=namespace, body=deployment)
    if resp and resp.metadata and resp.metadata.name:
        logging.info("deployment resource created. name='%s'" % resp.metadata.name)
    else:
        raise client_k8s_api.exceptions.ApiException()


# wait until the K8s service is created and the address is ready
def wait_k8s_service(k8s_api, service_name, req_addresses=1):
    sleep_time = 2
    waited_time = 0
    timeout = 240
    service_ok = False
    resp = None
    while not service_ok:
        logging.info("waiting %ds, total waited %ds/%ds for K8s service..." % (sleep_time, waited_time, timeout))
        time.sleep(sleep_time)
        waited_time += sleep_time
        resp = k8s_api.read_namespaced_endpoints(namespace="default", name=service_name)
        # logging.info("resp: " + str(resp))
        # check if response
        if resp and resp.subsets and len(resp.subsets) > 0:
            for subset in resp.subsets:
                # check if subset is ready
                if not subset.not_ready_addresses:
                    if len(subset.addresses) >= req_addresses:
                        service_ok = True
        sleep_time += 2
        if waited_time > timeout:
            return False
    return resp


def check_model_is_served(url):
    data = requests.get(url=url).json()
    if "model_version_status" in data:
        for mv_status in data["model_version_status"]:
            if "state" in mv_status and mv_status["state"] == "AVAILABLE":
                return True, None
            else:
                return False, "present but not available"
    else:
        return False, "not present: " + str(data)


def get_ips_ports(k8s_resp):
    for i, subset in enumerate(k8s_resp.subsets):
        # check if IP is present
        if not k8s_resp.subsets[i].addresses:
            status = "error K8s service IPs not found"
            logging.info(status)
            return False, False
        if len(k8s_resp.subsets[i].addresses) == 0:
            status = "error K8s service IPs empty"
            logging.info(status)
            return False, False

        ips = [address.ip for address in k8s_resp.subsets[i].addresses]
        ports = [port.port for port in k8s_resp.subsets[i].ports]

        logging.info("found ips: " + str(ips) + " ports: " + str(ports))
        return ips, ports


@app.route('/deployment', methods=['POST'])
def k8s_apply():
    global status, configs, models, containers

    # set deployment config
    data = request.get_json()

    fix_models_name(data["models"])

    if configs["k8s_config"].randomize_model_names:
        # append uuid to model name to make unique model names
        append_models_uuid(data["models"])

    # save models information
    configs["containers_manager"].models = data["models"]
    configs["k8s_config"].models = data["models"]
    models = ConfigurationsGenerator.model_list(data["models"])
    logging.info("models: " + str([model.name for model in models]))

    # config TF serving image
    configs["k8s_config"].tfs_image = data["tfs_image"]

    # save custom k8s api configuration
    if "k8s_api_configuration" in data:
        configs["k8s_config"].k8s_api_configuration = data["k8s_api_configuration"]

    logging.info("generating TFS configuration files")

    logging.info("models: " + str([model.name for model in models]))
    tfs_gen_res = generate_tfs_config_files()

    logging.info("generating k8s deployment and service...")
    logging.info("models: " + str([model.name for model in models]))
    k8s_gen_res = generate_k8s_deployments_services()
    if tfs_gen_res and k8s_gen_res:
        # configure K8s API
        if configs["k8s_config"].k8s_api_configuration:
            logging.info("k8s API using config: " + str(configs["k8s_config"].k8s_api_configuration))
            config_k8s_api.load_kube_config_from_dict(configs["k8s_config"].k8s_api_configuration)
        else:
            logging.info("K8s API using default config")
            config_k8s_api.load_kube_config()

        apps_api = client_k8s_api.AppsV1Api()
        core_api = client_k8s_api.CoreV1Api()

        # apply k8s daemonset and service for actuator
        try:
            apply_k8s_daemonset(apps_api, k8s_actuator_daemonset)
        except client_k8s_api.exceptions.ApiException as exc:
            status = "error K8s daemonset"
            logging.info(status)
            return {"result": "error during the creation of the K8s daemonset for actuator, error: " + str(exc)}, 400
        try:
            apply_k8s_service(core_api, k8s_actuator_service)
        except client_k8s_api.exceptions.ApiException as exc:
            status = "error K8s service"
            logging.info(status)
            return {"result": "error during the creation of the K8s service for actuator, error:" + str(exc)}, 400

        # apply k8s deployments and services for models and GPUs
        for k8s_deployment in k8s_models_cpu_dpl + k8s_models_gpu_dpl:
            try:
                apply_k8s_deployment(apps_api, k8s_deployment)
            except client_k8s_api.exceptions.ApiException as exc:
                status = "error K8s deployment"
                logging.info(status)
                return {"result": "error during the creation of the K8s deployment: " + str(exc)}, 400

        # apply k8s service for models and GPUs
        for k8s_service in k8s_models_cpu_svc + k8s_models_gpu_svc:
            try:
                apply_k8s_service(core_api, k8s_service)
            except client_k8s_api.exceptions.ApiException as exc:
                status = "error K8s service"
                logging.info(status)
                return {"result": "error during the creation of the K8s service: " + str(exc)}, 400

        logging.info("getting containers IPs and ports...")
        containers = []
        # wait until the service is applied in k8s to get node IPs and ports
        for model in models:
            if model.required_cpus > 0:
                logging.info("getting container ips/port for (CPU) model " + model.name)
                resp = wait_k8s_service(core_api, ConfigurationsGenerator.base_cpu_svc_name + model.name,
                                        req_addresses=model.required_cpus)
                if resp is False:
                    status = "error K8s service timeout"
                    logging.info(status)
                    return {"result": "error timeout waiting for K8s service"}, 400

                ips, ports = get_ips_ports(resp)

                if ips and ports:
                    # container serving the same app have the same port
                    port = ports[0]
                    for ip in ips:
                        url = tfs_protocol + str(ip) + ":" + str(port) + tfs_model_enpoint + str(model.name)
                        logging.info("checking that model is successfully served at " + str(url))
                        # wait for the TFS model deployment
                        time.sleep(2)
                        check, resp = check_model_is_served(url)

                        if check:
                            # the model was successfully deployed
                            logging.info("model is served at " + str(url) + " adding it to containers...")
                            container = Container(model=model.name, version=model.version, active=True,
                                                  container=ConfigurationsGenerator.base_cpu_cont_name + str(model.name),
                                                  node=ip, port=port, device=Device.CPU, quota=None)
                            containers.append(container)
                        else:
                            return {
                                "result": "the model is not available at " + str(url) + " TF Serving response is: " + str(resp)}
                else:
                    return {"result": "error K8s service, node IPs not found, API returned: " + str(resp)}, 400


        for i, g_models in enumerate(gpu_models):
            logging.info("getting container ips/port for GPU " + str(i))
            resp = wait_k8s_service(core_api, ConfigurationsGenerator.base_gpu_svc_name + str(i))
            if resp is False:
                status = "error K8s service timeout"
                logging.info(status)
                return {"result": "error timeout waiting for K8s service"}, 400

            ips, ports = get_ips_ports(resp)

            if ips and ports:
                # container serving the same app have the same port
                port = ports[0]
                for ip in ips:
                    for model in g_models:
                        url = tfs_protocol + str(ip) + ":" + str(port) + tfs_model_enpoint + str(model.name)
                        logging.info("checking that model is successfully served at " + str(url))
                        # wait for the TFS model deployment
                        time.sleep(2)
                        check, resp = check_model_is_served(url)

                        if check:
                            # the model was successfully deployed
                            logging.info("model is served at " + str(url) + " adding it to containers...")
                            container = Container(model=model.name, version=model.version, active=True,
                                                  container=ConfigurationsGenerator.base_gpu_cont_name + str(i),
                                                  node=ip, port=port, device=Device.GPU, quota=None)
                            containers.append(container)
                        else:
                            return {
                                "result": "the model is not available at " + str(url) + " TF Serving response is: " + str(resp)}
            else:
                return {"result": "error K8s service, node IPs not found, API returned: " + str(resp)}, 400

        logging.info("+ %d CPU containers, not linked yet", len(list(filter(lambda m: m.device == Device.CPU, containers))))
        logging.info("+ %d GPU containers, not linked yet", len(list(filter(lambda m: m.device == Device.GPU, containers))))
        logging.info("containers: " + str([c.to_json() for c in containers]))

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
                endpoints = {m["name"]: configs["orchestrator"].dispatcher + "/predict/" + m["name"]
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

    for component in ["containers_manager", "controller"]:
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
    global status, configs, tfs_configs, k8s_config, k8s_models_containers, k8s_deployment, k8s_service

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
                                             tfs_config_endpoint=data["orchestrator"]["tfs_config_endpoint"],
                                             available_cpus=int(data["orchestrator"]["available_cpus"]),
                                             available_gpus=int(data["orchestrator"]["available_gpus"]),
                                             randomize_model_names=data["orchestrator"]["randomize_model_names"])

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
                                                    window_time=data["controller"]["window_time"],
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
