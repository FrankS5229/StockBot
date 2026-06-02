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
| `notify/base.py` | 通知介面 | `Notifier`、`ConsoleNotifier`、`get_notifier()` |
| `core.py` | 共用流程 + watchlist/portfolio 管理 + 策略註冊表 | `load_config`、`analyze_symbol`、`get_strategy`、`add_symbol`/`remove_symbol`、`add_holding`/`remove_holding`/`get_portfolio_holdings`、`STRATEGY_REGISTRY` |
| `scanner.py` | CLI 主流程 | `main()` |
| `dashboard/app.py` | Streamlit 五面板 UI | `panel_chart/signals/backtest/portfolio/strategy_info` |

### 策略註冊表（新增策略只需兩步）
1. 在 `strategy/` 新增繼承 `Strategy` 的類別，設 `name`、`DESCRIPTION`，實作 `generate()`。
2. 在 `core.py` 的 `STRATEGY_REGISTRY` 與 `STRATEGY_LABELS` 登記。
之後側邊欄會自動出現該策略，`config.yaml` 的 `strategy.active` 可設預設。
儀表板靠把選到的策略名寫入 `cfg["strategy"]["active"]` 達成全域切換（K線/訊號/回測同源）。

### 使用者資料檔（皆 git 忽略）
- `user_watchlist.json`：介面新增的觀察標的（與 config.yaml 合併去重）。
- `user_portfolio.json`：介面新增的庫存（與 portfolio.yaml 合併，user 覆蓋同鍵）。

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
