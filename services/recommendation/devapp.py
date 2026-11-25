"""박정우: wire real embedding/recommendation through a separately tested adapter."""
from services.recommendation.http_service import app

__all__ = ["app"]  # uvicorn entry point: services.recommendation.devapp:app
