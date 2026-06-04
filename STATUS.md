# STATUS — 從這裡接續

> 開新工作階段先看這份：現在做到哪、下一步做什麼、怎麼跑起來。
> 最後更新：**2026-06-05**。完整歷史見 [`docs/DEVLOG.md`](docs/DEVLOG.md)。

---

## 一句話現況

**v1（規則型）已收尾**：4 支策略 + 6 面板 Streamlit 儀表板 + 自寫回測 + 投組跨幣別換算，全部離線/連網測試通過、已推上 GitHub。
**2026-06-05 完成一輪 review 修補 + 新增「🎯 目標價」前瞻引擎**（技術價位＋GBM 統計投影，輸出區間＋機率）、K 線常駐三態訊號徽章、手畫工具收圖角 popover、回測樣本外(OOS)對照。
下一階段 **v2**：訊號通知、進階即時資料源、進階看盤、ML 策略（見下方「v2 待辦」）。

## 快速啟動 / 驗證

**一鍵**：Windows 雙擊 `啟動儀表板.bat`；macOS 對 `啟動儀表板.command` 右鍵→打開——首次自動建 venv + 裝套件，之後直接開（`requirements.txt` 變動會自動重裝）。

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

## v1 已完成（收尾於 2026-06-03）

> 以下為 v1 範圍內的全部項目，均已完成並推上 GitHub。歷史細節見 [`docs/DEVLOG.md`](docs/DEVLOG.md)。

- [x] **目視驗證 UI**（2026-06-02）：K線標題與投組新版正常。
- [x] **記住選到的標的**（2026-06-02）：selectbox `key="sel_symbol"` + `st.query_params`（`?symbol=`），F5 可還原。
- [x] **投組庫存統一編輯**（2026-06-02）：`st.data_editor`（dynamic rows）三合一（新增/改/刪）+「💾 儲存」寫回 `user_portfolio.json`。
- [x] **投組刪改即時連動**（2026-06-02）：根因「存空清單被當 falsy → 退回 yaml 種子」；`get_portfolio_holdings` 改以**檔案存在**判斷，全刪存空也成立；存檔後重算市值/損益。測試補「全刪不復活」斷言。
- [x] **投組列排序**（2026-06-02）：data_editor 加「排序」數字欄，存檔依值重排並持久化。
- [x] **投組類別 filter**（2026-06-02）：估值明細上方加類別多選，連動估值表 / 總市值損益 / 類別小計圓餅。
- [x] **投組跨幣別換算**（2026-06-02）：`_usdtwd_rate()`（Yahoo `TWD=X`，快取 1 小時），以 **TWD 為基準**換算後加總；估值表保留「市值(原幣)/市值TWD」兩欄；抓不到匯率退回原幣混算並警告。
- [x] **盤中 30/60 分線**（2026-06-02）：interval 選單加 30/60 分；回測長度依週期動態夾制；年化 `_periods_per_year(interval, market)` 依市場分；`.TW`→`.TWO` 退回；盤中快取 15 分。⚠ Yahoo 延遲 ~15 分。
- [x] **依回測調策略參數**（2026-06-02，5y 日線 10 檔掃參）：ema_macd_rsi RSI 進場帶 50-70→**45-75**；fibonacci 進場區間 0.5→**0.382**-0.618。發現：趨勢濾網 close>SMA200 反而變差→不用；`atr_stop_mult`/`reward_risk_ratio` 僅顯示、不入回測。
- [x] ~~git init / 上 GitHub~~（`ShenBYFrank/StockBot`，`/code-review` 可用）。

---

## v2 待辦（下一階段）

> v1 之後的「新增能力 / 新外部依賴」集中於此。優先序由上而下，可獨立挑做。

### ✅ 已完成計畫（2026-06-05，計畫檔：`polished-coalescing-unicorn`）

四件一起做、依序完成並全測試通過：
- [x] **Step1 低風險 review 修補**：移除 `ta.py` 無效 f-string、移除 `obv` 死碼、FinMind 登入失敗改記警告、Sharpe 文字校正（含空手期間）。
- [x] **Step2 去全域 cfg 耦合**：`core.analyze_symbol/latest_signal/get_strategy` 加顯式 `strategy/interval/period` 覆寫，`_analyze` 變純函式（向後相容）。
- [x] **Step3 目標價引擎**（核心新功能）：新增 `targets.py`（Pivot／Fibonacci 擴展／量度移動／通道 技術價位 ＋ GBM 漂移波動統計投影 ＋ 達成機率），dashboard 新增「🎯 目標價」第 4 分頁，分短/長線、輸出**區間＋機率**、前瞻投影帶、誠實註記。前瞻式、與策略 buy/sell 解耦。
- [x] **Step4 UI**：手畫控制列收進圖角 `st.popover`（streamlit≥1.32，實測 1.58）；K 線上方常駐**三態訊號徽章**（買/賣/觀望，依最後一根 signal 亮/暗，歷史箭頭保留）。
- [x] **Step5 收尾修補**：回測接上樣本外 IS/OOS 對照 checkbox、`panel_signals` 改 `@st.fragment`＋局部刷新、新增防 look-ahead 回歸測試（4 策略）。
- [x] **QA/QT**：新增 `tests/test_targets.py`（5 測）；`run_all` 離線＋連網皆 ALL_TESTS_PASSED；Streamlit `AppTest` 跑整個 app.py 無例外（SMOKE_OK）。

