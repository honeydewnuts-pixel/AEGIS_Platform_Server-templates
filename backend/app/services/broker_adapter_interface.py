from abc import ABC, abstractmethod
from typing import Any

from app.schemas.trading import (
    MarketOrderRequest,
    PendingOrderRequest,
    ModifyPositionRequest,
    ClosePositionRequest,
    TradeExecutionResponse,
)
from app.schemas.trading_entities import (
    Position,
    PendingOrder,
    AccountInfo,
    SymbolInfo,
)


class BrokerAdapter(ABC):
    """
    Interface Version: 2.1

    Health Contract:
    health_check() MUST return a dictionary containing at least:

    {
        "healthy": bool,
        "connected": bool,
        "broker": str,
        "adapter_version": str,
        "timestamp": str,
    }
    """

    # ==========================================================
    # CONNECTION CONTRACT
    # ==========================================================

    @abstractmethod
    async def connect(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(
        self,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def is_connected(
        self,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def reconnect(
        self,
    ) -> bool:
        raise NotImplementedError

    # ==========================================================
    # EXECUTION CONTRACT
    # ==========================================================

    @abstractmethod
    async def place_market_order(
        self,
        request: MarketOrderRequest,
    ) -> TradeExecutionResponse:
        raise NotImplementedError

    @abstractmethod
    async def place_pending_order(
        self,
        request: PendingOrderRequest,
    ) -> TradeExecutionResponse:
        raise NotImplementedError

    @abstractmethod
    async def modify_position(
        self,
        request: ModifyPositionRequest,
    ) -> TradeExecutionResponse:
        raise NotImplementedError

    @abstractmethod
    async def close_position(
        self,
        request: ClosePositionRequest,
    ) -> TradeExecutionResponse:
        raise NotImplementedError

    @abstractmethod
    async def cancel_pending_order(
        self,
        order_ticket: int,
    ) -> TradeExecutionResponse:
        raise NotImplementedError

    # ==========================================================
    # TRADING DATA CONTRACT
    # ==========================================================

    @abstractmethod
    async def get_positions(
        self,
    ) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    async def get_orders(
        self,
    ) -> list[PendingOrder]:
        raise NotImplementedError

    # ==========================================================
    # MARKET & ACCOUNT INFORMATION CONTRACT
    # ==========================================================

    @abstractmethod
    async def get_account_info(
        self,
    ) -> AccountInfo:
        raise NotImplementedError

    @abstractmethod
    async def get_symbol_info(
        self,
        symbol: str,
    ) -> SymbolInfo:
        raise NotImplementedError

    # ==========================================================
    # OPERATIONAL CONTRACT
    # ==========================================================

    @abstractmethod
    async def health_check(
        self,
    ) -> dict[str, Any]:
        raise NotImplementedError
