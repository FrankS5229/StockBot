# StockBot 技術參考（TECHNICAL）

> 架構、資料流、各模組職責、指標公式、策略與回測邏輯、擴充指引。
> 開發紀錄見 [`DEVLOG.md`](DEVLOG.md)，定位見 [`PROJECT.md`](../PROJECT.md)，接續進度見 [`STATUS.md`](../STATUS.md)。

---

## 1. 環境

- **Python**：專案 venv `D:\CODE\StockBot\.venv`（Python 3.12）。系統 python 無套件、無 conda。
- **執行一律用**：`.venv\Scripts\python.exe`（或 `啟動儀表板.bat`）。
- **主要套件**：pandas / numpy / yfinance / FinMind / pyarrow / streamlit / plotly / pyyaml / python-dotenv。
- 安裝：`.venv\Scripts\python.exe -m pip install -r requirements.txt`

---

## 2. 架構與資料流

```
config.yaml ─┐
user_watchlist.json ─┤(合併)
             ↓
        core.load_config()
             ↓
  ┌──────────────────────────────────────────────┐
  │ core.analyze_symbol(symbol, market, cfg)      │
  │   1. data.fetchers.get_ohlcv()  → OHLCV       │
  │   2. indicators.ta.add_indicators() → +指標欄 │
  │   3. strategy.generate()  → +signal/reason/停損停利 │
  └──────────────────────────────────────────────┘
             ↓                         ↓
   scanner.py (CLI)          dashboard/app.py (Streamlit)
        ↓                              ↓
   notify.Notifier            backtest.run_backtest() → 績效
```

**設計原則**：`core.py` 是單一事實來源，scanner 與 dashboard 都呼叫它，避免邏輯重複。

---

## 3. 模組職責

| 檔案 | 職責 | 關鍵函式 |
|------|------|---------|
| `data/fetchers.py` | 抓 OHLCV、標準化、快取 | `get_ohlcv(symbol, market, interval, period)` |
| `indicators/ta.py` | 計算技術指標 | `add_indicators(df, cfg)`、各指標單獨函式 |
| `strategy/base.py` | 策略介面 + 訊號資料結構 | `Strategy`(含 `DESCRIPTION`)、`Signal`、`SIGNAL_COLS` |
| `strategy/ema_macd_rsi.py` | EMA+MACD+RSI 順勢動能策略（短中線） | `EmaMacdRsiStrategy.generate(df)` |
| `strategy/fibonacci.py` | Fibonacci 回撤順勢低接策略（短中線） | `FibonacciStrategy.generate(df)` |
| `strategy/golden_cross.py` | 50/200 均線黃金交叉趨勢策略（長期） | `GoldenCrossStrategy.generate(df)` |
| `strategy/bollinger.py` | 布林通道均值回歸策略（震盪盤） | `BollingerStrategy.generate(df)` |
| `backtest/runner.py` | 回測引擎 + 績效 | `run_backtest()`、`split_in_out()`、`METRIC_GLOSSARY` |
| `targets.py` | 前瞻式目標價（技術價位＋GBM 統計投影，含達成機率） | `build_report()`、`plain_summary()`、`gbm_params()`、`prob_terminal()`、`pivot_points/fib_extensions/measured_move/channel_targets()`、`SHORT_SPEC`/`LONG_SPEC` |
| `notify/base.py` | 通知介面 | `Notifier`、`ConsoleNotifier`、`get_notifier()` |
| `core.py` | 共用流程 + watchlist/portfolio 管理 + 策略註冊表 | `load_config`、`analyze_symbol(…, strategy/interval/period 可覆寫)`、`get_strategy(cfg, active=None)`、`add_symbol`/`remove_symbol`、`add_holding`/`remove_holding`/`get_portfolio_holdings`、`STRATEGY_REGISTRY` |
| `scanner.py` | CLI 主流程 | `main()` |
| `dashboard/app.py` | Streamlit 六面板 UI | `panel_chart/signals/backtest/targets/portfolio/strategy_info` |

### 策略註冊表（新增策略只需兩步）
1. 在 `strategy/` 新增繼承 `Strategy` 的類別，設 `name`、`DESCRIPTION`，實作 `generate()`。
2. 在 `core.py` 的 `STRATEGY_REGISTRY` 與 `STRATEGY_LABELS` 登記。
之後側邊欄會自動出現該策略，`config.yaml` 的 `strategy.active` 可設預設。
儀表板 `_analyze()` 把選到的 `strategy/interval/period` **顯式傳入** `analyze_symbol`（同時作為 `@st.cache_data` 的 cache key），切換時自然失效重算，不再依賴就地修改全域 `cfg` 的副作用（2026-06-05 重構）。

