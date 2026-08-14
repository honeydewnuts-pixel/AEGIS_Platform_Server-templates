"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : trading.py

Purpose
-------
Defines strongly typed request and response models for all trading
operations within AEGIS.

Current Stage:
CP-007 – File 1

Overview
--------
These schemas provide validation, documentation and strong typing
for the Trade Execution subsystem.

Why use Pydantic models?
------------------------
Instead of passing raw dictionaries between services, AEGIS uses
typed models. This provides:

• Automatic validation
• Better readability
• Improved IDE support
• Automatic OpenAPI documentation
• Easier maintenance

These models are broker-independent and can be reused by MT5,
MT4, cTrader, FIX, Binance, Bybit, IBKR and future adapters.
====================================================================
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MarketOrderRequest(BaseModel):
    """
    Request to place an immediate market order.

    A market order executes at the best available market price.
    """

    symbol: str = Field(
        ...,
        description="Trading symbol or instrument.",
        examples=["EURUSD"],
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Trading volume (lots).",
        examples=[0.10],
    )

    order_type: Literal["BUY", "SELL"] = Field(
        ...,
        description="Market order direction.",
        examples=["BUY"],
    )

    account_id: str = Field(
        ...,
        description="Broker account identifier.",
        examples=["12345678"],
    )

    comment: str | None = Field(
        default=None,
        description="Optional order comment.",
        examples=["AEGIS AI Trade"],
    )


class PendingOrderRequest(BaseModel):
    """
    Request to place a pending order.

    Pending orders remain inactive until the specified trigger
    price is reached.
    """

    symbol: str = Field(
        ...,
        description="Trading symbol.",
        examples=["EURUSD"],
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Trading volume.",
        examples=[0.10],
    )

    order_type: Literal[
        "BUY_LIMIT",
        "SELL_LIMIT",
        "BUY_STOP",
        "SELL_STOP",
    ] = Field(
        ...,
        description="Pending order type.",
        examples=["BUY_LIMIT"],
    )

    price: float = Field(
        ...,
        description="Pending order trigger price.",
        examples=[1.12345],
    )

    sl: float | None = Field(
        default=None,
        description="Optional stop-loss price.",
        examples=[1.12000],
    )

    tp: float | None = Field(
        default=None,
        description="Optional take-profit price.",
        examples=[1.13000],
    )

    account_id: str = Field(
        ...,
        description="Broker account identifier.",
        examples=["12345678"],
    )


class ModifyPositionRequest(BaseModel):
    """
    Request to modify an existing open position.

    Used for updating stop-loss and/or take-profit levels.
    """

    ticket: int = Field(
        ...,
        description="Broker position ticket.",
        examples=[987654321],
    )

    sl: float | None = Field(
        default=None,
        description="New stop-loss price.",
        examples=[1.11800],
    )

    tp: float | None = Field(
        default=None,
        description="New take-profit price.",
        examples=[1.13200],
    )

    account_id: str = Field(
        ...,
        description="Broker account identifier.",
        examples=["12345678"],
    )


class ClosePositionRequest(BaseModel):
    """
    Request to close a position.

    If volume is omitted, the entire position is closed.
    """

    ticket: int = Field(
        ...,
        description="Broker position ticket.",
        examples=[987654321],
    )

    volume: float | None = Field(
        default=None,
        gt=0,
        description="Optional partial close volume.",
        examples=[0.05],
    )

    account_id: str = Field(
        ...,
        description="Broker account identifier.",
        examples=["12345678"],
    )


class TradeExecutionResponse(BaseModel):
    """
    Standard response returned after any trading operation.

    This model is used for both successful and failed execution
    requests, providing a consistent interface across all broker
    implementations.
    """

    success: bool = Field(
        ...,
        description="True if the operation completed successfully.",
        examples=[True],
    )

    ticket: int | None = Field(
        default=None,
        description="Ticket assigned by the broker.",
        examples=[987654321],
    )

    message: str = Field(
        ...,
        description="Human-readable execution result.",
        examples=["Market order executed successfully."],
    )

    price: float | None = Field(
        default=None,
        description="Executed price.",
        examples=[1.12346],
    )

    error_code: int | None = Field(
        default=None,
        description="Broker or platform error code.",
        examples=[10009],
    )
