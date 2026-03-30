import logging
import multiprocessing

from fastapi import FastAPI
from nicegui import ui
import uvicorn

from admin_helper_cli.logger import logger
from admin_helper_cli.settings import settings


logging.getLogger("uvicorn.error").parent = logger
logging.getLogger("uvicorn.access").parent = logger

api = FastAPI()


@ui.page("/")
async def root():
    return ui.label("Hello World")


ui.run_with(app=api)

uvicorn.run(api,
            host=str(settings.dashboard.host),
            port=settings.dashboard.port,
            # workers=settings.dashboard.workers,
            log_config={
                "version": 1,
                "loggers": {
                    "uvicorn.error": {
                        "level": logger.level,
                    },
                    "uvicorn.access": {
                        "level": logger.level
                    }
                }
            })