### 使用者資料檔（皆 git 忽略）
- `user_watchlist.json`：介面新增的觀察標的（與 config.yaml 合併去重）。
- `user_portfolio.json`：介面新增的庫存（與 portfolio.yaml 合併，user 覆蓋同鍵）。

### user-data 儲存後端（可注入）＋ 無狀態模式（2026-10-09）

`core.py` 把 user data 讀寫抽象成一個可替換的 store，預設 `FileStore`（寫上面兩個 JSON，單機行為不變）：

- 介面：`watchlist_load/save`、`portfolio_load/save`、`portfolio_has_user_data()`。
  後者決定 `get_portfolio_holdings()` 是否退回 `portfolio.yaml` 種子（`FileStore`＝檔案是否存在）。
- `use_store(store)` 可在執行期覆寫 `_USER_STORE`。`core` 本身**不 import streamlit**，CLI/`scanner.py` 無感。

**無狀態（公開試用）模式**由旗標 `STOCKBOT_STATELESS` 開啟（環境變數優先，其次 `st.secrets`）：
`dashboard/app.py` 注入 `SessionStore`，user data 改存 `st.session_state` —— 每個瀏覽器分頁各自獨立、
重整（新 session）即歸零、完全不寫磁碟；`portfolio_has_user_data()` 恆為 `True` → 投組初始**完全空白、不吃 yaml 種子**。
本機不設旗標即維持 `FileStore`（寫檔記憶）。部署細節見 [`DEPLOY.md`](DEPLOY.md)。

**手機版面**：`?m=1` 或側欄 toggle 設 `MOBILE`；`layout_cols()` 於手機回傳垂直堆疊的 `st.container()`
取代 `st.columns()`，並下修圖高、精簡投組明細欄位。

---

## 4. 資料層細節

- **標準化輸出**：DatetimeIndex（升冪、去重）+ 欄位 `open/high/low/close/volume`，全轉數值。
- **路由**：`market="US"` → yfinance；`market="TW"` 日線 → FinMind，失敗或**盤中（30m/60m）** → yfinance。
- **台股代號後綴**：yfinance 對台股先試上市 `.TW`，抓不到再試上櫃 `.TWO`（OTC）。⚠ 上櫃股第一次試 `.TW` 會在 console 印 404 警告（正常，隨即由 `.TWO` 成功）。
- **盤中資料（yfinance/Yahoo）**：延遲約 15 分、非真即時；史料上限 **30m ≤ ~60 天、60m ≤ ~2 年**（儀表板的「回測長度」選單已依週期夾制）。
- **FinMind 重複欄位**：回傳會有重複 `close`，以 `~columns.duplicated()` 去重。
- **快取**：`data/cache/{market}_{symbol}_{interval}_{period}.parquet`。日/週/月線**當日有效**；**盤中（`_is_intraday`）改 15 分鐘失效**。無 pyarrow 時退回 csv。
- **台股 token**：建議 `.env` 設 `FINMIND_TOKEN`；未設時免費額度有限，fallback 會 `warnings.warn`。

---

## 5. 指標公式（純 pandas 實作，皆只用當下與過去資料）

| 指標 | 公式重點 | 函式 |
|------|---------|------|
| EMA | `series.ewm(span=N, adjust=False).mean()` | `ema(series, span)` |
| MACD | DIF=EMA_fast−EMA_slow；DEA=EMA(DIF, signal)；HIST=DIF−DEA | `macd(close, fast, slow, signal)` |
| RSI | Wilder 平滑：`ewm(alpha=1/period)`；`RSI=100−100/(1+RS)` | `rsi(close, period)` |
| 布林 | 中軌=SMA(N)；上下=中軌±k·std(ddof=0)；width=(上−下)/中 | `bbands(close, length, std)` |
| ATR | TR=max(H−L, |H−prevC|, |L−prevC|)；Wilder 平滑 | `atr(high, low, close, period)` |
| VWAP | **滾動近似**：N 日 Σ(典型價×量)/Σ量（日線無盤中，作趨勢濾網用） | `vwap(h,l,c,v,window)` |
| OBV | 漲日+量、跌日−量，累加 | `obv(close, volume)` |

> ⚠ VWAP 為滾動近似版；若日後接盤中資料，應改為「每日重置的累積 VWAP」。

---

## 6. 策略邏輯（EmaMacdRsiStrategy）

**多頭進場 buy（全部成立）**：
1. EMA_fast > EMA_slow（短期多頭排列）
2. close > VWAP（買方占優）
3. MACD 柱由負轉正（動能啟動，**觸發點**）
4. rsi_low ≤ RSI < rsi_high（中性偏多未過熱，預設 50–70）

**出場 sell（任一成立）**：MACD 柱由正轉負｜close < VWAP｜RSI < rsi_low｜EMA_fast < EMA_slow

