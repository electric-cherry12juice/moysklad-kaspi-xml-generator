import os
import logging
from celery import Celery
from dotenv import load_dotenv


load_dotenv()


logger = logging.getLogger("kaspi.worker")


app = Celery(
    "worker",
    broker="memory://",
    backend="cache+memory://",
    include=["tasks"]
)


app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
)


app.conf.timezone = "Asia/Almaty"


logger.info("Celery сконфигурирован в режиме eager (без Redis и воркера)")
