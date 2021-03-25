FROM python:3.7-alpine
ADD . /
RUN pip install -r requirements.txt
EXPOSE 8000
CMD gunicorn -w 10 "main:create_app(delete_config=True)" --bind 0.0.0.0:8000