**停損/停利**（buy 當根 ATR 估算）：
- 停損 = close − `atr_stop_mult` × ATR（預設 1.0）
- 停利 = close + `atr_stop_mult` × ATR × `reward_risk_ratio`（預設 2.0）
- ⚠ 這兩個值**僅供顯示建議**：`run_backtest` 只依 buy/sell 訊號於次根開盤進出、**不掛停損/停利單**，故調 `atr_stop_mult`/`reward_risk_ratio` 不影響回測績效（要納入需在 runner 增加觸價出場邏輯）。

**可解釋性**：`generate()` 同時產生 `reason` 欄（白話列出觸發條件）。`Signal.as_text()` 組成通知/顯示文字。

參數來源：`config.yaml` 的 `indicators` 與 `risk` 區塊。

---

## 7. 回測方法（防 look-ahead）

- **next-bar 執行**：第 t 根的訊號，於第 **t+1 根開盤**成交（不可能用到未來）。
- **成本**：單邊 `commission + slippage`，買進×(1+cost)、賣出×(1−cost)。台股/美股手續費見 config。
- **long-only**：buy 進場、sell 出場，期末強制平倉。
- **績效**：總報酬、年化、Sharpe（年化）、最大回撤、勝率、盈虧比、交易次數 + 淨值曲線 + 交易明細。
- **樣本外**：`split_in_out(df, ratio)` 時間序列切分（前 ratio 為 in-sample）。
- 指標白話：`METRIC_GLOSSARY` 供儀表板 tooltip。
- **Sharpe 定義說明（2026-06-05）**：以整段淨值序列計算，含空手期間（資金閒置報酬視為 0），故為「整體資金 Sharpe」，空手越久數字越保守，非僅統計持倉期間。`METRIC_GLOSSARY` tooltip 已載明。

---

## 7b. 目標價引擎（`targets.py`，2026-06-05）

**定位**：前瞻式價格情境，與策略 buy/sell **解耦**（策略是事後標註進出場，這裡是從當下往前看）。
只用當下與過去 K 棒（無 look-ahead）。分短/長線兩個 horizon（以 K 棒根數計）：`SHORT_SPEC`（10 根）、`LONG_SPEC`（120 根，預設零漂移較保守）。

**技術價位法**（規則明確、可解釋）：
- **Pivot Points（古典）**：`P=(H+L+C)/3`；`R1=2P−L, R2=P+(H−L), R3=H+2(P−L)`，`S1/S2/S3` 對稱。H/L/C 取最近 `pivot_window` 根聚合。
- **Fibonacci 擴展**：自近 `fib_lookback` 根的波段低點往上投影，目標 `= swing_low + (swing_high−swing_low)×ext`，`ext∈{1.272,1.618,2.618}`。
- **量度移動**：以近 `pole_window` 根波段幅度 pole 自現價投影 `spot+pole×{0.7,1.0,1.2}` → 保守/基準/樂觀。
- **通道**：Bollinger 上軌/中軌（重用既有欄位）＋ Donchian `donchian_n` 日高。

**統計投影法（GBM）**：由對數報酬 `r=ln(close/close.shift(1))` 估每根 `μ=mean(r)`、`σ=std(r)`（`zero_drift=True` 時 μ=0）。
- 中位 `S0·exp((μ−½σ²)H)`、期望 `S0·exp(μH)`。
- 信賴區間 `S0·exp((μ−½σ²)H ± z·σ√H)`，70%→z=1.0364、90%→z=1.6449。
- **達成機率（串接兩法的關鍵）**：對任一目標價 T，`P(S_H≥T)=Φ((ln(S0/T)+(μ−½σ²)H)/(σ√H))`（`down` 方向取補數）。Φ 用 `math.erf` 實作（免 scipy）。
- 每條技術目標價都會被算出「H 根後期末收在其上/其下」的機率 → UI 輸出「區間＋機率」。

**輸出**：`TargetReport`（統計帶 median/mean/low70/high70/low90/high90 + `levels: list[TargetLevel]` + 彙整保守/基準/樂觀）。`plain_summary(rep)` 把整份濃縮成一句白話結論。
儀表板第 4 分頁「🎯 目標價」：**一句話結論（恆在最上方）** + 三檔目標（保守/基準/樂觀）+ 風險區間；另有 **簡易/進階** 切換——進階才展開前瞻投影錐＋完整技術目標表（含達成機率）＋誠實註記（GBM 假設、過去≠未來、長線無基本面錨）。**讀法**：保守上檔＝第一停利目標、樂觀＝順勢想像、基準＝中性參考、達成機率＝篩掉不切實際的目標、70% 區間＝近期風險範圍；不是擇一，是分工。

---

## 8. 設定檔

