"""技術指標層（純 pandas 實作，無第三方指標庫相依）。

刻意不使用 pandas-ta：其 0.3.14b 會 `from numpy import NaN`，在 numpy 2.x 會直接報錯。
這裡自己實作，數學透明、可控，也方便在儀表板做「白話解釋」。

所有指標**只使用當下與過去的資料**，不會用到未來 K 線（避免 look-ahead bias）。

主函式 `add_indicators(df, cfg)`：吃標準化 OHLCV DataFrame，回傳附加指標欄位的新 DataFrame。
"""
from __future__ import annotations

import pandas as pd

# 預設參數（與 config.yaml 的 indicators 區塊對應）
DEFAULTS = {
    "ema_fast": 5,
    "ema_slow": 20,
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "rsi_period": 14,
    "bbands": {"length": 20, "std": 2.0},
    "atr_period": 14,
}


# --------------------------------------------------------------------------- #
# 個別指標
# --------------------------------------------------------------------------- #
def ema(series: pd.Series, span: int) -> pd.Series:
    """指數移動平均線。"""
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    """MACD：回傳 DIF(快線)、DEA(訊號線)、HIST(柱狀圖)。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = dif - dea
    return pd.DataFrame({"macd_dif": dif, "macd_dea": dea, "macd_hist": hist})


def rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI（Wilder 平滑）。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder 平滑 = alpha 1/period 的 EMA
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bbands(close: pd.Series, length: int, std: float) -> pd.DataFrame:
    """布林通道：中軌(SMA)、上軌、下軌、帶寬。"""
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    width = (upper - lower) / mid
    return pd.DataFrame(
        {"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width}
    )


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """ATR 平均真實波幅（Wilder 平滑）。"""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 20
) -> pd.Series:
    """滾動 VWAP（成交量加權平均價）。

    註：標準 VWAP 是「單日盤中累積」指標。對日線資料沒有盤中概念，
    這裡用 N 日滾動的成交量加權均價作為近似（趨勢濾網用途）。
    之後若接盤中資料，可改成每日重置的累積版本。
    """
    typical = (high + low + close) / 3
    pv = (typical * volume).rolling(window).sum()
    vol = volume.rolling(window).sum()
    return pv / vol


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """能量潮 OBV：漲日累加量、跌日扣量。"""
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).fillna(0).cumsum()


# --------------------------------------------------------------------------- #
# 主函式
# --------------------------------------------------------------------------- #
def add_indicators(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """在 OHLCV DataFrame 上附加所有指標欄位。

    Args:
        df: 含 open/high/low/close/volume 的標準化 DataFrame。
        cfg: 指標參數（對應 config.yaml 的 indicators 區塊）；缺項以 DEFAULTS 補。

    Returns:
        附加指標欄位的新 DataFrame（原欄位保留）。
    """
    if df is None or df.empty:
        return df

    c = {**DEFAULTS, **(cfg or {})}
    out = df.copy()
    close, high, low, vol = out["close"], out["high"], out["low"], out["volume"]

    out[f"ema_fast"] = ema(close, c["ema_fast"])
    out[f"ema_slow"] = ema(close, c["ema_slow"])

    m = c["macd"]
    out = out.join(macd(close, m["fast"], m["slow"], m["signal"]))

    out["rsi"] = rsi(close, c["rsi_period"])

    b = c["bbands"]
    out = out.join(bbands(close, b["length"], b["std"]))

    out["atr"] = atr(high, low, close, c["atr_period"])
    out["vwap"] = vwap(high, low, close, vol, b["length"])
    out["obv"] = obv(close, vol)

    return out


if __name__ == "__main__":  # 簡易手動測試
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data.fetchers import get_ohlcv

    raw = get_ohlcv("NVDA", "US", "1d", "6mo")
    enriched = add_indicators(raw)
    cols = ["close", "ema_fast", "ema_slow", "macd_hist", "rsi", "atr", "vwap"]
    print(enriched[cols].tail())
