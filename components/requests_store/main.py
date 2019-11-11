import time

from flask import Flask, jsonify
from flask import request
from flask_cors import CORS
import argparse
import logging
import requests
from models.req import Req
from models.model import Model
from models.container import Container

app = Flask(__name__)
CORS(app)


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/requests', methods=['DELETE'])
def delete_requests():
    global reqs
    reqs = []
    return jsonify(reqs)


@app.route('/requests', methods=['GET', 'POST'])
def get_requests():
    if request.method == 'GET':
        limit = request.args.get('limit')
        if limit is None:
            return jsonify([req.to_json() for req in reqs])
        else:
            limit = int(request.args.get('limit'))
            return jsonify([req.to_json() for req in reqs[-limit:]])
    elif request.method == 'POST':
        rs = request.get_json()
        reqs.append(Req(json_data=rs))
        # app.logger.info("+ %s", rs)
        return jsonify(rs)


@app.route('/requests/<node>', methods=['GET'])
def get_requests_by_node(node):
    return jsonify([req.to_json() for req in list(filter(lambda r: r.node == node, reqs))])


@app.route('/metrics/model', methods=['GET'])
def get_metrics_by_model():
    metrics = []
    from_ts = request.args.get('from_ts')

    for model in models:
        # filter the reqs associated with the model
        model_reqs = list(filter(lambda r: r.model == model.name and
                                           r.version == model.version, reqs))
        if from_ts is not None:
            model_reqs_from_ts = list(filter(lambda r: r.ts_in > float(from_ts), model_reqs))
            # compute the metrics
            metrics.append(
                {"model": model.name,
                 "version": model.version,
                 "metrics_from_ts": Req.metrics(model_reqs_from_ts)})
        else:
            # compute the metrics
            metrics.append(
                {"model": model.name,
                 "version": model.version,
                 "metrics": Req.metrics(model_reqs)})
    return jsonify(metrics)


@app.route('/metrics/container', methods=['GET'])
def get_metrics_by_container():
    metrics = []
    for container in containers:
        # filter the reqs associated with the container
        container_reqs = list(filter(lambda r: r.container == container.container, reqs))
        # compute the metrics
        metrics.append({"container": container.to_json(),
                        "metrics": Req.metrics(container_reqs)})
    return jsonify(metrics)


def get_data(url):
    try:
        response = requests.get(url)
    except Exception as e:
        logging.warning(e)
        response = []
    print(response)
    return response.json()


"""
@app.route('/metrics/model/<model>/<version>', methods=['GET'])
def get_metrics_by_model_interval(model, version):
    metrics = []
    model = str(model)
    version = int(version)
    samples_size = 30
    samples_width = 1
    start_ts = time.time() - samples_size*samples_width
    end_ts = start_ts + samples_width

    for interval in range(samples_size):
        # filter the reqs associated with the model
        model_reqs_interval = list(filter(lambda r: r.model == model and
                                                    r.version == version and
                                                    start_ts < r.ts_in < end_ts, reqs))

        # compute the metrics
        metrics.append(
            {"interval": interval,
             "metrics": Req.metrics(model_reqs_interval)})

        start_ts = start_ts + samples_width
        end_ts = start_ts + samples_width

    return jsonify(intervals=metrics)
"""

if __name__ == "__main__":
    reqs = []
    status = "running"

    parser = argparse.ArgumentParser()
    parser.add_argument('--containers_manager', type=str, required=True)
    args = parser.parse_args()

    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='DEBUG', format=log_format)

    # get models information
    models_endpoint = args.containers_manager + "/models"
    logging.info("Getting models from: %s", models_endpoint)
    models = [Model(json_data=json_model) for json_model in get_data(models_endpoint)]
    logging.info("Models: %s", [model.to_json() for model in models])

    # get containers information
    containers_endpoint = args.containers_manager + "/containers"
    logging.info("Getting containers from: %s", containers_endpoint)
    containers = [Container(json_data=json_container) for json_container in get_data(containers_endpoint)]
    logging.info("Containers: %s", [container.to_json() for container in containers])

    app.run(host='0.0.0.0', port=5002)
