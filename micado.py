import json
import uuid
import tempfile

from flask import jsonify, Flask, request
from werkzeug.exceptions import BadRequest, NotFound

from handle_micado import HandleMicado

threads = {}

app = Flask(__name__)
app.debug = True


@app.errorhandler(BadRequest)
def handle_generic_bad_request(error):
    return jsonify({"error": f"{error}"}), 400


@app.errorhandler(NotFound)
def handle_generic_not_found(error):
    return jsonify({"error": f"{error}"}), 404


@app.errorhandler(json.decoder.JSONDecodeError)
def handle_json_decode_error(error):
    return (
        jsonify(
            {"error": "400 Bad Request: Cannot decode input file to JSON"}
        ),
        400,
    )


@app.route("/micado_eec/health", methods=["GET"])
def get_health():
    """Returns the health of the EEC with a status message and code

    Returns:
        Response: JSON object
    """
    return jsonify({"status": "ok"})


@app.route("/micado_eec/supported_protocols", methods=["GET"])
def get_supported_protocols():
    """Returns protocols supported by the EEC

    Returns:
        Response: JSON object
    """
    return jsonify({"protocols": []})


@app.route("/micado_eec/get_ports", methods=["GET"])
def get_ports():
    """Returns required input files, created output files and available parameters

    Returns:
        Response: JSON object
    """
    # This GET request expects a body
    submit_data = request.json
    free_inputs, free_outputs, parameters = _get_artefact_ports(submit_data)
    return jsonify(
        {
            "free_inputs": free_inputs,
            "free_outputs": free_outputs,
            "parameters": parameters,
        }
    )


def _get_artefact_ports(artefact_data):
    """Fetches input, outputs and parameters to return via get_ports()

    List items under `free_inputs` and `free_outputs` contain these keys:

        filename: the name of the input
        id: a unique identifier of the input port, later when submitting
            artefacts for execution, the EMGWAM will use this identifier
            to specify the location of data to be used for the given port,
        nodename (optional):  name of the node in the workflow for the input

    List items under parameters contain the following keys:

        key: the key for the parameter,
        description: a textual description for the parameter for the user.

    Returns:
        tuple of lists of dicts: `free_inputs`, `free_outputs`, `parameters`
    """
    free_inputs, free_outputs, parameters = [], [], []

    # If there is no `adt` property pre-registered in the artefact
    # let the user know it is required as input
    if "adt" not in artefact_data:
        adt_input = {
            "filename": "adt.yaml",
            "id": "4d7",
        }
        free_inputs.append(adt_input)

    return free_inputs, free_outputs, parameters


@app.route("/micado_eec/get_eec_properties", methods=["GET"])
def get_properties():
    """Retrieves EEC and artefact specific details, given artefact data

    Returns:
        Response: JSON object with key `needs_abort` set True/False
    """
    # this GET request should include a body
    submit_data = request.json

    abort = _check_termination(submit_data)
    return jsonify({"needs_abort": abort})


def _check_termination(artefact):
    """Checks artefact to see if submission needs a manual abort

    Args:
        artefact (dict): JSON artefact data

    Returns:
        bool: if the submission should be manually aborted
    """
    # do something
    return True


@app.route("/micado_eec/submissions", methods=["POST"])
def submit_micado():
    """Submits an artefact to the EEC"""
    files = {x: request.files[x] for x in request.files}
    try:
        artefact_data = json.load(files.pop("artefact_data"))
        inouts = json.load(files.pop("inouts", {}))
    except KeyError as error:
        raise BadRequest(f"Missing input: {error}")

    submission_id = _submit_micado(
        artefact_data,
        inouts,
        files,
        *_get_artefact_ports(),
    )
    return jsonify({"submission_id": submission_id})


def _submit_micado(
    artefact_data,
    inouts,
    files,
    free_inputs,
    free_outputs,
    parameters,
):
    """Submits the artefact as an ADT to MiCADO

    Args:
        artefact_data (dict): JSON representation of artefact
        inouts (dict): content of input, output and parameters
        passfiles (dict): dict {file ID: JSON repr of file}
        artefact_ports (tuple): free_inputs, free_outputs and parameters

    Returns:
        string: ID of this submission (also of the thread)
    """
    thread_id = str(uuid.uuid4())
    file_paths = _write_files(files)
    thread = HandleMicado(
        thread_id,
        f"process_{thread_id}",
        artefact_data,
        inouts,
        file_paths,
        free_inputs,
        free_outputs,
        parameters,
    )
    threads[thread_id] = thread
    thread.start()
    return thread_id


def _write_files(files):
    """Writes any additional files to disk and returns their location

    Args:
        files (dict): map of file identifiers with their file data

    Returns:
        dict: map of file identifiers with their file paths
    """
    tempdir = tempfile.mkdtemp()
    file_paths = {}

    for file_id in files:
        path = tempdir + "/" + file_id
        with open(path, "wb") as file:
            while True:
                data = files[file_id].read(65536)
                if not data:
                    break
                file.write(data)

        print(f"Wrote content of file {file_id} to {path}")
        file_paths[file_id] = path

    return file_paths


@app.route("/micado_eec/submissions/<submission_id>", methods=["GET"])
def get_submission(submission_id):
    """Retrieves details of a specific submission, by its ID

    Args:
        submission_id (str): ID of the submission to retrieve

    Returns:
        Response: JSON object
    """
    thread = threads.get(submission_id)
    if not thread:
        raise NotFound("Cannot find submission {submission_id}")
    if thread.is_alive():
        return jsonify(thread.get_status())
    else:
        threads.pop(submission_id, None)
        return jsonify(
            {"status": 4, "details": "the requested submission was terminated"}
        )


@app.route(
    "/micado_eec/submissions/<submission_id>/usage_info", methods=["GET"]
)
def get_micado_resource_usage(submission_id):
    """Retrieves resource usage thus far for a submission, by ID

    Args:
        submission_id (str): ID of the submission to retrieve

    Returns:
        Response: JSON object
    """
    thread = threads.get(submission_id)
    if not thread:
        raise NotFound("Cannot find submission {submission_id}")
    runtime_seconds = thread.runtime_seconds()
    return jsonify({"runtime_seconds": runtime_seconds})


@app.route("/micado_eec/submissions/<submission_id>", methods=["DELETE"])
def remove_micado(submission_id):
    """Abort a submission

    Args:
        submission_id (str): ID of the submission to delete

    Returns:
        Response: JSON Object
    """
    if not _remove_micado(submission_id):
        return jsonify({"error": "500 Internal Server Error"}), 500
    return jsonify({"status": "submission removal successfully initiated"})


def _remove_micado(submission_id):
    """Deletes the application and the MiCADO cluster

    Args:
        submission_id (str): ID of the submission to remove
    """
    thread = threads.get(submission_id)
    if not thread:
        raise NotFound("Cannot find submission {submission_id}")
    thread.abort()
    return threads.pop(submission_id, None)


@app.route(
    "/micado_eec/submissions/<submission_id>/<port_id>", methods=["GET"]
)
def get_result_file(submission_id, port_id):
    """Retrieve results data where protocol not handled by the EEC

    Args:
        submission_id (str): ID of the submission to retrieve
        port_id (str): ID of the results data to retrieve

    Returns:
        Response: JSON Object
    """
    # TODO: ?


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
