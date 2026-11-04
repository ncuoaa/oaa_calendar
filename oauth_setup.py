"""One-time local OAuth flow; prints a refresh token for secure server storage."""

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.freebusy"]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Return credentials to the Windows setup script via stdout.")
    parser.add_argument("--manual", action="store_true", help="Write the authorization URL locally instead of launching a browser.")
    args = parser.parse_args()
    path = Path("credentials.json")
    if not path.is_file():
        raise SystemExit("請將 Google Cloud OAuth Desktop 用戶端 JSON 放在本資料夾，檔名為 credentials.json。")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    if args.manual:
        Path('.local').mkdir(exist_ok=True)
        with Path('.local/authorize-url.txt').open('w', encoding='utf-8', buffering=1) as link_file:
            with redirect_stdout(link_file):
                creds = flow.run_local_server(port=0, access_type="offline", prompt="consent", open_browser=False, authorization_prompt_message="{url}")
        Path('.local/authorize-url.txt').unlink(missing_ok=True)
    else:
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent", authorization_prompt_message="" if args.json else "Open this URL to authorize: {url}")
    if not creds.refresh_token:
        raise SystemExit("Google 沒有回傳 refresh token，請撤銷此應用授權後重新執行。")
    values = {"GOOGLE_OAUTH_CLIENT_ID": creds.client_id, "GOOGLE_OAUTH_CLIENT_SECRET": creds.client_secret, "GOOGLE_OAUTH_REFRESH_TOKEN": creds.refresh_token}
    if args.json:
        print(json.dumps(values))
    else:
        print("OAuth 授權完成。請將以下三個值存入託管服務的 Secret 環境變數，不要提交到 Git：")
        for key, value in values.items():
            print(f"{key}={value}")
