"""

Project : AEGIS
System : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File : mt5_execution_service.py
Version : 1.0.0 - DEMO_ONLY

Purpose : High-level execution service that uses MT5Adapter
          for all broker operations. This is what APIs will call.
          
SAFETY: DEMO_ONLY mode enforced. Will refuse live accounts.

"""

from __future__ import annotations
from typing import Any

from app.core.logging import configure_logging
from app.services.adapters.mt5_adapter import MT5Adapter
from app.schemas.trading import (
    MarketOrderRequest,
    PendingOrderRequest,
    ModifyPositionRequest,
    ClosePositionRequest,
    TradeExecutionResponse,
)
from app.schemas.trading_entities import AccountInfo

logger = configure_logging(__name__)

class MT5ExecutionService:
    """
    Orchestrates trading operations using the MT5Adapter.
    This service should be called by routers and strategies.
    DEMO_ONLY: Blocks trading on accounts > 10000 leverage or non-demo servers
    """

    def __init__(self) -> None:
        self.adapter = MT5Adapter()
        self.DEMO_ONLY = True  # Safety flag

    # ==========================================================
    # LIFECYCLE
    # ==========================================================

    async def connect(self, credentials: dict[str, Any]) -> bool:
        """Connect to MT5 using provided credentials"""
        server = str(credentials.get("server", "")).lower()
        if self.DEMO_ONLY and "demo" not in server and "practice" not in server:
            logger.error("DEMO_ONLY mode: Refusing to connect to live server: %s", server)
            return False
        return await self.adapter.connect(credentials)

    async def disconnect(self) -> bool:
        """Disconnect from MT5"""
        return await self.adapter.disconnect()

    async def health_check(self) -> dict[str, Any]:
        """Get adapter health"""
        return await self.adapter.health_check()

    # ==========================================================
    # TRADING OPERATIONS
    # ==========================================================

    async def execute_market_order(
        self, request: MarketOrderRequest
    ) -> TradeExecutionResponse:
        """Execute market order"""
        logger.info("Executing market order: %s %s", request.order_type, request.symbol)
        return await self.adapter.place_market_order(request)

    async def execute_pending_order(
        self, request: PendingOrderRequest
    ) -> TradeExecutionResponse:
        """Execute pending order"""
        logger.info("Placing pending order: %s %s", request.order_type, request.symbol)
        return await self.adapter.place_pending_order(request)

    async def modify_trade(
        self, request: ModifyPositionRequest
    ) -> TradeExecutionResponse:
        """Modify SL/TP"""
        logger.info("Modifying position: %s", request.ticket)
        return await self.adapter.modify_position(request)

    async def close_trade(
        self, request: ClosePositionRequest
    ) -> TradeExecutionResponse:
        """Close position"""
        logger.info("Closing position: %s", request.ticket)
        return await self.adapter.close_position(request)

    async def cancel_order(self, ticket: int) -> TradeExecutionResponse:
        """Cancel pending order"""
        logger.info("Cancelling order: %s", ticket)
        return await self.adapter.cancel_pending_order(ticket)

    # ==========================================================
    # DATA QUERIES
    # ==========================================================

    async def get_account(self) -> AccountInfo | None:
        return await self.adapter.get_account_info()

    async def get_positions(self):
        return await self.adapter.get_positions()

    async def get_pending_orders(self):
        return await self.adapter.get_orders()

    async def get_symbol(self, symbol: str):
        return await self.adapter.get_symbol_info(symbol)
