import io 
from functools import wraps

from enum import Enum

class ErrorMessages(Enum):
    
    ADT = ("U101", "There are error(s) in the generated ADT.")
    ID = ("U102", "The provided ID(s) are not correct.")
    PARAM = ("U103","There are error(s) in the parameter definition.")
    INPUT = ("U104", "Malformed input.") 
    IP = ("S101", "Floating IPs are not available.")


class MicadoBuildException(Exception):
    def __init__(self, message):
        self.message = message

class MicadoInfraException(Exception):
    def __init__(self, message):
        self.message = message


class MicadoAppException(Exception):
    def __init__(self, message):
        self.message = message


def handle_error(error_handler, final_task_handler = None, configs = None):
    """This is the base method for handling the exceptions."""
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            try:
                function(*args, **kwargs)
            except Exception as e:
                error_handler(e, configs, *args, **kwargs)
            finally:
                if final_task_handler is not None:
                    final_task_handler(configs, *args, **kwargs)
        return wrapper
    return decorator


def handle_node_data_error(e, configs, *args, **kwargs):
    """Handles the errors generated while setting the MiCADO node data."""
    if isinstance(e, AttributeError):
        args[0].node_data = ""
    else:
        raise e


def handle_create_node_error(e, configs, *args, **kwargs):
    """Handles the error while creating a MiCADO node."""
    threadID = args[0].threadID
    r = configs["redis_conn"]

    r.expire(threadID, 90)
    args[0].status_detail = str(e)
    args[0].status = configs["status"]
    args[0].set_status()
    raise e


def handle_submit_app_final_task(configs, *args, **kwargs):
    """This method closes the stream opened for a MiCADO application submission."""
    app_data = args[1]
    if isinstance(app_data, io.TextIOWrapper):
        app_data.close()

   
    
def handle_submit_app_error(e, configs, *args, **kwargs):
    """Handles the error(s) while submitting an application."""
    
    threadID = args[0].threadID
    r = configs["redis_conn"]
    STATUS_ERROR = configs["status"]
 
    r.expire(threadID, 90)
    args[0].status = STATUS_ERROR
    args[0]._kill_micado(msg=str(e))
    raise e
    


def handle_attach_to_existing_error(e, configs, *args, **kwargs):
    """Handles the error(s) while attaching MiCADO belonging to the thread ID"""

    if isinstance(e, LookupError):
        threadID = args[0].threadID
        r = configs["redis_conn"]
        r.delete(threadID)
    
    raise e


def handle_kill_micado_error(e, configs, *args, **kwargs):
    """Handles the error(s) while removing a MiCADO node."""
            
    STATUS_ERROR = configs["status"]
    STATUS_INFRA_REMOVE_ERROR = configs["status_detail"]
    if len(args)>1:
        msg = args[1]
    else:
        msg = None

    args[0].status = STATUS_ERROR
    args[0].status_detail = msg or STATUS_INFRA_REMOVE_ERROR
    args[0].set_status()
    raise e


def handle_valid_input_error(e, configs, *args, **kwargs):
    """Handles the error(s) while checking the input."""

    input_to_check = args[1]
    if isinstance(e, KeyError):
        error_message = " ".join(ErrorMessages.INPUT.value)
        raise MicadoBuildException(f"{error_message} {input_to_check}")
    else:
        raise e            