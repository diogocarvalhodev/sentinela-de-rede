FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends iputils-ping \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY exporter.py .
COPY nvr_monitor ./nvr_monitor
COPY units.json .

ENV EXPORTER_PORT=8000
EXPOSE 8000

CMD ["python", "exporter.py"]
