"""Render entry point for the private hosted FastAPI service."""

from frontend.hosted_api import create_hosted_app

app = create_hosted_app()
