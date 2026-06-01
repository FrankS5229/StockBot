"""資料層測試：可離線跑（合成資料）+ 可連網跑（真實抓取）。

執行：
    python -m tests.test_data           # 預設含連網測試
    python -m tests.test_data --offline # 只跑離線測試
"""
import sys

import tests.conftest_path  # noqa: F401
import pandas as pd

from data.fetchers import _standardize, STD_COLS


def test_standardize_offline():
    """_standardize 應整理欄位、排序、去重、轉數值。"""
    raw = pd.DataFrame(
        {
            "open": [1, 2], "high": [2, 3], "low": [0.5, 1.5],
            "close": [1.5, 2.5], "volume": [100, 200],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-01"]),  # 故意亂序
    )
    out = _standardize(raw)
    assert list(out.columns) == STD_COLS
    assert out.index.is_monotonic_increasing      # 已排序
    assert out["close"].dtype.kind == "f"          # 數值
    print("[offline] _standardize OK")


def test_fetch_online():
    """真實抓 NVDA，確認非空、欄位正確。"""
    from data.fetchers import get_ohlcv

    df = get_ohlcv("NVDA", "US", "1d", "3mo", use_cache=False)
    assert not df.empty, "抓不到 NVDA 資料"
    assert set(STD_COLS).issubset(df.columns)
    assert df.index.is_monotonic_increasing
    print(f"[online] NVDA 抓到 {len(df)} 列 OK")


if __name__ == "__main__":
    test_standardize_offline()
    if "--offline" not in sys.argv:
        test_fetch_online()
    print("test_data 全部通過")
