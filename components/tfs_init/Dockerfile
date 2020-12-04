FROM alpine
COPY . /home
RUN apk --no-cache add jq
ENTRYPOINT ["/home/main.sh"]