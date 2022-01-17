import json
import os
import time

from flask import Flask, jsonify, make_response
from flask import request
from flask_cors import CORS
import logging
import requests
from models.reqdb import Request, Base
from models.model import Model
from models.container import Container
from models.configurations import RequestsStoreConfiguration
import sqlalchemy as db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_
from prometheus_client import make_wsgi_app, Counter, Gauge, generate_latest


app = Flask(__name__)
CORS(app)

active = False
config = None
config_filename = 'config.json'
status = None
db_engine = None
db_session = None
MAX_RESP_REQS = 1000
models = []
containers = []

# Prometheus metrics
metrics_prefix = "nodemanager_"
m_completed = Gauge(metrics_prefix + "completed", "Completed requests", ["model", "version"])
m_created = Gauge(metrics_prefix + "created", "Created requests", ["model", "version"])
m_input_reqs = Gauge(metrics_prefix + "input_reqs", "Input requests", ["model", "version"])
m_on_gpu = Gauge(metrics_prefix + "on_gpu", "Number of requests completed by the GPU", ["model", "version"])
m_on_cpu = Gauge(metrics_prefix + "on_cpu", "Number of requests completed by the CPU", ["model", "version"])
m_rt_avg = Gauge(metrics_prefix + "avg", "Mean response time", ["model", "version"])
m_process_avg = Gauge(metrics_prefix + "avg_process", "Mean processing time", ["model", "version"])
m_rt_dev = Gauge(metrics_prefix + "rt_dev", "Standard deviation response time", ["model", "version"])
m_rt_min = Gauge(metrics_prefix + "rt_min", "Minimum response time", ["model", "version"])
m_rt_max = Gauge(metrics_prefix + "rt_max", "Maximum response time", ["model", "version"])
last_ts = 0

@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/requests', methods=['DELETE'])
def delete_requests():
    if not active and not configure():
        return {'error': 'component not configured'}
    db_session.query(Request).delete()
    db_session.commit()
    return {"result": "ok"}


@app.route('/requests', methods=['POST'])
def post_requests():
    if not active and not configure():
        return {'error': 'component not configured'}

    rs = request.get_json()
    req = db_session.query(Request).get(rs["id"])
    if req:
        # update
        req.ts_wait = rs["ts_wait"]
        req.ts_out = rs["ts_out"]
        req.process_time = rs["process_time"]
        req.resp_time = rs["resp_time"]
        req.node = rs["node"]
        req.container = rs["container"]
        req.container_id = rs["container_id"]
        req.device = rs["device"]
        req.state = rs["state"]
    else:
        # insert
        req = Request(id=rs["id"],
                      model=rs["model"],
                      version=rs["version"],
                      ts_in=rs["ts_in"],
                      ts_wait=rs["ts_wait"],
                      ts_out=rs["ts_out"],
                      process_time=rs["process_time"],
                      resp_time=rs["resp_time"],
                      node=rs["node"],
                      container=rs["container"],
                      container_id=rs["container_id"],
                      device=rs["device"],
                      state=rs["state"])
        db_session.add(req)
    db_session.commit()
    # app.logger.info("+ %s", rs)
    return jsonify(rs)


@app.route('/requests', methods=['GET'])
def get_requests():
    if not active and not configure():
        return {'error': 'component not configured'}

    max_reqs = int(request.args.get('max_reqs') or MAX_RESP_REQS)
    reqs = db_session.query(Request).order_by(Request.ts_in.desc()).limit(max_reqs)
    return jsonify([req.to_json() for req in reqs])


@app.route('/requests/<node>', methods=['GET'])
def get_requests_by_node(node):
    if not active and not configure():
        return {'error': 'component not configured'}

    max_reqs = int(request.args.get('max_reqs') or MAX_RESP_REQS)
    reqs = db_session.query(Request)\
        .filter(Request.node == node).limit(max_reqs)\
        .order_by(Request.ts_in.desc())
    return jsonify([req.to_json() for req in reqs])

