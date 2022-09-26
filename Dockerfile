FROM python:3.8-alpine

COPY requirements.txt /requirements.txt

RUN apk add --update --no-cache --virtual .build-deps build-base libffi-dev openssl-dev git \
  && pip install -r requirements.txt \
  && rm -f /requirements.txt \
  && rm -rf /root/.cache \
  && apk del .build-deps

RUN apk add --update --no-cache openssh

COPY micado_eec /micado_eec

WORKDIR /root/.ssh/
WORKDIR /etc/eec/
WORKDIR /etc/micado/
WORKDIR /

ENV MICADO_DIR=/etc/micado/
ENV MICADO_VERS=0.11.0
ENV MICADO_SPEC=/etc/eec/micado_spec.yaml
ENV FLASK_APP=/micado_eec/micado.py

CMD python3 -m flask run --host 0.0.0.0
