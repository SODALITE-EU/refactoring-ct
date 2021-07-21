#!/bin/bash
# example usage: export ROMA_MODEL="skyline-extraction" && export ROMA_REPS=5 && export ROMA_PARAMS="p1-skyline.yml" && export ROMA_RS="20.86.175.19:5002" && ./repeat.sh
MODEL="${ROMA_MODEL:=''}"
REPS="${ROMA_REPS:=5}"
PAR_FILE="${ROMA_PARAMS:='params.yml'}"
REQ_STORE="${ROMA_RS:=''}"


source env/bin/activate

echo "Starting benchmarks"
for (( i = 1; i <= $REPS; i++ ))
do
  OUTPUT_FILE="benchmark_${MODEL}_$i.out"
	echo "Rep $i, params: $PAR_FILE, output file: $OUTPUT_FILE"
	python main.py -p $PAR_FILE -o $OUTPUT_FILE
	echo "Wait..."
	sleep 5
	echo "Delete requests"
	curl -X DELETE --location "http://$REQ_STORE/requests" -H "Accept: application/json"
done
