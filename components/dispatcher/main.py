from dispatcher import Dispatcher
from dispatcher import DispatchingPolicy
from flask import Flask, jsonify, abort, request
from models.req import Req
from models.model import Model
from models.device import Device
from models.container import Container
from models.queues_policies import QueuesPolicies, QueuesPolicy
from concurrent.futures import ThreadPoolExecutor
from configuration import Configuration
from flask_cors import CORS
import logging
import requests
import queue
import coloredlogs
import time
import json

app = Flask(__name__)
CORS(app)

status = None
active = False
config = None
reqs_queues = {}
log_queue = queue.Queue()


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/predict', methods=['POST'])
def predict():
    # check if the component is active
    if not active:
        # check if configuration file was loaded (lazy-load)
        if not configure():
            return {'error': 'component not configured'}

    # the component is configured and active
    data = request.get_json()
    if not data:
        return {'error': 'input not specified'}
    elif 'model' not in data.keys():
        return {'error': 'key model not specified'}
    elif 'version' not in data.keys():
        return {'error': 'key version not specified'}
    elif 'instances' not in data.keys():
        return {'error': 'key instances not specified'}

    # app.logger.info("IN - REQ %s/V%s %s", data["model"], data["version"], data["instances"])

    # Queue and log incoming request
    req = Req(data["model"], data["version"], data["instances"])
    reqs_queues[data["model"]].put(req)
    log_queue.put(req)

    # Forward 200
    return {"status": "ok",
            "id": req.id}


def log_consumer():
    global config
    while True:
        payload = log_queue.get().to_json()
        requests.post(config.requests_store_host, json=payload)
        time.sleep(0.1)


def queues_pooling(dispatcher, policy, max_consumers):
    # Create the pool of consumers
    consumer_threads_poll = ThreadPoolExecutor(max_workers=max_consumers)

    while True:
        selected_queue = policy()
        if not reqs_queues[selected_queue].empty():
            # Get next request
            req = reqs_queues[selected_queue].get()
            # Consume the request
            consumer_threads_poll.submit(queue_consumer(dispatcher, req))
        else:
            time.sleep(0.001)


def queue_consumer(dispatcher, req):
    # Forward request (dispatcher)
    # logging.info("Consumer for %s sending to dispatcher...", dispatcher.device)
    dispatcher.compute(req)
    log_queue.put(req)


def get_data(url):
    try:
        response = requests.get(url)
    except Exception as e:
        logging.warning(e)
        response = []
    return response.json()


@app.route('/configuration', methods=['POST'])
def post_configuration():
    global config, status
    logging.info("saving configuration...")

    # read from configuration
    data = request.get_json()

    config = Configuration(containers_manager=data["containers_manager"],
                           requests_store=data["requests_store"],
                           verbose=data["verbose"],
                           gpu_queues_policy=data["gpu_queues_policy"],
                           max_log_consumers=data["max_log_consumers"],
                           max_polling_threads=data["max_polling_threads"],
                           max_consumers_cpu=data["max_consumers_cpu"],
                           max_consumers_gpu=data["max_consumers_gpu"])

    logging.info("configuration: " + str(config.__dict__))

    with open('config.json', 'w') as config_file:
        json.dump(config.__dict__, config_file)

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/configuration', methods=['GET'])
def get_configuration():
    global config
    logging.info("getting configuration started...")

    # read from file
    logging.info("read configuration from file")
    if read_config_from_file():
        return {"configuration": config.__dict__}, 200
    else:
        logging.info("configuration error")
        return {"error": "file error"}, 404


def read_config_from_file():
    global config
    try:
        with open('config.json') as json_file:
            data = json.load(json_file)
            config = Configuration(json_data=data)
            return True
    except IOError as e:
        logging.info("configuration error")
        return False


def configure():
    global status, active, reqs_queues, config

    if not config:
        logging.info("reading config from file")
        if not read_config_from_file():
            logging.info("configuration reading error")
            return False

    logging.info("configuration read: " + str(config.__dict__))
    logging.info("Getting models from: %s", config.models_endpoint)
    logging.info("Getting containers from: %s", config.containers_endpoint)

    # init models
    models = [Model(json_data=json_model) for json_model in get_data(config.models_endpoint)]
    if len(models) > 0:
        logging.info("Models: %s", [model.to_json() for model in models])
    else:
        logging.warning("No models found")

    # init containers
    containers = [Container(json_data=json_container) for json_container in get_data(config.containers_endpoint)]
    if len(containers) > 0:
        logging.info("Containers: %s", [container.to_json() for container in containers])
    else:
        logging.warning("No containers found")
    logging.info("Found %d models and %d containers", len(models), len(containers))

    # init requests queues
    reqs_queues = {model.name: queue.Queue() for model in models}
    responses_list = {model.name: [] for model in models}

    # init policy
    queues_policies = QueuesPolicies(reqs_queues, responses_list, models, logging)
    gpu_policy = queues_policies.policies.get(config.gpu_queues_policy)
    cpu_policy = queues_policies.policies.get(config.cpu_queues_policy)
    logging.info("Policy for GPUs: %s", config.gpu_queues_policy)
    logging.info("Policy for CPUs: %s", config.cpu_queues_policy)

    # disable logging if verbose == 0
    logging.info("Verbose: %d", config.verbose)
    if config.verbose == 0:
        app.logger.disabled = True
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

    # init dispatchers
    status = "Init dispatchers"
    logging.info(status)
    dispatcher_gpu = Dispatcher(app.logger, models, containers, DispatchingPolicy.ROUND_ROBIN, Device.GPU)
    dispatcher_cpu = Dispatcher(app.logger, models, containers, DispatchingPolicy.ROUND_ROBIN, Device.CPU)

    # start the send requests thread
    status = "Start send reqs thread"
    logging.info(status)
    log_consumer_threads_pool = ThreadPoolExecutor(max_workers=config.max_log_consumers)
    for i in range(config.max_log_consumers):
        log_consumer_threads_pool.submit(log_consumer)

    # start the queues consumer threads
    status = "Start queues consumer threads"
    logging.info(status)

    if list(filter(lambda c: c.device == Device.GPU and c.active, containers)):
        # threads that pools from the apps queues and dispatch to gpus
        polling_gpu_threads_pool = ThreadPoolExecutor(max_workers=config.max_polling_threads)
        for i in range(config.max_polling_threads):
            polling_gpu_threads_pool.submit(queues_pooling, dispatcher_gpu, gpu_policy, config.max_consumers_gpu)

    if list(filter(lambda c: c.device == Device.CPU and c.active, containers)):
        # threads that pools from the apps queues and dispatch to cpus
        pooling_cpu_threads_pool = ThreadPoolExecutor(max_workers=config.max_polling_threads)
        for i in range(config.max_polling_threads):
            pooling_cpu_threads_pool.submit(queues_pooling, dispatcher_cpu, cpu_policy, config.max_consumers_cpu)

    status = "active"
    active = True
    logging.info(status)
    return True


def create_app():
    global status

    # init log
    coloredlogs.install(level='DEBUG', milliseconds=True)
    # log_format = "%(asctime)s:%(levelname)s:%(name)s: %(filename)s:%(lineno)d:%(message)s"
    # logging.basicConfig(level='DEBUG', format=log_format)

    status = "inactive"
    logging.info(status)
    return app


if __name__ == '__main__':
    create_app()