# # Add prometheus wsgi middleware to route /metrics requests
# app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
#     '/metrics': make_wsgi_app()
# })

@app.route('/metrics/model', methods=['GET'])
def get_metrics_by_model():
    if not active and not configure():
        return {'error': 'component not configured'}

    metrics = []
    from_ts = request.args.get('from_ts')

    for model in models:
        # filter the reqs associated with the model
        reqs = db_session.query(Request)\
            .filter(and_(Request.model == model.name, Request.version == model.version))\
            .order_by(Request.ts_in.desc())
        if from_ts is not None:
            # compute the metrics from ts
            metrics.append(
                {"model": model.name,
                 "version": model.version,
                 "metrics_from_ts": Request.metrics(reqs, from_ts)})
        else:
            # compute the metrics
            metrics.append(
                {"model": model.name,
                 "version": model.version,
                 "metrics": Request.metrics(reqs)})
    return jsonify(metrics)


@app.route('/metrics')
def get_prometheus_metrics():
    global last_ts
    # update the metrics
    for model in models:
        # filter the reqs associated with the model
        reqs = db_session.query(Request) \
            .filter(and_(Request.model == model.name, Request.version == model.version)) \
            .order_by(Request.ts_in.desc())

        metrics = Request.metrics(reqs, last_ts)
        m_completed.labels(model=model.name, version=model.version).set(
            metrics["completed"] if metrics["completed"] is not None else 0)
        m_created.labels(model=model.name, version=model.version).set(
            metrics["created"] if metrics["created"] is not None else 0)
        m_input_reqs.labels(model=model.name, version=model.version).set(
            metrics["input_reqs"] if metrics["input_reqs"] is not None else 0)
        m_on_gpu.labels(model=model.name, version=model.version).set(
            metrics["on_gpu"] if metrics["on_gpu"] is not None else 0)
        m_on_cpu.labels(model=model.name, version=model.version).set(
            metrics["on_cpu"] if metrics["on_cpu"] is not None else 0)
        m_rt_avg.labels(model=model.name, version=model.version).set(
            metrics["avg"] if metrics["avg"] is not None else 0)
        m_process_avg.labels(model=model.name, version=model.version).set(
            metrics["avg_process"] if metrics["avg_process"] is not None else 0)
        m_rt_dev.labels(model=model.name, version=model.version).set(
            metrics["dev"] if metrics["dev"] is not None else 0)
        m_rt_min.labels(model=model.name, version=model.version).set(
            metrics["min"] if metrics["min"] is not None else 0)
        m_rt_max.labels(model=model.name, version=model.version).set(
            metrics["max"] if metrics["max"] is not None else 0)

    response = make_response(generate_latest(), 200)
    response.mimetype = "text/plain"

    last_ts = time.time()
    return response

@app.route('/metrics/container', methods=['GET'])
def get_metrics_by_container():
    if not active and not configure():
        return {'error': 'component not configured'}

    metrics = []
    from_ts = request.args.get('from_ts')

    for container in containers:
        # filter the reqs associated with the container
        reqs = db_session.query(Request)\
            .filter(and_(Request.model == container.model, Request.container_id == container.container_id))\
            .order_by(Request.ts_in.desc())
        if from_ts is not None:
            # compute the metrics from ts
            metrics.append({"container": container.to_json(),
                            "metrics_from_ts": Request.metrics(reqs, from_ts)})
        else:
            # compute the metrics
            metrics.append({"container": container.to_json(),
                            "metrics": Request.metrics(reqs)})
    return jsonify(metrics)


