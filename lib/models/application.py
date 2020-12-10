"""Module for managing and representing applications in MiCADO

"""

from .base import Model, Resource


class Application(Model):
    """Representation of an application deployed in MiCADO

    The state of an application can be refreshed with reload()
    """

    @property
    def adaptors(self):
        """
        Adaptor info for this application
        """
        return self.info.get("adaptors")


class Applications(Resource):
    """Model for managing applications in MiCADO

    Basic CRUD functionality is implemented here with
    create(), list()/get(), update() and delete()

    """

    model = Application

    def __init__(self, client):
        self.client = client

    def get(self, app_id):
        """Retrieves info on a specific application, given its ID

        Args:
            app_id (string): Application ID to fetch. Required

        Usage:

            >>> my_app = client.applications.get("stresstest")
            >>> my_app.id
            "stresstest"
            >>> my_app.adaptors
            {'KubernetesAdaptor': 'Executed', 'OccopusAdaptor': 'Skipped'}

        Returns:
            Application object: Relevant information for a single application
        """
        return self._make_model(app_id, self.client.api.inspect_app(app_id))

    def list(self):
        """Retrieves the available list of applications in MiCADO

        Usage:

            >>> running_apps = client.applications.list()
            >>> [app.id for app in running_apps]
            ["stresstest"]

        Returns:
            list of Application objects: Relevant info for all applications
        """
        app_ids = self.client.api.applications()
        return [self.get(i) for i in app_ids]

    def create(self, app_id=None, **kwargs):
        """Creates a new application in MiCADO

        Args:
            app_id (string, optional): Application ID. Generated if None.
            adt (dict, optional): YAML dict of Application Description
                Template. Required if URL is empty. Defaults to None.
            url (string, optional): URL of YAML ADT. Required if ADT is empty.
                Defaults to None.
            params (dict, optional): TOSCA input parameters. Defaults to {}.
            dryrun (bool, optional): Flag to skip execution of components.
                Defaults to False.

        Usage:

            >>> client.applications.create(app_id="stresstest",
                                           url="example.com/repo/adt.yaml")
            "stresstest created successfully"

        Returns:
            dict: ID and status of deployment
        """
        kwargs["app_id"] = app_id
        return self.client.api.create_app(**kwargs)

    def delete(self, app_id):
        """Deletes an application in MiCADO given its ID.

        Args:
            app_id (string): Application ID to delete

        Usage:

            >>> client.applications.delete("stresstest")
            "stresstest deleted successfully"

        Returns:
            dict: ID and status of deletion
        """
        return self.client.api.delete_app(app_id)
