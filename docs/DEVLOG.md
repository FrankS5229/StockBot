# StockBot 開發紀錄（DEVLOG）

> 記錄開發過程、決策、踩過的坑。技術細節另見 [`TECHNICAL.md`](TECHNICAL.md)，
> 專案定位與範圍見 [`PROJECT.md`](../PROJECT.md)，接續進度見 [`STATUS.md`](../STATUS.md)。

---

## 進度總覽

| 階段 | 狀態 | 說明 |
|------|------|------|
| 規劃與定位 | ✅ | 通用選股工具，不綁個人財務；功能=儀表板+回測+(延後)通知；不自動下單 |
| 資料層 | ✅ | `data/fetchers.py`：美股 yfinance、台股 FinMind→yfinance fallback、parquet 快取 |
| 指標層 | ✅ | `indicators/ta.py`：純 pandas 自實作 EMA/MACD/RSI/布林/ATR/VWAP（2026-06-05 移除未使用的 OBV） |
| 目標價引擎 | ✅ | `targets.py`：前瞻式價格情境＝技術價位（Pivot/Fib 擴展/量度移動/通道）＋ GBM 統計投影，輸出區間＋達成機率（2026-06-05） |
| 策略層 | ✅ | `strategy/`：可解釋訊號（每個訊號附白話理由）+ ATR 停損停利 |
| 回測層 | ✅ | `backtest/runner.py`：next-bar 執行、含手續費/滑點、防 look-ahead |
| 測試 | ✅ | `tests/`：離線（合成資料）+ 連網，`run_all` 一鍵 |
| 通知 | ⏸ | `notify/base.py` 介面 + ConsoleNotifier；管道未定（已排除 Telegram） |
| 儀表板 | ✅ | `dashboard/app.py`：六面板（K線/訊號/回測/目標價/投組/策略說明），AppTest 端到端無例外 |
| 一鍵啟動 | ✅ | `啟動儀表板.bat`：雙擊即開網頁 |
| 介面加標的 | ✅ | 左側欄「➕ 新增標的」，存 `user_watchlist.json`，免改 yaml |
| 介面加庫存 | ✅ | 投資組合 tab 可新增/移除庫存，存 `user_portfolio.json`，即時報價算損益 |
| 多策略 + 選擇器 | ✅ | 新增 Fibonacci 策略；側邊欄全域切換；策略註冊表於 `core.py` |
| 策略說明 tab | ✅ | 第五分頁，說明「參數 vs 策略」，動態列出各策略 `DESCRIPTION` |
| 長期策略 | ✅ | `strategy/golden_cross.py`：50/200 均線黃金交叉，交易少、對照買進持有（2026-06-01 加入） |
| 回測長度/週期選單 | ✅ | 側邊欄可選回測長度(6mo~max)與 K線週期(日/週/月線)；年化基準依週期套用，修掉寫死 252（2026-06-01） |
| 震盪市策略 | ✅ | `strategy/bollinger.py`：布林通道均值回歸（站回下軌買、回中軌停利/破下軌停損），補順勢策略外的缺口（2026-06-01） |
| 儀表板 UI 修正 | ✅ | K線子標題與頂部圖例/工具列分離；投組「配置圓餅」移到表格下方、移除庫存改置最底（2026-06-01） |

---

## 2026-06-05：四項計畫完成（UI 融合 / review 修補 / 常駐訊號狀態 / 目標價引擎）

> 計畫檔：`polished-coalescing-unicorn`。經整體 review 後一次規劃、依序實作，**已全部完成並通過 QA/QT**
> （`run_all` 離線＋連網 ALL_TESTS_PASSED；Streamlit `AppTest` 跑整個 app.py 無例外 SMOKE_OK）。
> 同時新增三條開發約定（見 `STATUS.md`）：計畫經確認須寫入 `.md` 留痕、實作完必做 QA/QT、開發結束回頭更新 `.md`。

