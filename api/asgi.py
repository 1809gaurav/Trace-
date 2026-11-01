"""ASGI entry point for Uvicorn."""

from api.config import Settings
from api.main import create_app

app = create_app(Settings(), initialize_db=True)
