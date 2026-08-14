"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : brain_router.py

POST /aegis/analyze — screenshot in, signal out. Records upload diagnostics
(latency, success/failure) for the admin diagnostics views.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.core.upload_config import MAX_UPLOAD_SIZE
from app.security import verify_api_key, require_account_match, AuthContext
from app.core.account_rate_limit import enforce_account_rate_limit

router = APIRouter(tags=["Brain / Vision Analysis"])

_IMAGE_CONTENT_TYPES = (
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/x-ms-bmp",
    "application/octet-stream",
)


@router.post("/aegis/analyze")
async def analyze_screenshot(
    request: Request,
    image: UploadFile = File(...),
    account_id: str = Form(...),
    captured_at_ms: int | None = Form(None),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    await enforce_account_rate_limit(request, account_id)

    brain = request.app.state.brain_cv_service
    history_service = request.app.state.indicator_history
    upload_diag = getattr(request.app.state, "upload_diagnostics", None)

    t0 = time.perf_counter()

    ct = (image.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _IMAGE_CONTENT_TYPES and not ct.startswith("image/"):
        if upload_diag:
            await upload_diag.record(
                account_id=account_id,
                success=False,
                http_status=400,
                latency_ms=(time.perf_counter() - t0) * 1000,
                error_code="bad_content_type",
                detail=str(image.content_type),
            )
        raise HTTPException(
            status_code=400,
            detail=f"Only image files are accepted (got content-type={image.content_type!r}).",
        )

    image_bytes = await image.read()

    if not image_bytes:
        if upload_diag:
            await upload_diag.record(
                account_id=account_id,
                success=False,
                http_status=400,
                latency_ms=(time.perf_counter() - t0) * 1000,
                error_code="empty_body",
            )
        raise HTTPException(status_code=400, detail="Empty image body.")

    if len(image_bytes) > MAX_UPLOAD_SIZE:
        if upload_diag:
            await upload_diag.record(
                account_id=account_id,
                success=False,
                http_status=413,
                latency_ms=(time.perf_counter() - t0) * 1000,
                image_bytes=len(image_bytes),
                error_code="too_large",
            )
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(image_bytes)} bytes). Max is {MAX_UPLOAD_SIZE} bytes.",
        )

    try:
        cv_image = brain.decode_image(image_bytes)
        frame_state = brain.extract_frame_state(cv_image)
        await history_service.append_frame(account_id, frame_state, captured_at_ms)
        history = await history_service.get_history(account_id)
        result = brain.evaluate(history)
    except ValueError as exc:
        if upload_diag:
            await upload_diag.record(
                account_id=account_id,
                success=False,
                http_status=400,
                latency_ms=(time.perf_counter() - t0) * 1000,
                image_bytes=len(image_bytes),
                error_code="decode_or_value",
                detail=str(exc)[:300],
            )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        if upload_diag:
            await upload_diag.record(
                account_id=account_id,
                success=False,
                http_status=500,
                latency_ms=(time.perf_counter() - t0) * 1000,
                image_bytes=len(image_bytes),
                error_code="analysis_failed",
            )
        brain.logger.exception("Screenshot analysis failed for account %s", account_id)
        raise HTTPException(status_code=500, detail="Analysis failed.") from exc

    latency_ms = (time.perf_counter() - t0) * 1000
    if upload_diag:
        await upload_diag.record(
            account_id=account_id,
            success=True,
            http_status=200,
            latency_ms=latency_ms,
            image_bytes=len(image_bytes),
        )

    signal_history = request.app.state.signal_history
    await signal_history.record(
        account_id, result["signal"], result["confidence"], result["rule_name"], result["details"]
    )

    result["timestamp"] = int(time.time() * 1000)
    result["latency_ms"] = round(latency_ms, 1)
    return result
