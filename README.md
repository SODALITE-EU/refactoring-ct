# Architecture Details
<img src="./doc/img/GeneralView.png">

## Components
### Dispatcher
This component takes as input requests and dispatches them to devices.

[More](./components/dispatcher/)

### Containers Manager
This component manages containers and models and all their relative information.

[More](./components/containers_manager/)

### Requests Store
This component takes care of requests. It is responsible for storing the information about the requests.

[More](./components/requests_store/)

### Controller
(not implemented yet)

This component interacts with the actuator to control nodes.

[More](./components/controller/)

### Actuator
This component is used to control the resources of nodes.

[More](./components/actuator/)

### Dashboard
This component is used to reach a dashboard where information about the system can be retrieved.

[More](./components/dashboard/)


## Deployments
K8s files to deploy the system.

[More](./deployments/)

## Models
The models served by the system.

[More](./models/)

## Testing
Test files

[More](./testing/)