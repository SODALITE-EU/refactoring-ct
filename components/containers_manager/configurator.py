from kubernetes import client
from models.container import Container
from models.device import Device

class Configurator:

    # generate a TF config file from a list of models
    @staticmethod
    def tf_config_generator(models, tf_serving_models_path):
        config = "model_config_list {\n"
        for model in models:
            config += "\tconfig {\n\t\tname: '" + model.name + "'\n\t\tbase_path: '" + \
                      tf_serving_models_path + model.name + "/" + "'\n\t\tmodel_platform: 'tensorflow'\n\t}\n "
        config += "}"

        return config

    # generate a K8s deployment and service
    @staticmethod
    def k8s_config_generator(workers, models, available_gpus, actuator_image, actuator_port, k8s_service_type,
                             tf_serving_models_path, tf_serving_config_file_name):
        # generate deployment
        containers, deployment = Configurator.k8s_deployment_generator(models, actuator_image, available_gpus,
                                                                       tf_serving_config_file_name,
                                                                       tf_serving_models_path, workers, actuator_port)
        # generate service
        service = Configurator.k8s_service_generator(models, available_gpus, k8s_service_type, actuator_port)

        return containers, deployment, service

    # generate a K8s deployment
    @staticmethod
    def k8s_deployment_generator(models, actuator_image, available_gpus, tf_serving_config_file_name,
                                 tf_serving_models_path, workers, actuator_port):

        # add containers
        containers = []
        k8s_containers = []
        # add actuator container
        k8s_container = client.V1Container(name="nodemanager-actuator",
                                           image=actuator_image,
                                           ports=[client.V1ContainerPort(container_port=actuator_port)],
                                           volume_mounts=[client.V1VolumeMount(name="docker-sock",
                                                                               mount_path="/var/run")])
        k8s_containers.append(k8s_container)

        # add CPU containers
        base_port = 8501
        for i, model in enumerate(models):
            container_name = "nodemanager-rest-cpu-" + str(i + 1)
            k8s_container = client.V1Container(name=container_name,
                                               image="tensorflow/serving:latest",
                                               args=["--model_config_file=" + tf_serving_config_file_name,
                                                     "--rest_api_port=" + str(base_port)],
                                               ports=[client.V1ContainerPort(container_port=base_port)],
                                               volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                   mount_path=tf_serving_models_path)])
            k8s_containers.append(k8s_container)
            containers.append(Container(model=model.name,
                                        version=model.version,
                                        active=False,
                                        container=container_name,
                                        node=None,
                                        port=base_port,
                                        device=Device.CPU,
                                        quota=None))
            base_port += 1

        # add GPU containers
        for gpu in range(available_gpus):
            container_name = "nodemanager-rest-gpu-" + str(gpu + 1)
            k8s_container = client.V1Container(name=container_name,
                                               image="tensorflow/serving:latest-gpu",
                                               args=["--model_config_file=" + tf_serving_config_file_name,
                                                     "--rest_api_port=" + str(base_port)],
                                               ports=[client.V1ContainerPort(container_port=base_port)],
                                               volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                   mount_path=tf_serving_models_path)],
                                               env=[client.V1EnvVar(name="NVIDIA_VISIBLE_DEVICES",
                                                                    value=str(gpu + 1))])
            k8s_containers.append(k8s_container)
            containers.append(Container(model="all",
                                        version=1,
                                        active=False,
                                        container=container_name,
                                        node=None,
                                        port=base_port,
                                        device=Device.GPU,
                                        quota=None))
            base_port += 1

        # add volumes
        volumes = [client.V1Volume(name="shared-models",
                                   host_path=client.V1HostPathVolumeSource(path=tf_serving_models_path)),
                   client.V1Volume(name="docker-sock",
                                   host_path=client.V1HostPathVolumeSource(path="/var/run"))]

        # set pod affinity
        affinity = client.V1Affinity(pod_anti_affinity=client.V1PodAffinity(required_during_scheduling_ignored_during_execution=[client.V1PodAffinityTerm(topology_key="kubernetes.io/hostname")]))

        # add pod spec
        pod_spec = client.V1PodSpec(containers=k8s_containers,
                                    volumes=volumes,
                                    affinity=affinity)
        # add pod template spec
        pod_template_spec = client.V1PodTemplateSpec(metadata=client.V1ObjectMeta(labels={"run": "nodemanager"}),
                                                     spec=pod_spec)
        # add deployment spec
        deployment_spec = client.V1DeploymentSpec(selector=client.V1LabelSelector(match_labels={"run": "nodemanager"}),
                                                  template=pod_template_spec,
                                                  replicas=workers)
        # build deployment
        deployment = client.V1Deployment(api_version="apps/v1",
                                         kind="Deployment",
                                         metadata=client.V1ObjectMeta(name="nodemanager-deploy",
                                                                      labels={"run": "nodemanager"}),
                                         spec=deployment_spec)

        return containers, deployment

    # generate a K8s deployment
    @staticmethod
    def k8s_service_generator(models, available_gpus, k8s_service_type, actuator_port):
        ports = []

        # add actuator port
        port = client.V1ServicePort(name="nodemanager-actuator",
                                    port=actuator_port,
                                    target_port=actuator_port)
        ports.append(port)

        # add CPU ports
        base_port = 8501
        for i, model in enumerate(models):
            port = client.V1ServicePort(name="nodemanager-rest-cpu-" + str(i + 1),
                                        port=base_port,
                                        target_port=base_port)
            ports.append(port)
            base_port += 1

        # add GPU ports
        for gpu in range(available_gpus):
            port = client.V1ServicePort(name="nodemanager-rest-gpu-" + str(gpu + 1),
                                        port=base_port,
                                        target_port=base_port)
            ports.append(port)
            base_port += 1

        service_spec = client.V1ServiceSpec(type=k8s_service_type,
                                            ports=ports,
                                            selector={"run": "nodemanager"})

        service = client.V1Service(api_version="v1",
                                   kind="Service",
                                   metadata=client.V1ObjectMeta(name="nodemanager-svc",
                                                                labels={"run": "nodemanager-svc"}),
                                   spec=service_spec)

        return service
