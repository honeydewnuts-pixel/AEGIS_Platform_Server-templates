"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : broker_types.py

Purpose
-------
Defines the canonical broker identifiers used throughout AEGIS.

Current Stage:
CP-006

Why this file exists
--------------------
As AEGIS grows, it will support multiple broker platforms and
exchanges. Using string literals such as "MT5" or "Binance"
throughout the codebase can lead to typing mistakes and inconsistent
comparisons.

Instead, every component should use the BrokerType enumeration.

Benefits
--------
• Single source of truth for broker identifiers
• Prevents spelling mistakes
• Easier to maintain and extend
• Works naturally with JSON because it inherits from both
  `str` and `Enum`
• Makes adapter selection deterministic

Future Support
--------------
The initial broker types included here are:

• MT5
• MT4
• cTrader
• FIX
• Binance
• Bybit
• Interactive Brokers (IBKR)

Additional broker types can be added here without changing the
public interface of the Broker Connection Service.
====================================================================
"""

from __future__ import annotations

from enum import Enum


class BrokerType(str, Enum):
    """
    Canonical broker identifiers for the AEGIS platform.

    This enumeration is inherited from both `str` and `Enum`.

    Why inherit from `str`?
    -----------------------
    Many Python frameworks (such as FastAPI and Pydantic) serialize
    string-based enums directly into JSON. This means:

        BrokerType.MT5

    is automatically represented as:

        "MT5"

    without requiring additional conversion code.

    All broker-specific adapters should compare against these values
    instead of hard-coded string literals.
    """

    MT5 = "MT5"
    MT4 = "MT4"
    CTRADER = "CTRADER"
    FIX = "FIX"
    BINANCE = "BINANCE"
    BYBIT = "BYBIT"
    IBKR = "IBKR"
