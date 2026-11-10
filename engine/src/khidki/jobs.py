"""Scheduled pipeline: stations → observations → CAMS → publish → verify → audit."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterable, Protocol

from .audit import audit_day
from .backtest import RULE_OF_THUMB, SCENARIOS, Scenario
from .exposure import inhalation_rate, interval_dose
from .forecast import Forecast, make_forecast, obs_before
from .ledger import build_commitment, ots_file, submit_opentimestamps
from .planner import candidate_starts, plan_window
from .store import Store

log = logging.getLogger("khidki.jobs")

IST = timezone(timedelta(hours=5, minutes=30))
MODEL_PREFERENCE = ("blend", "cams_bc", "clim", "cams")
PUBLISH_HOUR = 21  # IST, the evening before the target day
VERIFY_LAG_HOURS = 6  # wait after midnight for late readings before verifying


def now_ist() -> datetime:
    return datetime.now(IST)


def day_start(d: date) -> datetime:
    return datetime.combine(d, time(0), tzinfo=IST)


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=IST)


class LatestSource(Protocol):
    def latest(self) -> list[tuple[int, datetime, float]]:  # (location_id, hour_start, value)
        ...


class CamsSource(Protocol):
    def cams_many(self, points: list[tuple[float, float]], past_days: int, forecast_days: int) -> list[dict[datetime, float]]:
        ...


def station_coords(store: Store) -> dict[str, tuple[float, float]]:
    return {r["id"]: (r["lat"], r["lon"]) for r in store.q("SELECT id, lat, lon FROM stations WHERE active=1")}


# --- ingestion -------------------------------------------------------------------------


class RegistrySource(Protocol):
    def india_pm25_locations(self) -> list: ...


def refresh_stations(store: Store, source: RegistrySource, *, max_age_days: int = 3) -> dict:
    """Load India's reference-grade PM2.5 monitors (OpenAQ isMonitor) that have
    reported within ``max_age_days``. Low-cost sensors are left out on purpose:
    recommendations are built only on regulatory-grade instruments."""
    now = now_ist()
    rows, skipped_sensor, skipped_stale = [], 0, 0
    for loc in source.india_pm25_locations():
        if not getattr(loc, "is_monitor", True) or loc.lat is None or loc.lon is None:
            skipped_sensor += 1
            continue
        if loc.last_seen:
            seen = datetime.fromisoformat(loc.last_seen.replace("Z", "+00:00"))
            if now - seen > timedelta(days=max_age_days):
                skipped_stale += 1
                continue
        rows.append(
            {
                "id": f"oaq:{loc.id}",
                "source": "openaq",
                "name": loc.name,
                "city": loc.locality,
                "lat": loc.lat,
                "lon": loc.lon,
                "provider": loc.provider,
                "sensor_id": loc.pm25_sensor_id,
                "last_seen": loc.last_seen,
            }
        )
    n = store.upsert_stations(rows, now.isoformat())
    live = {r["id"] for r in rows}
    store.x(
        f"UPDATE stations SET active=CASE WHEN id IN ({','.join('?' * len(live)) or 'NULL'}) THEN 1 ELSE 0 END WHERE source='openaq'",
        list(live),
    )
    return {"active": n, "skipped_low_cost_or_no_coords": skipped_sensor, "skipped_stale": skipped_stale}


def ingest_latest(store: Store, source: LatestSource) -> int:
    known = {r["id"] for r in store.q("SELECT id FROM stations")}
    n = 0
    by_station: dict[str, dict[datetime, float]] = {}
    for loc, hour, value in source.latest():
        sid = f"oaq:{loc}"
        if sid in known and 0 < value < 1500:
            by_station.setdefault(sid, {})[hour] = value
    for sid, series in by_station.items():
        n += store.put_obs(sid, series)
        last = max(series)
        store.x("UPDATE stations SET last_seen=? WHERE id=? AND (last_seen IS NULL OR last_seen<?)", (last.isoformat(), sid, last.isoformat()))
    return n


def ingest_cams(store: Store, source: CamsSource, *, past_days: int = 15, forecast_days: int = 3, batch: int = 50) -> int:
    coords = station_coords(store)
    ids = sorted(coords)
    fetched_at = now_ist().isoformat()
    n = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        series_list = source.cams_many([coords[s] for s in chunk], past_days, forecast_days)
        for sid, series in zip(chunk, series_list):
            n += store.put_cams(sid, series, fetched_at)
    return n


# --- publishing ------------------------------------------------------------------------


def best_forecast(store: Store, sid: str, target: date, issued_at: datetime) -> Forecast | None:
    ds = day_start(target)
    obs = obs_before(store.get_obs(sid, ds - timedelta(days=16), ds), issued_at)
    cams = store.get_cams(sid, ds - timedelta(days=16), ds + timedelta(days=1))
    for m in MODEL_PREFERENCE:
        f = make_forecast(m, obs=obs, cams=cams, day_start=ds, issued_at=issued_at)
        if f is not None:
            return f
    return None


def recommend(f: Forecast, target: date, scenarios: Iterable[Scenario] = SCENARIOS) -> list[dict]:
    out = []
    for sc in scenarios:
        p = plan_window(
            f.values,
            activity=sc.activity,
            age=sc.age,
            minutes=sc.minutes,
            earliest=at(target, sc.earliest),
            latest_end=at(target, sc.latest_end),
            habitual_start=at(target, sc.habitual),
        )
        if p.status != "ok" or p.best is None:
            continue
        out.append(
            {
                "scenario": sc.key,
                "start": p.best.start.strftime("%H:%M"),
                "habitual": sc.habitual.strftime("%H:%M"),
                "forecast_mean": round(p.best.mean_conc, 1),
                "forecast_habitual_mean": round(p.habitual.mean_conc, 1) if p.habitual else None,
            }
        )
    return out


def publish(
    store: Store,
    target: date,
    *,
    issued_at: datetime | None = None,
    anchor: Callable[[str], dict[str, bytes]] | None = submit_opentimestamps,
) -> dict:
    """Forecast + recommend for every active station, commit and anchor."""
    issued_at = issued_at or now_ist()
    if issued_at >= day_start(target):
        raise ValueError("a commitment must be issued before its day starts")
    if store.one("SELECT day FROM commitments WHERE day=?", (target.isoformat(),)):
        return {"day": target.isoformat(), "status": "exists"}
    recs: list[dict] = []
    models: dict[str, int] = {}
    forecasts_rows = []
    for sid in sorted(station_coords(store)):
        f = best_forecast(store, sid, target, issued_at)
        if f is None:
            continue
        models[f.model] = models.get(f.model, 0) + 1
        forecasts_rows.append(
            (
                sid,
                target.isoformat(),
                f.model,
                issued_at.isoformat(),
                json.dumps({t.strftime("%H"): round(v, 1) for t, v in sorted(f.values.items())}),
                json.dumps({t.strftime("%H"): round(v, 3) for t, v in sorted(f.sigma_log.items())}),
            )
        )
        for r in recommend(f, target):
            recs.append({"station": sid, "model": f.model, **r})
    if not recs:
        return {"day": target.isoformat(), "status": "no_data"}
    model_label = max(models, key=models.get)
    c = build_commitment(target.isoformat(), issued_at.isoformat(), model_label, recs)
    ots = None
    if anchor is not None:
        proofs = anchor(c.sha256)
        ots = ots_file(c.sha256, proofs)
    with store.tx() as db:
        db.executemany(
            "INSERT OR REPLACE INTO forecasts(station_id, day, model, issued_at, values_json, sigma_json) VALUES (?,?,?,?,?,?)",
            forecasts_rows,
        )
        db.executemany(
            """INSERT OR REPLACE INTO recommendations(day, station_id, scenario, start, habitual, forecast_mean, forecast_habitual_mean)
               VALUES (?,?,?,?,?,?,?)""",
            [
                (c.day, r["station"], r["scenario"], r["start"], r["habitual"], r["forecast_mean"], r["forecast_habitual_mean"])
                for r in recs
            ],
        )
        db.execute(
            """INSERT INTO commitments(day, issued_at, model, sha256, n_stations, n_recommendations, payload, anchor)
               VALUES (?,?,?,?,?,?,?,?)""",
            (c.day, c.issued_at, c.model, c.sha256, c.n_stations, c.n_recommendations, c.payload, "opentimestamps" if ots else None),
        )
        if ots:
            db.execute(
                "INSERT INTO events(ts, kind, meta) VALUES (?,?,?)",
                (issued_at.isoformat(), "ots_proof", json.dumps({"day": c.day, "ots_hex": ots.hex()})),
            )
    return {"day": c.day, "status": "published", "sha256": c.sha256, "stations": c.n_stations, "recommendations": c.n_recommendations, "anchored": bool(ots)}


# --- verification ----------------------------------------------------------------------


def verify(store: Store, target: date, *, step_minutes: int = 15) -> dict:
    ds = day_start(target)
    scen = {s.key: s for s in SCENARIOS}
    recs = store.q("SELECT * FROM recommendations WHERE day=?", (target.isoformat(),))
    verified_at = now_ist().isoformat()
    rows = []
    counts = {"verified": 0, "unverifiable": 0}
    obs_cache: dict[str, dict] = {}
    for r in recs:
        sc = scen.get(r["scenario"])
        if sc is None:
            continue
        sid = r["station_id"]
        if sid not in obs_cache:
            obs_cache[sid] = store.get_obs(sid, ds, ds + timedelta(days=1))
        obs = obs_cache[sid]
        rate = inhalation_rate(sc.activity, sc.age)
        earliest, latest_end = at(target, sc.earliest), at(target, sc.latest_end)
        hab_start = at(target, sc.habitual)
        hab = interval_dose(obs, hab_start, sc.minutes, rate)
        oracle_start, oracle = None, None
        for s in candidate_starts(earliest, latest_end, sc.minutes, step_minutes):
            d = interval_dose(obs, s, sc.minutes, rate)
            if d is not None and (oracle is None or d.dose_ug < oracle.dose_ug):
                oracle_start, oracle = s, d
        rule = min(max(at(target, RULE_OF_THUMB), earliest), latest_end - timedelta(minutes=sc.minutes))
        khidki_start = datetime.combine(target, time.fromisoformat(r["start"]), tzinfo=IST)
        for policy, start in (("khidki", khidki_start), ("habitual", hab_start), ("rule_of_thumb", rule), ("oracle", oracle_start)):
            d = interval_dose(obs, start, sc.minutes, rate) if start else None
            ok = d is not None and hab is not None and oracle is not None
            counts["verified" if ok else "unverifiable"] += 1 if policy == "khidki" else 0
            rows.append(
                (
                    target.isoformat(),
                    sid,
                    sc.key,
                    policy,
                    "verified" if ok else "unverifiable",
                    start.strftime("%H:%M") if start else None,
                    round(d.mean_conc, 2) if ok else None,
                    round(d.dose_ug, 3) if ok else None,
                    round(hab.dose_ug, 3) if ok else None,
                    round(oracle.dose_ug, 3) if ok else None,
                    verified_at,
                )
            )
    with store.tx() as db:
        db.executemany(
            """INSERT OR REPLACE INTO verdicts(day, station_id, scenario, policy, status, start, mean_conc, dose_ug,
               habitual_dose_ug, oracle_dose_ug, verified_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return {"day": target.isoformat(), **counts}


def scoreboard(store: Store, since: str | None = None) -> dict:
    """Aggregate verified results: totals per scenario and policy."""
    args: list = []
    where = "status='verified'"
    if since:
        where += " AND day>=?"
        args.append(since)
    rows = store.q(
        f"""SELECT scenario, policy, COUNT(*) n, SUM(dose_ug) dose, SUM(habitual_dose_ug) hab, SUM(oracle_dose_ug) ora,
                   SUM(CASE WHEN dose_ug < habitual_dose_ug - 1e-9 THEN 1 ELSE 0 END) better,
                   SUM(CASE WHEN dose_ug > habitual_dose_ug + 1e-9 THEN 1 ELSE 0 END) worse,
                   MIN(day) first_day, MAX(day) last_day, COUNT(DISTINCT station_id) stations
            FROM verdicts WHERE {where} GROUP BY scenario, policy""",
        args,
    )
    out: dict = {}
    for r in rows:
        hab, dose, ora = r["hab"] or 0, r["dose"] or 0, r["ora"] or 0
        out.setdefault(r["scenario"], {})[r["policy"]] = {
            "station_days": r["n"],
            "stations": r["stations"],
            "reduction_vs_habitual_pct": round(100 * (hab - dose) / hab, 2) if hab else None,
            "captured_of_hindsight_best_pct": round(100 * (hab - dose) / (hab - ora), 1) if hab - ora > 1e-9 else None,
            "better_than_habit_pct": round(100 * r["better"] / r["n"], 1),
            "worse_than_habit_pct": round(100 * r["worse"] / r["n"], 1),
            "first_day": r["first_day"],
            "last_day": r["last_day"],
        }
    return out


# --- audit -----------------------------------------------------------------------------


def run_audit(store: Store, target: date) -> dict:
    ds = day_start(target)
    coords = station_coords(store)
    series = {sid: store.get_obs(sid, ds, ds + timedelta(days=1)) for sid in coords}
    flags = audit_day(ds, coords, {k: v for k, v in series.items() if v})
    created = now_ist().isoformat()
    with store.tx() as db:
        db.execute("DELETE FROM audit_flags WHERE day=?", (target.isoformat(),))
        db.executemany(
            "INSERT INTO audit_flags(day, station_id, kind, severity, detail, created_at) VALUES (?,?,?,?,?,?)",
            [(f.day, f.station_id, f.kind, f.severity, json.dumps(f.detail), created) for f in flags],
        )
    kinds: dict[str, int] = {}
    for f in flags:
        kinds[f.kind] = kinds.get(f.kind, 0) + 1
    return {"day": target.isoformat(), "stations": len(coords), "flags": len(flags), "by_kind": kinds}


# --- the hourly tick -------------------------------------------------------------------


def tick(store: Store, *, latest: LatestSource | None, cams: CamsSource | None, now: datetime | None = None) -> dict:
    """Run whatever is due. Idempotent: safe to call every hour (or more)."""
    now = now or now_ist()
    out: dict = {"now": now.isoformat()}
    run_id = store.x("INSERT INTO runs(job, started_at) VALUES (?,?)", ("tick", now.isoformat()))
    try:
        if latest is not None and hasattr(latest, "india_pm25_locations"):
            last = store.one("SELECT MAX(updated_at) u FROM stations WHERE source='openaq'")
            if not last or not last["u"] or datetime.fromisoformat(last["u"]) < now - timedelta(hours=20):
                out["stations"] = refresh_stations(store, latest)
        if latest is not None:
            out["obs"] = ingest_latest(store, latest)
        tomorrow = now.date() + timedelta(days=1)
        if now.hour >= PUBLISH_HOUR - 1 and cams is not None:
            last = store.one("SELECT MAX(fetched_at) f FROM cams")
            if not last or not last["f"] or datetime.fromisoformat(last["f"]) < now - timedelta(hours=12):
                out["cams"] = ingest_cams(store, cams)
        if now.hour >= PUBLISH_HOUR:
            out["publish"] = publish(store, tomorrow, issued_at=now)
        yesterday = now.date() - timedelta(days=1)
        if now.hour >= VERIFY_LAG_HOURS and not store.one(
            "SELECT 1 FROM verdicts WHERE day=? LIMIT 1", (yesterday.isoformat(),)
        ):
            if store.one("SELECT 1 FROM recommendations WHERE day=? LIMIT 1", (yesterday.isoformat(),)):
                out["verify"] = verify(store, yesterday)
            out["audit"] = run_audit(store, yesterday)
        store.x("UPDATE runs SET finished_at=?, ok=1, detail=? WHERE id=?", (now_ist().isoformat(), json.dumps(out, default=str), run_id))
    except Exception as e:  # recorded, then re-raised so the scheduler sees the failure
        store.x("UPDATE runs SET finished_at=?, ok=0, detail=? WHERE id=?", (now_ist().isoformat(), repr(e), run_id))
        raise
    return out
