import logging
from flask import request
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS
from controller_manager import ControllerManager
from controller_manager_2 import ControllerManager2
from controller_manager_rules import ControllerManagerRules
from models.configurations import ControllerConfiguration
import datetime
import time

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
    from_ts = request.args.get('from_ts') or 0.0
    app.logger.info("Getting logs from " + str(from_ts))
    if controller:
        return jsonify(controller.get_logs(from_ts=from_ts))
    else:
        return {}, 200


def control():
    app.logger.info("Controller updating...")
    if config.dry_run:
        app.logger.info("updating (dry-run)")
        controller.logs.append({"ts": time.time(), "date": str(datetime.datetime.now()), "msg": "updating (dry-run)"})
    else:
        controller.update()
    app.logger.info("Controller updated, waiting for next clock...")


@app.route('/configuration', methods=['GET'])
def get_configuration():
    logging.info("get configuration")
    if config:
        return {"configuration": config.__dict__}, 200
    else:
        logging.warning("configuration not found")
        return {"configuration": "not found"}, 400


@app.route('/configuration', methods=['POST'])
def configure():
    global status, config

    logging.info("configuration started...")

    # read from configuration
    data = request.get_json()
    config = ControllerConfiguration(json_data=data)

    logging.info("Setting models manager to: %s", config.models_endpoint)
    logging.info("Setting containers_manager to: %s", config.containers_endpoint)
    logging.info("Setting requests_store to: %s", config.requests_endpoint)

    status = "configured"
    logging.info(status)

    logging.info("configuration: " + str(config.__dict__))

    return {"result": "ok"}, 200


@app.route('/start', methods=['POST'])
def start_controller():
    global status, config, controller

    if config.control_type == "CT":
        controller = ControllerManager(config.models_endpoint,
                                       config.containers_endpoint,
                                       config.requests_store,
                                       config.actuator_port,
                                       config.window_time,
                                       config.min_cores,
                                       config.max_cores)
    elif config.control_type == "CT2":
        controller = ControllerManager2(config.models_endpoint,
                                        config.containers_endpoint,
                                        config.requests_store,
                                        config.actuator_port,
                                        config.control_period,
                                        config.min_cores,
                                        config.max_cores)
    else:
        controller = ControllerManagerRules(config.models_endpoint,
                                            config.containers_endpoint,
                                            config.requests_store,
                                            config.actuator_port,
                                            config.window_time,
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
