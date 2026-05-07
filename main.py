import os
import uuid
import logging
import threading
from fastapi import FastAPI, Request, HTTPException, Security
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security.api_key import APIKeyHeader
from tasks import update_kaspi_catalog


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kaspi.main")


app = FastAPI()

os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

XML_PATH = "static/kaspi_catalog.xml"

task_store: dict[str, dict] = {}


API_KEY = os.getenv("APP_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)):
    if not API_KEY:
        logger.warning(
            "APP_API_KEY не задан — эндпоинт /run-task открыт без авторизации."
        )
        return
    if api_key != API_KEY:
        logger.warning("Неверный API-ключ: попытка несанкционированного запуска задачи")
        raise HTTPException(status_code=403, detail="Неверный API-ключ")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/run-task")
async def run_task(_: None = Security(verify_api_key)):

    task_id = str(uuid.uuid4())
    task_store[task_id] = {"status": "PENDING", "result": None}
    logger.info(f"Новая задача создана: task_id={task_id}")

    def run():
        task_store[task_id]["status"] = "PROGRESS"
        logger.info(f"[{task_id}] Задача запущена в фоновом потоке")
        try:
            result = update_kaspi_catalog.apply()
            task_store[task_id] = {"status": "SUCCESS", "result": result.result}
            logger.info(f"[{task_id}] ✓ Задача выполнена успешно: {result.result}")
        except Exception as e:
            task_store[task_id] = {"status": "FAILURE", "result": str(e)}
            logger.error(f"[{task_id}] ✗ Ошибка выполнения задачи: {e}", exc_info=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"[{task_id}] Фоновый поток запущен")
    return {"task_id": task_id}


@app.get("/task-status/{task_id}")
async def get_status(task_id: str):
    task = task_store.get(task_id)
    if not task:
        logger.warning(f"Запрос статуса для несуществующей задачи: task_id={task_id}")
        raise HTTPException(status_code=404, detail="Задача не найдена")

    logger.debug(f"[{task_id}] Статус: {task['status']}")
    return {
        "task_id": task_id,
        "task_status": task["status"],
        "task_result": task["result"],
    }


@app.get("/kaspi.xml")
async def serve_kaspi_xml():

    if not os.path.exists(XML_PATH):
        logger.warning("Запрос /kaspi.xml — файл ещё не сгенерирован")
        raise HTTPException(
            status_code=404,
            detail="XML файл ещё не сгенерирован. Нажмите кнопку на главной странице."
        )

    file_size = os.path.getsize(XML_PATH)
    logger.info(f"Отдаём /kaspi.xml ({file_size} байт)")

    return FileResponse(
        path=XML_PATH,
        media_type="application/xml",
        filename="kaspi_catalog.xml",
    )
