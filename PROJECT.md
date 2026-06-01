# StockBot — 選股訊號與回測工具

> 一個**通用、可公開使用**的台股 / 美股技術分析訊號工具。
> 提供技術指標監控儀表板、策略回測、與（後續）訊號通知。**不自動下單**。

---

## 1. 定位

StockBot 是一個面向一般使用者的選股輔助工具，**不綁定任何個人財務資料**。
所有持股、資金、成本資訊一律由使用者自行輸入（`portfolio.yaml`、`config.yaml`），
工具本身保持通用、可給任何人使用。

設計理念來自兩份技術研究文件：
- **短線交易心法**：紀律優先、順勢操作、單筆風險 0.5–2%、技術停損、聚焦少數標的。
- **技術指標與 ML 演算法清單**：MACD / RSI / 布林 / ATR / VWAP / EMA 交叉等，以及第二階段的
  XGBoost / LSTM 等模型；特別強調回測時須**避免 look-ahead bias（使用未來資料）**。

> 註：個人財務藍圖屬私人文件，**不納入本工具**，僅供作者私下參考。

---

## 2. 功能範圍

| 功能 | 狀態 | 說明 |
|------|------|------|
| 監控儀表板 | **v1 優先** | Streamlit 網頁（5 面板），含 K 線+指標、訊號狀態、回測績效、投資組合概覽、策略說明 |
| **可解釋訊號** | **v1 核心** | 每個訊號附白話理由（為什麼進/出場）；指標與績效數字附一句話 tooltip 說明 |
| 圖表標註 | v1 基礎 | 程式自動標註（進出場箭頭、停損/停利線、均線/布林）+ Plotly 內建手畫工具 |
| 策略回測 | v1 | 規則型策略在歷史資料上的績效評估 |
| 訊號通知 | 延後 | 管道待定（候選：Discord Webhook / ntfy.sh / Email；已排除 Telegram、LINE） |
| 自動下單 | ❌ 不做 | 僅提供訊號輔助，不串券商自動交易 |

支援市場：**台股 + 美股**。

---

## 3. 架構

```
StockBot/
├── data/
│   ├── fetchers.py        # 台股(FinMind/yfinance) + 美股(yfinance) 統一取數介面
│   └── cache/             # 本地快取，避免重複打 API
├── indicators/
│   └── ta.py              # 純 pandas 自實作 EMA/MACD/RSI/BBands/ATR/VWAP/OBV
├── strategy/
│   ├── base.py            # Strategy 介面：DataFrame → signal/reason 欄位
│   ├── ema_macd_rsi.py    # 組合策略：EMA5/20 + VWAP + MACD柱 + RSI + ATR 停損
│   ├── fibonacci.py       # 黃金分割回撤順勢低接策略
│   ├── golden_cross.py    # 50/200 均線黃金交叉長期趨勢策略
│   └── bollinger.py       # 布林通道均值回歸策略（震盪盤）
├── backtest/
│   └── runner.py          # 自寫 next-bar 回測，輸出績效指標
├── notify/
│   └── base.py            # 通知介面（v1 僅 ConsoleNotifier 佔位）
├── dashboard/
│   └── app.py             # Streamlit 儀表板（5 面板）
├── core.py                # 共用流程：讀設定→抓資料→指標→訊號 + 策略註冊表
├── scanner.py             # CLI 主流程：抓資料→算指標→產訊號→輸出
├── tests/                 # 測試套件（離線合成資料 + 連網，run_all 一鍵）
├── 啟動儀表板.bat          # 雙擊一鍵啟動儀表板
├── config.yaml            # 觀察標的、指標/風控/回測參數
├── portfolio.yaml.example # 使用者持股輸入範本（自填，不含真實個人數字）
├── .env.example           # API 金鑰範本（FinMind token 等）
├── user_watchlist.json    # 介面新增的標的（git 忽略）
├── user_portfolio.json    # 介面新增的庫存（git 忽略）
├── requirements.txt
├── README.md              # 使用者導向說明（怎麼用）
├── PROJECT.md             # 本檔：專案定位 / 範圍 / 架構
├── STATUS.md              # 「從這裡接續」看板：現況 + 下一步 + 快速指令
└── docs/                  # 開發者文件與研究資料
    ├── TECHNICAL.md       # 技術參考（模組/指標/策略/回測/擴充）
    ├── DEVLOG.md          # 開發紀錄 / 決策 / 踩坑
    └── research/          # 技術研究報告（整個資料夾 git 忽略、不進版控，本機保留）
```

