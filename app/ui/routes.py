"""
UI Routes — Jinja2 template-rendered page views
"""
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

ui_router = APIRouter()


@ui_router.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})


@ui_router.get("/generate")
async def generate_page(request: Request):
    return templates.TemplateResponse("generator.html", {"request": request, "active": "generate"})


@ui_router.get("/metabase")
async def metabase_page(request: Request):
    return templates.TemplateResponse("metabase.html", {"request": request, "active": "metabase"})


@ui_router.get("/history")
async def history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request, "active": "history"})
