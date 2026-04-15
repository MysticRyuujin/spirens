# SPIRENS dns-sync — stdlib-only reconciler; tiny by design.
FROM python:3.14-alpine

RUN adduser -D -u 10001 sync
USER sync
WORKDIR /app

COPY sync.py /app/sync.py

ENTRYPOINT ["python3", "/app/sync.py"]
