"""

Low-level MiCADO API client, to be used by the higher-level ..client

"""

import requests

from .application import ApplicationMixin


class SubmitterClient(requests.Session, ApplicationMixin):
    """Low-level MiCADO client, prefer use of `micado.client`

    Args:
        endpoint (string): The endpoint of the running submitter.
        version (string, optional): API version. Defaults to 'v2.0'.
        verify (bool or string, optional): Whether to verify the
            connection with certificate on the client side. For
            self-signed certificates, this parameter can be a string
            path to the .pem certificate. Defaults to True.
        auth (tuple, optional): Basic auth username and password.
            Defaults to None.

    Raises:
        TypeError: If auth is in poorly formatted

    """

    def __init__(self, endpoint, version="v2.0", verify=True, auth=None):
        super().__init__()
        self.endpoint = endpoint.strip("/") + "/"
        self._version = version
        self.verify = verify
        if isinstance(auth, tuple):
            self.auth = auth
        elif auth:
            raise TypeError("Basic auth must be a tuple of (<user>, <pass>)")

    def _url(self, path):
        return self.endpoint + self._version + path
