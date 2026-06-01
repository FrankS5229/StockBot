"""範例組合策略：EMA 交叉 + VWAP + MACD 柱 + RSI，ATR 設停損停利。

依據 docs/research/deep-research-report_2.md 的短線框架。每個訊號都附白話理由。

多頭進場（buy）需同時成立：
  1. EMA5 > EMA20            → 短期均線多頭排列（黃金交叉狀態）
  2. 收盤 > VWAP            → 買方力道占優
  3. MACD 柱由負轉正        → 上漲動能剛啟動（觸發點）
  4. 50 ≤ RSI < 70         → 中性偏多、尚未過熱

出場（sell）任一成立：
  - MACD 柱由正轉負
  - 收盤跌破 VWAP
  - RSI 跌破 50
  - EMA5 跌破 EMA20（死亡交叉）

停損 = 進場價 − k×ATR；停利 = 停損距離 × reward_risk_ratio。
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy


class EmaMacdRsiStrategy(Strategy):
    name = "ema_macd_rsi"
    DESCRIPTION = (
        "**EMA + MACD + RSI 組合策略**（順勢動能）\n\n"
        "適合：有明顯趨勢的標的。靠均線判方向、MACD 抓動能啟動、RSI 確認沒過熱。\n\n"
        "**進場（買）**：EMA5 在 EMA20 之上（短期多頭）＋ 收盤站上 VWAP（買方占優）"
        "＋ MACD 柱由負轉正（動能啟動）＋ RSI 介於 50–70（偏多未過熱），四個同時成立。\n\n"
        "**出場（賣）**：MACD 柱翻負、跌破 VWAP、RSI 跌破 50、或 EMA5 跌破 EMA20，任一成立。\n\n"
        "**停損/停利**：停損 = 進場價 − ATR×倍數；停利 = 停損距離 × 報酬風險比。"
    )

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        risk = (cfg or {}).get("risk", {})
        self.atr_mult = risk.get("atr_stop_mult", 1.0)
        self.rr = risk.get("reward_risk_ratio", 2.0)
        self.rsi_low = risk.get("rsi_entry_low", 50)
        self.rsi_high = risk.get("rsi_entry_high", 70)

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        required = {"ema_fast", "ema_slow", "vwap", "macd_hist", "rsi", "atr", "close"}
        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"缺少指標欄位：{missing}，請先呼叫 add_indicators()")

        ema_bull = out["ema_fast"] > out["ema_slow"]
        above_vwap = out["close"] > out["vwap"]
        hist_up = (out["macd_hist"] > 0) & (out["macd_hist"].shift(1) <= 0)
        rsi_ok = (out["rsi"] >= self.rsi_low) & (out["rsi"] < self.rsi_high)

        buy = ema_bull & above_vwap & hist_up & rsi_ok

        # 出場條件
        hist_down = (out["macd_hist"] < 0) & (out["macd_hist"].shift(1) >= 0)
        below_vwap = out["close"] < out["vwap"]
        rsi_weak = out["rsi"] < self.rsi_low
        ema_bear = out["ema_fast"] < out["ema_slow"]
        sell = hist_down | below_vwap | rsi_weak | ema_bear

        # 停損/停利（以當根 ATR 估算，buy 訊號才填）
        stop = out["close"] - self.atr_mult * out["atr"]
        target = out["close"] + self.atr_mult * out["atr"] * self.rr

        out["signal"] = "hold"
        out.loc[sell, "signal"] = "sell"
        out.loc[buy, "signal"] = "buy"  # buy 優先（同時成立時視為進場）

        out["reason"] = [
            self._reason(row, prev_hist)
            for row, prev_hist in zip(
                out.itertuples(index=False),
                out["macd_hist"].shift(1).fillna(0),
            )
        ]
        out["stop_loss"] = stop.where(out["signal"] == "buy")
        out["take_profit"] = target.where(out["signal"] == "buy")
        return out

    # --------------------------------------------------------------------- #
    def _reason(self, row, prev_hist: float) -> str:
        """為單列產生白話理由字串。"""
        parts: list[str] = []
        if row.signal == "buy":
            parts.append("EMA5 在 EMA20 之上（短期多頭排列）")
            parts.append("收盤站上 VWAP（買方占優）")
            parts.append("MACD 柱由負轉正（動能啟動）")
            parts.append(f"RSI {row.rsi:.0f}，中性偏多未過熱")
        elif row.signal == "sell":
            if row.macd_hist < 0 <= prev_hist:
                parts.append("MACD 柱由正轉負（動能轉弱）")
            if row.close < row.vwap:
                parts.append("收盤跌破 VWAP（買方轉弱）")
            if row.rsi < self.rsi_low:
                parts.append(f"RSI {row.rsi:.0f} 跌破 {self.rsi_low}（轉弱）")
            if row.ema_fast < row.ema_slow:
                parts.append("EMA5 跌破 EMA20（死亡交叉）")
        return " ｜ ".join(parts)
