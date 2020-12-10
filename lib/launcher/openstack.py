#!/usr/bin/env python

import logging
import logging.config
import os
import random
import socket
import subprocess
import tarfile
import time
import uuid
from pathlib import Path
from shutil import copyfile

import requests
from Crypto.PublicKey import ECC
from keystoneauth1 import loading, session
from keystoneauth1.identity import v3
from novaclient import client as nova_client
from ruamel.yaml import YAML

import openstack
from openstack import connection

from ..exceptions import MicadoException

"""Low-level methods for handling a MiCADO master with OpenStackSDK

"""
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
fh = logging.handlers.RotatingFileHandler(
    filename=str(Path.home())+'/.micado-cli/micado-cli.log', mode='a', maxBytes=52428800, backupCount=3)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s : %(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
logger.addHandler(ch)
logger.addHandler(fh)


class OpenStackLauncher:
    """For launching a MiCADO Master with OpenStackSDK

    """
    home = str(Path.home())+'/.micado-cli/'
    micado_version = '0.9.1-rev1'
    ansible_folder = home+'ansible-micado-'+micado_version+'/'
    api_version = 'v2.0'

    def launch(self, auth_url, image, flavor, network, keypair, security_group='all', region=None,
               user_domain_name='Default', project_id=None, micado_user='admin', micado_password='admin'):
        """Create the MiCADO Master node

        Args:
            auth_url (string): Authentication URL for the NOVA
                resource.
            image (string): Name or ID of the image resource.
            flavor (string): Name or ID of the flavor resource.
            network (string): Name or ID of the network resource.
            keypair (string): Name or ID of the keypair resource.
            security_group (string, optional): name or ID of the
                security_group resource. Defaults to 'all'.
            region (string, optional): Name of the region resource.
                Defaults to None.
            user_domain_name (string, optional): Define the user_domain_name.
                Defaults to 'Default'
            project_id (string, optional): ID of the project resource.
                Defaults to None.
            micado_user (string, optional): MiCADO username.
                Defaults to admin.
            micado_password (string, optional): MiCADO password.
                Defaults to admin.

        Raises:
            MicadoException: Missing or incorrect data.
        """

        try:
            if not self._check_home_folder():
                os.mkdir(self.home)
            pub_key = self._get_pub_key()
            conn, conn_nova = self.get_connection(
                auth_url, region, project_id, user_domain_name)
            image = conn.get_image(image)
            flavor = conn.get_flavor(flavor)
            network = conn.get_network(network)
            keypair = conn.get_keypair(keypair)
            security_group = conn.get_security_group(security_group)
            if image == None:
                raise MicadoException("Can't find image!")
            if flavor == None:
                raise MicadoException("Can't find flavor!")
            if network == None:
                raise MicadoException("Can't find network!")
            if keypair == None:
                raise MicadoException("Can't find keypair!")
            if security_group == None:
                raise MicadoException("Can't find security_group!")

            unused_ip = self.get_unused_floating_ip(conn)
            if len(unused_ip) < 1:
                raise MicadoException("Can't find availabe floating IP!")
            ip = random.choice(unused_ip)
            logger.info('Creating VM...')
            cloud_init_config = """
            #cloud-config

            ssh_authorized_keys:
            - {}

            runcmd:
            # MTA cloud fix
            - chage -d 2020-08-04 ubuntu
            """.format(pub_key)
            name_id = uuid.uuid1()
            server = conn_nova.servers.create(
                'MiCADO-Master-{}'.format(name_id.hex),
                image.id,
                flavor.id,
                security_groups=[security_group.id],
                nics=[{"net-id": network.id}],
                key_name=keypair.name,
                userdata=cloud_init_config)
            # server = conn.compute.create_server(
            #     name='MiCADO-Master-{}'.format(name_id.hex), image_id=image.id, flavor_id=flavor.id,
            #     key_name=keypair.name, userdata=cloud_init_config, timeout=300, networks=[{"uuid": network.id}], security_groups=[{"name": security_group.id}])
            logger.info('The VM {} starting...'.format(server.id))
            server = conn.get_server(server.id)
            logger.info('Waiting for running state, and attach {} floating ip'.format(
                ip.floating_ip_address))
            conn.wait_for_server(server, auto_ip=False,
                                ips=ip.floating_ip_address, timeout=600)
            self._download_ansible_micado()
            self._extract_tar()
            self._configure_ansible_playbook(
                ip.floating_ip_address, micado_user, micado_password)
            self._check_port_availability(ip.floating_ip_address, 22)
            self._remove_know_host()
            self._get_ssh_fingerprint(ip.floating_ip_address)
            self._check_ssh_availability(ip.floating_ip_address)
            self._deploy_micado_master()
            self._check_port_availability(ip.floating_ip_address, 443)
            logger.info('MiCADO deployed!')
            self._get_self_signed_cert(ip.floating_ip_address, server.id)
            self._store_data(self.api_version, ip.floating_ip_address,
                            micado_user, micado_password, server.id, auth_url, region, project_id, user_domain_name)
            return server.id
        except MicadoException as e:
            logger.error(f"Exception cought: {e}")
        except Exception as e:
            logger.error(f"Exception cought: {e}")
            if 'server' in locals():
                conn.delete_server(server.id)
                logger.info(f"{server.id} VM dropped.")

    def get_api_endpoint(self, id):
        """Return the MiCADO Master Submitter API endpoint

        Args:
            id (string): MiCADO master UUID

        Raises:
            Exception: If UUID not found

        Returns:
            string: MiCADO Master Submitter API endpoint
        """
        yaml = YAML()
        content = None
        with open(self.home+'data.yml', mode='r') as f:
            content=yaml.load(f)
        search = [i for i in content["masters"] if i.get(id, None)]
        if not search:
            raise Exception("Can't find api-endpoint!")
        else:
            logger.info("VM ID: {} \t API endpoint: https://{}/toscasubmitter".format(id, search[0][id]["ip"]))
            return "https://{}/toscasubmitter".format(search[0][id]["ip"])
        return None

    def get_api_version(self):
        """
        Return the MiCADO Master Submitter API version. Only v2.0 supported.

        Returns:
            string: MiCADO Master Submitter API version
        """

        return "v2.0"

    def delete(self, id):
        """Destroy the existing MiCADO master VM.

        Args:
            id (string): The MiCADO master UUID.

        Raises:
            MicadoException: Missing or incorrect data.
        """
        try:
            auth_url = None
            region_name = None
            project_id = None
            user_domain_name = None
            yaml = YAML()
            content = None
            with open(self.home+'data.yml', mode='r') as f:
                content=yaml.load(f)
            search = [i for i in content["masters"] if i.get(id, None)]
            if not search:
                # TODO: handle if it is not in the file
                logger.debug("This {} ID can not find in the data file.".format(id))
                pass
            else:
                logger.debug("Remove {} record".format(search))
                auth_url = search[0][id]["auth_url"]
                region_name = search[0][id]["region_name"]
                project_id = search[0][id]["project_id"]
                user_domain_name = search[0][id]["user_domain_name"]
                content["masters"].remove(search[0])
                with open(self.home+'data.yml', mode='w') as f:
                    yaml.dump(content, f)
            conn, _ = self.get_connection(
                auth_url, region_name, project_id, user_domain_name)
            if conn.get_server(id) is None:
                raise MicadoException("{} is not a valid VM ID!".format(id))
            conn.delete_server(id)
            logger.info('Dropping node {}'.format(id))
            logger.info("remove {}-ssl.pem".format(self.home+id))
            os.remove(self.home+id+'-ssl.pem')
            return "Destroyed"
        except MicadoException as e:
            logger.error(f"Exception cought: {e}")

    def get_credentials(self):
        """Read credential from file.

        Raises:
            MicadoException: Missing or incorrect data.

        Returns:
            tuple: return authentication data
        """
        with open(self.home+'credentials-cloud-api.yml', 'r') as stream:
            yaml = YAML()
            auth_data = yaml.load(stream)

        username = None
        password = None
        application_credential_id = None
        application_credential_secret = None

        try:
            nova = [resource for resource in auth_data['resource']
                    if resource['type'] == 'nova'][0]
        except MicadoException as e:
            logger.info("Can't find Nova resource.")
            raise MicadoException("Can't find Nova resource type. Aborted")

        username = nova['auth_data'].get('username', None)
        password = nova['auth_data'].get('password', None)
        application_credential_id = nova['auth_data'].get(
            'application_credential_id', None)
        application_credential_secret = nova['auth_data'].get(
            'application_credential_secret', None)

        missing_app_credential = (not application_credential_id and application_credential_secret != None) or (
            application_credential_id != None and not application_credential_secret)
        missing_password_credential = (not username and password != None) or (
            username != None and not password)
        both_credential_missing = application_credential_id != None and application_credential_secret != None and username != None and password != None
        no_credential_specified = not application_credential_id and not application_credential_secret and not username and not password

        if missing_app_credential or missing_password_credential:
            raise MicadoException("Missing credentials!")

        if missing_app_credential and missing_password_credential:
            raise MicadoException("No credentials found.")

        if both_credential_missing:
            raise MicadoException(
                "Both credential specified. Please choose one of them.")

        if no_credential_specified:
            raise MicadoException(
                "No credential specified. Please follow the tutorial.")

        # Password type
        if not application_credential_id:
            return username, password, False
        # Application credential
        else:
            return application_credential_id, application_credential_secret, True

        return auth_data

    def get_unused_floating_ip(self, conn):
        """Return unused ip.

        Args:
            conn ([type]): OpenStack connection

        Returns:
            dict: Unused IP
        """
        return [addr for addr in conn.list_floating_ips() if addr.attached == False]

    def get_connection(self, auth_url, region_name, project_id, user_domain_name):
        """Create OpenStack connection.

        Args:
            auth_url (string): Authentication URL for the NOVA
                resource.
            region_name (string, optional): Name of the region resource.
                Defaults to None.
            project_id (string, optional): ID of the project resource.
                Defaults to None.
            user_domain_name (string, optional): Define the user_domain_name.
                Defaults to 'Default'

        Raises:
            Exception: Project ID missing

        Returns:
            tuple: OpenStackSDK connection, and nova_client Connection
        """
        auth_data = self.get_credentials()
        if auth_data[2]:
            app_cred_id = auth_data[0]
            app_cred_secret = auth_data[1]
            auth = v3.ApplicationCredential(
                auth_url, application_credential_id=app_cred_id, application_credential_secret=app_cred_secret)
        else:
            if project_id is None:
                raise Exception('Project ID is missing!')
            user = auth_data[0]
            password = auth_data[1]
            auth = v3.Password(auth_url=auth_url, username=user, password=password,
                               user_domain_name=user_domain_name, project_id=project_id)
        sess = session.Session(auth=auth)
        return connection.Connection(
            region_name=region_name,
            session=sess,
            compute_api_version='2',
            identity_interface='public'), nova_client.Client(2, session=sess, region_name=region_name)

    def _check_home_folder(self):
        """Check if homefolder exist

        Returns:
            boolean: True if it is exist
        """
        return os.path.isdir(self.home)

    def _check_ssh_key_existance(self):
        """Check if SSH config key exist.

        Returns:
            boolean: True if it is exist
        """
        return os.path.isfile(self.home + 'micado_cli_config_priv_key') and os.path.isfile(self.home + 'micado_cli_config_pub_key')

    def _get_pub_key(self):
        """Get public config key from home location.

        Returns:
            string: Public config key
        """
        if not self._check_ssh_key_existance():
            self._create_ssh_keys()
        with open(self.home + 'micado_cli_config_pub_key', 'r') as f:
            pub_key = f.readline()
        return pub_key

    def _create_ssh_keys(self):
        """Create SSH config key, and set the correct permission.

        """
        key = ECC.generate(curve='P-521')
        with open(self.home + 'micado_cli_config_priv_key', 'wt') as f:
            f.write(key.export_key(format='PEM'))
        with open(self.home + 'micado_cli_config_pub_key', 'wt') as f:
            f.write(key.public_key().export_key(format='OpenSSH'))
        os.chmod(self.home + 'micado_cli_config_priv_key', 0o600)
        os.chmod(self.home + 'micado_cli_config_pub_key',  0o666)

    def _download_ansible_micado(self):
        """Download ansible_micado from GitHub and write down to home directory.
        """
        logger.info('Download Ansible MiCADO')
        url = 'https://github.com/micado-scale/ansible-micado/releases/download/v' + \
                self.micado_version+'/ansible-micado-'+self.micado_version+'.tar.gz'
        r = requests.get(url)
        tarfile_location = self.home+'ansible-micado-'+self.micado_version+'.tar.gz'
        with open(tarfile_location, 'wb') as f:
            f.write(r.content)

    def _extract_tar(self):
        """Extract tar
        """
        logger.info('Extract Ansible MiCADO')
        tarfile_location = self.home+'ansible-micado-'+self.micado_version+'.tar.gz'
        tar_file = tarfile.open(tarfile_location)
        tar_file.extractall(self.home)
        tar_file.close()
        os.remove(tarfile_location)

    def _configure_ansible_playbook(self, ip, micado_user, micado_password):
        """Configure ansible-micado.

        Args:
            ip (string): MiCADO master IP
            micado_user (string): User defined MiCADO user
            micado_password ([type]): User defined MiCADO password
        """
        logger.info('Copy ansible sample files')
        copyfile(self.ansible_folder+'sample-credentials-micado.yml',
                 self.ansible_folder+'credentials-micado.yml')
        copyfile(self.home+'credentials-cloud-api.yml',
                 self.ansible_folder+'credentials-cloud-api.yml')
        self._create_micado_hostfile(ip)
        self._create_micado_credential(micado_user, micado_password)

    def _create_micado_hostfile(self, ip):
        """Create Ansible hostfile.

        Args:
            ip (string): MiCADO master IP
        """
        logger.info('Create and configure host file')
        with open(self.ansible_folder+'sample-hosts.yml', 'r') as f:
            yaml = YAML()
            host_dict = yaml.load(f)
            host_dict["all"]["hosts"]["micado-target"]["ansible_ssh_private_key_file"] = self.home + \
                'micado_cli_config_priv_key'
            host_dict["all"]["hosts"]["micado-target"]["ansible_ssh_extra_args"] = '-o StrictHostKeyChecking=no'
            host_dict["all"]["hosts"]["micado-target"]["ansible_host"] = ip
        with open(self.ansible_folder+'hosts.yml', "w") as f:
            yaml.dump(host_dict, f)

    def _create_micado_credential(self, micado_user, micado_password):
        """Create MiCADO credential file.

        Args:
            micado_user (string): User defined MiCADO user
            micado_password ([type]): User defined MiCADO password
        """
        logger.info('Create and configure credential-micado-file file')
        with open(self.ansible_folder+'sample-credentials-micado.yml', 'r') as f:
            yaml = YAML()
            credential_dict = yaml.load(f)
            credential_dict["authentication"]["username"] = micado_user
            credential_dict["authentication"]["password"] = micado_password
        with open(self.ansible_folder+'credentials-micado.yml', "w") as f:
            yaml.dump(credential_dict, f)

    def _check_port_availability(self, ip, port):
        """Check the given port availability.

        Args:
            ip (string): IP address of the VM
            port (string): Port number

        Raises:
            Exception: When timeout reached
        """
        logger.info('Check {} port availability'.format(port))
        attempts = 0
        sleep_time = 2
        max_attempts = 1000
        result = None
        logger.info('IP: {} \tPort: {} \tsleeptime:{}'.format(
            ip, port, sleep_time,))
        while attempts < max_attempts and result != 0:
            logger.debug('attempts:{}/{} Still no answer. Try again {} second later'.format(
                attempts+1, max_attempts, sleep_time))
            time.sleep(sleep_time)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socket.setdefaulttimeout(1)
            result = s.connect_ex((ip, port))
            s.close()
            attempts += 1

        if attempts == max_attempts:
            raise Exception('{} second passed, and still cannot reach {}.'.format(
                attempts * sleep_time, port))
        else:
            logger.info('{} port is available.'.format(port))

    def _deploy_micado_master(self):
        """Deploy MiCADO master services via ansible
        """
        logger.info('Deploy MiCADO master')
        subprocess.run(["ansible-playbook", "-i", "hosts.yml", "micado-master.yml"],
                       cwd=self.ansible_folder,
                       check=True)

    def get_ssh_key_path(self):
        """Get SSH key path

        Returns:
            string: location of the key
        """
        if self._check_ssh_key_existance():
            return "You can find the configuration keys under ~/.micado-cli/micado_cli_config_priv_key and ~/.micado-cli/micado_cli_config_pub_key"
        else:
            return "The key is not generated yet. Deploy the VM first"

    def _remove_know_host(self):
        """Remove known_host file
        """
        known_hosts = str(Path.home())+'/.ssh/known_hosts'
        with open(known_hosts) as file:
            all_lines = file.readlines()
        with open(known_hosts, 'a') as file2:
            file2.writelines(all_lines)
        os.remove(known_hosts)

    def _get_ssh_fingerprint(self, ip):
        """Get SSH fingerprint

        Args:
            ip (string): Target IP address
        """
        known_hosts = str(Path.home())+'/.ssh/known_hosts'
        result = subprocess.run(["ssh-keyscan", "-H", ip],
                                shell=False,
                                stdin=None,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                check=True)
        with open(known_hosts, 'a') as f:
            f.writelines(result.stdout.decode())

    def _check_ssh_availability(self, ip):
        """Check SSH availability

        Args:
            ip (string): Target IP

        Raises:
            Exception: When timeout reached
        """
        attempts = 0
        sleep_time = 2
        max_attempts = 100
        err = "default"
        while attempts < max_attempts and err != "":
            logger.debug('attempts:{}/{} Cloud-init still running. Try again {} second later'.format(
                attempts+1, max_attempts, sleep_time))
            time.sleep(sleep_time)
            result = subprocess.run(["ssh", "-i", self.home+'micado_cli_config_priv_key', "ubuntu@"+ip, "ls -lah"],
                                    shell=False,
                                    stdin=None,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    check=False)
            err = result.stderr.decode()
            logger.debug(result.stderr.decode())
            attempts += 1

        if attempts == max_attempts:
            raise Exception('{} second passed, and still cannot reach SSH.'.format(
                attempts * sleep_time))
        else:
            logger.info('SSH is available.')

    def _get_self_signed_cert(self, ip, id):
        """Get MiCADO master self signed SSL

        Args:
            ip (string): Target IP
            id (string): UUID of the VM
        """
        logger.info('Get MiCADO self_signed cert')
        subprocess.run(["scp", 'ubuntu@'+ip+':/var/lib/micado/zorp/config/ssl.pem', self.home+id+'-ssl.pem'],
                       shell=False,
                       stdin=None,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       check=True)

    def _store_data(self, api_version, ip, micado_user, micado_password, server_id, auth_url, region_name, project_id, user_domain_name):
        """Persist deployment data

        Args:
            api_version (string): Submitter API version
            ip (string): Master VM IP address
            micado_user (string): User defined MiCADO user
            micado_password (string): User defined MiCADO password
            server_id (string): MiCADO master VM ID
            auth_url (string): Authentication URL for the NOVA
                resource.
            region (string, optional): Name of the region resource.
                Defaults to None.
            project_id (string, optional): ID of the project resource.
                Defaults to None.
            user_domain_name (string, optional): Define the user_domain_name.
                Defaults to 'Default'
        """
        # check if file does exist
        logger.debug("Save data")
        file_location = self.home + 'data.yml'
        cert_path = self.home + server_id + '-ssl.pem'
        endpoint = 'https://' + ip + '/toscasubmitter'
        yaml = YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        content = None
        region_name = region_name
        if region_name is None:
            region_name = ''
        item = [{server_id: {"api_version": api_version,
                            "cert_path": cert_path,
                            "endpoint": endpoint,
                            "ip": ip,
                            "micado_user": micado_user,
                            "micado_password": micado_password,
                            "auth_url":auth_url,
                            "region_name": region_name,
                            "project_id":project_id,
                            "user_domain_name":user_domain_name}}]
        if os.path.isfile(file_location):
            logger.debug("Data file exist.")
            with open(file_location) as f:
                content = yaml.load(f)
                content["masters"] += item
        else:
            logger.debug("Data file does not exist. Creating new file")
            content = {"masters": [{server_id: {"api_version": api_version,
                                                "cert_path": cert_path, "endpoint": endpoint,
                                                "ip": ip,
                                                "micado_user": micado_user,
                                                "micado_password": micado_password,
                                                "auth_url":auth_url,
                                                "region_name": region_name,
                                                "project_id":project_id,
                                                "user_domain_name":user_domain_name}}]}
        with open(self.home+'data.yml', "w") as f:
            yaml.dump(content, f)

    def _get_property(self, key, id):
        """
        """
        yaml = YAML()
        content = None
        with open(self.home+'data.yml', mode='r') as f:
            content=yaml.load(f)
        search = [i for i in content["masters"] if i.get(id, None)]
        if not search:
            logger.error("Can't find {} property!".format(key))
            raise Exception("Can't find property!")
        else:
            return search[0][id][key]
        return None
