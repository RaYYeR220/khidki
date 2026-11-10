"""Public HTTP API."""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timedelta
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import jobs, service
from .aqi import pm25_category
from .exposure import Activity, AgeBand
from .jobs import now_ist
from .store import Store

app = FastAPI(title="Khidki API", version="0.1.0", docs_url="/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("KHIDKI_CORS", "*").split(",") if o],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(os.environ.get("KHIDKI_DB", "data/khidki.db"))


def _cams_point(lat: float, lon: float) -> dict[datetime, float]:
    from .sources.openmeteo import OpenMeteo

    return OpenMeteo().cams(lat, lon, past_days=1, forecast_days=2).series("pm2_5")


def _bad(e: Exception) -> HTTPException:
    return HTTPException(422, str(e))


@app.get("/v1/health")
def health(store: Store = Depends(get_store)) -> dict:
    last = store.one("SELECT MAX(hour) h FROM obs")
    run = store.one("SELECT job, started_at, ok FROM runs ORDER BY id DESC LIMIT 1")
    return {
        "ok": True,
        "time": now_ist().isoformat(),
        "stations": store.one("SELECT COUNT(*) n FROM stations WHERE active=1")["n"],
        "latest_reading_hour": last["h"] if last else None,
        "last_run": dict(run) if run else None,
    }


@app.get("/v1/window")
def window(
    lat: float = Query(..., ge=6, le=37.5),
    lon: float = Query(..., ge=68, le=97.5),
    activity: Activity = Activity.walk,
    minutes: int = Query(60, ge=10, le=240),
    earliest: str = "05:00",
    latest_end: str = "21:00",
    habitual: str | None = "06:00",
    age: AgeBand = AgeBand.adult,
    day: str = "today",
    store: Store = Depends(get_store),
) -> dict:
    try:
        return service.compute_window(
            store, lat=lat, lon=lon, activity=activity, minutes=minutes, earliest=earliest,
            latest_end=latest_end, habitual=habitual or None, age=age, day=day, now=now_ist(),
            cams_fallback=_cams_point,
        )
    except ValueError as e:
        raise _bad(e) from e


@app.get("/v1/airing")
def airing(
    lat: float = Query(..., ge=6, le=37.5),
    lon: float = Query(..., ge=68, le=97.5),
    open_minutes: int = Query(30, ge=10, le=120),
    earliest: str = "06:00",
    latest_end: str = "22:00",
    habitual: str | None = "07:00",
    day: str = "tomorrow",
    store: Store = Depends(get_store),
) -> dict:
    try:
        return service.compute_airing(
            store, lat=lat, lon=lon, open_minutes=open_minutes, earliest=earliest, latest_end=latest_end,
            habitual=habitual or None, day=day, now=now_ist(), cams_fallback=_cams_point,
        )
    except ValueError as e:
        raise _bad(e) from e


@app.get("/v1/air-now")
def air_now(lat: float = Query(..., ge=6, le=37.5), lon: float = Query(..., ge=68, le=97.5), store: Store = Depends(get_store)) -> dict:
    return service.air_now(store, lat, lon, now_ist())


@app.get("/v1/stations")
def stations(store: Store = Depends(get_store)) -> dict:
    rows = store.q(
        """SELECT s.id, s.name, s.city, s.state, s.lat, s.lon, s.provider, s.last_seen,
                  (SELECT pm25 FROM obs o WHERE o.station_id=s.id ORDER BY hour DESC LIMIT 1) latest,
                  (SELECT hour FROM obs o WHERE o.station_id=s.id ORDER BY hour DESC LIMIT 1) latest_hour
           FROM stations s WHERE s.active=1"""
    )
    out = []
    for r in rows:
        d = dict(r)
        d["category"] = pm25_category(r["latest"]) if r["latest"] is not None else None
        out.append(d)
    return {"count": len(out), "stations": out}


@app.get("/v1/stations/{sid}")
def station(sid: str, day: str = "today", store: Store = Depends(get_store)) -> dict:
    s = store.one("SELECT * FROM stations WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "unknown station")
    try:
        d = service.resolve_day(day, now_ist())
    except ValueError as e:
        raise _bad(e) from e
    ds = jobs.day_start(d)
    obs = store.get_obs(sid, ds, ds + timedelta(days=1))
    fc = store.one("SELECT * FROM forecasts WHERE station_id=? AND day=?", (sid, d.isoformat()))
    recs = store.q("SELECT scenario, start, habitual, forecast_mean, forecast_habitual_mean FROM recommendations WHERE station_id=? AND day=?", (sid, d.isoformat()))
    flags = store.q("SELECT kind, severity, detail FROM audit_flags WHERE station_id=? ORDER BY day DESC LIMIT 20", (sid,))
    return {
        "station": dict(s),
        "day": d.isoformat(),
        "measured": {h.strftime("%H"): v for h, v in obs.items()},
        "forecast": json.loads(fc["values_json"]) if fc else None,
        "forecast_model": fc["model"] if fc else None,
        "issued_at": fc["issued_at"] if fc else None,
        "recommendations": [dict(r) for r in recs],
        "audit_flags": [{"kind": f["kind"], "severity": f["severity"], "detail": json.loads(f["detail"])} for f in flags],
    }


@app.get("/v1/ledger")
def ledger_index(store: Store = Depends(get_store)) -> dict:
    rows = store.q("SELECT day, issued_at, model, sha256, n_stations, n_recommendations, anchor FROM commitments ORDER BY day DESC")
    return {"commitments": [dict(r) for r in rows]}


@app.get("/v1/ledger/{day}.json")
def ledger_payload(day: str, store: Store = Depends(get_store)) -> Response:
    r = store.one("SELECT payload FROM commitments WHERE day=?", (day,))
    if not r:
        raise HTTPException(404, "no commitment for that day")
    # served byte-for-byte as hashed
    return Response(content=r["payload"].encode("utf-8"), media_type="application/json")


@app.get("/v1/ledger/{day}.ots")
def ledger_ots(day: str, store: Store = Depends(get_store)) -> Response:
    rows = store.q("SELECT meta FROM events WHERE kind='ots_proof' ORDER BY id DESC")
    for r in rows:
        m = json.loads(r["meta"])
        if m.get("day") == day:
            return Response(content=bytes.fromhex(m["ots_hex"]), media_type="application/octet-stream",
                            headers={"content-disposition": f'attachment; filename="khidki-{day}.json.ots"'})
    raise HTTPException(404, "no timestamp proof for that day")


@app.get("/v1/scoreboard")
def scoreboard(since: str | None = None, store: Store = Depends(get_store)) -> dict:
    days = store.q("SELECT day, COUNT(DISTINCT station_id) stations FROM verdicts WHERE status='verified' GROUP BY day ORDER BY day")
    return {"by_scenario": jobs.scoreboard(store, since), "days": [dict(d) for d in days]}


@app.get("/v1/audit")
def audit(day: str | None = None, store: Store = Depends(get_store)) -> dict:
    if day is None:
        r = store.one("SELECT MAX(day) d FROM audit_flags")
        day = r["d"] if r and r["d"] else now_ist().date().isoformat()
    rows = store.q(
        """SELECT f.station_id, s.name, s.city, f.kind, f.severity, f.detail FROM audit_flags f
           LEFT JOIN stations s ON s.id=f.station_id WHERE f.day=? ORDER BY f.severity DESC, f.kind""",
        (day,),
    )
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {
        "day": day,
        "stations_audited": store.one("SELECT COUNT(*) n FROM stations WHERE active=1")["n"],
        "by_kind": by_kind,
        "flags": [{**{k: r[k] for k in ("station_id", "name", "city", "kind", "severity")}, "detail": json.loads(r["detail"])} for r in rows],
    }


@app.get("/v1/impact")
def impact(store: Store = Depends(get_store)) -> dict:
    """Live, unrounded counts straight from the database. Nothing here is estimated."""
    one = lambda sql, *a: (store.one(sql, a) or {})
    people = store.q("SELECT channel, COUNT(*) n FROM people GROUP BY channel")
    outcomes = store.one(
        "SELECT COUNT(*) n, SUM(dose_avoided_ug) avoided, AVG(reduction_pct) red FROM outcomes WHERE status='verified'"
    )
    return {
        "as_of": now_ist().isoformat(),
        "stations_covered": one("SELECT COUNT(*) n FROM stations WHERE active=1")["n"],
        "hours_of_readings": one("SELECT COUNT(*) n FROM obs")["n"],
        "days_published_in_advance": one("SELECT COUNT(*) n FROM commitments")["n"],
        "recommendations_published": one("SELECT COALESCE(SUM(n_recommendations),0) n FROM commitments")["n"],
        "recommendations_verified": one("SELECT COUNT(*) n FROM verdicts WHERE status='verified' AND policy='khidki'")["n"],
        "audit_flags_raised": one("SELECT COUNT(*) n FROM audit_flags")["n"],
        "people": {r["channel"]: r["n"] for r in people},
        "plans_made_for_people": one("SELECT COUNT(*) n FROM plans")["n"],
        "people_outcomes_verified": outcomes["n"] if outcomes else 0,
        "people_dose_avoided_ug": round(outcomes["avoided"], 1) if outcomes and outcomes["avoided"] else 0,
        "window_lookups": one("SELECT COUNT(*) n FROM events WHERE kind='window'")["n"],
    }


@app.post("/jobs/tick")
def job_tick(authorization: str | None = Header(None), store: Store = Depends(get_store)) -> dict:
    token = os.environ.get("KHIDKI_JOB_TOKEN")
    if not token or not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "unauthorised")
    from .sources.openmeteo import OpenMeteo

    latest = None
    if os.environ.get("OPENAQ_API_KEY"):
        from .sources.openaq import OpenAQClient

        latest = OpenAQClient()
    out = jobs.tick(store, latest=latest, cams=OpenMeteo())
    sender = None
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        from .telegram import BotApi

        sender = BotApi()
    from .telegram import daily_people_jobs

    out["people"] = daily_people_jobs(store, sender, cams_fallback=_cams_point)
    return out


async def _planner_reply(person_id: int, lat: float | None, lon: float | None, text: str) -> str:
    from .agents.runtime import run_turn

    state = {"person_id": person_id}
    if lat is not None and lon is not None:
        state.update(lat=lat, lon=lon)
    turn = await run_turn("planner", f"p{person_id}", text, state=state)
    return turn.text


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
    store: Store = Depends(get_store),
) -> dict:
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not secret or not hmac.compare_digest((x_telegram_bot_api_secret_token or "").encode(), secret.encode()):
        raise HTTPException(401, "unauthorised")
    from .telegram import BotApi, handle_update

    update = await request.json()
    await handle_update(store, BotApi(), update, _planner_reply)
    return {"ok": True}


@app.post("/v1/chat")
async def web_chat(request: Request, store: Store = Depends(get_store)) -> dict:
    """The same planner agent for the web app. Anonymous: the browser keeps a
    random id; location comes with the message."""
    body = await request.json()
    text = str(body.get("text", ""))[:1000].strip()
    anon = str(body.get("session", ""))[:64]
    if not text or not anon:
        raise HTTPException(422, "text and session are required")
    from . import people as ppl
    from .agents.runtime import run_turn

    pid = ppl.get_or_create_person(store, "web", anon, str(body.get("lang", "en"))[:5])
    lat, lon = body.get("lat"), body.get("lon")
    if lat is not None and lon is not None:
        try:
            ppl.set_location(store, pid, float(lat), float(lon))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    p = ppl.person(store, pid)
    state = {"person_id": pid}
    if p["lat"] is not None:
        state.update(lat=p["lat"], lon=p["lon"])
    turn = await run_turn("planner", f"p{pid}", text, state=state)
    store.event("chat", now_ist().isoformat(), {"channel": "web"})
    return {"reply": turn.text, "tools": [c["name"] for c in turn.tool_calls]}
