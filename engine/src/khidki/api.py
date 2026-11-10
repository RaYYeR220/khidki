"""Public HTTP API."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import jobs
from .aqi import HEALTH_STATEMENT, pm25_category
from .exposure import Activity, AgeBand, inhalation_rate
from .jobs import at, now_ist
from .planner import plan_airing, plan_window
from .point import point_forecast
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


def _hhmm(s: str) -> time:
    try:
        return time.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(422, f"bad time {s!r}, use HH:MM") from e


def _day(day: str) -> date:
    today = now_ist().date()
    if day in ("today", ""):
        return today
    if day == "tomorrow":
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(day)
    except ValueError as e:
        raise HTTPException(422, "day must be today, tomorrow or YYYY-MM-DD") from e


def _slot(s) -> dict | None:
    if s is None:
        return None
    return {
        "start": s.start.strftime("%H:%M"),
        "end": s.end.strftime("%H:%M"),
        "mean_pm25": round(s.mean_conc, 1),
        "dose_ug": round(s.dose_ug, 1),
        "category": pm25_category(s.mean_conc),
    }


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
    d = _day(day)
    now = now_ist()
    pf = point_forecast(store, lat, lon, d, now=now, cams_fallback=_cams_point)
    if pf.source == "none":
        return {"status": "no_data", "reason": "no monitor nearby has a forecast for this day yet", "day": d.isoformat()}
    e, le = at(d, _hhmm(earliest)), at(d, _hhmm(latest_end))
    if d == now.date():
        # only future starts make sense for today
        nxt = (now + timedelta(minutes=15 - now.minute % 15)).replace(second=0, microsecond=0)
        e = max(e, nxt)
    hab = at(d, _hhmm(habitual)) if habitual else None
    if e >= le - timedelta(minutes=minutes):
        return {"status": "window_closed", "reason": "the allowed time for today has passed", "day": d.isoformat()}
    plan = plan_window(
        pf.values,
        activity=activity,
        age=age,
        minutes=minutes,
        earliest=e,
        latest_end=le,
        habitual_start=hab,
        sigma_log=pf.sigma_log,
    )
    store.event("window", now.isoformat(), {"lat": round(lat, 2), "lon": round(lon, 2), "activity": activity.value})
    return {
        "status": plan.status,
        "day": d.isoformat(),
        "activity": activity.value,
        "minutes": minutes,
        "best": _slot(plan.best),
        "usual": _slot(plan.habitual),
        "worst": _slot(plan.worst),
        "alternatives": [_slot(a) for a in plan.alternatives],
        "dose_avoided_ug": round(plan.dose_avoided_ug, 1) if plan.dose_avoided_ug is not None else None,
        "reduction_pct": round(plan.reduction_pct, 1) if plan.reduction_pct is not None else None,
        "confidence": round(plan.confidence, 2) if plan.confidence is not None else None,
        "flags": plan.flags,
        "health": HEALTH_STATEMENT.get(plan.best_category or "", None),
        "curve": [
            {"hour": h.strftime("%H:%M"), "pm25": round(v, 1), "measured": h in pf.measured_hours}
            for h, v in sorted(pf.values.items())
        ],
        "source": pf.source,
        "neighbours": pf.neighbours,
        "issued_at": pf.issued_at,
        "nowcast_factor": round(pf.nowcast_factor, 2) if pf.nowcast_factor else None,
        "inhalation_m3_per_min": inhalation_rate(activity, age),
    }


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
    d = _day(day)
    pf = point_forecast(store, lat, lon, d, cams_fallback=_cams_point)
    if len(pf.values) < 24:
        return {"status": "no_data", "day": d.isoformat()}
    p = plan_airing(
        pf.values,
        day_start=jobs.day_start(d),
        open_minutes=open_minutes,
        earliest=at(d, _hhmm(earliest)),
        latest_end=at(d, _hhmm(latest_end)),
        habitual_start=at(d, _hhmm(habitual)) if habitual else None,
    )
    return {
        "status": p.status,
        "day": d.isoformat(),
        "open_at": p.best_start.strftime("%H:%M") if p.best_start else None,
        "open_minutes": open_minutes,
        "usual": habitual,
        "reduction_pct": round(p.reduction_pct, 1) if p.reduction_pct is not None else None,
        "dose_avoided_ug": round(p.dose_avoided_ug, 1) if p.dose_avoided_ug is not None else None,
        "flags": p.flags,
        "source": pf.source,
    }


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
    d = _day(day)
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
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(401, "unauthorised")
    from .sources.openmeteo import OpenMeteo

    latest = None
    if os.environ.get("OPENAQ_API_KEY"):
        from .sources.openaq import OpenAQClient

        latest = OpenAQClient()
    return jobs.tick(store, latest=latest, cams=OpenMeteo())
