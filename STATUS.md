# STATUS — 從這裡接續

> 開新工作階段先看這份：現在做到哪、下一步做什麼、怎麼跑起來。
> 最後更新：**2026-06-01**。完整歷史見 [`docs/DEVLOG.md`](docs/DEVLOG.md)。

---

## 一句話現況

**v1（規則型）已完成可用**：4 支策略 + 5 面板 Streamlit 儀表板 + 自寫回測，全部離線測試通過。
尚未做：訊號通知、v2 ML 策略。

## 快速啟動 / 驗證

**一鍵**：雙擊 `啟動儀表板.bat`——首次自動建 venv + 裝套件，之後直接開（`requirements.txt` 變動會自動重裝）。

```powershell
# 手動啟動儀表板
.venv\Scripts\streamlit run dashboard/app.py

# 跑測試（改完 code 先跑這個）
.venv\Scripts\python.exe -m tests.run_all --offline   # 離線
.venv\Scripts\python.exe -m tests.run_all             # 含連網
```

## 已完成（重點）

- 資料層 / 指標層（純 pandas）/ 回測（next-bar，防未來資料）/ 5 面板儀表板 / 測試套件。
- **4 支策略**：`ema_macd_rsi`（順勢）、`fibonacci`（順勢低接，已放寬為 0.5–0.618 區間）、
  `golden_cross`（長期 50/200 金叉）、`bollinger`（震盪市均值回歸）。
- 儀表板可選「回測長度 / K線週期」；年化基準依週期套用（修掉寫死 252）。
- 文件重整：PROJECT/README/STATUS 留 root，TECHNICAL/DEVLOG/研究報告移入 `docs/`。
- **一鍵啟動含環境建置**：`啟動儀表板.bat` 自我修復（偵測 Python→建 venv→依 `requirements.lock` 判斷是否裝套件→啟動）；移除未使用的 `backtesting` 依賴。

## 下一步（待辦）

### A. 待驗證 / 小修（優先）
- [ ] **目視驗證 UI**：K線子標題與頂部工具列分離、投組配置圓餅位置（這次調了版面但未啟動畫面確認）。
- [ ] **記住選到的標的**：selectbox 加固定 `key` + 用 `st.query_params`（如 `?symbol=NVDA`）存選擇，連瀏覽器 F5 都能還原（現在 F5＝新 session 會跳回第一個 0050）。

### B. 功能（v1 收尾）
- [ ] **投組庫存統一編輯**：改用 `st.data_editor`（dynamic rows）把新增/修改/刪除合到同一張表，存回 `user_portfolio.json`；`portfolio.yaml` 改為初始匯入種子。根治「`portfolio.yaml` 來源的持股按移除無效」（`remove_holding` 只動 user json）。
- [ ] **盤中 30/60 分線（Yahoo / yfinance）**：US 與 TW 共用 yfinance，且**已接好**（非日線自動退回 yfinance）。要補：interval 選單加 30m/60m、**期間依週期自動夾制**（實測 30m≤60 天、60m≤2 年）、`periods_per_year` 補 30m/60m（台股盤中每天 5 根、美股 ~7 根，需分開）、上櫃改 `.TWO`、盤中快取 TTL 縮短。⚠ Yahoo 為**延遲 ~15 分**、非真即時。選用：VWAP 改「每日重置累積版」。
- [ ] **訊號通知**：選定管道並實作 `Notifier`（Discord Webhook 最簡單）。`notify/base.py` 介面已備。
- [ ] 依回測再調策略參數（Fibonacci 區間、EMA 週期、ATR 倍數）或加趨勢濾網。

### C. 進階資料源 / 看盤（選用）
- [ ] **TWSE MIS 即時現價**：近即時快照（秒級）→ 做「部位即時市值 / 現價標籤」，接 dashboard `_spot_price`，純顯示 + `st.fragment` 自動刷新；需判斷上市(`tse_`)/上櫃(`otc_`)。屬附加層，**不動 bar 管線**。
- [ ] **真即時來源**（需帳號，做成可選後端，沒金鑰退回現狀）：台股 **Shioaji**（逐筆 push）、美股 **Alpaca(IEX 免費) / Finnhub**。
- [ ] （可選）手畫線保存、`lightweight-charts` + WebSocket 進階看盤。

### D. v2 / 雜項
- [ ] **v2 ML**：先 XGBoost/RandomForest（輕量可解釋），沿用同一 `Strategy` 介面，嚴守時間序列驗證。
- [ ] （未進版控）需要時 `git init` 建基準，之後才能用 `/code-review`。

> 資料源即時性備忘：**券商(逐筆即時 push) > TWSE MIS(秒級快照、poll、限速) >> yfinance/Yahoo(延遲 ~15–20 分)**。即時與否由「交易所授權等級 + 推/拉模式」決定。

## 開發約定（務必遵守）

- **只用專案 venv**：`.venv\Scripts\python.exe`（系統 python 無科學套件，機器無 conda）。
- **嚴防 look-ahead**：指標/訊號/回測只能用當下與過去 K 線。
- **驗證靠檔案不靠 stdout**：本機工具 stdout 可能重播舊輸出 → 把結果寫到新檔再讀、並看 exit code。
- **操作範圍僅限 `D:\CODE\StockBot`**；越界或改環境變數須先問使用者。

## 新增策略（兩步）

1. 在 `strategy/` 繼承 `Strategy`、設 `name`/`DESCRIPTION`、實作 `generate()`（**務必產生 `reason`**）。
2. 在 `core.py` 的 `STRATEGY_REGISTRY` 與 `STRATEGY_LABELS` 登記；並到 `tests/` 補測試（記得也加進 `tests/run_all.py`）。

詳見 [`docs/TECHNICAL.md`](docs/TECHNICAL.md)。
