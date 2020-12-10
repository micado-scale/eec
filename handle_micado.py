import base64
import threading
import time
from datetime import datetime

import ruamel.yaml as yaml

from lib import MicadoClient

STATUS_INIT = 0
STATUS_DEPLOYING = 1
STATUS_READY = 2
STATUS_ERROR = 3
STATUS_ABORTED = 4

STATUS_INFRA_INIT = "infrastructure initializing"
STATUS_INFRA_INIT_ERROR = (
    "error: failed to initialize infrastructure for MiCADO"
)
STATUS_INFRA_BUILD = "infrastructure for MiCADO building"
STATUS_INFRA_READY = "infrastructure for MiCADO ready"
STATUS_APP_BUILD = "application is being deployed on the infrastructure"
STATUS_APP_READY = "application is ready"
STATUS_APP_REMOVING = "application is being removed"
STATUS_APP_REMOVED = "application removed"
STATUS_INFRA_REMOVING = "infrastructure for MiCADO is being removed"
STATUS_INFRA_REMOVED = "infrastructure for MiCADO removed"
STATUS_INFRA_REMOVE_ERROR = "failed to remove infrastructure for MiCADO"

MASTER_CLOUD = "openstack"
DEFAULT_MASTER_YAML = "cloud.yml"
MASTER_YAML = "master.yaml"

ARTEFACT_ADT_REF = "deployment_adt"
INPUT_ADT_REF = "adt.yaml"

APP_ID_PARAM = "app_id"
APP_PARAMS = "params"


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
        artefact_data,
        inouts,
        file_paths,
        free_inputs,
        free_outputs,
        parameters,
    ):
        super().__init__()
        self.threadID = threadID
        self.name = name
        self.artefact_data = artefact_data
        self.inouts = inouts
        self.file_paths = file_paths
        self.free_inputs = free_inputs
        self.final_outputs = free_outputs
        self.parameters = parameters
        self.submit_time = datetime.now().timestamp()
        self.micado = MicadoClient(launcher=MASTER_CLOUD)

    def get_status(self):
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
                <h1>Node IP address information</h1>
                <p>Here you can find the IP address(es) allocated for the nodes
                {node_data}
            </body>
        </html>
        """
        return {
            "status": self.status,
            "details": str(
                base64.standard_b64encode(details.encode()), "utf-8"
            ),
        }

    def abort(self):
        self._abort = True
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_INFRA_REMOVING

    def runtime_seconds(self):
        return int(datetime.now().timestamp() - self.submit_time)

    def _check_abort(self):
        if not self._abort:
            return
        self.status = STATUS_ABORTED
        self._kill_micado()

    def run(self):
        """Builds a MiCADO Master and deploys an application"""
        try:
            # Load inputs and parameters
            files, parameters = self._load_data()
            master_node_data = self._get_master_node_data(files)
            app_data = self._get_deployment_data(files, parameters)

            # Create MiCADO Master
            self._create_master_node(master_node_data)

            # Submit ADT
            self._submit_app(app_data)

            # Wait for abort
            while True:
                self._check_abort()
                time.sleep(30)
        except MicadoBuildException as err:
            self.status = STATUS_ERROR
            self.status_detail = err.message
        except MicadoInfraException as err:
            self.status = STATUS_ERROR
            self.status_detail = err.message
            self._kill_micado()
        except MicadoAppException as err:
            self.status = STATUS_ERROR
            self.status_details = err.message
            self._delete_app()

    def _load_data(self):
        """Loads input and parameter data"""
        self.status = STATUS_INIT
        self.status_detail = STATUS_INFRA_INIT
        # Load files from free inputs
        files = {}
        for _input in self.free_inputs:
            if not self._is_valid_input(_input):
                raise MicadoBuildException(f"Missing input: {_input}")
            files[_input["filename"]] = _input

        # Load parameters
        parameters = {
            key: value
            for element in self.inouts.get("parameters", [])
            for key, value in element.items()
            if self._is_valid_param(key)
        }

        return files, parameters

    def _create_master_node(self, master_node_data):
        """Creates the MiCADO Master node"""
        self.status = STATUS_INIT
        self.status_detail = STATUS_INFRA_BUILD

        self.micado.master.create(**master_node_data)

        # TODO: Check master is running

        self.status_detail = STATUS_INFRA_READY

    def _submit_app(self, app_data):
        """Submits an application to MiCADO"""
        self.status = STATUS_DEPLOYING
        self.status_detail = STATUS_APP_BUILD

        self.micado.applications.create(**app_data)

        # TODO: Check app is running

        self.status = STATUS_READY
        self.status_detail = STATUS_APP_READY

    def _delete_app(self):
        """Removes the running application from MiCADO"""
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_APP_REMOVING
        [
            self.micado.applications.delete(app.id)
            for app in self.micado.applications.list()
        ]

        self.status_detail = STATUS_APP_REMOVED

    def _kill_micado(self):
        """Removes the MiCADO infrastructure and any applications"""
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_INFRA_REMOVING
        try:
            self.micado.master.destroy()
        except Exception:
            self.status = STATUS_ERROR
            self.status_detail = STATUS_INFRA_REMOVE_ERROR
            raise
        self.status = STATUS_ABORTED
        self.status_detail = STATUS_INFRA_REMOVED

    def _get_deployment_data(self, files, parameters):
        """Retrieves application deployment data"""
        app_data = {}
        if ARTEFACT_ADT_REF in self.artefact_data:
            app_data["adt"] = self.artefact_data[ARTEFACT_ADT_REF]
        elif INPUT_ADT_REF in files:
            file_id = files[INPUT_ADT_REF]["id"]
            app_data["adt"] = _load_yaml_file(self.file_paths[file_id])

        app_data[APP_ID_PARAM] = parameters.pop(APP_ID_PARAM, self.threadID)
        if parameters:
            app_data[APP_PARAMS] = parameters

        return app_data

    def _get_master_node_data(self, files):
        """Retrieves the Master node configuration"""
        if MASTER_YAML in files:
            file_id = files[MASTER_YAML]["id"]
            return _load_yaml_file(self.file_paths[file_id])["properties"]
        return _load_yaml_file(DEFAULT_MASTER_YAML)["properties"]

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
            key: value
            for element in self.parameters
            for key, value in element.items()
            if key == key_to_check
        }
        return len(available) == 1


def _load_yaml_file(path):
    """Loads YAML data from file"""
    try:
        with open(path, "r") as file:
            return yaml.safe_load(file)

    except yaml.error.YAMLError:
        raise MicadoInfraException(
            f"Could not load YAML at {path} for MiCADO deployment"
        )
