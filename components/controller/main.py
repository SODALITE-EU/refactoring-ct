import argparse
import logging
from flask import request
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS
from controller_manager import ControllerManager
from controller_manager_rules import ControllerManagerRules
from configuration import Configuration

app = Flask(__name__)
CORS(app)

status = None
config = None
controller = None


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/logs', methods=['GET'])
def get_logs():
    return jsonify(controller.get_logs())


def control():
    app.logger.info("Controller updating...")
    if config.dry_run:
        app.logger.info("updating (dry-run)")
    else:
        controller.update()
    app.logger.info("Controller updated, waiting for next clock...")


@app.route('/configuration', methods=['GET'])
def get_configuration():
    logging.info("get configuration")
    return {"configuration": config.__dict__}, 200


@app.route('/configuration', methods=['POST'])
def configure():
    global status, config

    logging.info("configuration started...")

    # read from configuration
    data = request.get_json()

    if data["control_type"] not in ["CT", "RL"]:
        status = "configuration error"
        logging.info(status)
        return {"result": "error control type"}, 400
    if "dry_run" in data:
        dry_run = data["dry_run"]
    else:
        dry_run = False

    logging.info(type(data["containers_manager"]))

    config = Configuration(containers_manager=data["containers_manager"],
                           requests_store=data["requests_store"],
                           min_cores=data["min_cores"],
                           max_cores=data["max_cores"],
                           control_period=data["control_period"],
                           control_type=data["control_type"],
                           actuator_port=data["actuator_port"],
                           dry_run=dry_run)

    logging.info("Setting models manager to: %s", config.models_endpoint)
    logging.info("Setting containers_manager to: %s", config.containers_endpoint)
    logging.info("Setting requests_store to: %s", config.requests_endpoint)

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/start', methods=['POST'])
def start_controller():
    global status, config, controller

    if config.control_type == "CT":
        controller = ControllerManager(config.models_endpoint,
                                       config.containers_endpoint,
                                       config.requests_endpoint,
                                       config.actuator_port,
                                       config.control_period,
                                       config.min_cores,
                                       config.max_cores)
    else:
        controller = ControllerManagerRules(config.models_endpoint,
                                            config.containers_endpoint,
                                            config.requests_endpoint,
                                            config.actuator_port,
                                            config.control_period,
                                            config.min_cores,
                                            config.max_cores)
    if config.dry_run:
        logging.info("Controller init (dry-run")
    else:
        controller.init()

    sched.add_job(control, 'interval', seconds=config.control_period, id='nodemanager-controller')

    status = "active"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/stop', methods=['POST'])
def stop_controller():
    global sched, status

    if status == "active":
        sched.remove_job('nodemanager-controller')

        status = "configured"
        logging.info(status)

        return {"result": "ok"}, 200


if __name__ == "__main__":
    # init log
    format = "%(threadName)s:%(asctime)s: %(message)s"
    logging.basicConfig(format=format,
                        level=logging.INFO,
                        datefmt="%H:%M:%S")

    sched = BackgroundScheduler()
    sched.start()

    status = "inactive"
    logging.info(status)
    app.run(host='0.0.0.0', port=5003, debug=False)
