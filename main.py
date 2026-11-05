"""Read-only Google Calendar FreeBusy API for the public availability page."""

from __future__ import annotations

import os
import math
from pathlib import Path
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from pydantic import BaseModel, Field, field_validator, model_validator
from access_auth import login, logout, require_session

TZ = ZoneInfo("Asia/Taipei")
SCOPES = ["https://www.googleapis.com/auth/calendar.freebusy"]
PEOPLE = {
    "dean": {"title": "教務長", "calendar_id": "deanoaa2018@gmail.com", "email": "deanoaa2018@gmail.com"},
    "deputy": {"title": "副教務長", "calendar_id": "oaancu2017@gmail.com", "email": "oaancu2017@gmail.com"},
    "registrar": {"title": "註冊組長", "calendar_id": "uk56hs13bgj775u2s9n8gf0i9k@group.calendar.google.com", "email": "uk56hs13bgj775u2s9n8gf0i9k@group.calendar.google.com"},
    "course": {"title": "課務組長", "calendar_id": "bkchang@g.ncu.edu.tw", "email": "bkchang@g.ncu.edu.tw"},
    "development": {"title": "教發中心主任", "calendar_id": "ziyang.ccu@gmail.com", "email": "ziyang.ccu@gmail.com"},
    "admissions": {"title": "招生組長", "calendar_id": "takee1016@gmail.com", "email": "takee1016@gmail.com"},
}
GOOGLE_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"

app = FastAPI(title="主管共同空檔查詢 API", version="1.0.0")
origins = [x.strip().rstrip("/") for x in os.getenv(
    "ALLOWED_ORIGINS",
    "https://december-2026-availability.oaaailab-6179.chatgpt.site,https://ncuoaa.github.io",
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning"],
    max_age=600,
)


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"status": "error", "message": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"status": "invalid_request", "message": "請確認日期、主管及時間條件；單次查詢最多 367 天。"}, status_code=422)


@app.get("/", include_in_schema=False)
@app.get("/availability", include_in_schema=False)
@app.get("/availability.html", include_in_schema=False)
def page():
    return FileResponse(Path(__file__).parent / "static" / "availability.html")