- **config.yaml**：`watchlist`、`data`（interval/period/cache_dir）、`indicators`、`risk`、`backtest`。
- **user_watchlist.json**：介面新增的標的（與 config 合併、去重；內建不可由介面刪）。git 忽略。
- **portfolio.yaml**（使用者自建，範本 `portfolio.yaml.example`）：持股 holdings + cash。git 忽略。
- **.env**（範本 `.env.example`）：`FINMIND_TOKEN` 等金鑰。git 忽略。

---

## 9. 執行方式

```powershell
# 儀表板（主要）
.venv\Scripts\streamlit run dashboard/app.py      # 或雙擊 啟動儀表板.bat

# CLI 掃描
.venv\Scripts\python.exe scanner.py [--only-signals]

# 測試
.venv\Scripts\python.exe -m tests.run_all [--offline]
```

### 一鍵啟動腳本（`啟動儀表板.bat`）

自我修復的 bootstrap，雙擊即可從零到開啟（前提：系統已裝 Python 3.10+）：
1. `where python` 偵測 + `sys.version_info>=(3,10)` 版本檢查；
2. 無 `.venv` 則 `python -m venv .venv`；
3. **依賴變動才安裝**：以 `fc /b` 比對 `requirements.txt` 與 `.venv\requirements.lock`，
   不同（或首次無 lock）才 `pip install -r requirements.txt`，裝完把 requirements.txt 複製成 lock；
4. `streamlit run dashboard/app.py --server.port 8501`。

> `requirements.lock` 放在 `.venv\` 內（隨 venv 一起，git 忽略）；刪掉 `.venv` 重跑即會重新建置。
> 刻意不打包成 exe / 內嵌 Python（見 DEVLOG 決策 #4）。

---

## 10. 擴充指引

### 新增技術指標
在 `indicators/ta.py` 加單獨函式，並在 `add_indicators()` 內掛上欄位；於 `tests/test_indicators.py` 補測試。

### 新增策略
繼承 `strategy/base.Strategy`，實作 `generate(df)` 回傳含 `SIGNAL_COLS`（signal/reason/stop_loss/take_profit）的 DataFrame；
在 `core.get_strategy()` 加選擇邏輯。**務必產生 `reason`**（專案核心：可解釋）。

### 新增通知管道
繼承 `notify/base.Notifier`，實作 `send(text)`；在 `get_notifier()` 註冊名稱；金鑰放 `.env`。
scanner/dashboard 透過介面呼叫，無需改動。

### ML 策略（v2）
在 `strategy/` 新增 ML 策略類別，沿用同一介面。**嚴守**：
- 時間序列切分（滾動窗口/留出），禁止隨機 shuffle。
- 特徵只用當下與過去；標籤為未來有限期間。
- 注意推論延遲（XGBoost/RF 快；LSTM/Transformer 需 GPU 或最佳化）。

---

## 11. 已知限制

- VWAP 為**滾動近似**，非標準盤中累積版；改用 30/60 分線時 VWAP 意義更接近盤中但仍是近似（待辦：每日重置累積版）。
- 回測為 long-only、單標的、全倉進出（未做部位大小/多標的組合）。
- 台股資料品質依賴 FinMind token；免 token 額度有限。
- 第一版策略為 baseline，未必優於買進持有，需調參。
- 手畫線（Plotly 工具列）重整後不保存。
- **「買進持有對照」= 整段回測期間抱滿**（第一根買、最後一根賣），期間長度由 `data.period` 決定；**儀表板側邊欄已可直接調整「回測長度」與「K線週期」**（2026-06-01），改 yaml 為備用方式。
- **年化基準依週期+市場套用**：儀表板 `_periods_per_year(interval, market)`（日 252／週 52／月 12；盤中：台股 30分9/60分5 根·美股 13/7，乘交易日）推算 `periods_per_year` 傳給 `run_backtest`，取代先前寫死 252。⚠ 盤中年化/Sharpe 本質噪音大（短窗放大），僅供參考。`runner.py` 預設仍為 252。
- **Fibonacci 進場區間演進**：0.618±2% 單線 →（2026-06-01）0.5–0.618 →（2026-06-02 掃參）**0.382–0.618**；下界放寬到 0.382（較淺回撤）後 5y/10 檔 Sharpe 中位 0.5→0.741、年化 0.146→0.176、交易 138→203。區間與緩衝由 `config.yaml` 的 `entry_low`/`entry_high`/`tolerance` 控制。回測期間建議 3–5 年以取得更足樣本。
- **ema_macd_rsi RSI 進場帶**：50–70 →（2026-06-02 掃參）**45–75**（`risk.rsi_entry_low`/`rsi_entry_high`），Sharpe 中位 0.601→0.657、年化 0.096→0.11。另測「close>SMA200 趨勢濾網」反而變差（Sharpe→0.447）故未採用。
