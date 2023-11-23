FROM python:3.11-slim as build-stage

WORKDIR /tmp/code

COPY . .

RUN pip wheel --wheel-dir ./dist '.[api]'

FROM python:3.11-slim

WORKDIR /app

COPY --from=build-stage /tmp/code/dist/ .

RUN pip install --no-cache-dir --no-index --find-links . dnschef[api]

EXPOSE 80 53/udp 53/tcp

CMD ["uvicorn", "dnschef.api:app", "--host", "0.0.0.0", "--port", "80"]

# If using a proxy
#CMD ["uvicorn", "app.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]