"""
Commercial subscription tiers for AEGIS.

max_trades_per_day: 0 means unlimited.
live_trading: false restricts to analysis / demo-style use.
"""

from __future__ import annotations

from typing import Any

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "demo": {
        "label": "Demo / Trial",
        "max_devices": 1,
        "max_trades_per_day": 5,
        "live_trading": False,
        "price_hint": "Free 14-day trial",
    },
    "starter": {
        "label": "Starter",
        "max_devices": 1,
        "max_trades_per_day": 15,
        "live_trading": True,
        "price_hint": "1 phone · 15 trades/day",
    },
    "pro": {
        "label": "Pro",
        "max_devices": 1,
        "max_trades_per_day": 50,
        "live_trading": True,
        "price_hint": "1 phone · 50 trades/day",
    },
    "business": {
        "label": "Business",
        "max_devices": 3,
        "max_trades_per_day": 200,
        "live_trading": True,
        "price_hint": "3 phones · 200 trades/day",
    },
    "enterprise": {
        "label": "Enterprise",
        "max_devices": 10,
        "max_trades_per_day": 0,
        "live_trading": True,
        "price_hint": "10 phones · unlimited trades",
    },
}


def resolve_plan(plan_code: str) -> dict[str, Any]:
    code = (plan_code or "starter").lower().strip()
    if code in ("live",):  # legacy alias
        code = "starter"
    return PLAN_CATALOG.get(code, PLAN_CATALOG["starter"]) | {"code": code if code in PLAN_CATALOG else "starter"}
