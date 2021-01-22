""" Base64 encode an ADT to fill artefact_data """

import base64
import sys

try:
    filename = sys.argv[1]
except IndexError:
    sys.exit("Please specify an ADT")

with open(filename) as file:
    adt = base64.b64encode(file.read().encode()).decode("utf-8")

with open("artefact_data", "w") as file:
    file.write('{"downloadUrl_content": "% s"}' % adt)
