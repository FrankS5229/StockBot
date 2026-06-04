"""回測層。

把 strategy 產生的 buy/sell 訊號，套用手續費與滑點後在歷史資料上模擬交易，
輸出績效指標（年化報酬、Sharpe、最大回撤、勝率、盈虧比、交易次數）與淨值曲線。

刻意自寫一個輕量「向量化」回測，而非依賴 backtesting.py 的 class API：
- 完全可控、邏輯透明（呼應「可解釋」目標）。
- 嚴守不使用未來資料：第 t 根的訊號，在第 t+1 根開盤才進場（next-bar execution）。
支援樣本外切分（前 split 比例 in-sample，其餘 out-of-sample）。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    total_return: float       # 總報酬率
    annual_return: float      # 年化報酬率
    sharpe: float             # 夏普比率（年化）
    max_drawdown: float       # 最大回撤（負值）
    win_rate: float           # 勝率
    profit_factor: float      # 盈虧比（總獲利/總虧損）
    num_trades: int           # 交易次數
    equity_curve: pd.Series   # 淨值曲線（起始 = 1.0）
    trades: pd.DataFrame      # 每筆交易明細

    def summary(self) -> dict:
        """不含序列的純數字摘要（給儀表板表格/通知）。"""
        d = asdict(self)
        d.pop("equity_curve")
        d.pop("trades")
        return d


# 績效指標的白話說明（給儀表板 tooltip）
METRIC_GLOSSARY = {
    "total_return": "整段期間的總報酬率。",
    "annual_return": "換算成每年的報酬率，方便跨期間比較。",
    "sharpe": (
        "每承擔一單位風險換到多少報酬，越高越好；>1 算不錯。"
        "註：以整段淨值（含空手期間，視同資金閒置報酬 0）計算，"
        "故空手越久數字越保守，非僅統計持倉期間。"
    ),
    "max_drawdown": "歷史上從高點跌最深的幅度（負值），衡量最壞情況。",
    "win_rate": "賺錢的交易佔所有交易的比例。",
    "profit_factor": "總獲利 ÷ 總虧損，>1 代表整體賺錢。",
    "num_trades": "總共進出場幾次（過少代表樣本不足）。",
}


def run_backtest(
    signal_df: pd.DataFrame,
    *,
    commission: float = 0.0015,
    slippage: float = 0.0005,
    periods_per_year: int = 252,
) -> BacktestResult:
    """以 next-bar 執行模擬多單交易（long-only）。

    Args:
        signal_df: 含 'open','close','signal' 欄位的 DataFrame（signal=buy/sell/hold）。
        commission: 單邊手續費率（含稅近似）。
        slippage: 單邊滑點率。
        periods_per_year: 年化用的每年根數（日線約 252）。
    """
    df = signal_df.copy()
    if "open" not in df.columns:
        df["open"] = df["close"]  # 無開盤價時退用收盤

    cost = commission + slippage  # 單邊成本

    position = 0          # 0=空手, 1=持有
    entry_price = np.nan
    entry_time = None
    equity = 1.0          # 淨值（含已實現）
    equity_curve = []
    trades = []

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    sigs = df["signal"].to_numpy()
    idx = df.index

    for t in range(len(df)):
        # 先依「前一根的訊號」在本根開盤執行
        if t > 0:
            prev_sig = sigs[t - 1]
            if position == 0 and prev_sig == "buy":
                entry_price = opens[t] * (1 + cost)  # 買進含成本
                entry_time = idx[t]
                position = 1
            elif position == 1 and prev_sig == "sell":
                exit_price = opens[t] * (1 - cost)   # 賣出扣成本
                ret = exit_price / entry_price - 1
                equity *= (1 + ret)
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": idx[t],
                        "entry": entry_price,
                        "exit": exit_price,
                        "return": ret,
                    }
                )
                position = 0
                entry_price = np.nan

        # 記錄當根淨值（含未實現損益）
        if position == 1:
            unreal = closes[t] / entry_price - 1
            equity_curve.append(equity * (1 + unreal))
        else:
            equity_curve.append(equity)

    # 期末若仍持有，以最後收盤平倉
    if position == 1:
        exit_price = closes[-1] * (1 - cost)
        ret = exit_price / entry_price - 1
        equity *= (1 + ret)
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": idx[-1],
                "entry": entry_price,
                "exit": exit_price,
                "return": ret,
            }
        )

    eq = pd.Series(equity_curve, index=idx, name="equity")
    trades_df = pd.DataFrame(trades)
    return _metrics(eq, trades_df, periods_per_year)


def _metrics(eq: pd.Series, trades: pd.DataFrame, ppy: int) -> BacktestResult:
    total_return = float(eq.iloc[-1] - 1) if len(eq) else 0.0

    n = len(eq)
    final = float(eq.iloc[-1])
    if n > 1 and final > 0:
        # 至少約半年資料才年化，避免短窗（如 5d 盤中）外推出 250%+ 的無意義暴衝值；
        # 資料太短時直接回報期間總報酬（不外推）。
        annual_return = final ** (ppy / n) - 1 if n >= ppy / 2 else final - 1
    else:
        annual_return = 0.0

    daily_ret = eq.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(ppy))
    else:
        sharpe = 0.0

    running_max = eq.cummax()
    drawdown = eq / running_max - 1
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    if not trades.empty:
        wins = trades[trades["return"] > 0]["return"]
        losses = trades[trades["return"] <= 0]["return"]
        win_rate = len(wins) / len(trades)
        gross_win = wins.sum()
        gross_loss = -losses.sum()
        profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
    else:
        win_rate = 0.0
        profit_factor = 0.0

    return BacktestResult(
        total_return=total_return,
        annual_return=float(annual_return),
        sharpe=sharpe,
        max_drawdown=max_dd,
        win_rate=float(win_rate),
        profit_factor=profit_factor,
        num_trades=int(len(trades)),
        equity_curve=eq,
        trades=trades,
    )


def split_in_out(df: pd.DataFrame, ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """時間序列樣本內/外切分（前 ratio 為 in-sample）。"""
    k = int(len(df) * ratio)
    return df.iloc[:k], df.iloc[k:]
