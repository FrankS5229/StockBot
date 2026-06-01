# StockBot 開發紀錄（DEVLOG）

> 記錄開發過程、決策、踩過的坑。技術細節另見 [`TECHNICAL.md`](TECHNICAL.md)，
> 專案定位與範圍見 [`PROJECT.md`](../PROJECT.md)，接續進度見 [`STATUS.md`](../STATUS.md)。

---

## 進度總覽

| 階段 | 狀態 | 說明 |
|------|------|------|
| 規劃與定位 | ✅ | 通用選股工具，不綁個人財務；功能=儀表板+回測+(延後)通知；不自動下單 |
| 資料層 | ✅ | `data/fetchers.py`：美股 yfinance、台股 FinMind→yfinance fallback、parquet 快取 |
| 指標層 | ✅ | `indicators/ta.py`：純 pandas 自實作 EMA/MACD/RSI/布林/ATR/VWAP/OBV |
| 策略層 | ✅ | `strategy/`：可解釋訊號（每個訊號附白話理由）+ ATR 停損停利 |
| 回測層 | ✅ | `backtest/runner.py`：next-bar 執行、含手續費/滑點、防 look-ahead |
| 測試 | ✅ | `tests/`：離線（合成資料）+ 連網，`run_all` 一鍵 |
| 通知 | ⏸ | `notify/base.py` 介面 + ConsoleNotifier；管道未定（已排除 Telegram） |
| 儀表板 | ✅ | `dashboard/app.py`：四面板，已驗證可啟動（HEALTH 200） |
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

## 待辦 / 下一步

👉 **未完成事項與下一步統一列於 [`STATUS.md`](../STATUS.md)**（開新工作階段先看那份）。
