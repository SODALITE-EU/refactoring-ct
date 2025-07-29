FROM python:3.14.0rc1-alpine

COPY . /app

WORKDIR /app

RUN pip install -r requirements.txt

ENV FLASK_DEBUG 1

EXPOSE 5000

CMD [ "python", "main.py" ]