### 儀表板五面板
1. **K線+指標疊圖** — plotly K 線疊 EMA/MACD/RSI/布林，可切換標的與時框。
   - 程式自動標註：進出場箭頭、停損/停利水平線、均線/布林通道、交叉點。
   - Plotly 內建手畫工具（折線/矩形/手繪/橡皮擦）供臨時標記。
2. **當前訊號狀態** — 各觀察標的 buy/sell/hold、觸發條件、建議停損/停利，**並附白話理由**。
3. **回測績效** — Sharpe / 最大回撤 / 勝率 / 盈虧比 + 淨值曲線（含買進持有對照），**數字旁附一句話說明**。
4. **投資組合概覽（通用）** — 讀使用者 `portfolio.yaml`，顯示現值、損益、配置比例。
5. **策略說明** — 動態列出各策略 `DESCRIPTION`，說明「參數 vs 策略」差異；側邊欄可全域切換策略。

### 可解釋訊號（v1 核心設計）
- 每個策略的輸出除了 `signal`，還必須產生 `reason`：逐條列出觸發的指標條件（白話），
  例：「EMA5 上穿 EMA20（黃金交叉）｜站上 VWAP｜MACD 柱翻紅｜RSI 54 中性」。
- 儀表板對技術名詞與績效指標提供 tooltip / 小教室（如 Sharpe、最大回撤的一句話定義），
  讓不熟演算法的使用者也看得懂為什麼進出場。

---

## 4. 技術選型

| 用途 | 套件 |
|------|------|
| 美股資料 | `yfinance` |
| 台股資料 | `FinMind`（首選）/ `yfinance`（`.TW`） |
| 技術指標 | **純 pandas 自實作**（原訂 `pandas-ta`，因 numpy 2.x 不相容改自寫，見 DEVLOG 決策 #1） |
| 回測 | **自寫 next-bar 引擎**（原訂 `backtesting.py`，為求邏輯透明與嚴防未來資料改自寫，見 DEVLOG 決策 #2） |
| 儀表板 | `streamlit` + `plotly` |
| 設定 | `pyyaml` + `python-dotenv` |
| 通知（延後） | Discord Webhook / ntfy.sh / Email SMTP |

---

## 5. Roadmap

- **v1（規則型）**：✅ 已完成。資料層 → 指標 → 四支策略（ema_macd_rsi、fibonacci、golden_cross、bollinger）→ 回測 → Streamlit 五面板儀表板（通知僅 Console 佔位）。
- **策略擴充**：已涵蓋短中線順勢（ema_macd_rsi、fibonacci）＋ 長期趨勢（golden_cross 50/200 金叉 ✅）＋ 震盪市均值回歸（bollinger 布林通道 ✅）。後續候選：Ichimoku、HMM 市場狀態濾網（視需求）。
- **v2（ML）**：在 `strategy/` 新增 ML 策略（先 XGBoost/RandomForest，輕量可解釋；LSTM 視需要），沿用同一介面；
  落實時間序列交叉驗證與特徵工程，嚴守不洩漏未來資料。
- **通知**：選定管道後補上對應 `Notifier` 實作。
- **進階看盤**（可選，視 v1 使用後再評估）：圖表引擎升級為 `lightweight-charts`（TradingView 開源版），
  支援可保存的手畫趨勢線、錨點等接近專業看盤軟體的體驗。

---

## 6. 風控與回測原則（內建約束）

- 單筆風險控制在資金的 0.5–2%；停損可用 ATR 距離或技術價位。
- 回測須計入手續費與滑點（台股單邊約 0.15%+證交稅、美股約 0.05%）。
- 指標與訊號**只能使用當下與過去 K 線**，嚴禁使用未來資料。
- 回測支援樣本外驗證（80/20 或滾動窗口）。