class AvailabilityRequest(BaseModel):
    selected: list[str] = Field(min_length=1, max_length=6)
    dateStart: date
    dateEnd: date

    @field_validator("selected")
    @classmethod
    def known_people(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(person not in PEOPLE for person in value):
            raise ValueError("主管選項無效或重複。")
        return value

    @model_validator(mode="after")
    def valid_range(self) -> "AvailabilityRequest":
        if self.dateEnd < self.dateStart:
            raise ValueError("結束日期不可早於開始日期。")
        if self.dateEnd == date.max:
            raise ValueError("結束日期超出支援範圍。")
        if (self.dateEnd - self.dateStart).days > 366:
            raise ValueError("單次查詢日期範圍最多 367 天。")
        return self


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@app.post('/api/login')
def sign_in(body: LoginRequest, request: Request):
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') not in origins:
        raise HTTPException(403, '來源網址未獲允許。')
    return {'status': 'success', 'token': login(body.username, body.password)}


@app.get('/api/session')
def session_status(request: Request):
    require_session(request)
    return {'status': 'success'}


@app.post('/api/logout')
def sign_out(request: Request):
    logout(request)
    return {'status': 'success'}


def credentials() -> Credentials:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    if not all((client_id, client_secret, refresh_token)):
        raise HTTPException(status_code=503, detail="Google Calendar API 尚未完成伺服器端 OAuth 設定。")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    try:
        creds.refresh(GoogleAuthRequest())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Google Calendar 授權失效或設定錯誤，請管理者重新授權。") from exc
    return creds


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/freebusy")
def freebusy(body: AvailabilityRequest, request: Request) -> dict:
    require_session(request)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in origins:
        raise HTTPException(status_code=403, detail="來源網址未獲允許。")

    people = [PEOPLE[key] for key in body.selected]
    time_min = datetime.combine(body.dateStart, time.min, TZ)
    time_max = datetime.combine(body.dateEnd + timedelta(days=1), time.min, TZ)
    payload = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "timeZone": "Asia/Taipei",
        "items": [{"id": person["calendar_id"]} for person in people],
    }
    try:
        auth = credentials()
        response = requests.post(
            GOOGLE_FREEBUSY_URL,
            json=payload,
            headers={"Authorization": f"Bearer {auth.token}"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except HTTPException:
        raise
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status in (401, 403):
            raise HTTPException(status_code=424, detail="授權帳號無權讀取部分所選行事曆的忙碌／空閒資訊。") from exc
        raise HTTPException(status_code=502, detail="Google Calendar 暫時無法提供空檔資料，請稍後再試。") from exc
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Google Calendar 暫時無法提供空檔資料，請稍後再試。") from exc

    calendars = data.get("calendars", {})
    result = []
    for key, person in zip(body.selected, people, strict=True):
        entry = calendars.get(person["calendar_id"], {})
        if entry.get("errors") or not isinstance(entry.get("busy"), list):
            raise HTTPException(status_code=424, detail=f"無法讀取{person['title']}的日曆，請確認分享權限；未將讀取失敗視為空檔。")
        result.append({
            "id": key,
            "title": person["title"],
            "email": person["email"],
            "busy": entry.get("busy", []),
            "errors": entry.get("errors", []),
        })
    return {
        "timeMin": payload["timeMin"],
        "timeMax": payload["timeMax"],
        "timeZone": "Asia/Taipei",
        "calendars": result,
    }


class CommonAvailabilityRequest(AvailabilityRequest):
    dailyStart: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    dailyEnd: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    minimumMinutes: int = Field(ge=30, le=1440)
    workdays: bool
    holidays: bool

    @model_validator(mode="after")
    def valid_times(self):
        if self.dailyStart >= self.dailyEnd or not (self.workdays or self.holidays):
            raise ValueError("請確認每日起訖時段與日期類型。")
        return self


def calculate_rows(body: CommonAvailabilityRequest, calendars: list[dict]) -> list[dict]:
    start_hour, start_minute = map(int, body.dailyStart.split(":"))
    end_hour, end_minute = map(int, body.dailyEnd.split(":"))
    work_start = start_hour * 60 + start_minute
    work_end = end_hour * 60 + end_minute
    # Matches the existing page; school-specific holidays require an official feed.
    known_holidays = {date(2026, 12, 25)}
    labels = ["一", "二", "三", "四", "五", "六", "日"]
    accounts = [{"title": c["title"], "email": c["email"]} for c in calendars]
    windows = []
    for calendar in calendars:
        for window in calendar["busy"]:
            try:
                start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))
                if start.tzinfo is None or end.tzinfo is None or end <= start:
                    raise ValueError("invalid interval")
                windows.append((start, end))
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=502, detail="Google Calendar 回傳的時段格式無效，查詢未完成。") from exc
    rows = []
    cursor_date = body.dateStart
    while cursor_date <= body.dateEnd:
        day = cursor_date.weekday()
        holiday = day >= 5 or cursor_date in known_holidays
        if (body.holidays and holiday) or (body.workdays and not holiday):
            midnight = datetime.combine(cursor_date, time.min, TZ)
            busy = sorted((max(work_start, math.floor((start - midnight).total_seconds() / 60)),
                           min(work_end, math.ceil((end - midnight).total_seconds() / 60)))
                          for start, end in windows
                          if end > midnight + timedelta(minutes=work_start)
                          and start < midnight + timedelta(minutes=work_end))
            free = []
            cursor = work_start
            for start, end in busy:
                if start - cursor >= body.minimumMinutes:
                    free.append((cursor, start))
                cursor = max(cursor, end)
            if work_end - cursor >= body.minimumMinutes:
                free.append((cursor, work_end))
            if free:
                rows.append({
                    "date": cursor_date.isoformat(), "weekday": labels[day],
                    "slots": [f"{s // 60:02d}:{s % 60:02d}–{e // 60:02d}:{e % 60:02d}" for s, e in free],
                    "accounts": accounts,
                    "note": f"已即時比對 {len(accounts)} 個共享行事曆；僅查忙碌／空閒",
                })
        cursor_date += timedelta(days=1)
    return rows


@app.post("/api/availability")
def availability(body: CommonAvailabilityRequest, request: Request):
    data = freebusy(body, request)
    rows = calculate_rows(body, data["calendars"])
    return {"status": "success", "rows": rows, "count": len(rows)}


