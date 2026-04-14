FROM python:3.11-slim

RUN apt-get update && apt-get -y install cron && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY crontab /etc/cron.d/my-cron

RUN chmod 0644 /etc/cron.d/my-cron

RUN touch /var/log/cron.log

COPY requirements.txt .
COPY loaddaily_TT.py .
# NOTE: .env is NOT copied into the image for security reasons.
# Pass environment variables via docker-compose env_file or runtime --env-file flag.

RUN pip install --no-cache-dir -r requirements.txt

CMD cron -f && tail -f /var/log/cron.log