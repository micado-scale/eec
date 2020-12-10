"""

Base class for models and resource collections in MiCADO

"""


class Model:
    """Generic class for models of objects in MiCADO

    """

    def __init__(self, client, id=None, info=None, resource=None):
        self.client = client
        self.id = id
        self.info = info or {}
        self.resource = resource

    def reload(self):
        if not self.resource:
            pass
        updated = self.resource.get(self.id)
        self.info = updated.info


class Resource:
    """Generic class for collections of resources in MiCADO

    """

    model = None

    def __init__(self, client=None):
        self.client = client

    def get(self):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def create(self):
        raise NotImplementedError

    def _make_model(self, id, info):
        return self.model(self.client, id, info, self)
