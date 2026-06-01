"""core 層測試：策略註冊表 + 使用者庫存 CRUD（離線）。

使用暫存檔避免污染真實 user_portfolio.json。
執行： python -m tests.test_core
"""
import tests.conftest_path  # noqa: F401

import core
from strategy.bollinger import BollingerStrategy
from strategy.ema_macd_rsi import EmaMacdRsiStrategy
from strategy.fibonacci import FibonacciStrategy
from strategy.golden_cross import GoldenCrossStrategy


def test_strategy_registry():
    assert "ema_macd_rsi" in core.STRATEGY_REGISTRY
    assert "fibonacci" in core.STRATEGY_REGISTRY
    assert "golden_cross" in core.STRATEGY_REGISTRY
    assert "bollinger" in core.STRATEGY_REGISTRY
    # 依 active 取對應策略
    assert isinstance(core.get_strategy({"strategy": {"active": "fibonacci"}}), FibonacciStrategy)
    assert isinstance(core.get_strategy({"strategy": {"active": "ema_macd_rsi"}}), EmaMacdRsiStrategy)
    assert isinstance(core.get_strategy({"strategy": {"active": "golden_cross"}}), GoldenCrossStrategy)
    assert isinstance(core.get_strategy({"strategy": {"active": "bollinger"}}), BollingerStrategy)
    # 未知策略 → 退回預設
    assert isinstance(core.get_strategy({"strategy": {"active": "nope"}}), EmaMacdRsiStrategy)
    # 無 strategy 區塊 → 預設
    assert isinstance(core.get_strategy({}), EmaMacdRsiStrategy)
    print("strategy registry OK")


def test_portfolio_crud(tmp_path=None):
    import tempfile
    from pathlib import Path

    # 暫時改 USER_PORTFOLIO 指向暫存檔
    original = core.USER_PORTFOLIO
    tmpf = Path(tempfile.gettempdir()) / "sb_test_portfolio.json"
    if tmpf.exists():
        tmpf.unlink()
    core.USER_PORTFOLIO = tmpf
    try:
        assert core.load_user_portfolio() == []
        assert core.add_holding("NVDA", "US", 10, 100.0) is True
        items = core.load_user_portfolio()
        assert len(items) == 1 and items[0]["symbol"] == "NVDA"
        assert items[0]["currency"] == "USD"  # 自動補幣別
        # 同標的再加 → 更新而非新增
        assert core.add_holding("NVDA", "US", 20, 120.0) is True
        items = core.load_user_portfolio()
        assert len(items) == 1 and items[0]["shares"] == 20 and items[0]["cost"] == 120.0
        # 股數 0 → 拒絕
        assert core.add_holding("AAPL", "US", 0, 50.0) is False
        # 台股自動補 TWD
        core.add_holding("2330", "TW", 1000, 600.0)
        tw = [h for h in core.load_user_portfolio() if h["symbol"] == "2330"][0]
        assert tw["currency"] == "TWD"
        # 移除
        core.remove_holding("NVDA", "US")
        syms = [h["symbol"] for h in core.load_user_portfolio()]
        assert "NVDA" not in syms and "2330" in syms
        print("portfolio CRUD OK")
    finally:
        core.USER_PORTFOLIO = original
        if tmpf.exists():
            tmpf.unlink()


def test_get_portfolio_holdings_merge():
    """user_portfolio 應覆蓋 portfolio.yaml 的同鍵。"""
    import tempfile
    from pathlib import Path

    original = core.USER_PORTFOLIO
    tmpf = Path(tempfile.gettempdir()) / "sb_test_merge.json"
    core.USER_PORTFOLIO = tmpf
    try:
        core.save_user_portfolio([
            {"symbol": "NVDA", "market": "US", "shares": 5, "cost": 200, "currency": "USD"},
        ])
        merged = core.get_portfolio_holdings()
        nvda = [h for h in merged if h["symbol"].upper() == "NVDA"]
        assert nvda and float(nvda[0]["shares"]) == 5
        print("portfolio merge OK")
    finally:
        core.USER_PORTFOLIO = original
        if tmpf.exists():
            tmpf.unlink()


if __name__ == "__main__":
    test_strategy_registry()
    test_portfolio_crud()
    test_get_portfolio_holdings_merge()
    print("test_core 全部通過")
