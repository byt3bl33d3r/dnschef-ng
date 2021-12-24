FROM python:3.10-slim as build-stage

WORKDIR /tmp/code

COPY . .

RUN pip3 install poetry
RUN poetry build

FROM python:3.10-slim

WORKDIR /app
COPY --from=build-stage /tmp/code/dist/dnschef-0.6-py3-none-any.whl /app/dnschef-0.6-py3-none-any.whl

RUN pip install --no-cache-dir --upgrade './dnschef-0.6-py3-none-any.whl[api]'

CMD ["uvicorn", "dnschef.api:app", "--host", "0.0.0.0", "--port", "80"]

# If using a proxy
#CMD ["uvicorn", "app.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]