# MiCADO EEC

The MiCADO Execution Engine Client (EEC) for the EMGWAM component
in [CloudiFacturing](https://www.cloudifacturing.eu/) and
[DIGITbrain](https://digitbrain.eu/).

Enables the deployment and execution of applications and services
using the [MiCADO](https://micado-scale.eu) cloud orchestration framework.

## Usage

The MiCADO EEC implements a RESTful API according to v1.4.0 of the
EMGWAM Execution Engine Client API. Please refer to the specification
for more detail.

## Deployment

The MiCADO EEC is shipped as a Docker container and makes heavy use of
the [MiCADO Client Library](https://github.com/micado-scale/micado-client).
It is deployed behind an NGINX reverse proxy and secured with SSL. Client
certificate verification is also enabled.

Docker-Compose is the recommeded deployment method:
  - [Get Docker](https://docs.docker.com/get-docker/)
  - [Get Docker-Compose](https://docs.docker.com/compose/install/)

### Preparing the host

**Run** `docker-compose up -d` for the first time and it will attempt to create the
following directories on the host. You can change these by modifying the
`volumes` sections in `docker-compose.yml`.
  - `/etc/micado` (Configuration dir for the MiCADO Client Library)
  - `/etc/eec` (Configuration dir for the MiCADO EEC)
  - `/etc/nginx` (Configuration dir the NGINX reverse proxy)
  - `/etc/certbot` (Configuration dir for certbot/letsencrypt)

**If** the NGINX directory is empty or was not created, you will need to
populate it manually:
```bash
docker run -td --rm --name nginx nginx
docker cp nginx:/etc/nginx /etc/
docker stop nginx
```

**If the other directories were not created, please do so now.**

### Preparing the configuration

*If you changed the host configuration directories, make sure to point to them in the steps below*

**Create** a [credentials file](https://micado-scale.readthedocs.io/en/develop/deployment.html#step-2-specify-cloud-credential-for-instantiating-micado-workers)
at `/etc/micado/credentials-cloud-api.yml` and fill in your OpenStack credentials.

* **Optional** *Create* a [private Docker regsitry credential file](https://micado-scale.readthedocs.io/en/develop/deployment.html#step-3b-optional-specify-credentials-to-use-private-docker-registries)
at `/etc/micado/credentials-docker-registry.yml` and fill in your private registry URL and credentials.

**Copy** `openstack_micado_spec.yml` or `cloudbroker_micado_spec.yml` to `/etc/eec/micado_spec.yml` and populate it with the relevant cloud IDs
and names that describe your desired MiCADO node on your desired cloud. This should be an instance meeting the
[recommended requirements](https://micado-scale.readthedocs.io/en/latest/deployment.html#prerequisites)
with an appropriate
[firewall configuration](https://micado-scale.readthedocs.io/en/latest/deployment.html#step-4-launch-an-empty-cloud-vm-instance-for-micado-master).

**Copy** `sample_nginx.conf` to `/etc/nginx/conf.d/eec.conf` and change all occurrences of
`example.com` within to your own domain name. Place the .PEM file for client certificate
verification at `/etc/nginx/cfg.pem`

### Generating SSL certificates

**Edit** `init-letsencrypt.sh` (thanks to: https://medium.com/@pentacent) and replace `example.com`
with your domain, and provide an email address. If you used a different directory on the host
for your certbot configuration, change the `data_path` accordingly.

**Run** `docker-compose down` and then run the `init-letsencrypt.sh` script. This will create
dummy certificates for NGINX and then request an actual certificate from letsencrypt using
the [HTTP challenge](https://letsencrypt.org/docs/challenge-types/). Once the challenge is
complete and the certificate is issued, run `docker-compose down`

**Edit** `docker-compose.yml` and un-comment the `entrypoint`/`command` directives for the
`nginx` and `certbot` services. This will enable automatic certificate renewal.

**Run** `docker-compose up -d` one last time and the deployment is complete.
