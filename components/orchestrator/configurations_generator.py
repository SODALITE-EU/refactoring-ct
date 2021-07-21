from kubernetes import client
from models.container import Container
from models.device import Device
from models.model import Model
from models.configurations import K8sConfiguration


class ConfigurationsGenerator:
    base_cpu_cont_name = "nodemanager-rest-cpu-"
    base_gpu_cont_name = "nodemanager-rest-gpu-"
    base_cpu_svc_name = "nodemanager-svc-"
    base_gpu_svc_name = "nodemanager-svc-gpu-"
    base_cpu_cont_port = 8501
    base_gpu_cont_port = 8601

    @staticmethod
    def model_list(models_dict):
        models = []
        for model in models_dict:
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
        return models

    # generate a TF config file from a list of models
    @staticmethod
    def tf_config_generator(models, tf_serving_models_path):
        config = "model_config_list {\n"

        # generate single model config files
        for model in models:
            config += "\tconfig {\n\t\tname: '" + model.name + "'\n\t\tbase_path: '" + \
                      tf_serving_models_path + model.name + "/" + "'\n\t\tmodel_platform: 'tensorflow'\n\t}\n "
        config += "}"

        return config

    # generate a K8s daemonset and service for Actuator
    @staticmethod
    def k8s_actuator_config_generator(k8s_config: K8sConfiguration, logging):
        # generate actuator daemonset
        actuator_daemonset = ConfigurationsGenerator.k8s_actuator_daemonset_generator(k8s_config)

        # generate actuator service
        actuator_service = ConfigurationsGenerator.k8s_actuator_service_generator(k8s_config)

        return actuator_daemonset, actuator_service

    # generate K8s deployments and services for models on CPUs
    @staticmethod
    def k8s_models_cpu_config_generator(models, k8s_config: K8sConfiguration, logging):
        # generate models deployments
        models_deployment = ConfigurationsGenerator.k8s_models_cpu_deployments_generator(models, k8s_config)

        # generate models services
        models_services = ConfigurationsGenerator.k8s_models_cpu_services_generator(models, k8s_config)

        return models_deployment, models_services

    # generate K8s deployments and services for models on GPUs
    @staticmethod
    def k8s_models_gpu_config_generator(gpu_models, k8s_config: K8sConfiguration, logging):
        # generate models deployments
        models_deployment = ConfigurationsGenerator.k8s_models_gpu_deployments_generator(gpu_models, k8s_config)

        # generate models services
        models_services = ConfigurationsGenerator.k8s_models_gpu_services_generator(gpu_models, k8s_config)

        return models_deployment, models_services

    # generate K8s daemonset for Actuator
    @staticmethod
    def k8s_actuator_daemonset_generator(k8s_config: K8sConfiguration):
        # add actuator container
        actuator_container = client.V1Container(name="nodemanager-actuator",
                                                image=k8s_config.actuator_image,
                                                ports=[client.V1ContainerPort(container_port=k8s_config.actuator_port)],
                                                volume_mounts=[client.V1VolumeMount(name="docker-sock",
                                                                                    mount_path="/var/run")],
                                                image_pull_policy=k8s_config.k8s_image_pull_policy)

        # add volumes
        volumes = [client.V1Volume(name="docker-sock",
                                   host_path=client.V1HostPathVolumeSource(path="/var/run"))]

        # add pod spec
        pod_spec = client.V1PodSpec(containers=[actuator_container],
                                    volumes=volumes,
                                    host_network=k8s_config.k8s_host_network,
                                    dns_policy="Default")

        # add pod template spec
        pod_template_spec = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"run": "nodemanager-actuator"}),
            spec=pod_spec)
        # add deployment spec with requested replicas
        daemonset_spec = client.V1DaemonSetSpec(
            selector=client.V1LabelSelector(match_labels={"run": "nodemanager-actuator"}),
            template=pod_template_spec)
        # build deployment
        daemonset = client.V1DaemonSet(api_version="apps/v1",
                                       kind="DaemonSet",
                                       metadata=client.V1ObjectMeta(
                                           name="nodemanager-actuator-daemonset",
                                           labels={"run": "nodemanager"}),
                                       spec=daemonset_spec)

        return daemonset

    # generate K8s deployments for models on CPUs
    @staticmethod
    def k8s_models_cpu_deployments_generator(models, k8s_config: K8sConfiguration):
        deployments = []
        base_port = ConfigurationsGenerator.base_cpu_cont_port

        # build deployments for CPUs (one for each application)
        for i, model in enumerate(models):
            # add CPU TF container serving only the model
            container_name = ConfigurationsGenerator.base_cpu_cont_name + str(model.name)
            model_container = client.V1Container(name=container_name,
                                                 image=k8s_config.tfs_image,
                                                 args=["--model_name=" + model.name,
                                                       "--model_base_path=" + k8s_config.tfs_models_path + model.name,
                                                       "--rest_api_port=" + str(base_port)],
                                                 ports=[client.V1ContainerPort(container_port=base_port)],
                                                 volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                     mount_path=k8s_config.tfs_models_path)])

            # add volumes
            volumes = [client.V1Volume(name="shared-models",
                                       empty_dir=client.V1EmptyDirVolumeSource())]

            # init container (download the model)
            container_name = "tfs-init-" + str(model.name)
            init_container = client.V1Container(name=container_name,
                                                image=k8s_config.tfs_init_image,
                                                args=["-f" + k8s_config.tfs_models_path,
                                                      "-d" + k8s_config.tfs_models_path + model.name,
                                                      "-m" + model.tfs_model_url],
                                                image_pull_policy=k8s_config.k8s_image_pull_policy,
                                                volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                    mount_path=k8s_config.tfs_models_path)])

            # set pod affinity (this ensures pods will land on separate hosts) https://minikube.sigs.k8s.io/docs/tutorials/multi_node/
            node_affinity = None
            if k8s_config.available_gpus > 0:
                node_affinity = client.V1NodeAffinity(
                    required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                        node_selector_terms=[client.V1NodeSelectorTerm(
                            match_expressions=[client.V1NodeSelectorRequirement(key="kubernetes.io/hostname",
                                                                                operator="NotIn",
                                                                                values=["gpuw-" + str(i) for i in range(1, k8s_config.available_gpus + 1)])]
                        )]))

            affinity = client.V1Affinity(pod_anti_affinity=client.V1PodAntiAffinity(
                required_during_scheduling_ignored_during_execution=[
                    client.V1PodAffinityTerm(topology_key="kubernetes.io/hostname",
                                             label_selector=client.V1LabelSelector(
                                                 match_expressions=[client.V1LabelSelectorRequirement(key="run",
                                                                                                      operator="In",
                                                                                                      values=["nodemanager-cpu-" + str(model.name)])]))
                ]), node_affinity=node_affinity)

            # add pod spec
            pod_spec = client.V1PodSpec(containers=[model_container],
                                        volumes=volumes,
                                        affinity=affinity,
                                        init_containers=[init_container],
                                        host_network=k8s_config.k8s_host_network,
                                        dns_policy="Default")

            # add pod template spec
            pod_template_spec = client.V1PodTemplateSpec(metadata=client.V1ObjectMeta(labels={"run": "nodemanager-cpu-" + str(model.name)}),
                                                         spec=pod_spec)
            # add deployment spec with requested replicas
            deployment_spec = client.V1DeploymentSpec(selector=client.V1LabelSelector(match_labels={"run": "nodemanager-cpu-" + str(model.name)}),
                                                      template=pod_template_spec,
                                                      replicas=model.required_cpus)
            # build deployment
            deployment = client.V1Deployment(api_version="apps/v1",
                                             kind="Deployment",
                                             metadata=client.V1ObjectMeta(name="nodemanager-deployment-cpu-" + str(model.name),
                                                                          labels={"run": "nodemanager"}),
                                             spec=deployment_spec)
            deployments.append(deployment)

            # increment port
            base_port += 1

        return deployments

    # generate K8s deployments for models on GPUs
    @staticmethod
    def k8s_models_gpu_deployments_generator(gpu_models, k8s_config: K8sConfiguration):
        # add containers
        deployments = []
        base_port = ConfigurationsGenerator.base_gpu_cont_port

        # build deployments for GPUs
        for i, models in enumerate(gpu_models):
            # add GPU TF container serving only the model
            container_name = ConfigurationsGenerator.base_gpu_cont_name + str(i)
            model_container = client.V1Container(name=container_name,
                                                 image=k8s_config.tfs_image,
                                                 args=["--model_config_file=" + k8s_config.tfs_models_path + "gpu-" + str(i) + ".config",
                                                       "--rest_api_port=" + str(base_port)],
                                                 ports=[client.V1ContainerPort(container_port=base_port)],
                                                 volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                     mount_path=k8s_config.tfs_models_path)],
                                                 resources=client.V1ResourceRequirements(limits={"nvidia.com/gpu": 1}))

            # add volumes
            volumes = [client.V1Volume(name="shared-models",
                                       empty_dir=client.V1EmptyDirVolumeSource())]

            # init container (download the model)
            init_containers = []
            for model in models:
                container_name = "tfs-init-" + str(model.name)
                init_container = client.V1Container(name=container_name,
                                                    image=k8s_config.tfs_init_image,
                                                    args=["-f" + k8s_config.tfs_models_path,
                                                          "-d" + k8s_config.tfs_models_path + model.name,
                                                          "-m" + model.tfs_model_url,
                                                          "-c" + k8s_config.tfs_config_endpoint + str(i),
                                                          "-n" + "gpu-" + str(i) + ".config"],
                                                    image_pull_policy=k8s_config.k8s_image_pull_policy,
                                                    volume_mounts=[client.V1VolumeMount(name="shared-models",
                                                                                        mount_path=k8s_config.tfs_models_path)])
                init_containers.append(init_container)


            # add pod spec
            pod_spec = client.V1PodSpec(containers=[model_container],
                                        volumes=volumes,
                                        init_containers=init_containers,
                                        host_network=k8s_config.k8s_host_network,
                                        dns_policy="Default")

            # add pod template spec
            pod_template_spec = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"run": "nodemanager-gpu-" + str(i)}),
                spec=pod_spec)
            # add deployment spec
            deployment_spec = client.V1DeploymentSpec(
                selector=client.V1LabelSelector(match_labels={"run": "nodemanager-gpu-" + str(i)}),
                template=pod_template_spec,
                replicas=1)
            # build deployment
            deployment = client.V1Deployment(api_version="apps/v1",
                                             kind="Deployment",
                                             metadata=client.V1ObjectMeta(
                                                 name="nodemanager-deployment-gpu-" + str(i),
                                                 labels={"run": "nodemanager"}),
                                             spec=deployment_spec)
            deployments.append(deployment)

            # increment port
            base_port += 1

        return deployments

    # generate K8s service for actuator
    @staticmethod
    def k8s_actuator_service_generator(k8s_config: K8sConfiguration):
        actuator_port = client.V1ServicePort(name="nodemanager-actuator-port",
                                             port=k8s_config.actuator_port,
                                             target_port=k8s_config.actuator_port)

        service_spec = client.V1ServiceSpec(type=k8s_config.k8s_service_type,
                                            ports=[actuator_port],
                                            selector={"run": "nodemanager-actuator"})

        service = client.V1Service(api_version="v1",
                                   kind="Service",
                                   metadata=client.V1ObjectMeta(name="nodemanager-svc-actuator",
                                                                labels={"run": "nodemanager-svc-actuator"}),
                                   spec=service_spec)

        return service

    # generate K8s services for models on GPUs
    @staticmethod
    def k8s_models_cpu_services_generator(models, k8s_config: K8sConfiguration):
        services = []
        base_port = ConfigurationsGenerator.base_cpu_cont_port

        for i, model in enumerate(models):
            # add CPU port
            model_cpu_port = client.V1ServicePort(name="nodemanager-rest-cpu-" + str(model.name),
                                                  port=base_port,
                                                  target_port=base_port)

            service_spec = client.V1ServiceSpec(type=k8s_config.k8s_service_type,
                                                ports=[model_cpu_port],
                                                selector={"run": "nodemanager-cpu-" + str(model.name)})

            service = client.V1Service(api_version="v1",
                                       kind="Service",
                                       metadata=client.V1ObjectMeta(name=ConfigurationsGenerator.base_cpu_svc_name + str(model.name),
                                                                    labels={"run": "nodemanager-svc-" + str(model.name)}),
                                       spec=service_spec)

            services.append(service)

            # increment port
            base_port += 1

        return services


    # generate K8s services for GPUs
    @staticmethod
    def k8s_models_gpu_services_generator(gpu_models, k8s_config: K8sConfiguration):
        services = []
        base_port = ConfigurationsGenerator.base_gpu_cont_port

        for i, model in enumerate(gpu_models):
            # add GPU port
            model_gpu_port = client.V1ServicePort(name="nodemanager-rest-gpu-" + str(i),
                                                  port=base_port,
                                                  target_port=base_port)

            service_spec = client.V1ServiceSpec(type=k8s_config.k8s_service_type,
                                                ports=[model_gpu_port],
                                                selector={"run": "nodemanager-gpu-" + str(i)})

            service = client.V1Service(api_version="v1",
                                       kind="Service",
                                       metadata=client.V1ObjectMeta(name=ConfigurationsGenerator.base_gpu_svc_name + str(i),
                                                                    labels={
                                                                        "run": "nodemanager-svc-gpu-" + str(i)}),
                                       spec=service_spec)

            services.append(service)

            # increment port
            base_port += 1

        return services
