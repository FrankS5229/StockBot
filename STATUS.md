# STATUS — 從這裡接續

> 開新工作階段先看這份：現在做到哪、下一步做什麼、怎麼跑起來。
> 最後更新：**2026-06-02**。完整歷史見 [`docs/DEVLOG.md`](docs/DEVLOG.md)。

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
- **已上 GitHub**：`ShenBYFrank/StockBot`（分支 `main`）。安全把關：`.venv`/個資/`StockBot.zip`/`docs/research` 皆未上傳；個人財務研究報告曾誤入歷史，已用 force-push 壓成單一乾淨 commit 清除。

## 下一步（待辦）

### A. 待驗證 / 小修（優先）
- [x] **目視驗證 UI** ✅：使用者確認 K線標題與投組新版正常（2026-06-02）。
- [x] **記住選到的標的** ✅：selectbox 加 `key="sel_symbol"` + `st.query_params`（`?symbol=`），F5 可還原（2026-06-02）。

### B. 功能（v1 收尾）
- [x] **投組庫存統一編輯** ✅：`st.data_editor`（dynamic rows）三合一（新增/改/刪）+「💾 儲存」寫回 `user_portfolio.json`；`get_portfolio_holdings` 改為「user json 非空則以它為準，否則用 portfolio.yaml 種子」，根治刪不掉（2026-06-02）。
- [x] **盤中 30/60 分線（Yahoo / yfinance）** ✅（2026-06-02）：interval 選單加 30/60 分；回測長度依週期動態夾制（30 分→5d/1mo、60 分→1mo~2y）；年化 `_periods_per_year(interval, market)` 依市場分（台股盤中每天 30分9/60分5 根、美股 13/7）；`_fetch_yfinance` 台股 `.TW`→`.TWO` 退回（上櫃）；盤中快取 15 分。⚠ Yahoo 延遲 ~15 分、非真即時。**選用未做**：VWAP 改每日重置累積版。
- [ ] **訊號通知**：選定管道並實作 `Notifier`（Discord Webhook 最簡單）。`notify/base.py` 介面已備。
- [x] **依回測調策略參數** ✅（2026-06-02，5y 日線 10 檔掃參）：ema_macd_rsi RSI 進場帶 50-70→**45-75**（Sharpe 中位 0.601→0.657、年化 0.096→0.11）；fibonacci 進場區間 0.5→**0.382**-0.618（Sharpe 0.5→0.741、年化 0.146→0.176、交易 138→203）。**發現**：①趨勢濾網 close>SMA200 反而變差→不用；②EMA 週期 5/20≈20/50 差距小→維持；③`atr_stop_mult`/`reward_risk_ratio` 只是顯示建議、**不入回測**（回測只依 buy/sell 訊號）。
- [x] **投組刪改即時連動** ✅（2026-06-02）：根因是「存空清單被當 falsy → 退回 yaml 種子」；`get_portfolio_holdings` 改以**檔案存在**判斷，全刪存空也成立；存檔後 `cache_data.clear()`+`rerun` 重算市值/損益。測試補「全刪不復活」斷言。
- [x] **投組列排序** ✅（2026-06-02）：`st.data_editor` 加「排序」數字欄，存檔依值重排並持久化（Streamlit data_editor 無原生滑鼠拖曳，採數字排序為等效解；如要真拖曳需加 `streamlit-sortables` 元件）。
- [x] **投組類別 filter** ✅（2026-06-02）：估值明細上方加類別多選；篩選連動估值表 / 總市值損益 / 類別小計圓餅。

### C. 進階資料源 / 看盤（選用）
- [ ] **TWSE MIS 即時現價**：近即時快照（秒級）→ 做「部位即時市值 / 現價標籤」，接 dashboard `_spot_price`，純顯示 + `st.fragment` 自動刷新；需判斷上市(`tse_`)/上櫃(`otc_`)。屬附加層，**不動 bar 管線**。
- [ ] **真即時來源**（需帳號，做成可選後端，沒金鑰退回現狀）：台股 **Shioaji**（逐筆 push）、美股 **Alpaca(IEX 免費) / Finnhub**。
- [ ] （可選）手畫線保存、`lightweight-charts` + WebSocket 進階看盤。

### D. v2 / 雜項
- [ ] **v2 ML**：先 XGBoost/RandomForest（輕量可解釋），沿用同一 `Strategy` 介面，嚴守時間序列驗證。
- [x] ~~git init / 上 GitHub~~ ✅（已完成；`/code-review` 現在可用）。

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
