"""Bollinger Bands（布林通道）均值回歸策略。

補足前幾支策略（ema_macd_rsi、fibonacci 順勢；golden_cross 長期趨勢）都偏「順勢」的缺口，
這支專打**震盪／盤整盤**：價格極端偏離後傾向回歸均值（中軌）。

依 docs/research/deep-research-report_2.md 的布林帶段落，做規則化、防未來資料：
- 進場（buy）：收盤由下「站回」布林下軌（前一根在下軌之下、本根收回下軌之上）→ 超賣反彈。
- 出場（sell）：收盤回到布林中軌（均值回歸完成，停利）；或再度跌破下軌（趨勢續弱，停損）。
- 停損參考 = 布林下軌；停利參考 = 布林中軌（均值）。

防 look-ahead：用前一根（shift(1)）的收盤與下軌判斷「站回」事件，不會用到未來資料。
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy


class BollingerStrategy(Strategy):
    name = "bollinger"
    DESCRIPTION = (
        "**Bollinger Bands（布林通道）策略**（均值回歸，適合震盪盤）\n\n"
        "適合：沒有明顯趨勢、上下來回整理的標的。理念是「漲多會回、跌深會彈」，"
        "價格貼到通道邊緣後傾向回到中間。\n\n"
        "**進場（買）**：收盤由下方「站回」布林下軌（從超賣反彈）。\n\n"
        "**出場（賣）**：收盤回到布林中軌（均值回歸完成，停利）；或再次跌破下軌（趨勢續弱，停損）。\n\n"
        "**停損/停利**：停損參考布林下軌、停利參考布林中軌。\n\n"
        "⚠ 注意：在強趨勢（單邊大漲/大跌）中，價格會「貼著帶走」，均值回歸容易連續觸發停損，"
        "此時應改用順勢策略。"
    )

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        required = {"bb_lower", "bb_mid", "close"}
        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"缺少指標欄位：{missing}，請先呼叫 add_indicators()")

        close = out["close"]
        lower = out["bb_lower"]
        mid = out["bb_mid"]

        # 站回下軌事件：前一根收盤在下軌之下、本根收回下軌之上（用 shift(1) 防未來資料）
        cross_back_up = (close > lower) & (close.shift(1) <= lower.shift(1)) & lower.notna()
        # 出場：回到中軌（停利）或再度跌破下軌（停損）
        reach_mid = close >= mid
        below_lower = close < lower
        sell = (reach_mid | below_lower) & mid.notna()

        out["signal"] = "hold"
        out.loc[sell, "signal"] = "sell"
        out.loc[cross_back_up, "signal"] = "buy"  # buy 優先

        out["reason"] = [self._reason(row) for row in out.itertuples(index=False)]
        # 停損 = 下軌、停利 = 中軌（buy 訊號才填）
        out["stop_loss"] = lower.where(out["signal"] == "buy")
        out["take_profit"] = mid.where(out["signal"] == "buy")
        return out

    # --------------------------------------------------------------------- #
    def _reason(self, row) -> str:
        parts: list[str] = []
        if row.signal == "buy":
            parts.append("收盤站回布林下軌（從超賣反彈）")
        elif row.signal == "sell":
            if row.close >= row.bb_mid:
                parts.append("回到布林中軌（均值回歸完成，停利）")
            elif row.close < row.bb_lower:
                parts.append("再度跌破布林下軌（趨勢續弱，停損）")
        return " ｜ ".join(parts)
