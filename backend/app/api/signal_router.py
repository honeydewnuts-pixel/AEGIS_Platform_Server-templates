"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : signal_router.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.security import verify_api_key, require_account_match, AuthContext

router = APIRouter(prefix="/api/signals", tags=["Signal History"])


@router.get("/{account_id}")
async def get_signal_history(
    account_id: str,
    request: Request,
    limit: int = Query(50, le=200),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    signal_history = request.app.state.signal_history
    return await signal_history.get_history(account_id, limit)
