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


def test_get_portfolio_holdings_user_priority():
    """存過 user json 後以它為準；連「全刪存空」也不會被 portfolio.yaml 種子復活。"""
    import tempfile
    from pathlib import Path

    original = core.USER_PORTFOLIO
    tmpf = Path(tempfile.gettempdir()) / "sb_test_holdings.json"
    core.USER_PORTFOLIO = tmpf
    try:
        # 1) 沒存過（檔案不存在）→ 回退 portfolio.yaml 種子
        if tmpf.exists():
            tmpf.unlink()
        seed = core.get_portfolio_holdings()  # 可能為空（若無 yaml）或 yaml 內容

        # 2) 存過 → 以 user json 為準
        core.save_user_portfolio([
            {"symbol": "NVDA", "market": "US", "shares": 5, "cost": 200, "currency": "USD"},
        ])
        held = core.get_portfolio_holdings()
        assert [h["symbol"].upper() for h in held] == ["NVDA"]
        assert float(held[0]["shares"]) == 5

        # 3) 全部刪光存成空清單 → 檔案存在但為空 → 應回空，不復活 yaml
        core.save_user_portfolio([])
        assert core.get_portfolio_holdings() == [], "空檔不該被 portfolio.yaml 種子復活"
        print("portfolio user-priority + 全刪不復活 OK")
        _ = seed  # 種子分支已執行（值依環境而定，不強制斷言）
    finally:
        core.USER_PORTFOLIO = original
        if tmpf.exists():
            tmpf.unlink()


def test_add_symbol_category():
    """add_symbol 帶 category 應寫進 watchlist；留空則不帶該鍵。"""
    import tempfile
    from pathlib import Path

    original = core.USER_WATCHLIST
    tmpf = Path(tempfile.gettempdir()) / "sb_test_watchlist.json"
    if tmpf.exists():
        tmpf.unlink()
    core.USER_WATCHLIST = tmpf
    try:
        assert core.add_symbol("NVDA", "US", "NVIDIA", "AI") is True
        items = core.load_user_watchlist()
        assert len(items) == 1 and items[0]["category"] == "AI"
        # 留空類別 → 不帶 category 鍵（由市場決定預設）
        assert core.add_symbol("2330", "TW", "台積電") is True
        tw = [it for it in core.load_user_watchlist() if it["symbol"] == "2330"][0]
        assert "category" not in tw
        # 重複代號 → False
        assert core.add_symbol("NVDA", "US") is False
        print("add_symbol category OK")
    finally:
        core.USER_WATCHLIST = original
        if tmpf.exists():
            tmpf.unlink()


if __name__ == "__main__":
    test_strategy_registry()
    test_portfolio_crud()
    test_get_portfolio_holdings_user_priority()
    test_add_symbol_category()
    print("test_core 全部通過")