- **Step1 低風險修補**：`ta.py` 無效 f-string、移除 `obv` 死碼、FinMind 登入失敗改記警告、Sharpe 文字校正為「含空手期間的整體資金 Sharpe」。
- **Step2 去全域 cfg 耦合**：`analyze_symbol` 加顯式 `strategy/interval/period` 覆寫，`_analyze` 變純函式（向後相容）。
- **Step3 目標價引擎（核心）**：新增 `targets.py`，**前瞻式**價格情境、與策略 buy/sell 解耦，分短/長線：
  - 技術價位法：Pivot Points（R1-R3/S1-S3）、Fibonacci 擴展（1.272/1.618/2.618）、量度移動（前波幅 70/100/120% → 保守/基準/樂觀）、Bollinger/Donchian 通道。
  - 統計投影法：對數報酬估 μ/σ，GBM 給中位/期望價與 70/90% 信賴區間 `S0·exp((μ−0.5σ²)H ± z·σ√H)`；以 `P(S_H≥T)=Φ((ln(S0/T)+(μ−0.5σ²)H)/(σ√H))` 替每條技術目標價算**達成機率** → 輸出「區間＋機率」。短窗 μ 雜訊大，長線預設零漂移純波動錐。
  - UI：dashboard「🎯 目標價」分頁。**一句話白話結論恆在最上方** + 三檔目標 + 風險區間；**簡易/進階**切換（進階才展開投影錐與完整技術目標表）。`plain_summary()` 產生結論句。
- **Step4 UI**：手畫控制列收進圖角 `st.popover`（streamlit≥1.32）；K 線上方常駐三態訊號徽章（亮=作用中/暗=未作用）。
- **Step5 收尾**：回測接上 IS/OOS 樣本外對照、`panel_signals` 改 `st.fragment`、新增防 look-ahead 回歸測試。

研究來源（目標價運算機制）：AAII、Chart Guys（Fib 擴展）、Morpher/AvaTrade（Pivot）、Warrior Trading/NetPicks（量度移動 70-120%）、GBM/Monte Carlo 投影文獻。

---

## 重要決策

1. **不用 pandas-ta，改純 pandas 自實作指標。**
   原因：`pandas-ta 0.3.14b` 會 `from numpy import NaN`，在 numpy 2.x 直接報錯。
   自實作更穩、數學透明，也利於儀表板做白話解釋。

2. **回測自寫，不用 backtesting.py 的 class API。**
   原因：完全可控、邏輯透明（呼應「可解釋」目標），並能嚴格實作 next-bar 執行避免未來資料。

3. **使用者自訂標的存 JSON，不寫回 config.yaml。**
   原因：避免破壞 config.yaml 的註解與結構；內建標的與使用者標的分離，內建不可被誤刪。

4. **不打包成 exe / 靜態 HTML。**
   - HTML：儀表板需 Python 後端即時抓價、跑回測，靜態 HTML 無法。
   - exe：PyInstaller 打包 Streamlit 易出錯且更肥（300–500MB）。
   - 結論：保留 venv（只裝一次）+ `啟動儀表板.bat` 雙擊啟動，最務實。

5. **通知管道延後。** 已排除 Telegram；LINE Messaging API 因需官方帳號+每月約200則上限+須先取得 userId 不適合自用。候選 Discord Webhook / ntfy.sh / Email。

---

## 踩過的坑（重要，避免重蹈）

### A. 開發環境的工具輸出會「重播舊結果」
這台機器的 PowerShell/部分工具 stdout **會回傳先前指令的舊輸出**，連帶 `Get-Random`/nonce 都被重播，一度導致：
- 誤報「測試全部通過」（其實檔案根本沒寫成功、套件沒裝）
- 誤判「台股資料壞掉」（其實正常）
- 把不存在的 conda 環境當成真的

**對策**：關鍵成敗一律「程式寫結果到帶完成標記的新檔名 → 用 Read 工具讀」，並交叉看 exit code。不可輕信即時 stdout。

### B. Python 環境
系統預設 `python`（`...\Programs\Python\Python312`）**沒有科學套件**，且機器上**沒有 conda**。
→ 一律建立並使用專案 venv：`D:\CODE\StockBot\.venv\Scripts\python.exe`。

### C. FinMind 台股回傳重複 "close" 欄位
`taiwan_stock_daily` 回傳含**重複的 close 欄位**（共 11 欄），直接取會 `float() argument must be ... not 'Series'`。
→ fetcher 以 `df.loc[:, ~df.columns.duplicated()]` 去重。這是台股一開始抓不到的根因。

### D. 台股資料源
FinMind 免 token 額度極少，多打幾次回 EMPTY；yfinance `.TW` 在此環境曾回不合理值。
→ 建議於 `.env` 設 `FINMIND_TOKEN` 取得穩定台股資料；fetcher 在 fallback 時 `warnings.warn` 提醒。