@app.route('/metrics/container/model', methods=['GET'])
def get_metrics_by_container_model():
    if not active and not configure():
        return {'error': 'component not configured'}

    metrics = {}
    from_ts = request.args.get('from_ts')
    if from_ts is None:
        from_ts = 0

    for container in containers:
        # filter the reqs associated with the container
        reqs = db_session.query(Request) \
            .filter(and_(Request.container_id == container.container_id, Request.ts_in > from_ts))\
            .order_by(Request.ts_in.desc())
            # .filter(and_(Request.container_id == container.container_id, or_(Request.ts_in > from_ts, Request.ts_wait > from_ts, Request.ts_out > from_ts)))
        reqs_by_model = {}
        for model in models:
            reqs_model = list(filter(lambda r: r.model == model.name, reqs))
            reqs_metrics = Request.metrics(reqs_model, from_ts)
            reqs_by_model[model.name] = reqs_metrics

        # compute the metrics
        metrics[container.container_id] = reqs_by_model
    return jsonify(metrics)


@app.route('/metrics/container/model/created', methods=['GET'])
def get_created_by_container_model():
    if not active and not configure():
        return {'error': 'component not configured'}

    metrics = {}
    for container in containers:
        reqs_by_model = {}
        for model in models:
            # filter the reqs associated with the container
            # TODO: richieste create
            reqs_model = db_session.query(Request)\
                .filter(and_(Request.container_id == container.container_id,
                            Request.model == model.name,
                            Request.ts_out == None))\
                .order_by(Request.ts_in.desc())\
                .count()
            reqs_created = {"created": reqs_model}
            reqs_by_model[model.name] = reqs_created

        # compute the metrics
        metrics[container.container_id] = reqs_by_model
    return jsonify(metrics)


def configure():
    global status, config, models, containers, active

    if not config:
        logging.info("reading config from file")
        if not read_config_from_file():
            logging.error("configuration reading error")
            return False
        else:
            logging.info("configuration read from file")

    logging.info("configuration read: " + str(config.__dict__))

    # get models information
    models = [Model(json_data=json_model) for json_model in get_data(config.models_endpoint)]
    logging.info("Models: %s", [model.to_json() for model in models])

    # get containers information
    containers = [Container(json_data=json_container) for json_container in get_data(config.containers_endpoint)]
    logging.info("Containers: %s", [container.to_json() for container in containers])

    status = "active"
    active = True
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/configuration', methods=['GET'])
def get_configuration():
    global config, status
    logging.info("get configuration")

    # read from file
    logging.info("read configuration from file")
    if config or read_config_from_file():
        status = "configured"
        return {"configuration": config.__dict__}, 200
    else:
        logging.warning("configuration not found")
        return {"configuration": "not found"}, 404


@app.route('/configuration', methods=['POST'])
def post_configuration():
    global status, config

    logging.info("configuration started...")

    # read data
    data = request.get_json()
    config = RequestsStoreConfiguration(json_data=data)

    logging.info("configuration: " + str(config.__dict__))

    logging.info("Getting models from: %s", config.models_endpoint)
    logging.info("Getting containers from: %s", config.containers_endpoint)

    with open(config_filename, 'w') as config_file:
        json.dump(config.__dict__, config_file)

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


def read_config_from_file():
    global config
    try:
        with open(config_filename) as json_file:
            data = json.load(json_file)
            config = RequestsStoreConfiguration(json_data=data)
            return True
    except IOError as e:
        logging.error("configuration error")
        return False


def get_data(url):
    try:
        response = requests.get(url)
    except Exception as e:
        logging.warning(e)
        response = []
    print(response)
    return response.json()



def create_app(db_echo=False, delete_config=True):
    global status, db_engine, db_session

    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='DEBUG', format=log_format)

    status = "inactive"
    logging.info(status)

    # delete config file
    if delete_config:
        logging.info("deleting config file")
        try:
            os.remove(config_filename)
        except FileNotFoundError as e:
            logging.info("file not found")

    db_engine = db.create_engine('postgresql://postgres:romapwd@localhost/postgres', echo=db_echo)
    Base.metadata.create_all(db_engine)
    Session = sessionmaker(bind=db_engine)
    db_session = Session()

    # clean db
    logging.info("cleaning db")
    db_session.query(Request).delete()
    db_session.commit()

    return app


if __name__ == '__main__':
    create_app()
