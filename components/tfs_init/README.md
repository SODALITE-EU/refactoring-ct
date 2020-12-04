# TensorFlow Serving Init
This container

- create the models folder
- download a ```tar.gz``` archive from the given url
- download the TensorFlow Serving configuration file from the given URL

Run:
```
./main.sh -c localhost:5000/configuration/tfs \
    -f /home/user/models \
    -m https://github.com/NicholasRasi/NodeManagerTestModels/archive/v1.tar.gz
```

With Docker:
```
docker run nodemanager-tfs-init:local -c localhost:5000/configuration/tfs \
    -f /home/user/models \
    -m https://github.com/NicholasRasi/NodeManagerTestModels/archive/v1.tar.gz
```