### E. dashboard import 中間狀態造成 NameError
加入 `load_user_watchlist` 等函式時，第一次 import 區塊的 Edit 因含重複行失敗，使用者重整時讀到舊版而報
`NameError: name 'load_user_watchlist' is not defined`。第二次修正後已解；重啟伺服器、瀏覽器重整即可。

### F. 測試合成資料 index 對齊造成整欄 NaN（2026-06-01 發現）
`tests/test_strategy.py` 的 `_trending()` 用「RangeIndex 的 close Series」配「DatetimeIndex 的 DataFrame」，
pandas 自動對齊 → OHLC 整欄變 NaN。後果：ema/fib 的「buy 停損」測試**長期空跑**（一直走「無 buy 訊號跳過」分支），
看似通過其實沒驗到買點邏輯。加 golden_cross 的「必須出現 buy」測試時才暴露。
→ 修法：建立 close 時就帶 `index=idx`。修正後 ema_macd_rsi 才真的測到 buy。
（同時印證 Fibonacci 進場過嚴：修正後它在合成資料仍 0 個 buy。）

---

## 第一版回測基準（2026-05-29 實測，2 年日線）

| 標的 | 策略總報酬 | 年化 | Sharpe | 最大回撤 | 勝率 | 交易 | 買進持有對照 |
|------|-----------|------|--------|---------|------|------|-------------|
| NVDA | −12.7% | −6.6% | −0.51 | −18.3% | 38% | 8 | +88.3% |
| 0050 | +39.7% | +19.0% | 1.62 | −14.7% | 23% | 13 | +156.8% |

解讀：策略落後買進持有屬正常（強多頭中短線頻繁進出會被停損消耗），數字「不漂亮」反而代表
**沒有偷看未來資料**。此為 baseline，後續調參數/加濾網再優化。

---

## 文件對齊與 review（2026-06-01）

把研究文件移到 `md/`，並對齊文件與實作後的盤點：

- **路徑/檔名修正**：`portfolio.yaml copy.example` → `portfolio.yaml.example`；`.gitignore` 補上 `user_portfolio.json`（先前漏列，個人庫存會被誤提交）、私人財務文件路徑改為 `md/financial_strategy_2026.md`。
- **PROJECT.md 追上現況**：結構樹補 `core.py`/`fibonacci.py`/`tests/`/`啟動儀表板.bat`/`user_*.json`；四面板→五面板；技術選型改「純 pandas 自實作 + 自寫回測」並註明原因。
- **review 發現（已記入 TECHNICAL「已知限制」）**：
  - 「買進持有對照」是抱滿整段回測期間（由 `data.period` 決定，目前 2y），且儀表板無 UI 可調期間。
  - 強多頭標的（NVDA/QQQ 等）下短線策略本就難贏 buy & hold（呼應 baseline 實測），**缺一支長期策略**。
  - `run_backtest` 的 `periods_per_year` 寫死 252，改非日線時年化/Sharpe 會錯。
  - Fibonacci 進場條件過嚴（0.618±2% 窄帶），交易次數過少、樣本不足。

> 註：上方「私人財務文件路徑改為 `md/financial_strategy_2026.md`」為當時狀態；後續（見下）已再移至 `docs/research/`。

---

## 文件重整（2026-06-01）

- **文件分層**：`README.md`（使用者導向，已重寫）與 `PROJECT.md`（定位/架構）留 root；新增 `STATUS.md`（接續看板）；
  `TECHNICAL.md`/`DEVLOG.md` 移入 `docs/`；研究報告 `md/` → `docs/research/`，刪掉空的 `md/`。
- **相應路徑更新**：`.gitignore`（財務文件改 `docs/research/...`、加 `*.log`）、三支策略檔註解對研究報告的引用、
  docs 內回連改 `../PROJECT.md`／`../STATUS.md`、PROJECT 結構樹。
- **清理**：刪除殘留暫存檔（`chk_*`/`dbg_*`/`_st.log`）與所有 `__pycache__`。

## 本輪完成（2026-06-01）

