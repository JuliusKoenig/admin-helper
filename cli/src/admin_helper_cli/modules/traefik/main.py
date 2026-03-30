import logging
import subprocess

from fastapi import FastAPI
from nicegui import ui
import uvicorn

from admin_helper_cli.logger import logger
from admin_helper_cli.settings import settings


print(f"Traefik Module")

subprocess.run([str(settings.traefik.binary_path), 
                "--help"], 
               check=True)
