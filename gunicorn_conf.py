import redis
from micado_eec.handle_micado import HandleMicado

bind = '0.0.0.0:5000'

workers = 5
timeout = 30

def on_starting(server):
    server.log.info("Cleaning-up uninitialised apps...")

    r = redis.StrictRedis("redis", decode_responses=True)
    if not r.ping():
        raise ConnectionError("Cannot connect to Redis")

    for thread_id in r.keys():
        try:
            micado = r.hget(thread_id, "micado_id")
            updated = r.hget(thread_id, "last_app_refresh")
        except redis.exceptions.ResponseError:
            raise TypeError("Database corrupt - contains wrong data types.")
        
        if not micado:
            server.log.info(f"App {thread_id} has no MiCADO, removing from DB.")
            r.delete(thread_id)
            continue

        if not updated:
            server.log.info(f"App {thread_id} has MiCADO, attempting abort.")
            r.expire(thread_id, 60)
            thread = HandleMicado(thread_id, f"process_{thread_id}")
            thread.start()
            thread.abort()

    server.log.info("App clean-up done.")

