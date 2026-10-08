# 部署指南 — 手機網頁版（無狀態公開試用）

把 StockBot 儀表板放到免費雲端、手機瀏覽器可直接開，供人試用。
**本機單機版不受影響**：只要不設 `STOCKBOT_STATELESS`，一切照舊（寫 JSON、記住資料）。

---

## 無狀態模式怎麼運作

雲端用一個旗標 `STOCKBOT_STATELESS` 切換（環境變數或平台 Secrets）：

| 模式 | 旗標 | 觀察清單 / 投組 | 重整後 | 磁碟 |
|------|------|----------------|--------|------|
| 本機單機（預設） | 不設 / 留空 | 存 `user_watchlist.json`、`user_portfolio.json` | 保留 | 會寫檔 |
| 雲端公開試用 | `STOCKBOT_STATELESS=1` | 存 `st.session_state` | **全部歸零** | 不寫檔 |

- 無狀態模式下每個瀏覽器分頁各自獨立，彼此看不到對方資料；關頁/重整即清空。
- 投組初始**完全空白**（不吃 `portfolio.yaml` 種子）。
- `config.yaml` 內建 watchlist 屬應用設定，仍保留（驅動標的選單與當前訊號），不算使用者資料。

手機版面另有開關：側欄「📱 手機版面」toggle，或在網址加 `?m=1`（會記在網址，重整可還原）。

---

## 平台比較

| 平台 | 免費額度 | 直接吃 GitHub？ | 睡眠/限制 | 設定秘密 | 身分露出點 |
|------|----------|----------------|-----------|----------|-----------|
| **Streamlit Community Cloud**（首選） | 免費、公開 app | ✅ 連 repo、指定 `dashboard/app.py` 即跑 | 閒置會休眠、喚醒需幾秒 | App 設定頁 Secrets | 網址可自訂 subdomain；app 的「原始碼」連結指向 repo 帳號 |
| Hugging Face Spaces (Streamlit SDK) | 免費 CPU Space | 需在 Space 放 `app.py`＋設定、另同步 | 閒置休眠、啟動較慢 | Space Settings → Secrets | 網址含 `<帳號>/<space>`，帳號名直接露出 |
| Render / Railway 免費 | 有限時數/會睡 | 需 Dockerfile/build 設定 | 免費層會睡、冷啟慢 | 環境變數 | 自訂網址、不綁 GitHub 帳號名 |

---

## Streamlit Community Cloud 步驟（建議）

1. 專案已在 GitHub（含本次改動）。到 <https://share.streamlit.io> 用 GitHub 登入。
2. **New app** → 選 repo、branch `main`、Main file path 填 `dashboard/app.py`。
3. **Advanced settings → Secrets** 貼上（TOML 格式）：
   ```toml
   STOCKBOT_STATELESS = "1"
   # 選填：台股資料較穩可加 FinMind token（沒有也能跑，自動退回免登入額度）
   FINMIND_TOKEN = "你的token"
   ```
   > 程式同時支援環境變數與 `st.secrets`；在此填 Secrets 即可。
4. Deploy。完成後得到 `https://<自動子網域>.streamlit.app`，手機瀏覽器可直接開。
5. （選用）在 app 的 **Settings → General** 設自訂 subdomain，讓網址不含帳號名。

### 驗證
- 手機開網址 → 新增標的 / 投組 → 重整頁面 → 應全部歸零、投組起始空白。
- 側欄開「📱 手機版面」或網址加 `?m=1` → 各分頁單欄堆疊、圖不過高、投組不需橫捲。

---

## 注意事項

- **資料延遲**：免費資料源（yfinance / Yahoo）延遲約 15–20 分，盤中非即時。
- **磁碟快取**：雲端檔案系統為暫存，`data/cache/` 會隨重啟消失（程式能 graceful fallback，不影響功能，只是多打幾次 API）。
- **匿名部署**：若要讓訪客看不出 owner 是本人，見 `STATUS.md` / 計畫中的「匿名部署（Step 7）」——自訂 subdomain + 公開 repo 放暱稱帳號/中性 org + commit 用匿名信箱。此步驟上線前另行處理。
