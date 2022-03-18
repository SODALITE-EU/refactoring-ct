FROM alpine:3.15
COPY . /home
RUN apk --no-cache add jq
RUN ["chmod", "+x", "/home/main.sh"]
ENTRYPOINT ["/home/main.sh"]