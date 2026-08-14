"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

Package : adapters

Purpose
-------
Exports broker adapter implementations.

Keeping all concrete broker adapters inside this package ensures
that broker-specific SDK code remains isolated from the rest of
AEGIS.
====================================================================
"""

from .mt5_adapter import MT5Adapter

__all__ = [
    "MT5Adapter",
]
