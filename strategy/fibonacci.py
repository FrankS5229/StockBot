"""Fibonacci Retracement（黃金分割回撤）策略。

依據 docs/research/deep-research-report_2.md 的 Fibonacci 段落，做規則化、防未來資料：
- 用滾動窗口（lookback，預設 60 根）取「過去」的波段最高/最低，
  計算回撤位 0.236 / 0.382 / 0.5 / 0.618 / 0.786。
- 在上升趨勢中（EMA_fast > EMA_slow），價格回踩到 0.5~0.618 黃金回撤區間且
  當根收紅（止穩）→ 視為低接買點 buy。
- 跌破 0.786（回撤過深，趨勢可能反轉）或 EMA 轉空 → sell。
- 停損/停利沿用 ATR（與 EMA 策略一致，重用 cfg["risk"]）。

防 look-ahead：第 t 根用的高低點僅取「t 之前（含 t）」的滾動窗口，
回撤位以 shift(1) 確保不會用到當根尚未確定的極值。
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy


class FibonacciStrategy(Strategy):
    name = "fibonacci"
    DESCRIPTION = (
        "**Fibonacci Retracement（黃金分割回撤）策略**（順勢低接）\n\n"
        "適合：上升趨勢中想「等回檔再買」的情境。把過去一段波段的高低，"
        "切出 0.382 / 0.5 / 0.618 / 0.786 幾條回撤線當支撐參考。\n\n"
        "**進場（買）**：趨勢仍多頭（EMA5 在 EMA20 之上）＋ 價格回踩到 0.5–0.618 "
        "黃金回撤區間＋ 當根收紅止穩。\n\n"
        "**出場（賣）**：跌破 0.786 回撤線（回檔過深、趨勢恐反轉），或 EMA5 跌破 EMA20。\n\n"
        "**停損/停利**：停損 = 進場價 − ATR×倍數；停利 = 停損距離 × 報酬風險比。\n\n"
        "💡 0.618 是知名的「黃金分割」比例，市場常在此附近獲得支撐。"
    )

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        risk = (cfg or {}).get("risk", {})
        self.atr_mult = risk.get("atr_stop_mult", 1.0)
        self.rr = risk.get("reward_risk_ratio", 2.0)

        fib = (cfg or {}).get("fibonacci", {})
        self.lookback = fib.get("lookback", 60)
        # 進場「黃金回撤區間」：回撤落在 entry_low~entry_high 之間就視為低接買點。
        # 預設 0.5~0.618（比舊版只貼 0.618 單線寬，命中率較高、回測樣本較足）。
        self.entry_low = fib.get("entry_low", 0.5)
        self.entry_high = fib.get("entry_high", 0.618)
        # 區間邊緣的額外緩衝（相對價格的百分比），讓貼近邊界的回踩也算數。
        self.tolerance = fib.get("tolerance", 0.01)

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        required = {"ema_fast", "ema_slow", "atr", "high", "low", "close", "open"}
        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"缺少欄位：{missing}，請先呼叫 add_indicators()")

        # 過去 lookback 根的波段高低（shift(1) 避免用到當根極值 → 防未來資料）
        swing_high = out["high"].rolling(self.lookback).max().shift(1)
        swing_low = out["low"].rolling(self.lookback).min().shift(1)
        span = swing_high - swing_low

        # 上升波段的回撤位：從高點往下回撤 ratio（回撤越深、價格越低）
        # 區間：淺(entry_low) 的價格較高、深(entry_high) 的價格較低
        fib_shallow = swing_high - span * self.entry_low   # 例 0.5 → 較高價
        fib_deep = swing_high - span * self.entry_high     # 例 0.618 → 較低價
        fib_786 = swing_high - span * 0.786
        out["fib_shallow"] = fib_shallow
        out["fib_deep"] = fib_deep
        out["fib_786"] = fib_786

        ema_bull = out["ema_fast"] > out["ema_slow"]
        ema_bear = out["ema_fast"] < out["ema_slow"]
        bullish_bar = out["close"] >= out["open"]  # 當根收紅止穩

        # 回踩黃金區間：收盤落在 [fib_deep*(1-tol), fib_shallow*(1+tol)] 之間
        in_zone = (
            (out["close"] >= fib_deep * (1 - self.tolerance))
            & (out["close"] <= fib_shallow * (1 + self.tolerance))
        )

        buy = ema_bull & in_zone & bullish_bar & span.notna()

        below_786 = out["close"] < fib_786
        sell = below_786 | ema_bear

        stop = out["close"] - self.atr_mult * out["atr"]
        target = out["close"] + self.atr_mult * out["atr"] * self.rr

        out["signal"] = "hold"
        out.loc[sell, "signal"] = "sell"
        out.loc[buy, "signal"] = "buy"  # buy 優先

        out["reason"] = [
            self._reason(row) for row in out.itertuples(index=False)
        ]
        out["stop_loss"] = stop.where(out["signal"] == "buy")
        out["take_profit"] = target.where(out["signal"] == "buy")
        return out

    # --------------------------------------------------------------------- #
    def _reason(self, row) -> str:
        parts: list[str] = []
        if row.signal == "buy":
            parts.append(f"回踩 {self.entry_low:g}–{self.entry_high:g} 黃金分割區間")
            parts.append("EMA5 在 EMA20 之上（趨勢仍多頭）")
            parts.append("當根收紅止穩")
        elif row.signal == "sell":
            if row.close < row.fib_786:
                parts.append("跌破 0.786 回撤線（回檔過深）")
            if row.ema_fast < row.ema_slow:
                parts.append("EMA5 跌破 EMA20（趨勢轉空）")
        return " ｜ ".join(parts)
