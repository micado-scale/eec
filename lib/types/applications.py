import ast


class ApplicationInfo(dict):
    def __init__(self, adt=None, url=None, params={}, dryrun=False):
        """Creates required JSON parameters for create_app

        Args:
            adt (dict, optional): YAML dict of Application Description
                Template. Required is URL is empty. Defaults to None.
            url (string, optional): URL of YAML ADT. Required if ADT is empty.
                Defaults to None.
            params (dict, optional): TOSCA input parameters. Defaults to {}.
            dryrun (bool, optional): Flag to skip execution of components.
                Defaults to False.
        """
        if adt:
            self["adt"] = adt
        elif url:
            self["url"] = url
        if isinstance(params, str):
            self["params"] = ast.literal_eval(params)
        elif isinstance(params, dict):
            self["params"] = params
        self["dryrun"] = dryrun