完整公式與運算機制（Pivot/Fib 擴展/量度移動 70-120%/GBM `S0·exp((μ−0.5σ²)H ± z·σ√H)`、達成機率 `Φ(·)`）見計畫檔與 `docs/TECHNICAL.md`。

### A. UI 改版（4 項）✅ 2026-06-03 完成（詳見 `docs/DEVLOG.md`）
- [x] **當前訊號涵蓋投組**：`_signal_universe()` = 觀察清單 ∪ 投組庫存（去重）；只在「當前訊號」tab。
- [x] **當前訊號類別子 tab**：依「類別」分子 tab（`st.tabs(["全部", …類別])`）；`add_symbol` 加 `category`、新增標的表單加類別欄；共用 `_category_of()`。
- [x] **K線手畫工具**：一鍵清除（`draw_nonce`→改 `plotly_chart` key 重掛）＋自訂顏色（`newshape.line.color`，僅影響之後新畫的線）。
- [x] **投組估值表多重篩選**：市場 / 類別 / 代號 / 關鍵字，累積套用、下游總計/圓餅連動。
- [x] **K線手畫控制列版面**（2026-06-05）：「畫線顏色」＋「清除手畫線」已收進標題列右側 `st.popover("🎨 手畫工具")`，與 K 線圖融合，不再佔版面。

### B. 訊號通知
- [ ] **訊號通知**：選定管道並實作 `Notifier`（**Discord Webhook 最簡單**）。`notify/base.py` 介面已備、`ConsoleNotifier` 已有。範圍：策略產生 buy/sell 時推播（標的 / 訊號 / 理由 / 價格）；webhook URL 走設定檔或環境變數、不入 git。

### C. 進階即時資料源 / 看盤
- [ ] **TWSE MIS 即時現價**：近即時快照（秒級）→「部位即時市值 / 現價標籤」，接 dashboard `_spot_price`，純顯示 + `st.fragment` 自動刷新；需判斷上市(`tse_`)/上櫃(`otc_`)。附加層，**不動 bar 管線**。
- [ ] **真即時來源**（需帳號，做成可選後端，沒金鑰退回現狀）：台股 **Shioaji**（逐筆 push）、美股 **Alpaca(IEX 免費) / Finnhub**。
- [ ] （可選）手畫線保存、`lightweight-charts` + WebSocket 進階看盤。

### D. ML 策略
- [ ] **v2 ML**：先 XGBoost/RandomForest（輕量可解釋），沿用同一 `Strategy` 介面，嚴守時間序列驗證（walk-forward、無未來資料）。

### 選用 / 備忘
- VWAP 改「每日重置累積版」（盤中線更貼近實務）。
- 資料源即時性：**券商(逐筆即時 push) > TWSE MIS(秒級快照、poll、限速) >> yfinance/Yahoo(延遲 ~15–20 分)**。

## 開發約定（務必遵守）

- **只用專案 venv**：`.venv\Scripts\python.exe`（系統 python 無科學套件，機器無 conda）。
- **嚴防 look-ahead**：指標/訊號/回測只能用當下與過去 K 線。
- **驗證靠檔案不靠 stdout**：本機工具 stdout 可能重播舊輸出 → 把結果寫到新檔再讀、並看 exit code。
- **操作範圍僅限 `D:\CODE\StockBot`**；越界或改環境變數須先問使用者。
- **計畫須留痕**：任何計畫經使用者確認後，必須寫入相關 `.md`（STATUS / DEVLOG / TECHNICAL）作為紀錄，再開始實作。
- **實作必做 QA/QT**：每項功能實作完成後，必須做相應的 QA/QT 實驗測試（單元/離線/連網/儀表板目視）驗證後才算完成。
- **結束回頭更新文件**：所有開發結束後，必須回過頭更新 `.md` 裡的紀錄（進度表、決策、技術細節、待辦勾選）。

## 新增策略（兩步）

1. 在 `strategy/` 繼承 `Strategy`、設 `name`/`DESCRIPTION`、實作 `generate()`（**務必產生 `reason`**）。
2. 在 `core.py` 的 `STRATEGY_REGISTRY` 與 `STRATEGY_LABELS` 登記；並到 `tests/` 補測試（記得也加進 `tests/run_all.py`）。

詳見 [`docs/TECHNICAL.md`](docs/TECHNICAL.md)。
