"""StockBot Streamlit 儀表板。

啟動：
    .venv\\Scripts\\streamlit run dashboard/app.py

五個面板：
  1. K線 + 指標疊圖（含進出場箭頭、停損/停利線）
  2. 當前訊號狀態（白話理由）
  3. 回測績效（指標附說明，含買進持有對照）
  4. 投資組合概覽（讀 portfolio.yaml，通用）
  5. 策略說明（動態列出各策略 DESCRIPTION）

側邊欄可全域切換：標的、策略、回測長度（period）、K線週期（interval）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 讓 dashboard/ 能 import 專案根目錄模組
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import (
    add_holding,
    add_symbol,
    analyze_symbol,
    get_portfolio_holdings,
    load_config,
    load_user_watchlist,
    remove_holding,
    remove_symbol,
    DEFAULT_STRATEGY,
    STRATEGY_LABELS,
    STRATEGY_REGISTRY,
)
from data.fetchers import get_ohlcv
from backtest.runner import METRIC_GLOSSARY, run_backtest

st.set_page_config(page_title="StockBot 看盤儀表板", layout="wide")
cfg = load_config()

# 回測長度 / K線週期 選項（盤中從略：台股不支援盤中、yfinance 盤中史料有限、年化基準較複雜）
PERIOD_OPTIONS = ["6mo", "1y", "2y", "5y", "max"]
INTERVAL_OPTIONS = ["1d", "1wk", "1mo"]
INTERVAL_LABELS = {"1d": "日線", "1wk": "週線", "1mo": "月線"}
# 各週期年化用的每年根數（給回測 Sharpe/年化換算；取代先前寫死 252 的限制）
PERIODS_PER_YEAR = {"1d": 252, "1wk": 52, "1mo": 12}


# --------------------------------------------------------------------------- #
# 共用
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def _analyze(symbol: str, market: str, strategy_name: str, interval: str, period: str):
    """抓資料 + 指標 + 訊號（快取 1 小時）。

    strategy_name / interval / period 納入 cache key，切換策略或回測長度/週期時才會重算
    （這些值本身不使用，實際靠全域 cfg 生效；列入簽章僅為了讓快取正確失效）。
    """
    return analyze_symbol(symbol, market, cfg)


def _watch_options() -> dict[str, dict]:
    return {f"{i.get('name', i['symbol'])}（{i['symbol']}）": i for i in cfg.get("watchlist", [])}


# --------------------------------------------------------------------------- #
# 面板 1：K 線 + 指標
# --------------------------------------------------------------------------- #
def panel_chart(df: pd.DataFrame, label: str):
    st.subheader(f"📈 {label} K線 + 指標")

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
        height=780, xaxis_rangeslider_visible=False, dragmode="drawline",
        # 圖例獨佔最上方一列，與圖內子標題拉開
        legend=dict(orientation="h", yanchor="bottom", y=1.16, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=130, b=10),
    )
    # 第一個子圖標題往下移，避免和上方圖例/手畫工具列重疊
    if fig.layout.annotations:
        fig.layout.annotations[0].update(yshift=-10)
    # Plotly 內建手畫工具列
    st.plotly_chart(
        fig, use_container_width=True,
        config={"modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"]},
    )
    st.caption("💡 圖表右上工具列可手畫趨勢線/方框；重整頁面後手畫線不會保留（之後可加保存功能）。")


# --------------------------------------------------------------------------- #
# 面板 2：當前訊號
# --------------------------------------------------------------------------- #
def panel_signals():
    st.subheader("🔔 當前訊號（所有觀察標的）")
    rows = []
    active = cfg["strategy"]["active"]
    d = cfg["data"]
    for label, item in _watch_options().items():
        try:
            df = _analyze(item["symbol"], item["market"], active, d["interval"], d["period"])
        except Exception as e:
            rows.append({"標的": label, "訊號": "錯誤", "理由": str(e)})
            continue
        if df.empty:
            rows.append({"標的": label, "訊號": "無資料", "理由": ""})
            continue
        last = df.iloc[-1]
        icon = {"buy": "🔼 買進", "sell": "🔽 賣出", "hold": "⏸ 觀望"}.get(last["signal"], last["signal"])
        rows.append({
            "標的": label,
            "日期": str(df.index[-1].date()),
            "收盤": round(float(last["close"]), 2),
            "訊號": icon,
            "理由": last["reason"] or "（條件未全部滿足，維持觀望）",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# 面板 3：回測
# --------------------------------------------------------------------------- #
def panel_backtest(df: pd.DataFrame, item: dict, label: str):
    st.subheader(f"🧪 {label} 策略回測")
    market = item["market"]
    bt = cfg.get("backtest", {})
    comm = bt.get("commission_tw" if market == "TW" else "commission_us", 0.001)
    ppy = PERIODS_PER_YEAR.get(cfg["data"]["interval"], 252)  # 依週期年化，避免寫死 252
    res = run_backtest(df, commission=comm, slippage=0.0005, periods_per_year=ppy)
    s = res.summary()

    # 買進持有對照
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)

    c = st.columns(4)
    c[0].metric("策略總報酬", f"{s['total_return']:+.1%}", help=METRIC_GLOSSARY["total_return"])
    c[1].metric("年化報酬", f"{s['annual_return']:+.1%}", help=METRIC_GLOSSARY["annual_return"])
    c[2].metric("Sharpe", f"{s['sharpe']:.2f}", help=METRIC_GLOSSARY["sharpe"])
    c[3].metric("最大回撤", f"{s['max_drawdown']:.1%}", help=METRIC_GLOSSARY["max_drawdown"])
    c2 = st.columns(4)
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
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    if not res.trades.empty:
        with st.expander(f"交易明細（{len(res.trades)} 筆）"):
            t = res.trades.copy()
            t["return"] = (t["return"] * 100).round(2).astype(str) + "%"
            st.dataframe(t, use_container_width=True, hide_index=True)


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


def panel_portfolio():
    st.subheader("💼 投資組合概覽")

    # ---- 新增庫存表單 ----
    with st.expander("➕ 新增 / 更新庫存", expanded=False):
        with st.form("add_holding_form", clear_on_submit=True):
            c = st.columns([2, 1, 1, 1])
            h_sym = c[0].text_input("代號", placeholder="如 NVDA / 2330")
            h_mkt = c[1].selectbox("市場", ["US", "TW"])
            h_shares = c[2].number_input("股數", min_value=0.0, step=1.0, value=0.0)
            h_cost = c[3].number_input("平均成本", min_value=0.0, step=1.0, value=0.0)
            submitted = st.form_submit_button("加入庫存")
        if submitted and h_sym.strip() and h_shares > 0:
            sym_u = h_sym.strip().upper()
            probe = _spot_price(sym_u, h_mkt)
            if probe != probe:  # NaN → 抓不到
                st.error(f"抓不到 {sym_u}（{h_mkt}）的報價，請確認代號與市場。")
            elif add_holding(sym_u, h_mkt, h_shares, h_cost):
                st.success(f"已加入/更新 {sym_u}（{h_mkt}）")
                st.cache_data.clear()
                st.rerun()
        elif submitted:
            st.warning("請填入代號與大於 0 的股數。")

    holdings = get_portfolio_holdings()
    if not holdings:
        st.info(
            "尚無庫存。可用上方「➕ 新增庫存」直接輸入，或建立 `portfolio.yaml`。"
            "本工具不會內嵌任何個人財務數字。"
        )
        return

    rows = []
    total_mv = total_cost = 0.0
    for h in holdings:
        px = _spot_price(h["symbol"], h["market"])
        shares, cost = float(h["shares"]), float(h["cost"])
        mv = px * shares
        pl = (px - cost) * shares
        pl_pct = (px / cost - 1) if cost else float("nan")
        if mv == mv:
            total_mv += mv
            total_cost += cost * shares
        rows.append({
            "標的": h["symbol"], "市場": h["market"], "幣別": h.get("currency", ""),
            "股數": shares, "成本": cost, "現價": round(px, 2),
            "市值": round(mv, 0), "損益": round(pl, 0),
            "報酬率": f"{pl_pct:+.1%}" if pl_pct == pl_pct else "—",
        })
    df = pd.DataFrame(rows)

    # 總覽指標
    if total_cost > 0:
        tot_pl = total_mv - total_cost
        m = st.columns(3)
        m[0].metric("總市值", f"{total_mv:,.0f}")
        m[1].metric("總損益", f"{tot_pl:,.0f}", f"{tot_pl / total_cost:+.1%}")
        m[2].metric("持股檔數", len(df))
        st.caption("⚠ 不同幣別未換匯，總計僅供概略參考。")

    st.dataframe(df, use_container_width=True, hide_index=True)

    # 配置比例（接在表格下方，避免被其他區塊擠壓）
    if not df.empty:
        alloc = df.groupby("標的")["市值"].sum()
        fig = go.Figure(data=[go.Pie(labels=alloc.index, values=alloc.values, hole=0.4)])
        fig.update_layout(
            height=340, margin=dict(l=10, r=10, t=46, b=10),
            title=dict(text="持股市值配置", y=0.97),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- 移除庫存（放最底，避免蓋住上方配置圖）----
    with st.expander("🗑 移除庫存", expanded=False):
        for h in holdings:
            col_a, col_b = st.columns([3, 1])
            col_a.write(f"{h['symbol']}（{h['market']}）{h['shares']} 股")
            if col_b.button("移除", key=f"rmh_{h['symbol']}_{h['market']}"):
                remove_holding(h["symbol"], h["market"])
                st.cache_data.clear()
                st.rerun()


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
# 版面
# --------------------------------------------------------------------------- #
st.title("📊 StockBot 看盤儀表板")
st.caption("技術指標訊號輔助 + 回測。僅供參考，不構成投資建議，不自動下單。")

options = _watch_options()
with st.sidebar:
    st.header("設定")
    label = st.selectbox("選擇標的", list(options.keys()))

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

    # ---- 回測長度 / K線週期（全域：影響 K線/訊號/回測）----
    d = cfg["data"]
    p_idx = PERIOD_OPTIONS.index(d["period"]) if d["period"] in PERIOD_OPTIONS else PERIOD_OPTIONS.index("2y")
    i_idx = INTERVAL_OPTIONS.index(d["interval"]) if d["interval"] in INTERVAL_OPTIONS else 0
    d["period"] = st.selectbox(
        "回測長度", PERIOD_OPTIONS, index=p_idx,
        help="抓多久的歷史資料來畫圖與回測，也決定「買進持有對照」抱多久。越長樣本越足（建議 ≥2 年）。",
    )
    d["interval"] = st.selectbox(
        "K線週期", INTERVAL_OPTIONS, index=i_idx,
        format_func=lambda x: INTERVAL_LABELS.get(x, x),
        help="K 線與訊號的時間單位。台股不支援盤中資料，故僅提供日／週／月線。",
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
            elif add_symbol(sym_u, new_mkt, new_name.strip() or None):
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

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["K線+指標", "當前訊號", "回測績效", "投資組合", "策略說明"]
)
with tab1:
    panel_chart(df, label)
with tab2:
    panel_signals()
with tab3:
    panel_backtest(df, item, label)
with tab4:
    panel_portfolio()
with tab5:
    panel_strategy_info()
