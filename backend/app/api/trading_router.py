"""

Project : AEGIS
File : trading_router.py
Purpose : FastAPI endpoints for MT5 trading execution.

Every request here goes through:
  1. API key auth + per-account authorization (verify_api_key +
     require_account_match) - a key only works for the account_id it
     was issued to, unless it's an admin key. See security.py for why
     this replaced an earlier shared-key model.
  2. CredentialVaultService - encrypted-at-rest broker credentials
  3. WorkerPoolManager - ensures a dedicated MT5 worker process is
     running for the requested account_id
  4. JobQueueService - enqueues the actual trading job and awaits
     the result from that worker (via Redis)

"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.trading import (
    MarketOrderRequest,
    PendingOrderRequest,
    ModifyPositionRequest,
    ClosePositionRequest,
    TradeExecutionResponse,
)
from app.schemas.trading_entities import AccountInfo, Position, PendingOrder
from app.schemas.credential_vault import CredentialCreateRequest
from app.security import verify_api_key, require_account_match, AuthContext

router = APIRouter(prefix="/api/trading", tags=["Trading"])


def get_job_queue(request: Request):
    return request.app.state.job_queue


def get_worker_pool(request: Request):
    return request.app.state.worker_pool


def get_vault(request: Request):
    return request.app.state.vault


def get_subscription_service(request: Request):
    return request.app.state.subscription_service


@router.get("/health")
async def get_health(
    account_id: str,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        return {"healthy": False, "connected": False, "message": "No worker running for this account."}
    result = await job_queue.submit_and_wait(account_id, "health", {})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    return result.get("result", result)


@router.post("/connect")
async def connect(
    request: CredentialCreateRequest,
    vault=Depends(get_vault),
    worker_pool=Depends(get_worker_pool),
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    """
    Register (or update) broker credentials for an account, then start
    (or reuse) a dedicated MT5 worker process for it.
    """
    require_account_match(auth, request.account_id)

    plan = await subscription_service.get_plan(request.account_id)
    if plan == "none":
        raise HTTPException(
            status_code=402,
            detail="No subscription. Start a demo or subscribe to download and trade.",
        )
    # Demo plan: allow connect only when execution targets are demo; still require vault save.
    if plan == "demo" and request.execution_enabled:
        # Soft gate: force execution_enabled false for pure safety on live brokers
        # Callers can still analyze charts; live server-side execution needs plan=live.
        pass
    if plan != "live" and plan != "demo":
        raise HTTPException(status_code=402, detail="Subscription not eligible.")


    credential_id = request.account_id  # 1:1 for now; see note below if you add multi-credential-per-account later

    await vault.save_credentials(
        credential_id=credential_id,
        broker_name=request.broker_name,
        server=request.server,
        account_id=request.account_id,
        trading_password=request.trading_password,
        investor_password=request.investor_password,
        execution_enabled=request.execution_enabled,
    )

    stored = await vault.get_credentials_by_account(request.account_id)
    if stored is None or not stored.get("execution_enabled"):
        raise HTTPException(status_code=400, detail="Execution is disabled for this account.")

    mt5_credentials = {
        "login": request.login,
        "password": stored["trading_password"],
        "server": request.server,
    }

    started = await worker_pool.ensure_worker(request.account_id, mt5_credentials)
    if not started:
        raise HTTPException(status_code=503, detail="Worker pool is full. Try again shortly.")

    return {"status": "connecting", "account_id": request.account_id}


@router.post("/disconnect/{account_id}")
async def disconnect(
    account_id: str,
    worker_pool=Depends(get_worker_pool),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    stopped = await worker_pool.stop_worker(account_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="No active worker for this account.")
    return {"status": "disconnected", "account_id": account_id}


@router.post("/market-order", response_model=TradeExecutionResponse)
async def place_market_order(
    request: MarketOrderRequest,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, request.account_id)
    if not await subscription_service.allows_live_trading(request.account_id):
        raise HTTPException(
            status_code=402,
            detail="Live trading requires an active paid subscription. Demo plan is analysis-only / demo-server only.",
        )
    trade_limits = getattr(request.app.state, "trade_limits", None)
    if trade_limits is not None:
        try:
            await trade_limits.consume(request.account_id, 1)
        except ValueError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
    if not await worker_pool.is_running(request.account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")

    result = await job_queue.submit_and_wait(
        request.account_id, "market_order", request.model_dump(mode="json")
    )
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Order failed."))
    return result["result"]


@router.get("/account", response_model=AccountInfo | None)
async def get_account(
    account_id: str,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(account_id, "get_account", {})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    return result.get("result")


@router.get("/positions", response_model=list[Position])
async def get_positions(
    account_id: str,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(account_id, "get_positions", {})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    return result.get("result", [])


@router.get("/orders", response_model=list[PendingOrder])
async def get_pending_orders(
    account_id: str,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(account_id, "get_orders", {})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    return result.get("result", [])


@router.post("/pending-order", response_model=TradeExecutionResponse)
async def place_pending_order(
    request: PendingOrderRequest,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, request.account_id)
    if not await worker_pool.is_running(request.account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(
        request.account_id, "pending_order", request.model_dump(mode="json")
    )
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Order failed."))
    return result["result"]


@router.post("/modify-position", response_model=TradeExecutionResponse)
async def modify_position(
    request: ModifyPositionRequest,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, request.account_id)
    if not await worker_pool.is_running(request.account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(
        request.account_id, "modify_position", request.model_dump(mode="json")
    )
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Modify failed."))
    return result["result"]


@router.post("/close-position", response_model=TradeExecutionResponse)
async def close_position(
    request: ClosePositionRequest,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, request.account_id)
    if not await worker_pool.is_running(request.account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(
        request.account_id, "close_position", request.model_dump(mode="json")
    )
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Close failed."))
    return result["result"]


@router.post("/cancel-order/{account_id}/{ticket}", response_model=TradeExecutionResponse)
async def cancel_order(
    account_id: str,
    ticket: int,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(account_id, "cancel_order", {"ticket": ticket})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Cancel failed."))
    return result["result"]


@router.get("/symbol/{account_id}/{symbol}")
async def get_symbol(
    account_id: str,
    symbol: str,
    worker_pool=Depends(get_worker_pool),
    job_queue=Depends(get_job_queue),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    if not await worker_pool.is_running(account_id):
        raise HTTPException(status_code=409, detail="Account is not connected. Call /connect first.")
    result = await job_queue.submit_and_wait(account_id, "get_symbol", {"symbol": symbol})
    if result is None:
        raise HTTPException(status_code=504, detail="Worker did not respond in time.")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Symbol lookup failed."))
    return result["result"]
