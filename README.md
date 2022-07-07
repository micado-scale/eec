# MiCADO EEC

The MiCADO Execution Engine Client (EEC) for the EMGWAM component
in [CloudiFacturing](https://www.cloudifacturing.eu/), Co-Versatile(https://co-versatile.eu) and
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
It is deployed behind traefik and secured with SSL. Client
certificate verification can be optionally enabled.

### Host Specification & Requirements

**Minimum specs.**
  - 2 vCPUs | 4GB RAM | 20GB Disk | Ubuntu 20.04
  - FQDN that resolves to the instance public IP 

**Install Docker and Docker-Compose.**
  - [Get Docker](https://docs.docker.com/get-docker/)
  - [Get Docker-Compose](https://docs.docker.com/compose/install/)

**Clone this repository into a directory of your choice**
```bash
git clone https://github.com/micado-scale/eec project_name_eec
cd project_name_eec
```

### Initial preparation of the host

Create the following default directories on the host. You can change these by modifying the
`volumes` sections in `docker-compose.yml`.
  - `/etc/micado` (Configuration dir for the MiCADO Client Library)
  - `/etc/eec` (Configuration dir for the MiCADO EEC)
  - `/etc/traefik/dynamic` (Configuration dir for traefik)

### Preparing the configuration

*If you did not use the default directories above, make sure to use the new names in the steps below*

**Create** a [credentials file](https://micado-scale.readthedocs.io/en/develop/deployment.html#step-2-specify-cloud-credential-for-instantiating-micado-workers)
at `/etc/micado/credentials-cloud-api.yml` and fill in your OpenStack or CloudBroker credentials.

* **Optional** *Create* a [private Docker regsitry credential file](https://micado-scale.readthedocs.io/en/develop/deployment.html#step-3b-optional-specify-credentials-to-use-private-docker-registries)
at `/etc/micado/credentials-docker-registry.yml` and fill in your private registry URL and credentials.

**Copy** `openstack_micado_spec.yml` or `cloudbroker_micado_spec.yml` to `/etc/eec/micado_spec.yml` and populate it with the relevant cloud IDs
and names that describe your desired MiCADO node on your desired cloud. This should be an instance meeting the
[recommended requirements](https://micado-scale.readthedocs.io/en/latest/deployment.html#prerequisites)
with an appropriate
[firewall configuration](https://micado-scale.readthedocs.io/en/latest/deployment.html#step-4-launch-an-empty-cloud-vm-instance-for-micado-master).

**Copy** `traefik.toml` to `/etc/traefik/traefik.toml` and replace `foo@example.com` with a valid email address.

**Copy** `force-https.toml` to `/etc/traefik/dynamic/force-https.toml`

**Create** an empty file in which Traefik can store retrieved HTTPS certificates. Set restrictive rw------- permissions for the created file.
```bash
touch /etc/traefik/acme.json
chmod 600 /etc/traefik/acme.json
```

### Generating SSL certificates

**Edit** `docker-compose.yml` and replace `example.com` with your domain. 

**Run** `docker-compose up -d` and the deployment is complete.

### Integration

Provide an EMGWAM administrator with your domain name and details.