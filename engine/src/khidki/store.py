"""SQLite storage. One file, replicated to object storage by Litestream in
production. All timestamps are ISO-8601 strings with an explicit offset."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stations (
  id TEXT PRIMARY KEY,              -- 'oaq:<location_id>'
  source TEXT NOT NULL,
  name TEXT NOT NULL,
  city TEXT,
  state TEXT,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  provider TEXT,
  sensor_id INTEGER,
  active INTEGER NOT NULL DEFAULT 1,
  last_seen TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS obs (
  station_id TEXT NOT NULL,
  hour TEXT NOT NULL,               -- hour start, IST
  pm25 REAL NOT NULL,
  PRIMARY KEY (station_id, hour)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS cams (
  station_id TEXT NOT NULL,
  hour TEXT NOT NULL,
  pm25 REAL NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (station_id, hour)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS forecasts (
  station_id TEXT NOT NULL,
  day TEXT NOT NULL,                -- target day YYYY-MM-DD (IST)
  model TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  values_json TEXT NOT NULL,        -- {"HH": µg/m³}
  sigma_json TEXT NOT NULL,
  PRIMARY KEY (station_id, day, model)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS commitments (
  day TEXT PRIMARY KEY,             -- target day
  issued_at TEXT NOT NULL,
  model TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  n_stations INTEGER NOT NULL,
  n_recommendations INTEGER NOT NULL,
  payload TEXT NOT NULL,            -- canonical JSON that was hashed
  anchor TEXT                       -- where the hash was published (URL)
);

CREATE TABLE IF NOT EXISTS recommendations (
  day TEXT NOT NULL,
  station_id TEXT NOT NULL,
  scenario TEXT NOT NULL,
  start TEXT NOT NULL,              -- HH:MM
  habitual TEXT NOT NULL,
  forecast_mean REAL NOT NULL,
  forecast_habitual_mean REAL,
  PRIMARY KEY (day, station_id, scenario)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS verdicts (
  day TEXT NOT NULL,
  station_id TEXT NOT NULL,
  scenario TEXT NOT NULL,
  policy TEXT NOT NULL,             -- khidki | habitual | rule_of_thumb | oracle
  status TEXT NOT NULL,             -- verified | unverifiable
  start TEXT,
  mean_conc REAL,
  dose_ug REAL,
  habitual_dose_ug REAL,
  oracle_dose_ug REAL,
  verified_at TEXT NOT NULL,
  PRIMARY KEY (day, station_id, scenario, policy)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS audit_flags (
  day TEXT NOT NULL,
  station_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  detail TEXT NOT NULL,             -- JSON
  created_at TEXT NOT NULL,
  PRIMARY KEY (day, station_id, kind)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel TEXT NOT NULL,            -- telegram | web
  external_id TEXT NOT NULL,        -- chat id / anonymous web id
  lang TEXT NOT NULL DEFAULT 'en',
  lat REAL,
  lon REAL,
  created_at TEXT NOT NULL,
  UNIQUE (channel, external_id)
);

CREATE TABLE IF NOT EXISTS routines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  activity TEXT NOT NULL,
  age TEXT NOT NULL DEFAULT 'adult',
  minutes INTEGER NOT NULL,
  habitual TEXT NOT NULL,           -- HH:MM
  earliest TEXT NOT NULL,
  latest_end TEXT NOT NULL,
  label TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  start TEXT NOT NULL,
  habitual TEXT NOT NULL,
  forecast_mean REAL,
  forecast_habitual_mean REAL,
  nudged_at TEXT,
  answered TEXT,                    -- went_planned | went_usual | skipped | other
  answered_at TEXT,
  went_at TEXT,                     -- HH:MM actually reported
  UNIQUE (routine_id, day)
);

CREATE TABLE IF NOT EXISTS outcomes (
  plan_id INTEGER PRIMARY KEY REFERENCES plans(id) ON DELETE CASCADE,
  status TEXT NOT NULL,             -- verified | unverifiable
  went_mean REAL,
  habitual_mean REAL,
  dose_avoided_ug REAL,
  reduction_pct REAL,
  verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  meta TEXT
);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);

CREATE TABLE IF NOT EXISTS bulletins (
  day TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  text TEXT NOT NULL,
  flags INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER,
  detail TEXT
);
"""


class Store:
    def __init__(self, path: str | Path = "data/khidki.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self.db.execute("BEGIN")
            try:
                yield self.db
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def q(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.db.execute(sql, tuple(args)))

    def one(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: Iterable[Any] = ()) -> int:
        with self._lock:
            cur = self.db.execute(sql, tuple(args))
            return cur.lastrowid or cur.rowcount

    # --- stations / observations ---------------------------------------------------

    def upsert_stations(self, rows: Iterable[Mapping[str, Any]], now: str) -> int:
        n = 0
        with self.tx() as db:
            for r in rows:
                db.execute(
                    """INSERT INTO stations(id, source, name, city, state, lat, lon, provider, sensor_id, active, last_seen, updated_at)
                       VALUES (:id, :source, :name, :city, :state, :lat, :lon, :provider, :sensor_id, 1, :last_seen, :now)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, city=excluded.city, state=excluded.state,
                         lat=excluded.lat, lon=excluded.lon, provider=excluded.provider, sensor_id=excluded.sensor_id,
                         last_seen=COALESCE(excluded.last_seen, stations.last_seen), updated_at=excluded.updated_at""",
                    {"city": None, "state": None, "provider": None, "sensor_id": None, "last_seen": None, **r, "now": now},
                )
                n += 1
        return n

    def put_obs(self, station_id: str, series: Mapping[datetime, float]) -> int:
        with self.tx() as db:
            db.executemany(
                "INSERT INTO obs(station_id, hour, pm25) VALUES (?,?,?) ON CONFLICT DO UPDATE SET pm25=excluded.pm25",
                [(station_id, t.isoformat(), float(v)) for t, v in series.items()],
            )
        return len(series)

    def get_obs(self, station_id: str, start: datetime, end: datetime) -> dict[datetime, float]:
        rows = self.q(
            "SELECT hour, pm25 FROM obs WHERE station_id=? AND hour>=? AND hour<? ORDER BY hour",
            (station_id, start.isoformat(), end.isoformat()),
        )
        return {datetime.fromisoformat(r["hour"]): r["pm25"] for r in rows}

    def put_cams(self, station_id: str, series: Mapping[datetime, float], fetched_at: str) -> int:
        with self.tx() as db:
            db.executemany(
                """INSERT INTO cams(station_id, hour, pm25, fetched_at) VALUES (?,?,?,?)
                   ON CONFLICT DO UPDATE SET pm25=excluded.pm25, fetched_at=excluded.fetched_at""",
                [(station_id, t.isoformat(), float(v), fetched_at) for t, v in series.items()],
            )
        return len(series)

    def get_cams(self, station_id: str, start: datetime, end: datetime) -> dict[datetime, float]:
        rows = self.q(
            "SELECT hour, pm25 FROM cams WHERE station_id=? AND hour>=? AND hour<? ORDER BY hour",
            (station_id, start.isoformat(), end.isoformat()),
        )
        return {datetime.fromisoformat(r["hour"]): r["pm25"] for r in rows}

    def event(self, kind: str, ts: str, meta: Mapping[str, Any] | None = None) -> None:
        self.x("INSERT INTO events(ts, kind, meta) VALUES (?,?,?)", (ts, kind, json.dumps(meta or {})))
