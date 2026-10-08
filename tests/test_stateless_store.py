"""無狀態儲存後端測試（離線）。

驗證 core 的可注入 store 契約（dashboard 的 SessionStore 即此契約的 streamlit 實作）：
  - 注入後 load/save 走 store，不碰磁碟；
  - portfolio_has_user_data()==True 時 get_portfolio_holdings() 不吃 portfolio.yaml 種子
    （雲端「初始完全空白」），且「重置」後歸零；
  - 預設 FileStore 行為與現狀一致。

執行： python -m tests.test_stateless_store
"""
import tests.conftest_path  # noqa: F401

import core


class _MemoryStore:
    """以記憶體 dict 保存，模擬 dashboard SessionStore（以 st.session_state 保存）的語意。"""

    def __init__(self):
        self._wl: list[dict] = []
        self._pf: list[dict] = []

    def reset(self):
        """模擬瀏覽器重整/新 session：全部歸零。"""
        self._wl, self._pf = [], []

    def watchlist_load(self):
        return list(self._wl)

    def watchlist_save(self, items):
        self._wl = list(items)

    def portfolio_load(self):
        return list(self._pf)

    def portfolio_save(self, items):
        self._pf = list(items)

    def portfolio_has_user_data(self):
        return True  # 永遠用 session 清單、不退回 yaml 種子


def test_injected_store_routes_and_resets():
    original = core._USER_STORE
    store = _MemoryStore()
    core.use_store(store)
    try:
        # 初始：完全空白（即使 portfolio.yaml 存在也不吃種子）
        assert core.load_user_watchlist() == []
        assert core.load_user_portfolio() == []
        assert core.get_portfolio_holdings() == [], "無狀態模式初始應為空（不吃 yaml 種子）"

        # 透過高階 API 寫入 → 走 store、不碰磁碟
        assert core.add_symbol("NVDA", "US", "NVIDIA", "AI") is True
        assert core.add_holding("NVDA", "US", 5, 200.0) is True
        assert [it["symbol"] for it in core.load_user_watchlist()] == ["NVDA"]
        held = core.get_portfolio_holdings()
        assert [h["symbol"] for h in held] == ["NVDA"] and float(held[0]["shares"]) == 5

        # 模擬重整 → 歸零
        store.reset()
        assert core.load_user_watchlist() == []
        assert core.get_portfolio_holdings() == []
        print("stateless store 路由 + 歸零 + 不吃種子 OK")
    finally:
        core.use_store(original)


def test_default_store_is_filestore():
    """未注入時預設為 FileStore，且行為與現狀一致（寫暫存檔→讀回→刪檔語意）。"""
    import tempfile
    from pathlib import Path

    assert isinstance(core._USER_STORE, core.FileStore)

    original = core.USER_PORTFOLIO
    tmpf = Path(tempfile.gettempdir()) / "sb_test_filestore.json"
    if tmpf.exists():
        tmpf.unlink()
    core.USER_PORTFOLIO = tmpf
    try:
        # 檔案不存在 → portfolio_has_user_data()==False（可回退 yaml 種子）
        assert core._USER_STORE.portfolio_has_user_data() is False
        core.save_user_portfolio([{"symbol": "AAPL", "market": "US", "shares": 1, "cost": 10, "currency": "USD"}])
        assert tmpf.exists() and core._USER_STORE.portfolio_has_user_data() is True
        assert [h["symbol"] for h in core.load_user_portfolio()] == ["AAPL"]
        print("default FileStore 行為一致 OK")
    finally:
        core.USER_PORTFOLIO = original
        if tmpf.exists():
            tmpf.unlink()


if __name__ == "__main__":
    test_injected_store_routes_and_resets()
    test_default_store_is_filestore()
    print("test_stateless_store 全部通過")
