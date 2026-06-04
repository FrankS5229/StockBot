"""指標層測試（純離線，用合成資料驗證數學正確性）。

執行： python -m tests.test_indicators
"""
import tests.conftest_path  # noqa: F401
import numpy as np
import pandas as pd

from indicators import ta


def _synthetic(n=120, seed=0):
    rng = np.random.default_rng(seed)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))
    high = close + rng.uniform(0, 1, n)
    low = close - rng.uniform(0, 1, n)
    vol = pd.Series(rng.integers(1000, 5000, n).astype(float))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def test_ema_matches_pandas():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    expected = s.ewm(span=3, adjust=False).mean()
    assert np.allclose(ta.ema(s, 3), expected)
    print("ema OK")


def test_rsi_bounds():
    df = _synthetic()
    r = ta.rsi(df["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all(), "RSI 必須落在 0~100"
    print("rsi bounds OK")


def test_macd_hist_identity():
    df = _synthetic()
    m = ta.macd(df["close"], 12, 26, 9)
    assert np.allclose(m["macd_hist"], m["macd_dif"] - m["macd_dea"], equal_nan=True)
    print("macd hist OK")


def test_bbands_order():
    df = _synthetic()
    b = ta.bbands(df["close"], 20, 2.0).dropna()
    assert (b["bb_upper"] >= b["bb_mid"]).all()
    assert (b["bb_mid"] >= b["bb_lower"]).all()
    print("bbands order OK")


def test_atr_positive():
    df = _synthetic()
    a = ta.atr(df["high"], df["low"], df["close"], 14).dropna()
    assert (a >= 0).all(), "ATR 不應為負"
    print("atr positive OK")


def test_add_indicators_columns():
    df = _synthetic()
    out = ta.add_indicators(df)
    for col in ["ema_fast", "ema_slow", "macd_hist", "rsi", "bb_upper", "atr", "vwap"]:
        assert col in out.columns, f"缺欄位 {col}"
    assert len(out) == len(df)
    print("add_indicators columns OK")


if __name__ == "__main__":
    test_ema_matches_pandas()
    test_rsi_bounds()
    test_macd_hist_identity()
    test_bbands_order()
    test_atr_positive()
    test_add_indicators_columns()
    print("test_indicators 全部通過")