- [x] 長期策略 `golden_cross`（50/200 金叉）
- [x] 布林帶策略 `bollinger`（震盪市均值回歸）
- [x] 放寬 Fibonacci 進場為 0.5–0.618 區間（實測 NVDA 11→19、QQQ 0→4 買點）
- [x] 儀表板「回測長度 / K線週期」選單（含 cache key 修正）
- [x] 修 `periods_per_year`（依週期 日252/週52/月12）
- [x] 文件重整 + 暫存清理
- [x] **一鍵啟動含環境建置**：`啟動儀表板.bat` 升級為自我修復 bootstrap（偵測 Python→建 venv→依 `requirements.lock` 判斷是否裝套件→啟動）；移除未使用的 `backtesting` 依賴（不再連帶拉進 bokeh）。決策：維持 venv+bat、不打包 exe / 內嵌 Python（呼應決策 #4）。

---

## A/B 待辦推進（2026-06-02）

- **上 GitHub**：`ShenBYFrank/StockBot`。過程擋掉兩個外洩：`StockBot.zip`（含個資）未上傳；研究報告含個人財務數字曾誤入歷史，已 force-push 壓成單一乾淨 commit 清除。`docs/research/` 整個資料夾改為 git 忽略。
- **A2 記住標的**：selectbox 加 `key="sel_symbol"` + `st.query_params`（`?symbol=`），F5/重開可還原。
- **B1 投組統一編輯**：投組分頁改 `st.data_editor`（dynamic rows）新增/改/刪三合一 +「💾 儲存」寫 `user_portfolio.json`；`get_portfolio_holdings` 改為「user json 非空則以它為準，否則用 `portfolio.yaml` 種子」→ **根治 yaml 來源持股刪不掉**。
- **B2 盤中 30/60 分線**：interval 選單加 30/60 分、回測長度依週期動態夾制、`_periods_per_year(interval, market)` 市場感知、`_fetch_yfinance` 台股 `.TW`→`.TWO` 退回、盤中快取 15 分。實測 US 30m/60m、TW 0050 60m、上櫃 6488/8069（.TWO）皆正常。Yahoo 盤中延遲 ~15 分、非真即時。

---

## B 區收尾：調參 + 投組三項（2026-06-02）

- **B2-調參（數據驅動）**：寫一次性掃參腳本（5y 日線、watchlist 10 檔，跑完即刪）。結論套進 `config.yaml`：
  - ema_macd_rsi RSI 進場帶 `50-70 → 45-75`（Sharpe 中位 0.601→0.657、年化均 0.096→0.11、勝率 0.403→0.419；更激進 40-80 可到 Sharpe 0.707）。
  - fibonacci 進場區間下界 `0.5 → 0.382`（Sharpe 0.5→0.741、年化 0.146→0.176、交易 138→203，樣本更足）。lookback 維持 60（改 90 與此區間合用反而略降）。
  - **重要發現**：①「close>SMA200 趨勢濾網」反而拉低績效（Sharpe 0.601→0.447）→ 不採用；②EMA 週期 5/20 與 20/50 差距很小 → 維持短線 5/20；③`atr_stop_mult`/`reward_risk_ratio` **不入回測**（`run_backtest` 只依 buy/sell 訊號、不掛停損單），僅供顯示建議——調它們對回測無感。config 已加註。
- **投組刪改即時連動（修 bug）**：根因＝「存空清單 `[]` 被當 falsy → `get_portfolio_holdings` 退回 `portfolio.yaml` 種子 → 全刪復活、刪改後市值損益沒變」。改以 **`USER_PORTFOLIO.exists()`** 判斷使用者是否存過（檔案存在即以它為準，空清單也算數）。測試由 `*_merge` 改名 `*_user_priority` 並補「全刪不復活」斷言。
- **投組列排序**：`st.data_editor` 加「排序」數字欄，存檔依值穩定重排並持久化到 json（顯示/圖表都依此序）。Streamlit data_editor 無原生滑鼠拖曳，數字排序為等效解；要真拖曳需另加 `streamlit-sortables` 元件（待辦）。
- **投組類別 filter**：估值明細上方加「類別篩選」多選（預設全選），連動估值表 / 總市值損益 metrics / 類別小計 + 圓餅。

---

## 投組跨幣別換算（2026-06-02）

