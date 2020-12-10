"""
Higher-level methods to manage the MiCADO master
"""

from .base import Model

from ..api.client import SubmitterClient


class MicadoMaster(Model):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def master_id(self):
        return self.client.master_id

    @master_id.setter
    def master_id(self, master_id):
        self.client.master_id = master_id

    @property
    def launcher(self):
        return self.client.launcher

    @property
    def api(self):
        return self.client.api

    @api.setter
    def api(self, api):
        self.client.api = api

    def init_api(self):
        """Configure Submitter API

        Returns:
            SubmitterClient: return SubmitterClient
        """
        api_end = self.launcher._get_property("endpoint", self.master_id)
        api_vers = self.launcher._get_property("api_version", self.master_id)
        cert_path = self.launcher._get_property("cert_path", self.master_id)
        auth_data = (self.launcher._get_property("micado_user", self.master_id),
                     self.launcher._get_property("micado_password", self.master_id))
        return SubmitterClient(endpoint=api_end, version=api_vers, verify=cert_path, auth=auth_data)

    def attach(self, master_id):
        """Configure the master object to handle the instance
        created by the def:create()

        Args:
            master_id (string): master ID returned by def:create()
        """
        self.master_id = master_id
        self.api = self.init_api()

    def create(self, **kwargs):
        """Creates a new MiCADO master VM and deploy MiCADO service on it.

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

        Usage:

            >>> client.master.create(
            ...     auth_url='yourendpoint',
            ...     project_id='project_id',
            ...     image='image_name or image_id',
            ...     flavor='flavor_name or flavor_id',
            ...     network='network_name or network_id',
            ...     keypair='keypair_name or keypair_id',
            ...     security_group='security_group_name or security_group_id'
            ... )

        Returns:
            string: ID of MiCADO master

        """
        self.master_id = self.launcher.launch(**kwargs)
        self.api = self.init_api()
        return self.master_id

    def destroy(self):
        """Destroy running applications and the existing MiCADO master VM.

        Usage:

            >>> client.master.destroy()

        """
        self.api = self.init_api()
        self.api._destroy()
        self.api = None
        self.launcher.delete(self.master_id)
