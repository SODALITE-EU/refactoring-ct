import argparse
import logging
from flask import request
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS
from controller_manager import ControllerManager
from controller_manager_rules import ControllerManagerRules

app = Flask(__name__)
CORS(app)

status = None
models_endpoint = None
containers_endpoint = None
min_cores = None
max_cores = None
control_period = None
control_type = None
actuator_port = None
sched = None
controller = None
dry_run = None


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/logs', methods=['GET'])
def get_logs():
    global controller
    return jsonify(controller.get_logs())


def control():
    global dry_run
    global controller

    app.logger.info("Controller updating...")
    if dry_run:
        app.logger.info("updating (dry-run)")
    else:
        controller.update()
    app.logger.info("Controller updated, waiting for next clock...")


@app.route('/configuration', methods=['POST'])
def configure():
    global status
    global models_endpoint
    global containers_endpoint
    global requests_endpoint
    global min_cores
    global max_cores
    global control_period
    global control_type
    global actuator_port
    global dry_run

    logging.info("configuration started...")

    # read from configuration
    data = request.get_json()

    containers_manager = data["containers_manager"]
    requests_store = data["requests_store"]
    min_cores = data["min_cores"]
    max_cores = data["max_cores"]
    control_period = data["control_period"]
    control_type = data["control_type"]
    if control_type not in ["CT", "RL"]:
        return {"result": "error control type"}, 400
    actuator_port = data["actuator_port"]
    if "dry_run" in data:
        dry_run = data["dry_run"]
    else:
        dry_run = False

    models_endpoint = containers_manager + "/models"
    logging.info("Setting models manager to: %s", models_endpoint)
    containers_endpoint = containers_manager + "/containers"
    logging.info("Setting containers_manager to: %s", containers_endpoint)
    requests_endpoint = requests_store
    logging.info("Setting requests_store to: %s", requests_endpoint)

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/stop', methods=['POST'])
def stop_controller():
    global sched
    global status

    sched.remove_job('nodemanager-controller')

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/start', methods=['POST'])
def start_controller():
    global status
    global models_endpoint
    global containers_endpoint
    global min_cores
    global max_cores
    global control_period
    global control_type
    global actuator_port
    global sched
    global controller

    if control_type == "CT":
        controller = ControllerManager(models_endpoint,
                                       containers_endpoint,
                                       requests_endpoint,
                                       actuator_port,
                                       control_period,
                                       min_cores,
                                       max_cores)
    else:
        controller = ControllerManagerRules(models_endpoint,
                                            containers_endpoint,
                                            requests_endpoint,
                                            actuator_port,
                                            control_period,
                                            min_cores,
                                            max_cores)
    if dry_run:
        logging.info("Controller init (dry-run")
    else:
        controller.init()

    sched.add_job(control, 'interval', seconds=control_period, id='nodemanager-controller')
    sched.start()

    status = "active"
    logging.info(status)

    return {"result": "ok"}, 200


if __name__ == "__main__":
    # init log
    format = "%(threadName)s:%(asctime)s: %(message)s"
    logging.basicConfig(format=format,
                        level=logging.INFO,
                        datefmt="%H:%M:%S")

    sched = BackgroundScheduler()

    status = "inactive"
    logging.info(status)
    app.run(host='0.0.0.0', port=5003, debug=False)
