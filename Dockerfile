FROM python:3.8-alpine

COPY requirements.txt /requirements.txt

RUN apk add --update --no-cache --virtual .build-deps build-base libffi-dev openssl-dev \
  && sed -e '$ d' /requirements.txt | pip3 install -r /dev/stdin \
  && rm -f /requirements.txt \
  && rm -rf /root/.cache \
  && apk del .build-deps

RUN apk add --update --no-cache --virtual .build-deps git \
  && pip3 install git+git://github.com/micado-scale/micado-client@develop#egg=micado-client \
  && rm -rf /root/.cache \
  && apk del .build-deps

RUN apk add --update --no-cache openssh

COPY micado_eec /micado_eec

WORKDIR /root/.ssh/
WORKDIR /etc/eec/
WORKDIR /etc/micado/
WORKDIR /

ENV MICADO_DIR=/etc/micado/
ENV MICADO_VERS=0.9.2-rc1
ENV MASTER_SPEC=/etc/eec/master_spec.yaml
ENV FLASK_APP=/micado_eec/micado.py

CMD python3 -m flask run --host 0.0.0.0
