"""回測層測試（離線，用建構好的訊號驗證邏輯與防未來資料）。

執行： python -m tests.test_backtest
"""
import tests.conftest_path  # noqa: F401
import numpy as np
import pandas as pd

from backtest.runner import run_backtest, split_in_out


def _one_winning_trade():
    """買在低、之後上漲、賣在高的單筆獲利情境。"""
    idx = pd.date_range("2024-01-01", periods=6, freq="B")
    close = pd.Series([100, 100, 110, 120, 130, 130.0], index=idx)
    sig = pd.Series(["buy", "hold", "hold", "sell", "hold", "hold"], index=idx)
    return pd.DataFrame({"open": close, "close": close, "signal": sig})


def test_next_bar_execution_and_profit():
    """buy 在 t=0 → 應在 t=1 開盤(100)進場；上漲後賣出應獲利。"""
    res = run_backtest(_one_winning_trade(), commission=0.0, slippage=0.0)
    assert res.num_trades == 1, f"應有 1 筆交易，得到 {res.num_trades}"
    assert res.total_return > 0, "上漲後賣出應獲利"
    assert abs(res.trades.iloc[0]["entry"] - 100) < 1e-6  # 進場價為 t=1 開盤
    print(f"next-bar 執行 + 獲利 OK（報酬 {res.total_return:.2%}）")


def test_cost_reduces_return():
    no_cost = run_backtest(_one_winning_trade(), commission=0.0, slippage=0.0)
    with_cost = run_backtest(_one_winning_trade(), commission=0.005, slippage=0.001)
    assert with_cost.total_return < no_cost.total_return, "加入成本後報酬應下降"
    print("手續費/滑點影響 OK")


def test_no_signal_flat():
    """全 hold 應無交易、淨值維持 1.0。"""
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame(
        {"open": [10] * 5, "close": [10, 11, 9, 12, 8], "signal": ["hold"] * 5},
        index=idx,
    )
    res = run_backtest(df)
    assert res.num_trades == 0
    assert np.allclose(res.equity_curve.values, 1.0)
    print("無訊號不交易 OK")


def test_split():
    df = pd.DataFrame({"x": range(10)})
    a, b = split_in_out(df, 0.8)
    assert len(a) == 8 and len(b) == 2
    print("樣本內外切分 OK")


if __name__ == "__main__":
    test_next_bar_execution_and_profit()
    test_cost_reduces_return()
    test_no_signal_flat()
    test_split()
    print("test_backtest 全部通過")
