# 教務處主管行程查詢：Apps Script 試行版

此資料夾是 Google 雲端執行版本。它不依賴本機 Python、ngrok 或 Cloudflare Tunnel。原有 Python 與 GitHub Pages 仍是現行服務，試行版驗證通過前不切換正式入口。

## 功能與資料

- 保留網站帳密登入、8 小時登入期限及登出。每分鐘最多 20 次登入嘗試。
- 每個查詢入口在後端驗證登入。密碼使用與 Python 版相同的 PBKDF2-SHA256 格式；不能從雜湊還原密碼。
- 主管名稱、排列、日曆 ID、聯絡說明與假日清單集中於 `Config.gs`。前端只在登入後取得顯示資料。
- Calendar API 僅使用 FreeBusy 查詢與 `calendar.events.freebusy` 唯讀範圍。不讀取活動標題或內容，不新增、修改、刪除行程。
- 日期不限定月份，單次最多 367 天；僅顯示符合最少連續時間的日期。
- 延續原版假日清單，目前明列 2026-12-25，其他假日只計週六、週日。需要依學校實際行事曆維護。

## 必要資訊

1. 擁有所有目標行事曆忙碌／空閒檢視權限的 Google 部署帳號。
2. Google Apps Script 專案及部署權限；若使用 clasp，需由管理者開啟 Apps Script API。
3. 後端 Script Properties 中的 `WEB_USERNAME` 與 `WEB_PASSWORD_HASH`。沿用本機帳密時，由管理者將本機加密設定轉入這兩個屬性；不要放進原始碼、前端或 GitHub。
4. 日曆 ID 清單、維護者與交接人員。Google Workspace 管理規範可能限制部署方式或外部訪客存取。

## 檔案

| 檔案 | 用途 |
|---|---|
| `Config.gs` | 網站名稱、日曆白名單、顯示順序、聯絡文字與已知假日 |
| `Code.gs` | 登入、工作階段、輸入驗證與空檔計算 |
| `Crypto.gs` | 打包後的純 JavaScript 密碼驗證套件 |
| `Index.html` | 由 Apps Script 提供的登入與查詢頁，使用 `google.script.run` |
| `appsscript.json` | 時區、Calendar v3 進階服務及最小 OAuth 範圍 |

所有輔助伺服器函式以底線結尾，禁止瀏覽器 RPC 直接呼叫。公開的查詢函式必須驗證 session，登入函式只回傳隨機登入權杖，不回傳 Google OAuth 權杖或密碼雜湊。

## 手動部署

1. 用管理帳號建立獨立 Apps Script 專案，將 `.gs`、`Index.html` 與 manifest 上傳。
2. 確認「服務」包含 Calendar API v3。若使用標準 Google Cloud 專案，也需在該 Cloud 專案啟用 Calendar API。
3. 在「專案設定 → 指令碼屬性」建立 `WEB_USERNAME`、`WEB_PASSWORD_HASH`。只允許可信任的維護人員編輯專案。
4. 先從編輯器執行 `authorizeAndCheckCalendars_`，由管理者完成 Google 忙碌／空閒資訊授權並檢查目標日曆權限。
5. 建立「網頁應用程式」部署：執行身分選擇部署者；訪客範圍依學校政策設定。若要保留自訂帳密而不要求訪客 Google 登入，平台必須允許匿名訪客存取；平台公開不代表 API 可免除網站登入驗證。
6. 使用 `/exec` 部署網址試行；`/dev` 只供專案編輯者測試。

Google 授權與部署須由帳號持有人核准。Apps Script 的存取政策、Calendar API 配額及執行限制仍適用。試行版預設不允許任意網站 iframe 嵌入；如決定用 Google Sites 嵌入，可在風險確認後將 `ENABLE_SITES_EMBED` Script Property 設為 `true`，或直接使用 Sites 的連結按鈕開啟。

## 使用 clasp 同步

Google 官方 clasp 可以同步原始碼及建立部署。OAuth 檔 `.clasprc.json` 與綁定專案的 `.clasp.json` 不應提交。編輯器及 clasp 不要同時修改同一檔案，以免覆蓋版本。

`Crypto.gs` 已包含可部署版本，正常維護不用重建。要重建時，在此資料夾安裝 `package.json` 的開發相依套件並執行 `npm run build:crypto`。執行 `npm test` 可檢查本機運算與權限邏輯；它不代表 Google 雲端讀取或部署已驗證。

## 上線前驗收

1. 未登入、錯誤帳密、逾期及已登出權杖不能查詢。
2. 管理帳號可讀取全部主管日曆；單一與多位主管查詢結果正確。
3. 日曆權限不足、Google 回傳錯誤或格式無效時，顯示錯誤而非空檔。
4. 平日／假日、重疊行程、跨日時段與最少連續時間符合預期。
5. 由實際訪客試行；確認沒有把 Google OAuth 憑證或後端屬性送到瀏覽器。
6. 維護人員確認部署帳號、授權交接、配額紀錄與回復網址。

全部確認後才調整正式入口。可保留舊版作回復方案；不要在尚未驗證前停掉 Windows 排程。
