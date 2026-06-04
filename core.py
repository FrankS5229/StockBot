"""共用流程：讀設定、抓資料、算指標、產訊號。

scanner.py 與 dashboard/app.py 都從這裡取資料，避免重複邏輯。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from data.fetchers import get_ohlcv
from indicators.ta import add_indicators
from strategy.base import Signal
from strategy.bollinger import BollingerStrategy
from strategy.ema_macd_rsi import EmaMacdRsiStrategy
from strategy.fibonacci import FibonacciStrategy
from strategy.golden_cross import GoldenCrossStrategy

ROOT = Path(__file__).resolve().parent
USER_WATCHLIST = ROOT / "user_watchlist.json"
USER_PORTFOLIO = ROOT / "user_portfolio.json"

# --------------------------------------------------------------------------- #
# 策略註冊表（新增策略時在此登記即可被 UI 與 CLI 選用）
# --------------------------------------------------------------------------- #
STRATEGY_REGISTRY = {
    EmaMacdRsiStrategy.name: EmaMacdRsiStrategy,
    FibonacciStrategy.name: FibonacciStrategy,
    GoldenCrossStrategy.name: GoldenCrossStrategy,
    BollingerStrategy.name: BollingerStrategy,
}
STRATEGY_LABELS = {
    EmaMacdRsiStrategy.name: "EMA + MACD + RSI（順勢動能）",
    FibonacciStrategy.name: "Fibonacci 回撤（順勢低接）",
    GoldenCrossStrategy.name: "Golden Cross 50/200（長期趨勢）",
    BollingerStrategy.name: "Bollinger 布林通道（均值回歸/震盪盤）",
}
DEFAULT_STRATEGY = EmaMacdRsiStrategy.name


def load_config(path: str | Path | None = None) -> dict:
    """讀 config.yaml，並把使用者透過介面加入的標的合併進 watchlist。"""
    p = Path(path) if path else ROOT / "config.yaml"
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["watchlist"] = _merge_watchlist(cfg.get("watchlist", []), load_user_watchlist())
    return cfg


# --------------------------------------------------------------------------- #
# 使用者自訂 watchlist（存成 JSON，避免破壞 config.yaml 的註解）
# --------------------------------------------------------------------------- #
def load_user_watchlist() -> list[dict]:
    """讀使用者透過介面加入的標的清單。"""
    if not USER_WATCHLIST.exists():
        return []
    try:
        return json.loads(USER_WATCHLIST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_user_watchlist(items: list[dict]) -> None:
    USER_WATCHLIST.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_symbol(
    symbol: str, market: str, name: str | None = None, category: str | None = None
) -> bool:
    """新增一個標的到使用者清單。已存在則回 False。

    category（選填）：自訂分組，供「當前訊號」依類別分子 tab；留空則由市場（台股/美股）決定。
    """
    symbol = symbol.strip().upper()
    market = market.strip().upper()
    if not symbol:
        return False
    items = load_user_watchlist()
    for it in items:
        if it["symbol"].upper() == symbol and it["market"].upper() == market:
            return False  # 已存在
    item = {"symbol": symbol, "market": market, "name": name or symbol}
    cat = (category or "").strip()
    if cat:
        item["category"] = cat
    items.append(item)
    save_user_watchlist(items)
    return True


def remove_symbol(symbol: str, market: str) -> None:
    """從使用者清單移除標的（config.yaml 內建的無法移除）。"""
    items = [
        it for it in load_user_watchlist()
        if not (it["symbol"].upper() == symbol.upper() and it["market"].upper() == market.upper())
    ]
    save_user_watchlist(items)


def _merge_watchlist(base: list[dict], user: list[dict]) -> list[dict]:
    """合併內建與使用者標的，以 (symbol, market) 去重。"""
    seen = {(b["symbol"].upper(), b["market"].upper()) for b in base}
    merged = list(base)
    for u in user:
        key = (u["symbol"].upper(), u["market"].upper())
        if key not in seen:
            merged.append(u)
            seen.add(key)
    return merged


def load_portfolio(path: str | Path | None = None) -> dict | None:
    """讀 portfolio.yaml（沒有就回 None）。"""
    p = Path(path) if path else ROOT / "portfolio.yaml"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# 使用者庫存（UI 輸入，存 JSON；不動 portfolio.yaml）
# --------------------------------------------------------------------------- #
def load_user_portfolio() -> list[dict]:
    """讀使用者透過介面輸入的庫存清單。"""
    if not USER_PORTFOLIO.exists():
        return []
    try:
        return json.loads(USER_PORTFOLIO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_user_portfolio(items: list[dict]) -> None:
    USER_PORTFOLIO.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_holding(
    symbol: str, market: str, shares: float, cost: float, currency: str = ""
) -> bool:
    """新增一筆庫存。同 (symbol, market) 已存在則更新股數/成本並回 True。"""
    symbol = symbol.strip().upper()
    market = market.strip().upper()
    if not symbol or shares <= 0:
        return False
    items = load_user_portfolio()
    for it in items:
        if it["symbol"].upper() == symbol and it["market"].upper() == market:
            it.update(shares=shares, cost=cost, currency=currency)
            save_user_portfolio(items)
            return True
    items.append(
        {
            "symbol": symbol, "market": market,
            "shares": shares, "cost": cost,
            "currency": currency or ("TWD" if market == "TW" else "USD"),
        }
    )
    save_user_portfolio(items)
    return True


def remove_holding(symbol: str, market: str) -> None:
    items = [
        it for it in load_user_portfolio()
        if not (it["symbol"].upper() == symbol.upper() and it["market"].upper() == market.upper())
    ]
    save_user_portfolio(items)


def get_portfolio_holdings() -> list[dict]:
    """取得庫存清單。

    一旦使用者透過介面存過庫存（`user_portfolio.json` **檔案存在**），即**以它為準**——
    介面可完整新增/修改/刪除，連「全部刪光存成空清單」也成立（不會被 yaml 種子復活）。
    這根治了「portfolio.yaml 來源持股刪不掉 / 刪改後市值損益沒更新」。
    若使用者還沒存過（檔案不存在），則回退到 `portfolio.yaml` 當初始種子。
    """
    if USER_PORTFOLIO.exists():
        return load_user_portfolio()
    yaml_pf = load_portfolio()
    return (yaml_pf or {}).get("holdings", []) if yaml_pf else []


def get_strategy(cfg: dict, active: str | None = None):
    """從註冊表取策略。

    active 給定時以它為準（顯式覆寫）；否則用 cfg['strategy']['active']；
    未知或未設則退回 DEFAULT_STRATEGY。
    """
    name = active or (cfg.get("strategy") or {}).get("active", DEFAULT_STRATEGY)
    cls = STRATEGY_REGISTRY.get(name, STRATEGY_REGISTRY[DEFAULT_STRATEGY])
    return cls(cfg)


def analyze_symbol(
    symbol: str,
    market: str,
    cfg: dict,
    *,
    strategy: str | None = None,
    interval: str | None = None,
    period: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """抓單一標的資料並附上指標與訊號欄位。

    strategy / interval / period 為顯式覆寫；留 None 則沿用 cfg（向後相容）。
    顯式傳入可讓呼叫端（如儀表板快取）不依賴就地修改全域 cfg 的副作用。
    """
    d = cfg.get("data", {})
    raw = get_ohlcv(
        symbol,
        market,
        interval=interval or d.get("interval", "1d"),
        period=period or d.get("period", "2y"),
        use_cache=use_cache,
    )
    if raw.empty:
        return raw
    df = add_indicators(raw, cfg.get("indicators"))
    return get_strategy(cfg, strategy).generate(df)


def latest_signal(
    symbol: str, market: str, cfg: dict, *, strategy: str | None = None, **kw
) -> Signal | None:
    """取單一標的最新訊號快照。"""
    df = analyze_symbol(symbol, market, cfg, strategy=strategy, **kw)
    if df.empty:
        return None
    return get_strategy(cfg, strategy).latest_signal(df, symbol)
