import pytest

from micado_eec.micado import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_response(client):
    rv = client.get("micado_eec/health")
    assert rv.json["status"] == "ok"


def test_protocols_response(client):
    rv = client.get("micado_eec/supported_protocols")
    assert rv.json["protocols"] == []


def test_get_ports_user_adt(client):
    body = {"artefact_data": {}}
    rv = client.get("micado_eec/get_ports", json=body)
    for element in rv.json["free_inputs"]:
        if "adt.yaml" in element.values():
            break
    else:
        pytest.fail("ADT missing from free inputs")


def test_get_ports_preregistered_adt(client):
    body = {"artefact_data": {"adt": "mybase64adtgoeshere"}}
    rv = client.get("micado_eec/get_ports", json=body)
    for element in rv.json["free_inputs"]:
        if "adt.yaml" in element.values():
            pytest.fail("ADT present in free inputs")
