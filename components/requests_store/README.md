# Requests Store

This component takes care of requests. It is responsible for storing the information about the requests.

<img src="../../doc/img/RequestsStoreView.png">

This component:

- saves information about requests (with Postgres database)
- produces metrics

## Required interfaces
The controller requires:

- *Containers Manager*: to get information about models


### Example of requests
[More information here](../common/README.md)


## Run
### Init
```
virtualenv env
source env/bin/activate
pip install -r requirements.txt
```
### Start
Start the Postgres DB container
```
docker run --name romadb -e POSTGRES_PASSWORD=romapwd -d -p 5432:5432 postgres
```
Then start the component
```
gunicorn -w <num_workers> "main:create_app(db_echo=False)" --bind 0.0.0.0:5002
```

## Endpoints
See "rest-client.rest" for examples 

DEFAULT PORT: 5001

##### GET /
Get the status of the component

##### GET /requests
Get the requests

##### GET /metrics/model
Get the metrics grouped by model

##### GET /metrics/container
Get the metrics grouped by container

##### POST /requests
Post a request

##### DELETE /request
Delete the requests