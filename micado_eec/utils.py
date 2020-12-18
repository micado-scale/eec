import base64
import json

import ruamel.yaml as yaml


def load_yaml_file(path):
    """Loads YAML data from file"""
    with open(path, "r") as file:
        return yaml.safe_load(file)


def base64_to_yaml(base64_yaml):
    """Decode base64 to YAML

    Args:
        base64_yaml (string): base64 representation of YAML

    Returns:
        dict: dict representation of YAML
    """
    try:
        decoded_string = base64.b64decode(base64_yaml).decode("utf-8")
        return yaml.safe_load(decoded_string)
    except yaml.YAMLError:
        raise ValueError("Could not parse YAML")
    except ValueError:
        raise ValueError("Could not decode base64 string")


def file_to_json(file):
    """Transforms Flask file object to json

    Args:
        file (werkzeug.FileStorage): File object

    Returns:
        dict: JSON data from file
    """
    return json.loads(file.read().decode("utf-8"))


def is_valid_adt(adt):
    return all(
        [
            adt["tosca_definitions_version"]
            in ["tosca_simple_yaml_1_0", "tosca_simple_yaml_1_2"],
            adt["imports"],
            adt["topology_template"]["node_templates"],
        ]
    )


def get_adt_inputs(adt):
    return [
        {
            "key": key,
            "description": details.get("description", "n/a").rstrip(),
        }
        for key, details in adt.get("inputs", {}).items()
    ]
