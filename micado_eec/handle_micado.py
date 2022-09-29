import os
import io
import base64
import threading
import time
from datetime import datetime
from typing import Optional

import ruamel.yaml as yaml
from redis import StrictRedis
from micado import MicadoClient

from .utils import base64_to_yaml, load_yaml_file

STATUS_INIT = 0  # initializing
STATUS_RUNNING = 1  # running
STATUS_RESULTS = 2  # results available
STATUS_ERROR = 3  # error
STATUS_ABORTED = 4  # stopping
STATUS_STOPPED = 5  # stopped

STATUS_INFRA_INIT = "infrastructure initializing"
STATUS_INFRA_INIT_ERROR = "error: failed to initialize infrastructure for MiCADO"
STATUS_INFRA_BUILD = "infrastructure for MiCADO building"
STATUS_INFRA_READY = "infrastructure for MiCADO ready"
STATUS_APP_BUILD = "application is being deployed on the infrastructure"
STATUS_APP_READY = "application is ready"
STATUS_APP_REMOVING = "application is being removed"
STATUS_APP_REMOVED = "application removed"
STATUS_INFRA_REMOVING = "infrastructure for MiCADO is being removed"
STATUS_INFRA_REMOVED = "infrastructure for MiCADO removed"
STATUS_INFRA_REMOVE_ERROR = "failed to remove infrastructure for MiCADO"

MICADO_CLOUD = "openstack"
MICADO_INSTALLER = "ansible"
MICADO_NODE = "micado"

DEFAULT_MICADO_YAML = os.environ.get("MICADO_SPEC", "/etc/eec/micado_spec.yaml")

ARTEFACT_ADT_REF = "deployment_adt"
INPUT_ADT_REF = "adt.yaml"

APP_ID_PARAM = "app_id"
APP_PARAMS = "params"

r = StrictRedis("redis", decode_responses=True)
if not r.ping():
    raise ConnectionError("Cannot connect to Redis")


class MicadoBuildException(Exception):
    def __init__(self, message):
        self.message = message


class MicadoInfraException(Exception):
    def __init__(self, message):
        self.message = message


class MicadoAppException(Exception):
    def __init__(self, message):
        self.message = message


