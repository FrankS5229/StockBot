"""Golden Cross（50/200 均線黃金交叉）長期趨勢策略。

這是專案第一支**長期**策略，用來補足原有兩支（ema_macd_rsi、fibonacci）都偏短/中線的缺口。
邏輯經典、交易次數天然極少，適合一路吃大波段，常用來和「買進持有」對照。

- 進場（buy）：短期均線（預設 50 日 SMA）**上穿**長期均線（預設 200 日 SMA）→ 黃金交叉，長期多頭啟動。
- 出場（sell）：短期均線**位於**長期均線之下 → 死亡交叉／長期轉空，退出。
- 停損參考：以長期均線（200 SMA）當防線（跌破即代表長期趨勢破壞）；趨勢跟蹤無固定停利，
  順勢抱到死亡交叉為止，故 take_profit 不設。

防 look-ahead：均線只用「當下與過去」收盤；交叉判斷用 shift(1) 比較前一根狀態，不會用到未來資料。
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy


class GoldenCrossStrategy(Strategy):
    name = "golden_cross"
    DESCRIPTION = (
        "**Golden Cross（50/200 均線黃金交叉）策略**（長期趨勢）\n\n"
        "適合：想長期持有、少進出、吃大波段的大盤 ETF 或龍頭股。\n\n"
        "**進場（買）**：50 日均線由下往上穿過 200 日均線（黃金交叉），代表長期趨勢轉多。\n\n"
        "**出場（賣）**：50 日均線跌回 200 日均線之下（死亡交叉），代表長期趨勢轉空。\n\n"
        "**停損/停利**：以 200 日均線當長期防線（跌破即趨勢破壞）；順勢策略不設固定停利，"
        "抱到死亡交叉為止。\n\n"
        "💡 交易次數天然很少（一年常常只有 0–2 次訊號），是用來對照「買進持有」的長線基準。"
    )

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        gc = (cfg or {}).get("golden_cross", {})
        self.short = gc.get("short", 50)
        self.long = gc.get("long", 200)

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "close" not in out.columns:
            raise ValueError("缺少 close 欄位，請先取得 OHLCV 資料")

        # 長短期 SMA（只用當下與過去收盤 → 防未來資料）
        sma_short = out["close"].rolling(self.short).mean()
        sma_long = out["close"].rolling(self.long).mean()
        out["sma_short"] = sma_short
        out["sma_long"] = sma_long

        # 黃金交叉：前一根 short<=long、本根 short>long（用 shift(1) 防未來資料）
        prev_short = sma_short.shift(1)
        prev_long = sma_long.shift(1)
        golden = (sma_short > sma_long) & (prev_short <= prev_long) & sma_long.notna()
        # 死亡交叉狀態：短期在長期之下（退出並維持空手到下次黃金交叉）
        death = (sma_short < sma_long) & sma_long.notna()

        out["signal"] = "hold"
        out.loc[death, "signal"] = "sell"
        out.loc[golden, "signal"] = "buy"  # buy 優先

        out["reason"] = [self._reason(row) for row in out.itertuples(index=False)]
        # 停損 = 200 日均線（長期防線）；趨勢跟蹤不設固定停利
        out["stop_loss"] = sma_long.where(out["signal"] == "buy")
        out["take_profit"] = pd.Series(float("nan"), index=out.index)
        return out

    # --------------------------------------------------------------------- #
    def _reason(self, row) -> str:
        parts: list[str] = []
        if row.signal == "buy":
            parts.append(f"{self.short} 日均線上穿 {self.long} 日均線（黃金交叉，長期多頭啟動）")
        elif row.signal == "sell":
            parts.append(f"{self.short} 日均線在 {self.long} 日均線之下（死亡交叉／長期轉空，退出）")
        return " ｜ ".join(parts)
