import multiprocessing
import os
import uuid

from dispatcher import Dispatcher
from dispatcher import DispatchingPolicy
from flask import Flask, request
from models.reqdb import Request
from models.model import Model
from models.device import Device
from models.container import Container
from models.queues_policies import QueuesPolicies
from models.configurations import DispatcherConfiguration
from flask_cors import CORS
import logging
import requests
import coloredlogs
import time
import json
import sqlalchemy as db
from sqlalchemy.orm import sessionmaker

app = Flask(__name__)
CORS(app)

status = None
active = False
config = None
log_response = False
reqs_queues = {}
reqs_log_queue = multiprocessing.Queue()
reqs_computable_queue = multiprocessing.Queue()
config_filename = 'config.json'
db_session = None


# get the current status of the component
@app.route('/', methods=['GET'])
def get_status():
    get_configuration()
    return {"status": status}


# receive predict requests
@app.route('/predict/<model>', methods=['POST'])
def predict(model):
    # check if the component is active and the configuration file was loaded (lazy-load)
    if not active and not configure():
        return {'error': 'component not configured'}

    # the component is configured and active thus get the request data
    data = request.get_json()
    if not data:
        return {'error': 'input not specified'}
    elif not model:
        return {'error': 'model not specified'}
    elif 'version' not in data.keys():
        return {'error': 'key version not specified'}
    elif 'instances' not in data.keys():
        return {'error': 'key instances not specified'}

    # app.logger.info("IN - REQ %s/V%s %s", model, data["version"], data["instances"])

    # create the request
    req = Request(id=str(uuid.uuid4()), model=model, version=data["version"], ts_in=time.time())
    # put the req in the model queue
    reqs_queues[model].put((req, data["instances"]))
    # log request (creation)
    reqs_log_queue.put(req)

    # Forward 200
    return {"status": "ok",
            "id": req.id}


def queues_pooling(reqs_queues, reqs_log_queue, reqs_computable_queue, dispatcher, policy):
    while True:
        selected_queue = policy()
        if not reqs_queues[selected_queue].empty():
            # get next request
            req, instances = reqs_queues[selected_queue].get()
            # allocate request
            dispatcher.allocate(req)
            # log request (allocation)
            reqs_log_queue.put(req)
            # put request in computable
            reqs_computable_queue.put((req, instances))
        else:
            time.sleep(0.001)


def send_request(reqs_computable_queue, reqs_log_queue):
    while True:
        req, instances = reqs_computable_queue.get()
        # Forward request (dispatcher)
        # logging.info("Consumer for %s sending to dispatcher...", dispatcher.device)
        Dispatcher.compute(req, instances, log_response)
        # log request (completed)
        reqs_log_queue.put(req)


def get_data(url):
    try:
        response = requests.get(url)
    except Exception as e:
        logging.warning(e)
        response = []
    return response.json()


# get the configuration
@app.route('/configuration', methods=['POST'])
def post_configuration():
    global config, status
    logging.info("saving configuration...")

    # read the configuration
    data = request.get_json()
    config = DispatcherConfiguration(json_data=data)

    logging.info("configuration: " + str(config.__dict__))

    # save the configuration to file
    with open(config_filename, 'w') as config_file:
        json.dump(config.__dict__, config_file)

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/configuration', methods=['GET'])
def get_configuration():
    global config, status
    logging.info("getting configuration started...")

    # read from file
    logging.info("read configuration from file")
    if config or read_config_from_file():
        status = "configured"
        return {"configuration": config.__dict__}, 200
    else:
        logging.warning("configuration not found")
        return {"configuration": "not found"}, 404


def read_config_from_file():
    global config
    try:
        with open(config_filename) as json_file:
            data = json.load(json_file)
            config = DispatcherConfiguration(json_data=data)
            return True
    except IOError as e:
        logging.error("configuration error")
        return False


def reqs_saver(reqs_log_queue):
    while True:
        req = reqs_log_queue.get()
        save_request(req)


def save_request(req: Request):
    db_req = db_session.query(Request).get(req.id)
    if db_req:
        # update
        db_req.ts_wait = req.ts_wait
        db_req.ts_out = req.ts_out
        db_req.process_time = req.process_time
        db_req.resp_time = req.resp_time
        db_req.node = req.node
        db_req.container = req.container
        db_req.container_id = req.container_id
        db_req.device = req.device
        db_req.state = req.state
    else:
        # insert
        db_session.add(req)
    db_session.commit()


def configure():
    global status, active, reqs_queues, config

    if not config:
        logging.info("reading config from file")
        if not read_config_from_file():
            logging.error("configuration reading error")
            return False
        else:
            logging.info("configuration read from file")

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
    reqs_queues = {model.name: multiprocessing.Queue() for model in models}
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

    # start the send requests process
    status = "Start send reqs process"
    logging.info(status)
    reqs_saver_process = multiprocessing.Process(target=reqs_saver, args=(reqs_log_queue,))
    reqs_saver_process.start()

    # start the queues consumer processes
    status = "Start queues allocation processes"
    logging.info(status)

    if list(filter(lambda c: c.device == Device.GPU and c.active, containers)):
        # create the process that reads the apps queues and dispatch requests to gpus
        gpu_worker_process = multiprocessing.Process(target=queues_pooling, args=(reqs_queues, reqs_log_queue,
                                                                                  reqs_computable_queue,
                                                                                  dispatcher_gpu, gpu_policy,))
        gpu_worker_process.start()

    if list(filter(lambda c: c.device == Device.CPU and c.active, containers)):
        # create the process that reads the apps queues and dispatch requests to cpus
        cpu_worker_process = multiprocessing.Process(target=queues_pooling, args=(reqs_queues, reqs_log_queue,
                                                                                  reqs_computable_queue,
                                                                                  dispatcher_cpu, cpu_policy,))
        cpu_worker_process.start()

    # start the queues consumer process
    status = "Start queues consumer processe"
    logging.info(status)
    sender_worker_process = multiprocessing.Process(target=send_request, args=(reqs_computable_queue, reqs_log_queue,))
    sender_worker_process.start()


    status = "active"
    active = True
    logging.info(status)
    return True


def create_app(delete_config=True, debug_response=False, db_echo=False):
    global status, log_response, db_session

    log_response = debug_response

    # init log
    coloredlogs.install(level='DEBUG', milliseconds=True)
    # log_format = "%(asctime)s:%(levelname)s:%(name)s: %(filename)s:%(lineno)d:%(message)s"
    # logging.basicConfig(level='DEBUG', format=log_format)

    # delete config file
    if delete_config:
        logging.info("deleting config file")
        try:
            os.remove(config_filename)
        except FileNotFoundError as e:
            logging.info("file not found")

    db_engine = db.create_engine('postgresql://postgres:romapwd@localhost/postgres', echo=db_echo)
    Session = sessionmaker(bind=db_engine)
    db_session = Session()

    status = "inactive"
    logging.info(status)
    return app


if __name__ == '__main__':
    create_app()
