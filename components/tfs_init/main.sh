#!/bin/sh
PROGNAME=$0

usage() {
  cat << EOF >&2
Usage: $PROGNAME [-f <path>] -m <url> -c <url>

-f <path>: folder where to save the downloaded models
 -m <url>: URL where to download the models archive
 -c <url>: URL where to download the TF Serving config file
EOF
  exit 1
}

echo "TF Serving init"
models_dir="/home/models"

while getopts ":f:m:c:" o; do
    case "${o}" in
        f) models_dir=$OPTARG;;
        m) models_url=$OPTARG;;
        c) config_url=$OPTARG;;
        *) usage;;
    esac
done
shift $((OPTIND-1))

if [ ! "$models_url" ] || [ ! "$config_url" ]
then
    usage
fi


echo "creating models dir in $models_dir"
mkdir -p $models_dir

echo "downloading models from $models_url"
wget -c $models_url -O - | tar -xz -C $models_dir --strip-components 1

echo "downloading TF Serving config file from $config_url"
config_resp=$(wget -c $config_url -q -O -)

echo "response: $config_resp"
config=$(echo $config_resp | jq -r '.configuration')

echo "writing to file config: $config"
printf '%s' "$config" > $models_dir/tf_serving_models.config
