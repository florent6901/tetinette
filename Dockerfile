FROM python:3.12-alpine
RUN apk add --no-cache openssl
WORKDIR /app
COPY app/ .
ENV TZ=Europe/Paris
VOLUME /data
EXPOSE 8086
CMD ["python", "-u", "server.py"]
