# 主管共同空檔查詢 API

## GitHub Pages 固定查詢頁

網址為 https://magilin-66.github.io/oaa_calendar/ 。Pages 的發布來源設為 `main` 分支的 `/docs`，提供免登入的查詢介面。GitHub Pages 不執行 Python，頁面透過 `docs/api-config.json` 指定的 HTTPS API 讀取即時結果，OAuth 憑證留在 Windows 主機。

目前後端使用臨時 Cloudflare Tunnel。Windows 必須保持開機、不休眠，API 與 Tunnel 也必須持續執行。Tunnel 重新啟動後，要更新 `docs/api-config.json` 的 `baseUrl` 並推送到 GitHub；頁面固定網址不變。要讓後端位址也固定，需另設定固定 HTTPS 網域或 Named Tunnel。

修改介面時同步更新 `static/availability.html` 與 `docs/index.html`。

唯讀 Python API，使用 Google Calendar FreeBusy API 回傳忙碌區間，不讀取活動名稱或內容，也沒有建立、修改或刪除活動的端點。

## 端點

- `GET /health`：服務健康狀態。
- `POST /api/freebusy`：Request JSON 範例：

```json
{"selected":["dean","registrar"],"dateStart":"2026-12-01","dateEnd":"2026-12-31"}
```

`selected` 僅接受 `dean`, `deputy`, `registrar`, `course`, `development`, `admissions`，不接受任意 calendar ID。日期範圍最多 367 天。

## OAuth 設定

1. 在 Google Cloud Console 建立專案、啟用 Google Calendar API，設定 OAuth 同意畫面並建立 Desktop app OAuth 用戶端。
2. 將下載的 OAuth JSON 暫存為 `credentials.json`（不要提交到 Git）。
3. 執行 `python -m pip install -r requirements.txt`，再執行 `python oauth_setup.py`，以一個固定管理帳號完成一次性授權。
4. 授權帳號必須具有所有主管日曆的忙碌／空閒查看權限。
5. 將輸出的 `GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET`、`GOOGLE_OAUTH_REFRESH_TOKEN` 設為託管服務的 Secret 環境變數。不要放進原始碼、前端 JavaScript、Git 或一般文字檔。

公開訪客不需要 Google 或 ChatGPT 登入，但任何取得網站網址的人都能查詢這些帳號的忙碌／空閒資料。

## 本機執行

Windows 主機可用以下腳本，無需建立 Cloud Run 帳單帳戶。請安裝 Python 3.12 以上，在此目錄開啟 PowerShell，依序執行：

```powershell
.\install-windows.ps1
.\authorize-windows.ps1
.\start-windows.ps1
```

授權前先將 Desktop OAuth 用戶端 JSON 放為此目錄下的 `credentials.json`。授權腳本會開啟瀏覽器，由管理者選擇具有主管日曆權限的 Google 帳號。授權結果使用 Windows DPAPI 加密儲存在 `.local/google-oauth.xml`，啟動時載入程序環境變數；必須使用同一台電腦、同一個 Windows 使用者執行。服務健康檢查網址為 `http://127.0.0.1:8080/health`。

此腳本僅監聽本機，供 HTTPS 反向代理連線。要讓現有公開網站使用，需由校內資訊單位提供對外 HTTPS API 網址，代理至此服務並設定查詢速率限制；目前尚未設定公開網路、開機啟動或網站串接。更換主機需重新授權。OAuth 應用若處於 Google 的 External/Testing 狀態，日曆授權的 refresh token 通常會在 7 天到期，長期運作前需調整發布狀態或依學校 Workspace 的應用政策設定。

以下為手動使用環境變數執行方式：

```powershell
$env:ALLOWED_ORIGINS='https://december-2026-availability.oaaailab-6179.chatgpt.site,http://localhost:3000'
uvicorn main:app --host 127.0.0.1 --port 8080 --reload
```

## Windows 臨時公開連線

完成授權並安裝 Cloudflare 官方 `cloudflared` 後，可在 PowerShell 執行 `./start-public-windows.ps1`。它會建立臨時 HTTPS Tunnel，啟動 API 及免登入查詢頁，並將新網址寫入 `.local/public-url.txt`。啟動前先停止原本占用 8080 的服務。按 Ctrl+C 會停止本次服務及 Tunnel。這個方式不需開放路由器的入站連線埠。

電腦必須保持開機且不休眠。Quick Tunnel 只供測試，沒有運作時間保證，重新啟動會換網址。要長期使用需設定具固定網域的 Named Tunnel。此 Python 版查詢頁在自己的網址提供服務；原有 chatgpt.site 網址尚未切換。

## Cloud Run 部署（替代方式）

從此資料夾建置容器並部署至 Cloud Run；服務需允許 unauthenticated invocation，並把三個 OAuth 值設為 Secret Manager 綁定的環境變數。正式環境的 `ALLOWED_ORIGINS` 只保留目前網站網址。部署後將 API base URL 設定到網站端，再把網站後端切換至此服務。

開放匿名呼叫的 API 會消耗 Google API 配額。正式公開前應在 Cloud Run/API Gateway 加上配額或速率限制；CORS 是瀏覽器政策，不是 API 身分驗證。
