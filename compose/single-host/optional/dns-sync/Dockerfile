# SPIRENS dns-sync — stdlib-only reconciler; tiny by design.
FROM python:3.14-alpine

# Alpine reserves the names "sync" and "syslog" in /etc/passwd. Use a
# unique username + a non-reserved UID.
RUN adduser -D -u 10101 dnsyn
USER dnsyn
WORKDIR /app

COPY sync.py /app/sync.py

ENTRYPOINT ["python3", "/app/sync.py"]
