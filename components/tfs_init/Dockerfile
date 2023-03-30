FROM alpine:3.17.3
COPY . /home
RUN apk --no-cache add jq
RUN ["chmod", "+x", "/home/main.sh"]
ENTRYPOINT ["/home/main.sh"]