FROM alpine:3.18.3
COPY . /home
RUN apk --no-cache add jq
RUN ["chmod", "+x", "/home/main.sh"]
ENTRYPOINT ["/home/main.sh"]