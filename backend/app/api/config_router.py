"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : config_router.py

Exposes just the capture-relevant subset of colors_config.json to the
mobile app, so client-side ROI cropping can use the SAME bounds the
backend uses for panel extraction - one source of truth
(colors_config.json), not two copies that could drift out of sync.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.security import verify_api_key, AuthContext

router = APIRouter(prefix="/api/config", tags=["Config"])


@router.get("/capture-roi")
async def get_capture_roi(request: Request, auth: AuthContext = Depends(verify_api_key)):
    """
    Returns the union bounds of price_panel + indicator_panel from
    colors_config.json - the region actually worth capturing. Any
    screenshot content above top_percent or below bottom_percent (status
    bar, MT5 toolbar chrome, nav bar) is currently NOT part of either
    panel's own top/bottom bounds and can be safely cropped client-side
    before upload, once those bounds are tightened from their current
    0.0/1.0 defaults (see colors_config.json's roi section - right now
    they span the full image, so this is a real endpoint with a
    currently-trivial answer, not a placeholder).
    """
    roi = request.app.state.brain_cv_service.config.get("roi", {})
    price_panel = roi.get("price_panel", {"top_percent": 0.0, "bottom_percent": 1.0})
    indicator_panel = roi.get("indicator_panel", {"top_percent": 0.0, "bottom_percent": 1.0})

    return {
        "capture_top_percent": min(price_panel["top_percent"], indicator_panel["top_percent"]),
        "capture_bottom_percent": max(price_panel["bottom_percent"], indicator_panel["bottom_percent"]),
    }
