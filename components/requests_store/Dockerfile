FROM python:3.7-alpine
ADD . /
RUN pip install -r requirements.txt
EXPOSE 5002
CMD python main.py --containers_manager "http://containers_manager:5001"