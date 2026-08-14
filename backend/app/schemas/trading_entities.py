"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : trading_entities.py

Purpose
-------
Defines broker-independent trading domain entities used throughout
the AEGIS execution subsystem.

Current Stage:
CP-007 – File 2A

Overview
--------
These models represent data returned from broker adapters rather
than requests sent to them.

Keeping these entities separate from request models provides:

• Clear separation of responsibilities
• Strong typing
• Better OpenAPI documentation
• Broker-independent domain models
• Easier support for multiple brokers

Future broker adapters (MT5, MT4, cTrader, FIX, Binance, Bybit,
IBKR, etc.) should convert their native SDK objects into these
common models before returning them to the rest of AEGIS.
====================================================================
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderType(str, Enum):
    """
    Supported trading order types.

    The enumeration inherits from both `str` and `Enum` so values
    serialize naturally in JSON responses.
    """

    BUY = "BUY"
    SELL = "SELL"

    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"

    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class Position(BaseModel):
    """
    Represents an open trading position.

    Broker adapters convert native position objects into this
    broker-independent model.
    """

    ticket: int = Field(
        ...,
        description="Broker position ticket.",
        examples=[987654321],
    )

    symbol: str = Field(
        ...,
        description="Trading instrument.",
        examples=["EURUSD"],
    )

    type: OrderType = Field(
        ...,
        description="Position direction.",
        examples=["BUY"],
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Open position volume (lots).",
        examples=[0.10],
    )

    open_price: float = Field(
        ...,
        description="Executed entry price.",
        examples=[1.12345],
    )

    current_price: float = Field(
        ...,
        description="Latest market price.",
        examples=[1.12410],
    )

    sl: float | None = Field(
        default=None,
        description="Current stop-loss.",
        examples=[1.12000],
    )

    tp: float | None = Field(
        default=None,
        description="Current take-profit.",
        examples=[1.13000],
    )

    profit: float = Field(
        ...,
        description="Current floating profit or loss.",
        examples=[12.45],
    )

    swap: float = Field(
        ...,
        description="Accumulated swap value.",
        examples=[-0.15],
    )

    open_time: datetime = Field(
        ...,
        description="Position opening timestamp.",
    )


class PendingOrder(BaseModel):
    """
    Represents a pending order waiting to be triggered.
    """

    ticket: int = Field(
        ...,
        description="Broker pending order ticket.",
        examples=[123456789],
    )

    symbol: str = Field(
        ...,
        description="Trading instrument.",
        examples=["GBPUSD"],
    )

    type: OrderType = Field(
        ...,
        description="Pending order type.",
        examples=["BUY_LIMIT"],
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Order volume (lots).",
        examples=[0.20],
    )

    price: float = Field(
        ...,
        description="Trigger price.",
        examples=[1.24500],
    )

    sl: float | None = Field(
        default=None,
        description="Stop-loss level.",
        examples=[1.24000],
    )

    tp: float | None = Field(
        default=None,
        description="Take-profit level.",
        examples=[1.25500],
    )

    open_time: datetime = Field(
        ...,
        description="Order creation timestamp.",
    )


class AccountInfo(BaseModel):
    """
    Snapshot of a trading account.

    Returned by broker adapters to provide a broker-independent
    account summary.
    """

    login: int = Field(
        ...,
        description="Broker login number.",
        examples=[12345678],
    )

    server: str = Field(
        ...,
        description="Broker server.",
        examples=["ICMarketsSC-Demo"],
    )

    company: str = Field(
        ...,
        description="Broker company name.",
        examples=["IC Markets"],
    )

    name: str = Field(
        ...,
        description="Account holder name.",
        examples=["John Doe"],
    )

    balance: float = Field(
        ...,
        description="Account balance.",
        examples=[10000.00],
    )

    equity: float = Field(
        ...,
        description="Current account equity.",
        examples=[10045.75],
    )

    margin: float = Field(
        ...,
        description="Margin currently in use.",
        examples=[125.30],
    )

    margin_free: float = Field(
        ...,
        description="Available free margin.",
        examples=[9920.45],
    )

    currency: str = Field(
        ...,
        description="Account deposit currency.",
        examples=["USD"],
    )

    leverage: int = Field(
        ...,
        description="Account leverage.",
        examples=[500],
    )


class SymbolInfo(BaseModel):
    """
    Broker-independent market information for a trading symbol.
    """

    name: str = Field(
        ...,
        description="Trading symbol.",
        examples=["EURUSD"],
    )

    bid: float = Field(
        ...,
        description="Current bid price.",
        examples=[1.12345],
    )

    ask: float = Field(
        ...,
        description="Current ask price.",
        examples=[1.12360],
    )

    point: float = Field(
        ...,
        description="Minimum price increment.",
        examples=[0.00001],
    )

    digits: int = Field(
        ...,
        description="Number of decimal places.",
        examples=[5],
    )

    trade_mode: int = Field(
        ...,
        description="Broker trading mode value.",
        examples=[4],
    )