- **問題**：美股以 USD、台股以 TWD 計價，但總市值/損益與**類別圓餅直接把兩種幣別相加**，比例失真（使用者回報「圓餅上美金台幣計價一樣」）。
- **修法**：新增 `_usdtwd_rate()`（Yahoo `TWD=X`，快取 1 小時）；估值以 **TWD 為基準**換算後才加總——美股市值 × 匯率、台股不變。總市值/總損益/類別小計/圓餅全部改用 `市值TWD`；估值表同時保留「市值(原幣)」與「市值TWD」兩欄，現價/成本維持原幣。
- **退化保護**：匯率抓不到時 `fx_ok=False`，退回原幣混算並顯示警告（不致 crash）。實測匯率 ~31.4 TWD/USD。

---

## v1 收尾 + 待辦轉 v2（2026-06-03）

- **v1（規則型）正式收尾**：A/B 區可執行項全數完成（投組統一編輯、刪改連動、排序、類別 filter、跨幣別換算、盤中 30/60 分線、依回測調參、記住標的、UI 目視驗證）。三個 commit 已推上 `origin/main`。
- **剩餘待辦改列為 v2**：訊號通知（Discord Webhook）、進階即時資料源（TWSE MIS / Shioaji / Alpaca / Finnhub）、進階看盤（lightweight-charts + WebSocket、手畫線保存）、v2 ML 策略（XGBoost/RandomForest，時間序列驗證）。理由：這些都屬「新增能力 / 新外部依賴」，非 v1 範圍內的修補，集中到 v2 規劃較清楚。詳見 [`STATUS.md`](../STATUS.md) 的「v2 待辦」。
- 本輪為規劃/文件整理，無程式碼變更。

---

## v2 UI 改版（2026-06-03）

v2 第一批 UI 改進，全在 `dashboard/app.py` + `core.py`，未動 bar 管線/回測/look-ahead。

- **當前訊號涵蓋投組**：新增 `_signal_universe()` = 觀察清單 ∪ `get_portfolio_holdings()`，以 (symbol, market) 去重；**只**套用到「當前訊號」tab（側邊欄選單不變）。庫存中但不在觀察清單的標的也會出現。
- **當前訊號依類別分子 tab**：`panel_signals()` 改成 `st.tabs(["全部", …類別])`，不再只分台股/美股。類別來源：抽出共用 `_category_of(item)`（觀察項與庫存共用，沿用原 `_holding_category` 邏輯）；觀察項可自訂類別——`core.add_symbol()` 多收選填 `category`、側邊欄「新增標的」表單加「類別」欄；兩邊都有的標的若觀察項沒填類別則用庫存類別補，最後 fallback 市場（台股/美股）。
- **K線手畫工具**：`panel_chart()` 加 `st.color_picker`（設 `fig.layout.newshape.line.color`，只影響之後新畫的線——Plotly 限制）＋「🧹 清除手畫線」按鈕（改 `draw_nonce` → `plotly_chart` 的 `key` 重新掛載 → client 端手畫線清空）。保留 modebar 橡皮擦（單條刪除）。
- **投組估值表多重篩選**：`panel_portfolio()` 把單一類別篩選擴成 **市場 / 類別 / 代號 / 關鍵字** 四項（放 `🔍 篩選` expander），累積套用到 `view`；下游總計/估值表/類別小計/圓餅已全部吃 `view`，自動連動，空集合由既有 guard 處理。
- **測試**：`tests/test_core.py` 加 `test_add_symbol_category`（帶/不帶 category、重複代號），併入 `run_all`；離線測試全綠。

---

## macOS 一鍵啟動（2026-06-03）

- 新增 `啟動儀表板.command`（macOS / Linux），對應 `啟動儀表板.bat` 的流程：檢查 Python 3.10+ → 首次建 `.venv` → `requirements.txt` 變動才重裝（比對 `.venv/requirements.lock`）→ 啟動 `streamlit`。差別只在 venv 路徑 `.venv/bin/`（非 `Scripts\`）與 shell 寫法；Finder 右鍵「打開」即可雙擊執行。
- 新增 `.gitattributes`：`*.command` / `*.sh` 強制 `eol=lf`，避免 Windows 上被轉成 CRLF 造成 macOS 執行 `bash\r` 報錯；該檔以 `100755`（可執行）入庫。
- README 第一/三節補上 macOS 安裝與啟動（一鍵 + 手動 `python3 -m venv` 路徑）。

---

## 待辦 / 下一步

👉 **未完成事項與下一步統一列於 [`STATUS.md`](../STATUS.md)**（開新工作階段先看那份）。