class HandleMicado(threading.Thread):

    _abort = False

    status = STATUS_INIT
    status_detail = STATUS_INFRA_INIT

    def __init__(
        self,
        threadID,
        name,
        artefact_data: Optional[dict] = None,
        inouts: Optional[dict] = None,
        file_paths: Optional[dict] = None,
        free_inputs: Optional[dict] = None,
        free_outputs: Optional[dict] = None,
        parameters: Optional[dict] = None,
    ):
        super().__init__()
        self.threadID = threadID
        self.name = name

        if not r.hgetall(threadID):
            r.hset(threadID, "submit_time", datetime.now().timestamp())
            self.set_status()

        self.artefact_data = artefact_data or {}
        self.inouts = inouts or {}
        self.file_paths = file_paths or {}
        self.free_inputs = free_inputs or {}
        self.final_outputs = free_outputs or {}
        self.parameters = parameters or {}
        self.micado = MicadoClient(launcher=MICADO_CLOUD, installer=MICADO_INSTALLER)

    def set_status(self):
        try:
            node_data = self.micado.micado.details.replace("\n", "<br>   ")
        except AttributeError:
            node_data = ""

        # Can get node data here, if relevant

        details = f"""
        <html>
            <head>
                <title>MiCADO execution status report</title>
            </head>
            <body>
                <h1>Overview</h1>
                <p>This page summarizes the status of the MiCADO deployment</p>
                <p>Status of the deployment: <b>{self.status_detail}</b></p>
                <h1>MiCADO login information</h1>
                <p>Here you can find login info for the MiCADO dashboard:
                {node_data}
                </p>
            </body>
        </html>
        """
        r.hset(self.threadID, "status", self.status)
        r.hset(
            self.threadID,
            "details",
            str(base64.standard_b64encode(details.encode()), "utf-8"),
        )
        r.hset(self.threadID, "only_status", True)

    def abort(self):
        r.expire(self.threadID, 90)
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_INFRA_REMOVING
        self.set_status()
        if self.micado.micado.api:
            self._kill_micado()
        self.status_detail = STATUS_INFRA_REMOVED
        self.set_status()

    def _is_aborted(self):
        if r.hexists(self.threadID, "abort"):
            return True
        return False

    def run(self):
        """Builds a MiCADO node and deploys an application"""
        if not r.hexists(self.threadID, "micado_id"):
            # Create MiCADO
            micado_node_data = _get_micado_spec()
            self._create_micado_node(micado_node_data)

            # Submit app
            deployment_adt = self._get_adt()
            parameters = self._load_params()
            self._submit_app(deployment_adt, parameters)

        else:
            self._attach_to_existing()

        # Wait for abort
        while True:
            if self._is_aborted():
                self.abort()
                break
            time.sleep(15)

    def _create_micado_node(self, micado_node_data):
        """Creates the MiCADO node"""
        self.status = STATUS_INIT
        self.status_detail = STATUS_INFRA_BUILD
        self.set_status()

        try:
            self._create_micado_node(micado_node_data)
        except Exception as e:
            r.expire(self.threadID, 90)
            self.status_detail = str(e)
            self.status = STATUS_ERROR
            self.set_status()
            raise
        r.hset(self.threadID, "micado_id", self.micado.micado.micado_id)

        # TODO: Check micado is running

        self.status_detail = STATUS_INFRA_READY
        self.set_status()

    def _submit_app(self, app_data, params):
        """Submits an application to MiCADO"""
        self.status = STATUS_INIT
        self.status_detail = STATUS_APP_BUILD
        self.set_status()

        try:
            if isinstance(app_data, dict):
                self.micado.applications.create(adt=app_data, params=params)
            else:
                self.micado.applications.create(file=app_data, params=params)
        except Exception as e:
            r.expire(self.threadID, 90)
            self.status = STATUS_ERROR
            self._kill_micado(msg=str(e))
            raise
        finally:
            if isinstance(app_data, io.TextIOWrapper):
                app_data.close()

        # TODO: Check app is running

        self.status = STATUS_RUNNING
        self.status_detail = STATUS_APP_READY
        self.set_status()

    def _attach_to_existing(self):
        """Attempt to attach to a MiCADO belonging to the thread ID"""
        micado_id = r.hget(self.threadID, "micado_id") or ""
        try:
            self.micado.micado.attach(micado_id)
            self.status = STATUS_RUNNING
            self.status_detail = STATUS_APP_READY
            self.set_status()
        except LookupError:
            r.delete(self.threadID)
            raise

    def _get_adt(self):
        """Get inputs for YAML or CSAR"""
        if self.artefact_data["downloadUrl"].endswith(".yaml"):
            deployment_adt = base64_to_yaml(self.artefact_data["downloadUrl_content"])
        else:
            file_content = base64.b64decode(self.artefact_data["downloadUrl_content"])
            file_name = f"{self.artefact_data['id']}.csar"
            with open(file_name, "wb+") as f:
                f.write(file_content)
            deployment_adt = open(file_name, "rb")

        return deployment_adt

    def _load_params(self):
        """Loads parameter data"""
        self.status = STATUS_INIT
        self.status_detail = STATUS_INFRA_INIT
        self.set_status()

        parameters = {
            element["key"]: element["value"]
            for element in self.inouts.get("parameters", [])
            if self._is_valid_param(element["key"])
        }

        return parameters

    def _load_files(self):
        """Loads files data"""
        files = {}
        for _input in self.free_inputs:
            if not self._is_valid_input(_input):
                raise MicadoBuildException(f"Missing input: {_input}")
            files[_input["filename"]] = _input

        return files

    def _delete_app(self):
        """Removes the running application from MiCADO"""
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_APP_REMOVING
        self.set_status()
        [
            self.micado.applications.delete(app.id)
            for app in self.micado.applications.list()
        ]

        self.status_detail = STATUS_APP_REMOVED
        self.set_status()

    def _kill_micado(self, msg=None):
        """Removes the MiCADO infrastructure and any applications"""
        self.status_detail = msg or STATUS_INFRA_REMOVING
        self.set_status()
        try:
            self.micado.micado.destroy()
        except Exception:
            self.status = STATUS_ERROR
            self.status_detail = msg or STATUS_INFRA_REMOVE_ERROR
            self.set_status()
            raise

    def _is_valid_input(self, input_to_check):
        """Checks if the input is valid"""
        try:
            available = [
                _input
                for _input in self.inouts.get("free_inputs", [])
                if _input["id"] == input_to_check["id"]
            ]
        except KeyError:
            raise MicadoBuildException(f"Malformed input: {input_to_check}")
        return len(available) == 1

    def _is_valid_param(self, key_to_check):
        """Checks if the parameter is valid"""
        available = {
            value
            for element in self.parameters
            for value in element.values()
            if value == key_to_check
        }
        return len(available) > 0


def _get_micado_spec():
    """Retrieves the MiCADO node configuration"""
    try:
        properties = load_yaml_file(DEFAULT_MICADO_YAML)["properties"]
    except (yaml.YAMLError, KeyError):
        raise MicadoInfraException(
            f"Could not get default MiCADO spec from {DEFAULT_MICADO_YAML}"
        )

    return {key: val for key, val in properties.items() if val is not None}
