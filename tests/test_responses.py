import base64
import pytest
import json
import io

from werkzeug.datastructures import FileStorage

from micado_eec.micado import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def b64_yaml():
    adt = b"""\
    tosca_definitions_version: tosca_simple_yaml_1_2
    imports:
    - micado_types.yaml
    inputs:
      test:
        description: test adt input
    topology_template:
      node_templates:
        stressng:
          type: tosca.nodes.MiCADO.Container.Application.Docker.Deployment
          properties:
            image: lorel/docker-stress-ng
    """
    return base64.b64encode(adt).decode("utf-8")


def test_health_response(client):
    rv = client.get("micado_eec/health")
    assert rv.json["status"] == "ok"


def test_protocols_response(client):
    rv = client.get("micado_eec/supported_protocols")
    assert rv.json["protocols"] == []


def test_get_ports_with_json_artefact(client):
    body = {"artefact_data": {"downloadUrl_content": b64_yaml()}}
    rv = client.get("micado_eec/get_ports", json=body)
    assert rv.status_code == 200


def test_get_ports_with_file_artefact(client):
    body = {"downloadUrl_content": b64_yaml()}
    print(body)
    my_file = FileStorage(
        stream=io.BytesIO(json.dumps(body).encode("utf-8")),
        filename="artefact_data",
    )
    rv = client.get(
        "micado_eec/get_ports",
        data={"artefact_data": my_file},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 200


def test_get_ports_parameters(client):
    body = {"artefact_data": {"downloadUrl_content": b64_yaml()}}
    rv = client.get("micado_eec/get_ports", json=body)
    assert len(rv.json["parameters"]) == 1
    assert rv.json["parameters"][0]["key"] == "test"
    assert rv.json["parameters"][0]["description"] == "test adt input"
