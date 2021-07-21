from flask import Flask, jsonify
from flask import request
import logging
import requests
from flask_cors import CORS
from models.device import Device
from models.model import Model
from models.container import Container
from models.configurations import ContainersManagerConfiguration

app = Flask(__name__)
CORS(app)

config = None
models = []
containers = []


@app.route('/', methods=['GET'])
def get_status():
    return {"status": status}


@app.route('/containers', methods=['GET', 'PATCH'])
def get_update_containers():
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
                app.logger.info("Container %s updated", data["container_id"])
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
def models_endpoint():
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
    global status, models, containers, config

    logging.info("configuration started...")

    # read data
    data = request.get_json()
    config = ContainersManagerConfiguration(json_data=data)
    logging.info("configuration: %s", str(config.__dict__))

    # build models and containers list
    # models
    if config.models:
        logging.info("Found %d models from configuration", len(config.models))
        for model in config.models:
            m = Model(name=model["name"],
                      version=model["version"],
                      sla=model["sla"],
                      alpha=model["alpha"],
                      tfs_model_url=model["tfs_model_url"],
                      required_cpus=model["required_cpus"],
                      required_gpus=model["required_gpus"])
            if "profiled_rt" in model:
                m.profiled_rt = model["profiled_rt"]
            models.append(m)

    logging.info("+ %d models", len(models))

    # containers
    if config.containers:
        logging.info("Found %d containers from configuration", len(config.containers))
        for container in config.containers:
            containers.append(
                Container(container["model"],
                          container["version"],
                          container["active"],
                          container["container"],
                          container["node"],
                          container["port"],
                          container["device"],
                          container["quota"]))
    logging.info("+ %d CPU containers", len(list(filter(lambda m: m.device == Device.CPU, containers))))
    logging.info("+ %d GPU containers", len(list(filter(lambda m: m.device == Device.GPU, containers))))
    logging.info([container.to_json() for container in containers])

    status = "configured"
    logging.info(status)

    return {"result": "ok"}, 200


@app.route('/start', methods=['POST'])
def start():
    global status

    # link containers (get containers IDs)
    status = "linking"
    logging.info(status)
    containers_linking()

    # set initial CPU quota
    status = "quota reset"
    logging.info(status)
    quota_reset()

    status = "active"
    logging.info(status)

    return {"result": "ok"}, 200


def containers_linking():
    """
    Link containers with ids
    """
    global containers

    # get the set of nodes
    nodes = set(map(lambda c: c.node, containers))
    logging.info("Nodes: %s", nodes)

    # get the list of running containers for every node
    for node in nodes:
        containers_on_node = list(filter(lambda c: c.node == node, containers))

        try:
            response = requests.get("http://" + node + ":" + str(config.actuator_port) + config.container_list_endpoint)
            logging.info("Response: %d %s", response.status_code, response.text)

            if response.ok:
                # get the containers from the response
                running_containers = response.json()
                logging.info("Found %d containers on node %s", len(running_containers), node)

                # set the containers id
                linked_containers = 0
                for container in containers_on_node:
                    for running_container in running_containers:
                        if container.container == running_container["container_name"]:
                            container.container_id = running_container["id"]
                            logging.info("+ link: %s <-> %s", container.model, container.container_id)
                            linked_containers = linked_containers + 1
                            break
                logging.info("Linked %d containers on node %s",
                             linked_containers, node)
            else:
                # disable model if actuator_controller response status is not 200
                logging.info("No containers found on node %s, (response not ok)", node)
                for container in containers_on_node:
                    container.active = False

        except Exception as e:
            logging.warning("Disabling containers for node: %s because %s", node, e)

            # disable containers if actuator_controller not reachable
            for container in containers_on_node:
                container.active = False

            break


def quota_reset():
    """
    Set a default number of cores for all the containers
    """
    global containers

    logging.info("setting default cores for all containers to: %d", config.init_quota)
    for container in containers:
        if container.device == Device.CPU:
            response = requests.post("http://" + container.node + ":" + str(config.actuator_port) +
                                     config.container_list_endpoint + "/" + container.container_id,
                                     json={"cpu_quota": int(config.init_quota * 100000)})
            logging.info("actuator response: %s", response.text)
            container.quota = int(config.init_quota * 100000)


if __name__ == "__main__":
    # init log
    log_format = "%(asctime)s:%(levelname)s:%(name)s:" \
                 "%(filename)s:%(lineno)d:%(message)s"
    logging.basicConfig(level='DEBUG', format=log_format)

    # start
    status = "inactive"
    logging.info(status)
    app.run(host='0.0.0.0', port=5001)
