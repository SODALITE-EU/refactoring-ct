FROM python:3.7-alpine
ADD . /
RUN pip install -r requirements.txt
EXPOSE 5003
CMD python main.py --containers_manager "http://containers_manager:5001" --requests_store "http://requests_store:5002" --min_c 1 --max_c 6 --time 5.0 --actuator_port 5000