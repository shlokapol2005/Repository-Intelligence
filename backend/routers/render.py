"""
render.py — Diagram rendering endpoints.

Surface-agnostic image rendering so every client (Discord bot, future Slack
adapter, web UI) turns Mermaid into a PNG the same way, via one primitive.
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from utils.diagram_renderer import render_mermaid_png_sync

router = APIRouter()


class MermaidRequest(BaseModel):
    mermaid: str


@router.post(
    "/mermaid",
    responses={200: {"content": {"image/png": {}}}},
    response_class=Response,
)
async def render_mermaid(req: MermaidRequest):
    """Render Mermaid source to a PNG image (image/png bytes)."""
    png = render_mermaid_png_sync(req.mermaid)
    if png is None:
        raise HTTPException(
            status_code=502,
            detail="Diagram rendering failed (renderer unreachable or invalid Mermaid).",
        )
    return Response(content=png, media_type="image/png")
