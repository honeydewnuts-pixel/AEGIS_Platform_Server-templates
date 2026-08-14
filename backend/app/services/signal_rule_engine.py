"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : signal_rule_engine.py

Purpose
-------
Evaluates the AEGIS indicator rulebook against a frame history
(see indicator_history_service.py) and returns a signal.

Coordinate convention
----------------------
All positions are pixel Y-coordinates from the extracted image.
Smaller Y = higher on the chart = higher price/indicator level.
"Above" means a smaller Y value. Keep this in mind reading the code
below - it trips people up.

Frame state shape (one entry per historical frame):
{
    "band1": {"U": y, "M": y, "L": y},   # #1 white BB - reference
    "band2": {"U": y, "M": y, "L": y},   # #2 green BB - motional
    "ma4":   y,                           # #4 magenta MA
    "cci5":  y,                           # #5 red CCI
    "rsi6":  y,                           # #6 cobalt RSI
    "price_close": y | None,              # candle close position, if tracked
    "price_band7": {"U","M","L"} | None,  # main chart white BB
    "price_band8": {"U","M","L"} | None,  # main chart cobalt BB
    "_ts": float
}

WHAT'S IMPLEMENTED VS. FLAGGED
-------------------------------
Implemented with confidence:
  - Base 4-condition SELL (uptrend exhaustion) / BUY (downtrend exhaustion)
  - The three straightforward "Uptrend/Downtrend" 4-condition variants
    that only vary which #2 sub-band crosses and whether #4 is
    between-or-crossed
  - The #7/#8 price-panel filter variant (4-condition)

Deliberately NOT encoded yet (flagged, not guessed):
  - The 5/6/7-condition variants containing hedge language like
    "or has not crossed", "sometimes", "any of them can be inside or
    outside the band or none of them will be" - these don't resolve
    to an unambiguous true/false condition as written. Encoding a
    guess here means encoding wrong trade logic with no way to tell
    it apart from a correct one. See RULEBOOK_TODO at the bottom for
    the exact list with the ambiguous phrase called out - resolve
    these with concrete pixel-behavior descriptions (or example
    screenshots showing the pattern) and I'll add them.
====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Side = Literal["above", "below"]


# ------------------------------------------------------------------
# Primitives
# ------------------------------------------------------------------

def side_of(value_y: float, level_y: float) -> Side:
    return "above" if value_y < level_y else "below"


def crossed(prev_value_y: float, prev_level_y: float, cur_value_y: float, cur_level_y: float) -> Side | None:
    """Returns 'above' if value just crossed above level, 'below' if just crossed below, else None."""
    prev_side = side_of(prev_value_y, prev_level_y)
    cur_side = side_of(cur_value_y, cur_level_y)
    if prev_side == cur_side:
        return None
    return cur_side


def is_between(value_y: float, low_y: float, high_y: float) -> bool:
    lo, hi = min(low_y, high_y), max(low_y, high_y)
    return lo <= value_y <= hi


def higher_high(values_y: list[float], current_y: float) -> bool:
    """True if current_y is a new (price-sense) high vs. the given window - i.e. a SMALLER y than all of them."""
    if not values_y:
        return False
    return current_y < min(values_y)


def lower_low(values_y: list[float], current_y: float) -> bool:
    if not values_y:
        return False
    return current_y > max(values_y)


def divergence(indicator_series_y: list[float], price_series_y: list[float]) -> str | None:
    """
    Simple two-swing divergence check over the given window.
    Compares the most recent extreme half of the window against the
    earlier half.

    Returns "bearish" (price higher-high, indicator lower-high),
    "bullish" (price lower-low, indicator higher-low), or None.
    """
    n = len(price_series_y)
    if n < 4 or len(indicator_series_y) != n:
        return None

    mid = n // 2
    price_early, price_late = price_series_y[:mid], price_series_y[mid:]
    ind_early, ind_late = indicator_series_y[:mid], indicator_series_y[mid:]

    price_new_high = min(price_late) < min(price_early)   # price making a higher high
    ind_new_high = min(ind_late) < min(ind_early)          # indicator also making a higher high

    if price_new_high and not ind_new_high:
        return "bearish"   # price higher-high, indicator failed to confirm -> bearish divergence

    price_new_low = max(price_late) > max(price_early)
    ind_new_low = max(ind_late) > max(ind_early)

    if price_new_low and not ind_new_low:
        return "bullish"

    return None


# ------------------------------------------------------------------
# Rule evaluation
# ------------------------------------------------------------------

@dataclass
class RuleResult:
    fired: bool
    signal: str | None       # "BUY" / "SELL"
    rule_name: str
    reason: str


