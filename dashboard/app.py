"""StockBot Streamlit 儀表板。

啟動：
    .venv\\Scripts\\streamlit run dashboard/app.py

六個面板：
  1. K線 + 指標疊圖（含進出場箭頭、停損/停利線、常駐三態訊號徽章、手畫工具 popover）
  2. 當前訊號狀態（白話理由）
  3. 回測績效（指標附說明，含買進持有對照、樣本外 IS/OOS 對照）
  4. 目標價（前瞻情境：技術價位＋GBM 統計投影，輸出區間＋達成機率）
  5. 投資組合概覽（讀 portfolio.yaml，通用）
  6. 策略說明（動態列出各策略 DESCRIPTION）

側邊欄可全域切換：標的、策略、回測長度（period）、K線週期（interval）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 讓 dashboard/ 能 import 專案根目錄模組
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import targets
from core import (
    add_symbol,
    analyze_symbol,
    get_portfolio_holdings,
    load_config,
    load_user_watchlist,
    remove_symbol,
    save_user_portfolio,
    use_store,
    DEFAULT_STRATEGY,
    STRATEGY_LABELS,
    STRATEGY_REGISTRY,
)
from data.fetchers import get_ohlcv
from backtest.runner import METRIC_GLOSSARY, run_backtest, split_in_out

st.set_page_config(page_title="StockBot 看盤儀表板", layout="wide")


# --------------------------------------------------------------------------- #
# 無狀態（雲端）模式：user data 走 session，不碰磁碟、重整即歸零
# --------------------------------------------------------------------------- #
def _truthy(v) -> bool:
    return v is not None and str(v).strip().lower() not in ("", "0", "false", "no", "off")


def _flag(name: str):
    """讀旗標：優先環境變數，其次 st.secrets（本機無 secrets.toml 時安全略過）。"""
    val = os.getenv(name)
    if val is None:
        try:
            val = st.secrets.get(name)
        except Exception:
            val = None
    return val


class SessionStore:
    """無狀態後端：watchlist / portfolio 存 st.session_state。

    每個瀏覽器分頁各自獨立、重整（新 session）即歸零、完全不寫磁碟。
    portfolio_has_user_data() 恆為 True → 永遠用 session 空清單、不吃 portfolio.yaml 種子
    （符合雲端「初始完全空白」）。
    """

    def _get(self, key: str) -> list[dict]:
        if key not in st.session_state:
            st.session_state[key] = []
        return st.session_state[key]

    def watchlist_load(self) -> list[dict]:
        return list(self._get("_wl"))

    def watchlist_save(self, items: list[dict]) -> None:
        st.session_state["_wl"] = list(items)

    def portfolio_load(self) -> list[dict]:
        return list(self._get("_pf"))

    def portfolio_save(self, items: list[dict]) -> None:
        st.session_state["_pf"] = list(items)

    def portfolio_has_user_data(self) -> bool:
        return True


STATELESS = _truthy(_flag("STOCKBOT_STATELESS"))
if STATELESS:
    use_store(SessionStore())  # 需在 load_config() 之前注入（watchlist 於此合併）

cfg = load_config()


# --------------------------------------------------------------------------- #
# 手機版面：窄螢幕改單欄堆疊、縮圖高、投組精簡欄位
# --------------------------------------------------------------------------- #
# MOBILE 由側欄 toggle 決定（以 ?m= 記在網址，重整可還原）；於側欄區塊賦值為模組全域。
MOBILE = False


def layout_cols(spec):
    """手機模式回傳垂直堆疊的 container；桌機回傳 st.columns(spec)。

    spec 同 st.columns：int（等寬欄數）或 list（相對寬度）。回傳皆可用 [i] 取用、
    支援 .metric/.subheader/.popover 等，故呼叫端無需分流。
    """
    if not MOBILE:
        return st.columns(spec)
    n = spec if isinstance(spec, int) else len(spec)
    return [st.container() for _ in range(n)]

# K線週期選項（日/週/月 + 盤中 60/30 分；盤中走 yfinance，延遲約 15 分）
INTERVAL_OPTIONS = ["1d", "1wk", "1mo", "60m", "30m"]
INTERVAL_LABELS = {"1d": "日線", "1wk": "週線", "1mo": "月線", "60m": "60 分線", "30m": "30 分線"}
# 各週期可選的回測長度。盤中受 Yahoo 史料上限：30 分 ≤ ~60 天、60 分 ≤ ~2 年。
DEFAULT_PERIOD_OPTIONS = ["6mo", "1y", "2y", "5y", "max"]
PERIOD_OPTIONS_BY_INTERVAL = {
    "30m": ["5d", "1mo"],
    "60m": ["1mo", "3mo", "6mo", "1y", "2y"],
}


def _periods_per_year(interval: str, market: str) -> int:
    """年化用的每年根數。盤中依市場交易時數不同（台股盤中較短）。"""
    base = {"1d": 252, "1wk": 52, "1mo": 12}
    if interval in base:
        return base[interval]
    tw = market.upper() == "TW"
    days = 245 if tw else 252
    per_day = {"30m": 9 if tw else 13, "60m": 5 if tw else 7}.get(interval, 1)
    return per_day * days


# --------------------------------------------------------------------------- #
# 共用
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def _analyze(symbol: str, market: str, strategy_name: str, interval: str, period: str):
    """抓資料 + 指標 + 訊號（快取 1 小時）。

    strategy_name / interval / period 顯式傳入 analyze_symbol，同時作為 cache key；
    切換策略或回測長度/週期時自然失效重算，不再依賴就地修改全域 cfg 的副作用。
    """
    return analyze_symbol(
        symbol, market, cfg,
        strategy=strategy_name, interval=interval, period=period,
    )


def _watch_options() -> dict[str, dict]:
    return {f"{i.get('name', i['symbol'])}（{i['symbol']}）": i for i in cfg.get("watchlist", [])}


def _category_of(item: dict) -> str:
    """標的所屬類別；未自訂則依市場給預設（台股 / 美股）。觀察項與庫存共用。"""
    c = (item.get("category") or "").strip()
    if c:
        return c
    return "台股" if (item.get("market") or "").upper() == "TW" else "美股"


def _signal_universe() -> list[dict]:
    """當前訊號的觀察宇宙 = 觀察清單 ∪ 投組庫存（以 (symbol, market) 去重）。

    每筆統一為 {symbol, market, name, category}。觀察項沒填類別、但同標的有庫存時，
    用庫存類別補；都沒有則由市場決定（台股/美股）。
    """
    uni: dict[tuple[str, str], dict] = {}
    for it in cfg.get("watchlist", []):
        key = (it["symbol"].upper(), it["market"].upper())
        uni[key] = {
            "symbol": it["symbol"], "market": it["market"],
            "name": it.get("name", it["symbol"]),
            "category": (it.get("category") or "").strip(),
        }
    for h in get_portfolio_holdings():
        sym, mkt = h.get("symbol"), h.get("market")
        if not sym or not mkt:
            continue
        key = (sym.upper(), mkt.upper())
        if key in uni:
            if not uni[key]["category"]:          # 觀察項沒填類別 → 用庫存類別補
                uni[key]["category"] = _category_of(h)
        else:
            uni[key] = {"symbol": sym, "market": mkt, "name": sym, "category": _category_of(h)}
    out = []
    for v in uni.values():
        if not v["category"]:                      # 都沒有 → 市場預設
            v["category"] = _category_of(v)
        out.append(v)
    return out


# --------------------------------------------------------------------------- #
# 面板 1：K 線 + 指標
# --------------------------------------------------------------------------- #
def _signal_badges(active: str):
    """K 線上方常駐三態訊號徽章：作用中那一態亮、其餘暗（比照 legend 亮/暗）。"""
    spec = [("buy", "🔼 買進", "#dc2626"), ("sell", "🔽 賣出", "#16a34a"), ("hold", "⏸ 觀望", "#6b7280")]
    cols = layout_cols(3)
    for col, (key, text, color) in zip(cols, spec):
        if active == key:  # 亮：飽和底色 + 邊框
            style = f"background:{color};color:#fff;border:2px solid {color};opacity:1;font-weight:700;"
        else:              # 暗：透明底、低不透明度
            style = f"background:transparent;color:{color};border:1px solid {color};opacity:0.35;font-weight:400;"
        col.markdown(
            f"<div style='text-align:center;padding:6px 0;border-radius:8px;{style}'>{text}</div>",
            unsafe_allow_html=True,
        )


def panel_chart(df: pd.DataFrame, label: str):
    # 標題列：左標題、右側「手畫工具」popover（顏色 + 清除收進圖角，視覺上幾乎只剩 K 線圖）
    hdr = layout_cols([6, 1])
    hdr[0].subheader(f"📈 {label} K線 + 指標")
    with hdr[1].popover("🎨 手畫工具", use_container_width=True):
        draw_color = st.color_picker("手畫線顏色", "#2563eb", key="draw_color")
        if st.button("🧹 清除手畫線", help="清掉圖上所有手畫的線/方框"):
            # 圖每次 run 都重建且不含 shape；改 nonce 讓圖元件重新掛載，確保 client 端手畫線清空
            st.session_state["draw_nonce"] = st.session_state.get("draw_nonce", 0) + 1
            st.rerun()

    # 常駐當前訊號狀態（依最後一根 K 棒）：三態恆在，亮=目前訊號、暗=未作用
    last_signal = str(df["signal"].iloc[-1]) if "signal" in df.columns and len(df) else "hold"
    _signal_badges(last_signal)
    st.caption("上方為**目前訊號狀態**（最新一根 K 棒）：亮起者為當前訊號，其餘兩態淡顯但恆在。下圖箭頭為歷史進出場點。")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=("價格 / EMA / 布林通道", "MACD", "RSI"),
    )

    # 主圖：K 線
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="K線", increasing_line_color="#ef4444", decreasing_line_color="#22c55e",
        ),
        row=1, col=1,
    )
    # EMA
    fig.add_trace(go.Scatter(x=df.index, y=df["ema_fast"], name="EMA5", line=dict(width=1, color="#f59e0b")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["ema_slow"], name="EMA20", line=dict(width=1, color="#3b82f6")), row=1, col=1)
    # 布林通道
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="布林上軌", line=dict(width=0.5, color="rgba(150,150,150,0.5)")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="布林下軌", line=dict(width=0.5, color="rgba(150,150,150,0.5)"), fill="tonexty", fillcolor="rgba(150,150,150,0.08)"), row=1, col=1)

    # 進出場箭頭
    buys = df[df["signal"] == "buy"]
    sells = df[df["signal"] == "sell"]
    fig.add_trace(go.Scatter(x=buys.index, y=buys["low"] * 0.98, mode="markers", name="買進",
                             marker=dict(symbol="triangle-up", size=11, color="#dc2626")), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells.index, y=sells["high"] * 1.02, mode="markers", name="賣出",
                             marker=dict(symbol="triangle-down", size=11, color="#16a34a")), row=1, col=1)

    # 最新一筆 buy 的停損/停利線
    if not buys.empty:
        last_buy = buys.iloc[-1]
        if pd.notna(last_buy["stop_loss"]):
            fig.add_hline(y=last_buy["stop_loss"], line=dict(color="red", dash="dot", width=1),
                          annotation_text="停損", row=1, col=1)
        if pd.notna(last_buy["take_profit"]):
            fig.add_hline(y=last_buy["take_profit"], line=dict(color="green", dash="dot", width=1),
                          annotation_text="停利", row=1, col=1)

    # MACD
    colors = ["#dc2626" if v >= 0 else "#16a34a" for v in df["macd_hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["macd_hist"], name="MACD柱", marker_color=colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_dif"], name="DIF", line=dict(width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_dea"], name="DEA", line=dict(width=1)), row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI", line=dict(width=1, color="#8b5cf6")), row=3, col=1)
    fig.add_hline(y=70, line=dict(color="red", dash="dash", width=0.5), row=3, col=1)
    fig.add_hline(y=30, line=dict(color="green", dash="dash", width=0.5), row=3, col=1)

    fig.update_layout(
        height=460 if MOBILE else 780, xaxis_rangeslider_visible=False, dragmode="drawline",
        # 手畫新線/方框用所選顏色（Plotly newshape 限制：只影響之後新畫的，不改已畫好的）
        newshape=dict(line=dict(color=draw_color, width=2)),
        # 圖例獨佔最上方一列，與圖內子標題拉開
        legend=dict(orientation="h", yanchor="bottom", y=1.16, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=130, b=10),
    )
    # 第一個子圖標題往下移，避免和上方圖例/手畫工具列重疊
    if fig.layout.annotations:
        fig.layout.annotations[0].update(yshift=-10)
    # Plotly 內建手畫工具列；key 帶 nonce，按「清除手畫線」後重新掛載即清空
    st.plotly_chart(
        fig, use_container_width=True,
        key=f"kline_chart_{st.session_state.get('draw_nonce', 0)}",
        config={"modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"]},
    )
    st.caption(
        "💡 上方選顏色後再用右上工具列手畫趨勢線/方框（顏色只套用到之後新畫的）；"
        "工具列橡皮擦可單條刪除，「🧹 清除手畫線」一次清光。重整頁面手畫線不會保留。"
    )


# --------------------------------------------------------------------------- #
# 面板 2：當前訊號
# --------------------------------------------------------------------------- #
@st.fragment
def panel_signals():
    head = layout_cols([6, 1])
    head[0].subheader("🔔 當前訊號（觀察清單 ＋ 投組庫存）")
    # 局部刷新：只重算本面板（其餘分頁/側欄不重跑），避免每次互動都掃整個觀察宇宙
    if head[1].button("🔄 重新整理", key="refresh_signals", help="只重算當前訊號面板"):
        st.rerun(scope="fragment")
    universe = _signal_universe()
    if not universe:
        st.info("尚無觀察標的。可在左側欄「➕ 新增標的」，或於「投資組合」加入庫存。")
        return

    active = cfg["strategy"]["active"]
    d = cfg["data"]
    rows = []
    for it in universe:
        label = f"{it['name']}（{it['symbol']}）"
        try:
            df = _analyze(it["symbol"], it["market"], active, d["interval"], d["period"])
        except Exception as e:
            rows.append({"類別": it["category"], "標的": label, "訊號": "錯誤", "理由": str(e)})
            continue
        if df.empty:
            rows.append({"類別": it["category"], "標的": label, "訊號": "無資料", "理由": ""})
            continue
        last = df.iloc[-1]
        icon = {"buy": "🔼 買進", "sell": "🔽 賣出", "hold": "⏸ 觀望"}.get(last["signal"], last["signal"])
        rows.append({
            "類別": it["category"],
            "標的": label,
            "日期": str(df.index[-1].date()),
            "收盤": round(float(last["close"]), 2),
            "訊號": icon,
            "理由": last["reason"] or "（條件未全部滿足，維持觀望）",
        })

    all_df = pd.DataFrame(rows)
    cats = sorted(all_df["類別"].unique().tolist())
    show_cols = [c for c in ["日期", "收盤", "訊號", "理由"] if c in all_df.columns]
    # 子 tab 依類別分組；「全部」涵蓋所有標的（含類別欄）
    tabs = st.tabs([f"全部（{len(all_df)}）"] + [f"{c}（{int((all_df['類別'] == c).sum())}）" for c in cats])
    with tabs[0]:
        st.dataframe(all_df[["類別", "標的", *show_cols]], use_container_width=True, hide_index=True)
    for tab, c in zip(tabs[1:], cats):
        with tab:
            sub = all_df[all_df["類別"] == c]
            st.dataframe(sub[["標的", *show_cols]], use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# 面板 3：回測
# --------------------------------------------------------------------------- #
def panel_backtest(df: pd.DataFrame, item: dict, label: str):
    st.subheader(f"🧪 {label} 策略回測")
    market = item["market"]
    bt = cfg.get("backtest", {})
    comm = bt.get("commission_tw" if market == "TW" else "commission_us", 0.001)
    ppy = _periods_per_year(cfg["data"]["interval"], market)  # 依週期+市場年化，避免寫死 252
    res = run_backtest(df, commission=comm, slippage=0.0005, periods_per_year=ppy)
    s = res.summary()

    # 買進持有對照
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)

    c = layout_cols(4)
    c[0].metric("策略總報酬", f"{s['total_return']:+.1%}", help=METRIC_GLOSSARY["total_return"])
    c[1].metric("年化報酬", f"{s['annual_return']:+.1%}", help=METRIC_GLOSSARY["annual_return"])
    c[2].metric("Sharpe", f"{s['sharpe']:.2f}", help=METRIC_GLOSSARY["sharpe"])
    c[3].metric("最大回撤", f"{s['max_drawdown']:.1%}", help=METRIC_GLOSSARY["max_drawdown"])
    c2 = layout_cols(4)
    c2[0].metric("勝率", f"{s['win_rate']:.0%}", help=METRIC_GLOSSARY["win_rate"])
    pf = s["profit_factor"]
    c2[1].metric("盈虧比", "∞" if pf == float("inf") else f"{pf:.2f}", help=METRIC_GLOSSARY["profit_factor"])
    c2[2].metric("交易次數", s["num_trades"], help=METRIC_GLOSSARY["num_trades"])
    c2[3].metric("買進持有對照", f"{bh:+.1%}", help="同期間單純買進並抱住不動的報酬，用來對照策略好壞。")

    # 淨值曲線（策略 vs 買進持有）
    eq = res.equity_curve
    bh_curve = df["close"] / df["close"].iloc[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name="策略淨值", line=dict(color="#3b82f6")))
    fig.add_trace(go.Scatter(x=bh_curve.index, y=bh_curve.values, name="買進持有", line=dict(color="#9ca3af", dash="dash")))
    fig.update_layout(height=240 if MOBILE else 320, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    if not res.trades.empty:
        with st.expander(f"交易明細（{len(res.trades)} 筆）"):
            t = res.trades.copy()
            t["return"] = (t["return"] * 100).round(2).astype(str) + "%"
            st.dataframe(t, use_container_width=True, hide_index=True)

    # ---- 樣本內 / 樣本外（IS/OOS）對照 ----
    split = bt.get("out_of_sample_split", 0.8)
    if st.checkbox(
        f"顯示樣本外（OOS）對照（前 {split:.0%} 訓練 / 後 {1 - split:.0%} 驗證）",
        help="把資料時間序切兩段：前段樣本內(IS)、後段樣本外(OOS)。OOS 表現接近 IS 才代表策略較穩、非過度配適。",
    ):
        is_df, oos_df = split_in_out(df, split)
        if len(oos_df) < 10:
            st.info("資料太短，切不出有意義的樣本外段，請拉長回測長度。")
        else:
            r_is = run_backtest(is_df, commission=comm, slippage=0.0005, periods_per_year=ppy)
            r_oos = run_backtest(oos_df, commission=comm, slippage=0.0005, periods_per_year=ppy)

            def _col(r):
                d = r.summary()
                return {
                    "總報酬": f"{d['total_return']:+.1%}",
                    "年化": f"{d['annual_return']:+.1%}",
                    "Sharpe": f"{d['sharpe']:.2f}",
                    "最大回撤": f"{d['max_drawdown']:.1%}",
                    "勝率": f"{d['win_rate']:.0%}",
                    "交易數": d["num_trades"],
                }

            comp = pd.DataFrame(
                {f"樣本內 IS（{len(is_df)} 根）": _col(r_is),
                 f"樣本外 OOS（{len(oos_df)} 根）": _col(r_oos)}
            )
            st.dataframe(comp, use_container_width=True)
            st.caption("⚠ OOS 遠差於 IS＝可能過度配適（參數只擬合了歷史）；兩者接近才較可信。")


# --------------------------------------------------------------------------- #
# 面板 4：投資組合
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def _spot_price(symbol: str, market: str) -> float:
    """取最新收盤價（快取 10 分鐘，避免重複抓）。"""
    try:
        return float(get_ohlcv(symbol, market, "1d", "5d")["close"].iloc[-1])
    except Exception:
        return float("nan")


@st.cache_data(ttl=3600, show_spinner=False)
def _usdtwd_rate() -> float:
    """1 USD 可換多少 TWD（Yahoo `TWD=X`，快取 1 小時）。抓不到回 NaN。"""
    try:
        import yfinance as yf
        df = yf.download("TWD=X", period="5d", interval="1d", progress=False)
        return float(df["Close"].squeeze().dropna().iloc[-1])
    except Exception:
        return float("nan")


def panel_portfolio():
    st.subheader("💼 投資組合概覽")

    holdings = get_portfolio_holdings()

    # ---- 可隱藏的編輯表單（無庫存時自動展開，有庫存時收合）----
    with st.expander("✏️ 編輯庫存（新增 / 修改 / 刪除）", expanded=not holdings):
        if STATELESS:
            st.caption(
                "直接新增列 / 改數字 / 刪列，按「💾 儲存」生效。"
                "「類別」可自訂分組（如 台股 / 美股 / ETF / AI…），留空則依市場自動歸類。"
                "⚠ 此為公開試用版：資料只存在本次瀏覽階段，**重整或關閉頁面即歸零**。"
            )
        else:
            st.caption(
                "直接新增列 / 改數字 / 刪列，按「💾 儲存」生效（存到 `user_portfolio.json`）。"
                "「類別」可自訂分組（如 台股 / 美股 / ETF / AI…），留空則依市場自動歸類。"
                "首次以 `portfolio.yaml` 為初始內容；存過後以你編輯的為準。"
            )
        st.caption("「排序」欄填數字即可重新排列（小→大）；存檔後估值與圖表都依此順序。")
        edit_df = pd.DataFrame(
            [
                {
                    "排序": i + 1,
                    "代號": h.get("symbol", ""),
                    "市場": (h.get("market") or "US").upper(),
                    "類別": _category_of(h),
                    "股數": float(h.get("shares", 0) or 0),
                    "成本": float(h.get("cost", 0) or 0),
                    "幣別": (h.get("currency") or "").upper(),
                }
                for i, h in enumerate(holdings)
            ],
            columns=["排序", "代號", "市場", "類別", "股數", "成本", "幣別"],
        )
        edited = st.data_editor(
            edit_df, num_rows="dynamic", use_container_width=True, hide_index=True,
            key="holdings_editor",
            column_config={
                "排序": st.column_config.NumberColumn("排序", help="填數字重排（小→大）", min_value=1, step=1, width="small"),
                "代號": st.column_config.TextColumn("代號", help="美股如 NVDA；台股如 2330", required=True),
                "市場": st.column_config.SelectboxColumn("市場", options=["US", "TW"], required=True),
                "類別": st.column_config.TextColumn("類別", help="自訂分組，留空依市場（台股/美股）"),
                "股數": st.column_config.NumberColumn("股數", min_value=0.0, step=1.0),
                "成本": st.column_config.NumberColumn("平均成本", min_value=0.0, step=0.01, format="%.2f"),
                "幣別": st.column_config.SelectboxColumn("幣別（留空自動）", options=["TWD", "USD"]),
            },
        )
        if st.button("💾 儲存庫存變更"):
            staged = []
            for pos, r in enumerate(edited.to_dict("records")):
                sym = str(r.get("代號") or "").strip().upper()
                mkt = str(r.get("市場") or "").strip().upper()
                try:
                    shares = float(r.get("股數") or 0)
                    cost = float(r.get("成本") or 0)
                except (TypeError, ValueError):
                    continue
                if not sym or mkt not in ("US", "TW") or shares <= 0:
                    continue  # 跳過空白/無效列
                cur = str(r.get("幣別") or "").strip().upper() or ("TWD" if mkt == "TW" else "USD")
                rec = {"symbol": sym, "market": mkt, "shares": shares, "cost": cost, "currency": cur}
                cat = str(r.get("類別") or "").strip()
                if cat:
                    rec["category"] = cat
                try:
                    order = float(r.get("排序"))
                except (TypeError, ValueError):
                    order = float("inf")  # 沒填排序的列排到最後（保留輸入次序）
                staged.append((order, pos, rec))
            staged.sort(key=lambda t: (t[0], t[1]))  # 依排序值；同值維持原列序（穩定）
            recs = [rec for _, _, rec in staged]
            save_user_portfolio(recs)
            st.session_state.pop("holdings_editor", None)  # 清掉編輯器暫存，避免套用到舊資料
            st.cache_data.clear()
            st.success(f"已儲存 {len(recs)} 筆庫存。")
            st.rerun()

    if not holdings:
        st.info("尚無庫存。可展開上方「✏️ 編輯庫存」直接輸入，或建立 `portfolio.yaml`。")
        return

    # ---- 匯率：以 TWD 為基準，美股市值換算後才能跨幣別加總/比例 ----
    rate = _usdtwd_rate()
    fx_ok = (rate == rate) and rate > 0  # 抓得到才換算

    # ---- 估值（讀現價；保留庫存儲存順序）----
    rows = []
    for h in holdings:
        px = _spot_price(h["symbol"], h["market"])
        shares, cost = float(h["shares"]), float(h["cost"])
        cur = (h.get("currency") or ("TWD" if (h.get("market") or "").upper() == "TW" else "USD")).upper()
        mv = px * shares
        pl = (px - cost) * shares
        pl_pct = (px / cost - 1) if cost else float("nan")
        # 換成 TWD：USD 乘匯率、TWD 不變；匯率抓不到則退回原幣（混算，會警告）
        fx = (rate if cur == "USD" else 1.0) if fx_ok else 1.0
        mv_twd = mv * fx
        cost_base_twd = cost * shares * fx
        rows.append({
            "類別": _category_of(h),
            "標的": h["symbol"], "市場": h["market"], "幣別": cur,
            "股數": shares, "成本": cost, "現價": round(px, 2),
            "市值(原幣)": round(mv, 0), "市值TWD": round(mv_twd, 0),
            "成本基礎TWD": cost_base_twd, "損益(原幣)": round(pl, 0),
            # 存「百分比數值」float（如 9.0 代表 +9.0%），顯示交給 NumberColumn 格式化；
            # 不要存格式化字串，否則使用者點欄位標頭排序會變字串排序（"+9.0%" 排在 "+30.0%" 前）。
            "報酬率": pl_pct * 100 if pl_pct == pl_pct else float("nan"),
        })
    val_df = pd.DataFrame(rows)

    # ---- 篩選（市場 / 類別 / 代號 / 關鍵字；累積套用，下游總計/圓餅連動）----
    with st.expander("🔍 篩選", expanded=False):
        f = layout_cols(3)
        mkts = sorted(val_df["市場"].unique().tolist())
        picked_mkt = f[0].multiselect("市場", mkts, default=mkts, key="mkt_filter")
        cats = sorted(val_df["類別"].unique().tolist())
        picked_cat = f[1].multiselect("類別", cats, default=cats, key="cat_filter")
        syms = sorted(val_df["標的"].unique().tolist())
        picked_sym = f[2].multiselect("代號（空＝全部）", syms, default=[], key="sym_filter")
        kw = st.text_input("關鍵字搜尋（比對 標的 / 類別 / 市場）", key="kw_filter").strip()

    view = val_df
    view = view[view["市場"].isin(picked_mkt)] if picked_mkt else view.iloc[0:0]
    view = view[view["類別"].isin(picked_cat)] if picked_cat else view.iloc[0:0]
    if picked_sym:                       # 代號空＝不過濾（看全部）
        view = view[view["標的"].isin(picked_sym)]
    if kw:
        k = kw.lower()
        mask = (
            view["標的"].astype(str).str.lower().str.contains(k)
            | view["類別"].astype(str).str.lower().str.contains(k)
            | view["市場"].astype(str).str.lower().str.contains(k)
        )
        view = view[mask]

    # 總計（TWD）依篩選後連動；市值取非 NaN，成本基礎同步對齊
    ok = view["市值TWD"].notna()
    total_mv = float(view.loc[ok, "市值TWD"].sum())
    total_cost = float(view.loc[ok, "成本基礎TWD"].sum())
    unit = "TWD" if fx_ok else ""
    if total_cost > 0:
        tot_pl = total_mv - total_cost
        m = layout_cols(3)
        m[0].metric(f"總市值 {unit}".strip(), f"{total_mv:,.0f}")
        m[1].metric(f"總損益 {unit}".strip(), f"{tot_pl:,.0f}", f"{tot_pl / total_cost:+.1%}")
        m[2].metric("持股檔數", len(view))
        if fx_ok:
            st.caption(f"💱 美股以 1 USD = {rate:.2f} TWD 換算後加總（匯率每小時更新；現價/成本欄仍為原幣）。")
        else:
            st.caption("⚠ 匯率抓取失敗，未換算，不同幣別直接相加，總計僅供概略參考。")

    st.markdown("##### 估值明細")
    if MOBILE:
        # 手機：精簡欄位避免 10+ 欄橫向捲動（代號 / 市值TWD / 報酬率）
        show_cols = ["標的", "市值TWD", "報酬率"]
    else:
        show_cols = ["類別", "標的", "市場", "幣別", "股數", "成本", "現價",
                     "市值(原幣)", "市值TWD", "損益(原幣)", "報酬率"]
    st.dataframe(
        view[show_cols], use_container_width=True, hide_index=True,
        column_config={
            "報酬率": st.column_config.NumberColumn("報酬率", format="%.1f%%"),
        },
    )

    # ---- 類別小計 + 配置圓餅（依 TWD 市值；隨篩選連動）----
    if not view.empty and float(view["市值TWD"].dropna().sum()) > 0:
        cat_g = view.groupby("類別")["市值TWD"].sum()
        tot = float(cat_g.sum())
        c1, c2 = layout_cols(2)
        with c1:
            st.markdown(f"##### 類別小計（{unit or '原幣混算'}）")
            cat_tbl = cat_g.reset_index()
            cat_tbl["市值TWD"] = cat_tbl["市值TWD"].round(0)
            cat_tbl["佔比"] = [f"{v / tot * 100:.1f}%" for v in cat_g.values]
            st.dataframe(cat_tbl, use_container_width=True, hide_index=True)
        with c2:
            fig = go.Figure(data=[go.Pie(labels=cat_g.index, values=cat_g.values, hole=0.4)])
            fig.update_layout(height=240 if MOBILE else 300, margin=dict(l=10, r=10, t=40, b=10),
                              title=dict(text=f"類別配置（{unit or '原幣'}）", y=0.97))
            st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# 面板 5：策略說明
# --------------------------------------------------------------------------- #
def panel_strategy_info():
    st.subheader("📚 策略說明")
    st.markdown(
        "#### 先搞懂兩個詞\n"
        "- **策略（Strategy）**：一整套「什麼時候買、什麼時候賣」的規則。換策略＝換一套買賣邏輯。\n"
        "- **參數（Parameter）**：策略裡可以調的數字旋鈕。例如 EMA 用 **5 日**還是 **10 日**、"
        "RSI 進場區間設 **50–70** 還是 **40–60**、停損用 **1 倍**還是 **2 倍** ATR。\n\n"
        "> 同一個策略，調參數會改變訊號的鬆緊；換策略則是換完全不同的進出場思路。"
        "可在左側欄切換策略，**K線箭頭、當前訊號、回測**會同步換成該策略的結果來比較。\n"
    )
    st.divider()
    for name, cls in STRATEGY_REGISTRY.items():
        active_mark = "✅ （目前使用中）" if name == cfg["strategy"]["active"] else ""
        st.markdown(f"### {STRATEGY_LABELS.get(name, name)} {active_mark}")
        st.markdown(cls.DESCRIPTION or "（尚無說明）")
        st.divider()
    st.info(
        "提醒：策略只是輔助判斷的工具。回測**落後「買進持有」是正常的**"
        "（尤其強多頭標的），數字不漂亮反而代表沒有偷看未來資料。實務上需要依回測結果調整參數。"
    )


# --------------------------------------------------------------------------- #
# 面板 6：目標價（前瞻情境）
# --------------------------------------------------------------------------- #
def panel_targets(df: pd.DataFrame, item: dict, label: str):
    st.subheader(f"🎯 {label} 目標價（前瞻情境）")
    st.caption(
        "與買賣訊號不同：訊號是 K 線走完後的**事後**標註；這裡是**從當下往前看**估未來價位。"
        "展望以目前 K 線週期的「根數」計：短線＝未來 10 根、長線＝未來 120 根。"
    )

    cset = layout_cols([1.2, 1, 2])
    horizon = cset[0].radio("展望", ["短線", "長線"], horizontal=True, key="target_horizon")
    mode = cset[1].radio("顯示", ["簡易", "進階"], horizontal=True, key="target_mode",
                         help="簡易＝三檔目標＋一句結論；進階＝再加投影圖與完整技術目標表（含機率）。")
    base_spec = targets.SHORT_SPEC if horizon == "短線" else targets.LONG_SPEC
    advanced = mode == "進階"
    zero = base_spec.zero_drift
    if advanced:
        zero = cset[2].checkbox(
            "零漂移（μ=0，純波動錐，較保守）", value=base_spec.zero_drift,
            help="短窗估的漂移雜訊大；長線預設開啟。關閉＝用歷史平均報酬外推（過去 ≠ 未來，請謹慎）。",
        )
    spec = replace(base_spec, zero_drift=zero)
    rep = targets.build_report(df, item["symbol"], spec)
    if rep is None:
        st.warning("資料不足，無法計算目標價。")
        return

    # 一句話白話結論（兩模式都放最上方，是整頁的重點）
    st.success(targets.plain_summary(rep))

    def _fmt(v: float) -> str:
        return f"{v:,.2f}（{v / rep.spot - 1:+.1%}）"

    c = layout_cols(4)
    c[0].metric("現價", f"{rep.spot:,.2f}")
    c[1].metric("基準（統計中位）", _fmt(rep.base), help="GBM 中位投影價，五五波的中間參考。")
    c[2].metric("保守上檔（第一目標）", _fmt(rep.conservative), help="最接近現價的上檔技術關卡，當第一停利目標。")
    c[3].metric("樂觀上檔", _fmt(rep.optimistic), help="最遠的上檔目標（含統計 90% 上界），順勢時的想像空間。")
    st.caption(
        f"統計投影（GBM，{rep.horizon_bars} 根）：70% 區間 {rep.low70:,.2f}–{rep.high70:,.2f}；"
        f"90% 區間 {rep.low90:,.2f}–{rep.high90:,.2f}"
        f"（μ={rep.mu:.4f}／根、σ={rep.sigma:.4f}／根{'，零漂移' if rep.zero_drift else ''}）。"
    )

    if not advanced:
        st.caption(
            "💡 怎麼讀：**保守上檔**＝第一停利目標、**樂觀上檔**＝順勢想像、**基準**＝中性參考、"
            "**70% 區間**＝近期風險範圍。想看每個價位的「達成機率」與完整關卡，切到上方「進階」。"
            "　⚠ 目標價是情境推估非預測。"
        )
        return

    # ---- 以下為「進階」內容：前瞻投影錐 + 完整技術目標表 ----
    # ---- 前瞻投影錐（近 60 根歷史 + 未來中位線與 70/90% 帶）----
    hist = df["close"].iloc[-60:]
    step = (df.index[-1] - df.index[-2]) if len(df.index) > 1 else pd.Timedelta(days=1)
    future = [df.index[-1] + step * (i + 1) for i in range(rep.horizon_bars)]
    ks = np.arange(1, rep.horizon_bars + 1)
    dr = rep.mu - 0.5 * rep.sigma ** 2
    sq = rep.sigma * np.sqrt(ks)
    med = rep.spot * np.exp(dr * ks)
    hi70, lo70 = rep.spot * np.exp(dr * ks + 1.0364 * sq), rep.spot * np.exp(dr * ks - 1.0364 * sq)
    hi90, lo90 = rep.spot * np.exp(dr * ks + 1.6449 * sq), rep.spot * np.exp(dr * ks - 1.6449 * sq)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist.values, name="歷史收盤", line=dict(color="#3b82f6")))
    fig.add_trace(go.Scatter(x=future, y=hi90, name="90% 上界", line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=future, y=lo90, name="90% 區間", fill="tonexty",
                             fillcolor="rgba(59,130,246,0.10)", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=future, y=hi70, name="70% 上界", line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=future, y=lo70, name="70% 區間", fill="tonexty",
                             fillcolor="rgba(59,130,246,0.18)", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=future, y=med, name="中位投影", line=dict(color="#f59e0b", dash="dash")))
    fig.update_layout(height=240 if MOBILE else 340, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    # ---- 技術目標表（含 GBM 達成機率）----
    tl = pd.DataFrame(
        [
            {
                "方法": lv.label,
                "方向": "上檔" if lv.direction == "up" else "下檔",
                "目標價": round(lv.price, 2),
                "距現價": (lv.price / rep.spot - 1) * 100,
                "達成機率": (lv.prob_reach * 100) if lv.prob_reach is not None else float("nan"),
            }
            for lv in rep.levels
        ]
    ).sort_values("目標價").reset_index(drop=True)
    st.markdown("##### 技術目標價（附 GBM 達成機率）")
    st.dataframe(
        tl, use_container_width=True, hide_index=True,
        column_config={
            "距現價": st.column_config.NumberColumn("距現價", format="%.1f%%"),
            "達成機率": st.column_config.NumberColumn("達成機率", format="%.0f%%",
                                                  help="GBM 估：H 根後期末價收在該目標之上(上檔)/之下(下檔)的機率。"),
        },
    )
    st.info(
        "⚠ 目標價是「情境推估」非預測。技術價位法給明確價位、統計投影法給機率區間；"
        "GBM 假設對數常態隨機漫步且 μ/σ 固定，真實市場有肥尾與情境轉換。"
        "長線純技術/統計、無基本面（估值）錨，請搭配其他依據判斷。"
    )


# --------------------------------------------------------------------------- #
# 版面
# --------------------------------------------------------------------------- #
st.title("📊 StockBot 看盤儀表板")
st.caption("技術指標訊號輔助 + 回測。僅供參考，不構成投資建議，不自動下單。")
if STATELESS:
    st.info("🌐 公開試用版：你的觀察清單與投資組合只存在本次瀏覽階段，**重整或關閉頁面即全部歸零**，不會記錄任何個人資料。", icon="ℹ️")

options = _watch_options()
with st.sidebar:
    st.header("設定")

    # ---- 手機版面開關（以 ?m= 記在網址，重整可還原）----
    if "mobile_mode" not in st.session_state:
        _qp_m = st.query_params.get("m")
        st.session_state["mobile_mode"] = _truthy(_qp_m) if _qp_m is not None else False
    MOBILE = st.toggle(
        "📱 手機版面", key="mobile_mode",
        help="窄螢幕用：多欄改單欄堆疊、縮小圖高、投組只留精簡欄位。也可在網址加 ?m=1 直接開。",
    )
    st.query_params["m"] = "1" if MOBILE else "0"

    # 記住選到的標的：用 ?symbol= 還原（連瀏覽器 F5 都不會跳回第一個）
    labels = list(options.keys())
    qp_sym = st.query_params.get("symbol")
    sym_idx = 0
    if qp_sym:
        for i, it in enumerate(options.values()):
            if it["symbol"].upper() == qp_sym.upper():
                sym_idx = i
                break
    label = st.selectbox("選擇標的", labels, index=sym_idx, key="sel_symbol")
    st.query_params["symbol"] = options[label]["symbol"]  # 寫回網址，下次/重整還原

    # ---- 策略選擇（全域：影響 K線/訊號/回測）----
    strat_names = list(STRATEGY_REGISTRY.keys())
    default_idx = strat_names.index(cfg["strategy"]["active"]) if cfg["strategy"]["active"] in strat_names else 0
    chosen = st.selectbox(
        "選擇策略", strat_names, index=default_idx,
        format_func=lambda n: STRATEGY_LABELS.get(n, n),
        help="切換後 K線買賣箭頭、當前訊號、回測都會換成此策略的結果。說明見「策略說明」分頁。",
    )
    if chosen != cfg["strategy"]["active"]:
        cfg["strategy"]["active"] = chosen  # 全域生效（_analyze 以策略名為 cache key）

    # ---- K線週期 / 回測長度（全域：影響 K線/訊號/回測）----
    # 先選週期，再依週期提供合法的回測長度（盤中受 Yahoo 史料上限）
    d = cfg["data"]
    i_idx = INTERVAL_OPTIONS.index(d["interval"]) if d["interval"] in INTERVAL_OPTIONS else 0
    d["interval"] = st.selectbox(
        "K線週期", INTERVAL_OPTIONS, index=i_idx,
        format_func=lambda x: INTERVAL_LABELS.get(x, x),
        help="日/週/月線史料完整；30/60 分線為 Yahoo 盤中資料、延遲約 15 分（30 分僅近 ~60 天、60 分約 ~2 年）。",
    )
    period_opts = PERIOD_OPTIONS_BY_INTERVAL.get(d["interval"], DEFAULT_PERIOD_OPTIONS)
    p_idx = period_opts.index(d["period"]) if d["period"] in period_opts else 0
    d["period"] = st.selectbox(
        "回測長度", period_opts, index=p_idx,
        help="抓多久的歷史來畫圖與回測，也決定「買進持有對照」抱多久。盤中週期的上限由 Yahoo 限制。",
    )

    if st.button("🔄 清除快取重新抓資料"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"資料週期：{cfg['data']['interval']}｜長度：{cfg['data']['period']}｜策略：{STRATEGY_LABELS.get(chosen, chosen)}")

    # ---- 直接新增標的（免編輯 yaml）----
    st.divider()
    with st.expander("➕ 新增標的", expanded=False):
        with st.form("add_symbol_form", clear_on_submit=True):
            new_sym = st.text_input("代號", placeholder="美股如 AAPL；台股如 2454")
            new_mkt = st.radio("市場", ["US", "TW"], horizontal=True)
            new_name = st.text_input("顯示名稱（選填）", placeholder="留空則用代號")
            new_cat = st.text_input("類別（選填）", placeholder="如 AI / ETF / 半導體；留空依市場")
            submitted = st.form_submit_button("加入")
        if submitted and new_sym.strip():
            sym_u = new_sym.strip().upper()
            # 先驗證抓得到資料，避免加入無效代號
            try:
                probe = get_ohlcv(sym_u, new_mkt, "1d", "1mo")
            except Exception:
                probe = None
            if probe is None or probe.empty:
                st.error(f"抓不到 {sym_u}（{new_mkt}）的資料，請確認代號與市場。")
            elif add_symbol(sym_u, new_mkt, new_name.strip() or None, new_cat.strip() or None):
                st.success(f"已加入 {new_name.strip() or sym_u}（{sym_u}）")
                st.cache_data.clear()
                st.rerun()
            else:
                st.warning(f"{sym_u}（{new_mkt}）已在清單中。")

    # ---- 移除使用者自行加入的標的 ----
    user_items = load_user_watchlist()
    if user_items:
        with st.expander("🗑 移除我加入的標的", expanded=False):
            for it in user_items:
                col_a, col_b = st.columns([3, 1])
                col_a.write(f"{it.get('name', it['symbol'])}（{it['symbol']}/{it['market']}）")
                if col_b.button("移除", key=f"rm_{it['symbol']}_{it['market']}"):
                    remove_symbol(it["symbol"], it["market"])
                    st.cache_data.clear()
                    st.rerun()
        st.caption("註：config.yaml 內建的標的需到檔案編輯，介面僅能移除自行加入的。")

item = options[label]
try:
    df = _analyze(item["symbol"], item["market"], cfg["strategy"]["active"],
                  cfg["data"]["interval"], cfg["data"]["period"])
except Exception as e:
    st.error(f"抓取/分析失敗：{e}")
    st.stop()

if df.empty:
    st.warning("抓不到資料，請換標的或檢查網路。")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["K線+指標", "當前訊號", "回測績效", "🎯 目標價", "投資組合", "策略說明"]
)
with tab1:
    panel_chart(df, label)
with tab2:
    panel_signals()
with tab3:
    panel_backtest(df, item, label)
with tab4:
    panel_targets(df, item, label)
with tab5:
    panel_portfolio()
with tab6:
    panel_strategy_info()
