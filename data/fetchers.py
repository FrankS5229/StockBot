"""資料取得層。

提供統一介面 `get_ohlcv(symbol, market, interval, period)`，
依市場路由到不同資料源：
- US（美股）: yfinance
- TW（台股）: FinMind（需 token，首選）→ 取不到時退回 yfinance 的 `.TW`

回傳標準化 DataFrame：
    index = DatetimeIndex（升冪）
    columns = open, high, low, close, volume
並快取到本地 parquet，避免重複打 API。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 標準化後的欄位
STD_COLS = ["open", "high", "low", "close", "volume"]

CACHE_DIR = Path(__file__).resolve().parent / "cache"

# 盤中（分鐘/小時）週期：快取有效期較短，且 Yahoo 史料有上限
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


def _is_intraday(interval: str) -> bool:
    return interval in _INTRADAY_INTERVALS


# --------------------------------------------------------------------------- #
# 對外主函式
# --------------------------------------------------------------------------- #
def get_ohlcv(
    symbol: str,
    market: str,
    interval: str = "1d",
    period: str = "2y",
    *,
    use_cache: bool = True,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """取得單一標的的 OHLCV 資料。

    Args:
        symbol: 股票代號（台股如 "0050"/"2330"，美股如 "NVDA"）。
        market: "TW" 或 "US"。
        interval: K 線週期，如 "1d"/"1h"/"15m"。
        period: 歷史長度，如 "2y"/"6mo"/"1y"。
        use_cache: 是否使用當日本地快取。
        cache_dir: 自訂快取目錄；預設 data/cache。

    Returns:
        標準化 DataFrame（index 為 DatetimeIndex，欄位見 STD_COLS）。
    """
    market = market.upper()
    if market not in ("TW", "US"):
        raise ValueError(f"market 必須是 'TW' 或 'US'，收到：{market!r}")

    cdir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_file = cdir / f"{market}_{symbol}_{interval}_{period}.parquet"

    if use_cache:
        # 盤中資料 15 分鐘失效；日/週/月線當日有效
        max_age = 900 if _is_intraday(interval) else None
        cached = _load_cache(cache_file, max_age)
        if cached is not None:
            return cached

    if market == "US":
        df = _fetch_yfinance(symbol, market, interval, period)
    else:  # TW
        df = _fetch_finmind(symbol, interval, period)
        if df is None or df.empty:
            # 退回 yfinance（.TW 後綴）
            df = _fetch_yfinance(symbol, market, interval, period)

    df = _standardize(df)

    if use_cache and not df.empty:
        _save_cache(df, cache_file)
    return df


# --------------------------------------------------------------------------- #
# 各資料源
# --------------------------------------------------------------------------- #
def _fetch_yfinance(symbol: str, market: str, interval: str, period: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise ImportError("需要安裝 yfinance：pip install yfinance") from e

    # 台股：先試上市 .TW，抓不到再試上櫃 .TWO；美股用原代號
    candidates = [f"{symbol}.TW", f"{symbol}.TWO"] if market == "TW" else [symbol]
    df = None
    for ticker in candidates:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        if df is not None and not df.empty:
            break
    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance 新版多檔會回 MultiIndex 欄位，這裡只取單檔
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    return df


def _fetch_finmind(symbol: str, interval: str, period: str) -> pd.DataFrame | None:
    """以 FinMind 取台股日線。僅支援日線；非日線回 None 讓上層退回 yfinance。"""
    if interval != "1d":
        return None

    token = os.getenv("FINMIND_TOKEN")
    try:
        from FinMind.data import DataLoader
    except ImportError:
        return None  # 未安裝 → 上層退回 yfinance

    api = DataLoader()
    if token:
        try:
            api.login_by_token(api_token=token)
        except Exception as e:
            # token 失效也先試免登入額度，但記一行警告方便除錯
            print(f"⚠ FinMind token 登入失敗（改用免登入額度）：{e}")

    start = _period_to_start(period)
    try:
        raw = api.taiwan_stock_daily(
            stock_id=symbol,
            start_date=start.strftime("%Y-%m-%d"),
        )
    except Exception:
        return None

    if raw is None or raw.empty:
        return pd.DataFrame()

    raw = raw.rename(
        columns={
            "max": "high",
            "min": "low",
            "Trading_Volume": "volume",
        }
    )
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.set_index("date")
    return raw[["open", "high", "low", "close", "volume"]]


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """整理成標準欄位、排序、去除全空列。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=STD_COLS)

    keep = [c for c in STD_COLS if c in df.columns]
    df = df[keep].copy()

    df.index = pd.to_datetime(df.index)
    df.index.name = "datetime"
    df = df[~df.index.duplicated(keep="last")].sort_index()

    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["close"])
    return df


def _period_to_start(period: str) -> datetime:
    """把 yfinance 風格的 period 字串換成起始日期。"""
    period = period.strip().lower()
    now = datetime.now()
    try:
        if period.endswith("y"):
            return now - timedelta(days=365 * int(period[:-1]))
        if period.endswith("mo"):
            return now - timedelta(days=30 * int(period[:-2]))
        if period.endswith("d"):
            return now - timedelta(days=int(period[:-1]))
    except ValueError:
        pass
    return now - timedelta(days=365 * 2)  # 預設兩年


def _load_cache(path: Path, max_age: float | None = None) -> pd.DataFrame | None:
    """讀回快取。

    max_age 給秒數時：超過該秒數即過期（盤中用，預設 15 分鐘）。
    max_age 為 None 時：當日有效、隔日過期（日/週/月線用）。
    """
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    if max_age is not None:
        if (datetime.now() - mtime).total_seconds() > max_age:
            return None  # 盤中過期 → 重新抓
    elif mtime.date() != datetime.now().date():
        return None  # 隔日過期 → 重新抓
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _save_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path)
    except Exception:
        # 沒裝 pyarrow 等情況 → 退回 csv（不影響主流程）
        df.to_csv(path.with_suffix(".csv"))


if __name__ == "__main__":  # 簡易手動測試
    out = get_ohlcv("NVDA", "US", "1d", "6mo")
    print(out.tail())
    print(f"\n{len(out)} rows, columns={list(out.columns)}")
