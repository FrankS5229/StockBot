"""策略層測試（離線，用合成資料）。

執行： python -m tests.test_strategy
"""
import tests.conftest_path  # noqa: F401
import numpy as np
import pandas as pd

from indicators.ta import add_indicators
from strategy.base import SIGNAL_COLS
from strategy.bollinger import BollingerStrategy
from strategy.ema_macd_rsi import EmaMacdRsiStrategy
from strategy.fibonacci import FibonacciStrategy
from strategy.golden_cross import GoldenCrossStrategy


def _trending(n=200, seed=1):
    """製造有漲有跌的走勢，確保會出現 buy/sell 訊號。"""
    rng = np.random.default_rng(seed)
    drift = np.concatenate([np.full(n // 2, 0.3), np.full(n - n // 2, -0.3)])
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # close 直接用 idx 建立，避免與 DataFrame 的 index 對齊不上而整欄變 NaN
    close = pd.Series(100 + np.cumsum(drift + rng.normal(0, 1, n)), index=idx)
    return pd.DataFrame(
        {
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close,
            "volume": pd.Series(rng.integers(1000, 5000, n).astype(float)).values,
        },
        index=idx,
    )


def test_signal_columns_and_values():
    df = add_indicators(_trending())
    out = EmaMacdRsiStrategy().generate(df)
    for c in SIGNAL_COLS:
        assert c in out.columns, f"缺訊號欄位 {c}"
    assert set(out["signal"].unique()).issubset({"buy", "sell", "hold"})
    print("signal columns/values OK")


def test_buy_has_reason_and_stops():
    df = add_indicators(_trending())
    out = EmaMacdRsiStrategy().generate(df)
    buys = out[out["signal"] == "buy"]
    if buys.empty:
        print("（本資料無 buy 訊號，跳過停損檢查）")
        return
    row = buys.iloc[0]
    assert row["reason"], "buy 訊號必須附理由"
    assert row["stop_loss"] < row["close"] < row["take_profit"], "停損<現價<停利"
    print(f"buy reason/stops OK（共 {len(buys)} 個 buy）")


def test_missing_indicator_raises():
    df = _trending()  # 未加指標
    try:
        EmaMacdRsiStrategy().generate(df)
    except ValueError:
        print("缺指標時正確報錯 OK")
        return
    raise AssertionError("缺指標欄位時應該要報 ValueError")


def test_fibonacci_columns_and_values():
    df = add_indicators(_trending())
    out = FibonacciStrategy().generate(df)
    for c in SIGNAL_COLS:
        assert c in out.columns, f"Fib 缺訊號欄位 {c}"
    assert set(out["signal"].unique()).issubset({"buy", "sell", "hold"})
    print("fibonacci columns/values OK")


def test_fibonacci_buy_stops():
    df = add_indicators(_trending())
    out = FibonacciStrategy().generate(df)
    buys = out[out["signal"] == "buy"]
    if buys.empty:
        print("（Fib 本資料無 buy 訊號，跳過停損檢查）")
        return
    row = buys.iloc[0]
    assert row["reason"], "Fib buy 訊號必須附理由"
    assert row["stop_loss"] < row["close"] < row["take_profit"], "停損<現價<停利"
    print(f"fibonacci buy reason/stops OK（共 {len(buys)} 個 buy）")


def test_fibonacci_missing_indicator_raises():
    df = _trending()  # 未加指標
    try:
        FibonacciStrategy().generate(df)
    except ValueError:
        print("Fib 缺指標時正確報錯 OK")
        return
    raise AssertionError("Fib 缺指標欄位時應該要報 ValueError")


def _long_trending(n=500, seed=2):
    """先跌後漲的長序列。

    刻意讓 50/200 均線都在「下跌段」就成形（短期在長期之下），
    之後轉漲時短期上穿長期 → 出現可偵測的黃金交叉事件（不會卡在 200 根暖身期）。
    """
    rng = np.random.default_rng(seed)
    drift = np.concatenate([np.full(n // 2, -0.1), np.full(n - n // 2, 0.5)])
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    # close 直接用 idx 建立，避免與 DataFrame 的 index 對齊不上而整欄變 NaN
    close = pd.Series(100 + np.cumsum(drift + rng.normal(0, 0.5, n)), index=idx)
    return pd.DataFrame(
        {
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close,
            "volume": pd.Series(rng.integers(1000, 5000, n).astype(float)).values,
        },
        index=idx,
    )


def test_golden_cross_columns_and_values():
    # golden_cross 只需要 close，不必先 add_indicators
    out = GoldenCrossStrategy().generate(_long_trending())
    for c in SIGNAL_COLS:
        assert c in out.columns, f"GC 缺訊號欄位 {c}"
    assert {"sma_short", "sma_long"}.issubset(out.columns)
    assert set(out["signal"].unique()).issubset({"buy", "sell", "hold"})
    print("golden_cross columns/values OK")


def test_golden_cross_buy_on_crossover():
    out = GoldenCrossStrategy().generate(_long_trending())
    buys = out[out["signal"] == "buy"]
    assert not buys.empty, "先漲後跌的資料應至少出現一次黃金交叉 buy"
    row = buys.iloc[0]
    assert row["reason"], "GC buy 訊號必須附理由"
    # 黃金交叉時 200 日均線在價格之下 → 當停損防線應低於現價
    assert row["stop_loss"] < row["close"], "GC 停損（200MA）應低於現價"
    print(f"golden_cross buy/stop OK（共 {len(buys)} 個 buy）")


def test_golden_cross_missing_close_raises():
    df = pd.DataFrame({"open": [1, 2, 3]})  # 無 close
    try:
        GoldenCrossStrategy().generate(df)
    except ValueError:
        print("GC 缺 close 時正確報錯 OK")
        return
    raise AssertionError("GC 缺 close 欄位時應該要報 ValueError")


def test_bollinger_columns_and_values():
    df = add_indicators(_trending())
    out = BollingerStrategy().generate(df)
    for c in SIGNAL_COLS:
        assert c in out.columns, f"BB 缺訊號欄位 {c}"
    assert set(out["signal"].unique()).issubset({"buy", "sell", "hold"})
    print("bollinger columns/values OK")


def test_bollinger_buy_stops():
    df = add_indicators(_trending())
    out = BollingerStrategy().generate(df)
    buys = out[out["signal"] == "buy"]
    if buys.empty:
        print("（BB 本資料無 buy 訊號，跳過停損檢查）")
        return
    row = buys.iloc[0]
    assert row["reason"], "BB buy 訊號必須附理由"
    # 停損=下軌、停利=中軌：站回下軌買進時應 下軌 < 現價 < 中軌
    assert row["stop_loss"] < row["close"] < row["take_profit"], "停損<現價<停利"
    print(f"bollinger buy reason/stops OK（共 {len(buys)} 個 buy）")


def test_bollinger_missing_indicator_raises():
    df = _trending()  # 未加指標（無 bb_*）
    try:
        BollingerStrategy().generate(df)
    except ValueError:
        print("BB 缺指標時正確報錯 OK")
        return
    raise AssertionError("BB 缺指標欄位時應該要報 ValueError")


if __name__ == "__main__":
    test_signal_columns_and_values()
    test_buy_has_reason_and_stops()
    test_missing_indicator_raises()
    test_fibonacci_columns_and_values()
    test_fibonacci_buy_stops()
    test_fibonacci_missing_indicator_raises()
    test_golden_cross_columns_and_values()
    test_golden_cross_buy_on_crossover()
    test_golden_cross_missing_close_raises()
    test_bollinger_columns_and_values()
    test_bollinger_buy_stops()
    test_bollinger_missing_indicator_raises()
    print("test_strategy 全部通過")
