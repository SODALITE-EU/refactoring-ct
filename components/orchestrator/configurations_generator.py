from kubernetes import client
from models.container import Container
from models.device import Device
from models.model import Model
from models.configurations import K8sConfiguration


class ConfigurationsGenerator:
    @staticmethod
    def model_list(models_dict):
        models = []
        for model in models_dict:
            m = Model(name=model["name"],
                      version=model["version"],
                      sla=model["sla"],
                      alpha=model["alpha"],
                      tfs_model_url=model["tfs_model_url"],
                      initial_replicas=model["initial_replicas"])
            if "profiled_rt" in model:
                m.profiled_rt = model["profiled_rt"]
            models.append(m)
        return models

    # generate a TF config file from a list of models
    @staticmethod
    def tf_config_generator(models_dict, tf_serving_models_path):
        models = ConfigurationsGenerator.model_list(models_dict)
        config = "model_config_list {\n"
        for model in models:
            config += "\tconfig {\n\t\tname: '" + model.name + "'\n\t\tbase_path: '" + \
                      tf_serving_models_path + model.name + "/" + "'\n\t\tmodel_platform: 'tensorflow'\n\t}\n "
        config += "}"

        return config

    # generate a K8s deployment and service
    @staticmethod
    def k8s_config_generator(k8s_config: K8sConfiguration, logging):
        # generate deployment
        containers, deployment = ConfigurationsGenerator.k8s_deployment_generator(k8s_config)
        # generate service
        service = ConfigurationsGenerator.k8s_service_generator(k8s_config)

        return containers, deployment, service

    # generate a K8s deployment
    @staticmethod
    def k8s_deployment_generator(k8s_config: K8sConfiguration):
        # add containers
        containers = []
        k8s_containers = []
        # add actuator container
        k8s_container = client.V1Container(name="nodemanager-actuator",
                                           image=k8s_config.actuator_image,
                                           ports=[client.V1ContainerPort(container_port=k8s_config.actuator_port)],
                                           volume_mounts=[client.V1VolumeMount(name="docker-sock",
                                                                               mount_path="/var/run")],
                                           image_pull_policy=k8s_config.k8s_image_pull_policy)
        k8s_containers.append(k8s_container)

        # add CPU containers
        base_port = 8501
        for i, model in enumerate(ConfigurationsGenerator.model_list(k8s_config.models)):
            container_name = "nodemanager-rest-cpu-" + str(i + 1)
            k8s_container = client.V1Container(name=container_name,
                                               image=k8s_config.tfs_image,
                                               args=["--model_config_file=" + k8s_config.tfs_config_file_name,
                                                     "--rest_api_port=" + str(base_port)],
                                               ports=[client.V1ContainerPort(container_port=base_port)],
                                               volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                   mount_path=k8s_config.tfs_models_path)])
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
        for gpu in range(k8s_config.available_gpus):
            container_name = "nodemanager-rest-gpu-" + str(gpu + 1)
            k8s_container = client.V1Container(name=container_name,
                                               image=k8s_config.tfs_image + "-gpu",
                                               args=["--model_config_file=" + k8s_config.tfs_config_file_name,
                                                     "--rest_api_port=" + str(base_port)],
                                               ports=[client.V1ContainerPort(container_port=base_port)],
                                               volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                   mount_path=k8s_config.tfs_models_path)],
                                               env=[client.V1EnvVar(name="NVIDIA_VISIBLE_DEVICES", value=str(gpu + 1))])
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
        volumes = [client.V1Volume(name="docker-sock",
                                   host_path=client.V1HostPathVolumeSource(path="/var/run")),
                   client.V1Volume(name="shared-models",
                                   empty_dir=client.V1EmptyDirVolumeSource())]

        # set pod affinity
        affinity = client.V1Affinity(pod_anti_affinity=client.V1PodAffinity(required_during_scheduling_ignored_during_execution=[client.V1PodAffinityTerm(topology_key="kubernetes.io/hostname")]))

        # init containers
        init_containers = []
        for i, model in enumerate(ConfigurationsGenerator.model_list(k8s_config.models)):
            container_name = "tfs-init-" + str(i + 1)
            init_containers.append(client.V1Container(name=container_name,
                                                      image=k8s_config.tfs_init_image,
                                                      args=["-c", k8s_config.tfs_config_endpoint,
                                                            "-m", model.tfs_model_url],
                                                      image_pull_policy=k8s_config.k8s_image_pull_policy,
                                                      volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                          mount_path=k8s_config.tfs_models_path)]))

        # add pod spec
        pod_spec = client.V1PodSpec(containers=k8s_containers,
                                    volumes=volumes,
                                    affinity=affinity,
                                    init_containers=init_containers,
                                    host_network=k8s_config.k8s_host_network,
                                    dns_policy="Default")
        # add pod template spec
        pod_template_spec = client.V1PodTemplateSpec(metadata=client.V1ObjectMeta(labels={"run": "nodemanager"}),
                                                     spec=pod_spec)
        # add deployment spec
        deployment_spec = client.V1DeploymentSpec(selector=client.V1LabelSelector(match_labels={"run": "nodemanager"}),
                                                  template=pod_template_spec,
                                                  replicas=k8s_config.initial_replicas)
        # build deployment
        deployment = client.V1Deployment(api_version="apps/v1",
                                         kind="Deployment",
                                         metadata=client.V1ObjectMeta(name="nodemanager-deploy",
                                                                      labels={"run": "nodemanager"}),
                                         spec=deployment_spec)

        return containers, deployment

    # generate a K8s deployment
    @staticmethod
    def k8s_service_generator(k8s_config: K8sConfiguration):
        ports = []

        # add actuator port
        port = client.V1ServicePort(name="nodemanager-actuator",
                                    port=k8s_config.actuator_port,
                                    target_port=k8s_config.actuator_port)
        ports.append(port)

        # add CPU ports
        base_port = 8501
        for i, model in enumerate(k8s_config.models):
            port = client.V1ServicePort(name="nodemanager-rest-cpu-" + str(i + 1),
                                        port=base_port,
                                        target_port=base_port)
            ports.append(port)
            base_port += 1

        # add GPU ports
        for gpu in range(k8s_config.available_gpus):
            port = client.V1ServicePort(name="nodemanager-rest-gpu-" + str(gpu + 1),
                                        port=base_port,
                                        target_port=base_port)
            ports.append(port)
            base_port += 1

        service_spec = client.V1ServiceSpec(type=k8s_config.k8s_service_type,
                                            ports=ports,
                                            selector={"run": "nodemanager"})

        service = client.V1Service(api_version="v1",
                                   kind="Service",
                                   metadata=client.V1ObjectMeta(name="nodemanager-svc",
                                                                labels={"run": "nodemanager-svc"}),
                                   spec=service_spec)

        return service
