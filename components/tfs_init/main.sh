#!/bin/sh
PROGNAME=$0

usage() {
  cat << EOF >&2
Usage: $PROGNAME [-f <path> -c <url> -n <name>] -d <path> -m <url>

 -f <path>: folder where to save the config file
 -d <path>: folder where to save the downloaded model
 -m <url>: URL where to download the models archive
 -c <url>: URL where to download the TF Serving config file
 -n <name>: config file name
EOF
  exit 1
}

echo "TF Serving init"
models_dir="/home/models"

while getopts ":f:d:m:c:n:" o; do
    case "${o}" in
        f) models_dir=$OPTARG;;
        d) model_dir=$OPTARG;;
        m) models_url=$OPTARG;;
        c) config_url=$OPTARG;;
        n) config_filename=$OPTARG;;
        *) usage;;
    esac
done
shift $((OPTIND-1))

if [ ! "$models_url" ]
then
    usage
fi

echo "creating models dir in $models_dir"
mkdir -p $models_dir

echo "creating model dir in $model_dir"
mkdir -p $model_dir

echo "downloading models from $models_url"
wget -c $models_url -O - | tar -xz -C $model_dir --strip-components 2

if [ "$config_url" ] || [ "$config_filename" ]
then
    echo "downloading TF Serving config file from $config_url"
    config_resp=$(wget -c $config_url -q -O -)

    echo "response: $config_resp"
    config=$(echo $config_resp | jq -r '.configuration')

    echo "writing to file config: $config"
    printf '%s' "$config" > $models_dir$config_filename
fi
