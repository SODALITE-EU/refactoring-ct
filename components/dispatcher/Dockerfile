FROM python:3.7-alpine
ADD . /
RUN pip install -r requirements.txt
EXPOSE 8000
CMD gunicorn -w 10 "main:create_app(containers_manager='http://containers_manager:5001',requests_store='http://requests_store:5002',gpu_queues_policy=2,max_polling=1,max_consumers_cpu=50,max_log_consumers=6)" --bind 0.0.0.0:8000