class SignalRuleEngine:
    """
    Evaluates history (a list of frame_state dicts, oldest first)
    against the encoded rulebook. Call evaluate() with at least ~12
    frames of history for divergence-dependent rules to have enough
    data; base rules only need the last 2 frames.
    """

    def __init__(self, divergence_lookback: int = 12, higher_high_lookback: int = 8) -> None:
        self.divergence_lookback = divergence_lookback
        self.higher_high_lookback = higher_high_lookback

    def evaluate(self, history: list[dict[str, Any]]) -> RuleResult:
        if len(history) < 2:
            return RuleResult(False, None, "insufficient_history", "Need at least 2 frames.")

        prev, cur = history[-2], history[-1]

        for rule_fn in self._rules():
            result = rule_fn(prev, cur, history)
            if result is not None and result.fired:
                return result

        return RuleResult(False, None, "no_rule_matched", "No condition set fully matched this frame.")

    # --------------------------------------------------------------
    # Encoded rules
    # --------------------------------------------------------------

    def _rules(self):
        return [
            self._rule_base_sell,
            self._rule_base_buy,
            self._rule_uptrend_2u_sell,
            self._rule_downtrend_2l_buy,
            self._rule_price_filter_sell,
            self._rule_price_filter_buy,
        ]

    def _rule_base_sell(self, prev, cur, history) -> RuleResult | None:
        """
        SELL (uptrend exhaustion):
        (1) #2(2M) has crossed #1(1U)
        (2) #4 is between #1(1M)/#1(1U) OR has crossed #1(1U)
        (3) #6 has crossed above #1(1U)
        (4) #5 diverges with price (price higher-high, #5 higher-low)
        """
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["M"], pb1["U"], b2["M"], b1["U"]) == "above"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["U"]) or side_of(cur["ma4"], b1["U"]) == "above"
        cond3 = crossed(prev["rsi6"], pb1["U"], cur["rsi6"], b1["U"]) == "above" or side_of(cur["rsi6"], b1["U"]) == "above"

        prices = [f.get("price_close") for f in history[-self.divergence_lookback:] if f.get("price_close") is not None]
        cci_vals = [f.get("cci5") for f in history[-self.divergence_lookback:] if f.get("cci5") is not None]
        cond4 = divergence(cci_vals, prices) == "bearish" if len(prices) == len(cci_vals) else False

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(
            fired, "SELL" if fired else None, "base_sell",
            f"cond1(2M x #1U)={cond1}, cond2(#4 pos)={cond2}, cond3(#6 x #1U)={cond3}, cond4(#5 bearish div)={cond4}",
        )

    def _rule_base_buy(self, prev, cur, history) -> RuleResult | None:
        """Mirror of _rule_base_sell for downtrend exhaustion -> BUY."""
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["M"], pb1["L"], b2["M"], b1["L"]) == "below"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["L"]) or side_of(cur["ma4"], b1["L"]) == "below"
        cond3 = crossed(prev["rsi6"], pb1["L"], cur["rsi6"], b1["L"]) == "below" or side_of(cur["rsi6"], b1["L"]) == "below"

        prices = [f.get("price_close") for f in history[-self.divergence_lookback:] if f.get("price_close") is not None]
        cci_vals = [f.get("cci5") for f in history[-self.divergence_lookback:] if f.get("cci5") is not None]
        cond4 = divergence(cci_vals, prices) == "bullish" if len(prices) == len(cci_vals) else False

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(
            fired, "BUY" if fired else None, "base_buy",
            f"cond1(2M x #1L)={cond1}, cond2(#4 pos)={cond2}, cond3(#6 x #1L)={cond3}, cond4(#5 bullish div)={cond4}",
        )

    def _rule_uptrend_2u_sell(self, prev, cur, history) -> RuleResult | None:
        """
        Uptrend variant:
        (1) #2(2U) has crossed above #1(1U)
        (2) #4 between #1(1M)/#1(1U) or crossed above #1(1U)
        (3) #6 crossed above #1(1U)
        (4) #5 diverges (higher-low vs. price higher-high)
        """
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["U"], pb1["U"], b2["U"], b1["U"]) == "above"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["U"]) or side_of(cur["ma4"], b1["U"]) == "above"
        cond3 = crossed(prev["rsi6"], pb1["U"], cur["rsi6"], b1["U"]) == "above"

        prices = [f.get("price_close") for f in history[-self.divergence_lookback:] if f.get("price_close") is not None]
        cci_vals = [f.get("cci5") for f in history[-self.divergence_lookback:] if f.get("cci5") is not None]
        cond4 = divergence(cci_vals, prices) == "bearish" if len(prices) == len(cci_vals) else False

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(fired, "SELL" if fired else None, "uptrend_2u_sell",
                           f"cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}")

    def _rule_downtrend_2l_buy(self, prev, cur, history) -> RuleResult | None:
        """Mirror: #2(2L) crossed below #1(1L) -> BUY variant."""
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["L"], pb1["L"], b2["L"], b1["L"]) == "below"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["L"]) or side_of(cur["ma4"], b1["L"]) == "below"
        cond3 = crossed(prev["rsi6"], pb1["L"], cur["rsi6"], b1["L"]) == "below"

        prices = [f.get("price_close") for f in history[-self.divergence_lookback:] if f.get("price_close") is not None]
        cci_vals = [f.get("cci5") for f in history[-self.divergence_lookback:] if f.get("cci5") is not None]
        cond4 = divergence(cci_vals, prices) == "bullish" if len(prices) == len(cci_vals) else False

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(fired, "BUY" if fired else None, "downtrend_2l_buy",
                           f"cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}")

    def _rule_price_filter_sell(self, prev, cur, history) -> RuleResult | None:
        """
        (1) #2(2M) crossed below #1(1M) [and then #1(1L)]
        (2) #4 between #1(1M)/#1(1U) or #1(1M)/#1(1L)
        (3) #6 crossed above #1(1U)
        (4) Price crosses/closes above #7 and #8 (whichever is outside)
        -> SELL
        """
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["M"], pb1["M"], b2["M"], b1["M"]) == "below"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["U"]) or is_between(cur["ma4"], b1["M"], b1["L"])
        cond3 = crossed(prev["rsi6"], pb1["U"], cur["rsi6"], b1["U"]) == "above"

        cond4 = False
        pb7, pb8 = cur.get("price_band7"), cur.get("price_band8")
        price = cur.get("price_close")
        if pb7 and pb8 and price is not None:
            outer_level = min(pb7["U"], pb8["U"])  # smaller y = higher = "outside" on the up side
            cond4 = price < outer_level

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(fired, "SELL" if fired else None, "price_filter_sell",
                           f"cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4(price>#7/#8)={cond4}")

    def _rule_price_filter_buy(self, prev, cur, history) -> RuleResult | None:
        """Mirror of _rule_price_filter_sell for BUY."""
        b1, b2 = cur["band1"], cur["band2"]
        pb1, pb2 = prev["band1"], prev["band2"]

        cond1 = crossed(pb2["M"], pb1["M"], b2["M"], b1["M"]) == "above"
        if not cond1:
            return None

        cond2 = is_between(cur["ma4"], b1["M"], b1["U"]) or is_between(cur["ma4"], b1["M"], b1["L"])
        cond3 = crossed(prev["rsi6"], pb1["L"], cur["rsi6"], b1["L"]) == "below"

        cond4 = False
        pb7, pb8 = cur.get("price_band7"), cur.get("price_band8")
        price = cur.get("price_close")
        if pb7 and pb8 and price is not None:
            outer_level = max(pb7["L"], pb8["L"])
            cond4 = price > outer_level

        fired = cond1 and cond2 and cond3 and cond4
        return RuleResult(fired, "BUY" if fired else None, "price_filter_buy",
                           f"cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4(price<#7/#8)={cond4}")


