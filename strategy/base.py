"""策略層共用介面與資料結構。

設計重點：**可解釋訊號**。每個策略不只輸出 buy/sell/hold，
還要產生 `reason`（白話列出觸發的條件）與建議的停損/停利價，
讓不熟演算法的使用者也看得懂為什麼進出場。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

import pandas as pd

# 訊號欄位（generate 回傳的 DataFrame 會附上這些）
SIGNAL_COLS = ["signal", "reason", "stop_loss", "take_profit"]


@dataclass
class Signal:
    """單一時點的訊號（給儀表板/通知用的快照）。"""

    symbol: str
    timestamp: pd.Timestamp
    action: str  # "buy" / "sell" / "hold"
    price: float
    reasons: list[str] = field(default_factory=list)
    stop_loss: float | None = None
    take_profit: float | None = None

    def as_text(self) -> str:
        """組成白話訊息（通知/儀表板共用）。"""
        icon = {"buy": "🔼 買進訊號", "sell": "🔽 賣出訊號", "hold": "⏸ 觀望"}.get(
            self.action, self.action
        )
        lines = [f"{icon} @ {self.symbol} {self.price:.2f}"]
        if self.reasons:
            lines.append("原因：")
            lines += [f"  • {r}" for r in self.reasons]
        if self.action == "buy" and self.stop_loss and self.take_profit:
            lines.append(f"建議停損 {self.stop_loss:.2f}／停利 {self.take_profit:.2f}")
        return "\n".join(lines)


class Strategy(abc.ABC):
    """策略抽象基底。

    子類別實作 `generate(df)`：吃含指標欄位的 DataFrame，
    回傳附上 SIGNAL_COLS 的同長度 DataFrame。
    """

    name: str = "base"
    # 給「策略說明」tab 顯示用的白話說明（子類別覆寫）
    DESCRIPTION: str = ""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    @abc.abstractmethod
    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        """逐列產生訊號。回傳的 DataFrame 需含 SIGNAL_COLS。"""
        raise NotImplementedError

    def latest_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        """取最後一根 K 棒的訊號快照。"""
        out = self.generate(df)
        last = out.iloc[-1]
        reasons = last["reason"].split(" ｜ ") if last["reason"] else []
        return Signal(
            symbol=symbol,
            timestamp=out.index[-1],
            action=last["signal"],
            price=float(last["close"]),
            reasons=[r for r in reasons if r],
            stop_loss=_to_float(last["stop_loss"]),
            take_profit=_to_float(last["take_profit"]),
        )


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if f != f else f  # 過濾 NaN
    except (TypeError, ValueError):
        return None