# ------------------------------------------------------------------
# Variants intentionally not yet encoded - resolve ambiguity, then add.
# ------------------------------------------------------------------
RULEBOOK_TODO = [
    {
        "variant": "6-condition Uptrend/Downtrend (#2 sub-bands + '#6 crosses #1M but did not cross #1U')",
        "ambiguous_phrase": "\"#2(2L) has crossed above #1(1U) or it has not crossed below #1(1U)\" - "
                             "the second half is true almost always, so as written this clause never rules anything out.",
    },
    {
        "variant": "5-condition '#6 makes one move from below #1M and cross #1U'",
        "ambiguous_phrase": "\"makes one move\" - unclear if this means exactly one frame-to-frame jump, "
                             "or just 'eventually crosses without dwelling at #1M'. Needs a concrete pixel-frame example.",
    },
    {
        "variant": "7-condition variants ending '#5 and #6 makes divergence or any of them makes divergence'",
        "ambiguous_phrase": "\"any of them\" - if only one of two conditions needs to hold, the rule is much "
                             "looser than the base rule and will fire far more often. Needs confirmation this is intentional.",
    },
    {
        "variant": "7-condition variant, clause (5)",
        "ambiguous_phrase": "\"Any of #2(2U,2M,2L) can be inside #1 band or outside the #1 band or none of "
                             "#2 will be inside #1 band\" - this covers literally every possible state of #2, "
                             "i.e. it's not a filter at all as written. Likely means something more specific "
                             "that got lost in phrasing - please clarify what this clause is meant to exclude.",
    },
    {
        "variant": "MA(4)-crosses-#2(2M) sequencing variants",
        "ambiguous_phrase": "\"#2(2M) cross above #4 going up, either to cross above #1(1U) or not\" - "
                             "order-of-events across #4 and #2 relative to each other needs a labeled example "
                             "screenshot sequence to encode reliably.",
    },
]
