import type { Metadata } from "next";
import Nav from "@/components/Nav";
import Bulletin from "@/components/monitors/Bulletin";
import s from "@/components/monitors/monitors.module.css";
import { api, settle, type AuditFlag, type Station } from "@/lib/api";
import { dateTimeIST, dayLabel, int, nowIST, ug } from "@/lib/format";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Monitor health",
  description:
    "A daily data-quality audit of India's government PM2.5 monitors: silent monitors, missing hours, gaps during Severe air, frozen values and disagreements with neighbours.",
  alternates: { canonical: "/monitors" },
};

type Kind =
  "silent" | "missing_hours" | "dark_during_severe" | "frozen_value" | "disagrees_with_neighbours" | "implausible_value";

const KINDS: { kind: Kind; title: string; plain: string }[] = [
  { kind: "silent", title: "Silent all day", plain: "The monitor reported no PM2.5 reading for any of the 24 hours." },
  { kind: "missing_hours", title: "Missing hours", plain: "Four or more hourly readings are missing from the day." },
  {
    kind: "dark_during_severe",
    title: "Dark while neighbours read Severe",
    plain: "No reading in hours when the monitors within 10 km read Severe (250 µg/m³ or more).",
  },
  { kind: "frozen_value", title: "Frozen value", plain: "The exact same value repeated for four hours or more in a row." },
  {
    kind: "disagrees_with_neighbours",
    title: "Disagrees with neighbours",
    plain: "The day's average is at least double, or under half, the median of monitors within 10 km.",
  },
  { kind: "implausible_value", title: "Impossible value", plain: "A reading of zero or below, or 999 and above." },
];

function kindOf(f: AuditFlag): Kind {
  if (f.kind === "missing_hours" && Number(f.detail?.missing) >= 24) return "silent";
  return (KINDS.find((k) => k.kind === f.kind)?.kind ?? "missing_hours") as Kind;
}

function cityOf(name: string | null, city: string | null): string {
  if (city) return city;
  const m = name?.match(/,\s*([^,]+?)\s*-\s*[A-Za-z]+\s*$/);
  return m ? m[1] : "City not listed";
}

/** ["00","01","02","13"] → "00–02, 13" */
function hourRanges(hours: unknown): string {
  if (!Array.isArray(hours)) return "";
  const hs = hours
    .map(Number)
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < hs.length; i++) {
    const a = hs[i];
    let b = a;
    while (i + 1 < hs.length && hs[i + 1] === b + 1) b = hs[++i];
    const p = (n: number) => String(n).padStart(2, "0");
    out.push(a === b ? p(a) : `${p(a)}–${p(b)}`);
  }
  return out.join(", ");
}

function flagDetail(f: AuditFlag, k: Kind): string {
  const d = f.detail ?? {};
  switch (k) {
    case "silent":
      return "no readings";
    case "missing_hours":
      return `${d.missing} hours missing: ${hourRanges(d.hours)}`;
    case "dark_during_severe": {
      const med = Array.isArray(d.neighbour_median) ? (d.neighbour_median as number[]) : [];
      const range = med.length ? ` · neighbours ${Math.min(...med)}–${Math.max(...med)} µg/m³` : "";
      return `hours ${hourRanges(d.hours)}${range}`;
    }
    case "frozen_value":
      return `${d.value} µg/m³ for ${d.hours} hours from ${String(d.from).padStart(2, "0")}:00`;
    case "disagrees_with_neighbours":
      return `day mean ${d.station_mean} vs neighbours ${d.neighbour_mean} µg/m³`;
    case "implausible_value":
      return `hours ${hourRanges(d.hours)}`;
  }
}

function groupByCity(stations: Station[]) {
  const m = new Map<string, Station[]>();
  for (const st of stations) {
    const c = cityOf(st.name, st.city);
    if (!m.has(c)) m.set(c, []);
    m.get(c)!.push(st);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

export default async function MonitorsPage() {
  const [audit, stations, bulletin] = await Promise.all([settle(api.audit()), settle(api.stations()), settle(api.bulletin())]);

  const counts = new Map<Kind, number>();
  const byCity = new Map<string, Map<string, { name: string; flags: { k: Kind; f: AuditFlag }[] }>>();
  for (const f of audit?.flags ?? []) {
    const k = kindOf(f);
    counts.set(k, (counts.get(k) ?? 0) + 1);
    const city = cityOf(f.name, f.city);
    if (!byCity.has(city)) byCity.set(city, new Map());
    const m = byCity.get(city)!;
    if (!m.has(f.station_id)) m.set(f.station_id, { name: f.name ?? f.station_id, flags: [] });
    m.get(f.station_id)!.flags.push({ k, f });
  }
  const flaggedMonitors = new Set((audit?.flags ?? []).map((f) => f.station_id)).size;
  const cities = [...byCity.entries()].sort((a, b) => b[1].size - a[1].size || a[0].localeCompare(b[0]));
  const live = stations?.stations.filter((x) => x.latest != null) ?? [];
  // The engine falls back to today's date when no audit has been stored yet.
  const notYet = !!audit && audit.flags.length === 0 && audit.day >= nowIST().date;

  return (
    <>
      <div className="wrap">
        <Nav />
      </div>
      <main id="main">
        <div className="wrap">
          <header className="page-head">
            <h1>Monitor health</h1>
            <p className="lede">
              Every day Khidki checks each government PM2.5 monitor it reads for gaps and odd values, and publishes what it finds.
              A flag is a data-quality signal, not a judgement about anyone: a monitor can go quiet for many ordinary reasons.
            </p>
          </header>

          <section className="sec" aria-labelledby="audit-h">
            {audit === null ? (
              <div className="empty">
                <strong>The audit is unreachable right now</strong>
                Try again in a minute.
              </div>
            ) : (
              <>
                <div className={s.top}>
                  <div>
                    <h2 className="h2" id="audit-h">
                      {notYet
                        ? "No audit published yet"
                        : dayLabel(audit.day, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                    </h2>
                    <p className={s.sub}>
                      {notYet
                        ? `The audit runs each morning for the day before. The first one covers ${dayLabel(audit.day, { day: "numeric", month: "long" })}.`
                        : "Latest audited day, hours in IST"}
                    </p>
                  </div>
                  {!notYet && (
                    <dl className={s.totals}>
                      <div>
                        <dt>Monitors audited</dt>
                        <dd>{int(audit.stations_audited)}</dd>
                      </div>
                      <div>
                        <dt>With a data-quality flag</dt>
                        <dd>{int(flaggedMonitors)}</dd>
                      </div>
                      <div>
                        <dt>Flags raised</dt>
                        <dd>{int(audit.flags.length)}</dd>
                      </div>
                    </dl>
                  )}
                </div>

                <ul className={s.kinds}>
                  {KINDS.map((k) => (
                    <li key={k.kind} className={(counts.get(k.kind) ?? 0) === 0 ? s.zero : undefined}>
                      <p className={s.kindN}>{notYet ? "–" : int(counts.get(k.kind) ?? 0)}</p>
                      <p className={s.kindT}>{k.title}</p>
                      <p className={s.kindP}>{k.plain}</p>
                    </li>
                  ))}
                </ul>

                {notYet ? null : cities.length === 0 ? (
                  <div className="empty">
                    <strong>No flags for this day</strong>
                    No monitor crossed a data-quality threshold on this day.
                  </div>
                ) : (
                  <div className={s.cities}>
                    {cities.map(([city, mons]) => (
                      <section key={city} className={s.city} aria-label={city}>
                        <h3 className={s.cityT}>
                          {city} <span className={s.cityN}>{mons.size} flagged</span>
                        </h3>
                        <ul>
                          {[...mons.entries()]
                            .sort((a, b) => a[1].name.localeCompare(b[1].name))
                            .map(([id, m]) => (
                              <li key={id} className={s.mon}>
                                <p className={s.monName}>{m.name}</p>
                                <ul className={s.monFlags}>
                                  {m.flags.map(({ k, f }, i) => (
                                    <li key={i}>
                                      <span className={s.flagT}>{KINDS.find((x) => x.kind === k)?.title}</span>
                                      <span className="mono">{flagDetail(f, k)}</span>
                                    </li>
                                  ))}
                                </ul>
                              </li>
                            ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>

          {bulletin?.status === "ok" && bulletin.text && (
            <section className="sec" aria-labelledby="bulletin-h">
              <div className={s.top}>
                <div>
                  <h2 className="h2" id="bulletin-h">
                    The day&apos;s bulletin
                  </h2>
                  <p className={s.sub}>
                    Written by Khidki&apos;s auditor from the flags above
                    {bulletin.created_at ? ` · ${dateTimeIST(bulletin.created_at)}` : ""}
                  </p>
                </div>
              </div>
              <Bulletin text={bulletin.text} />
            </section>
          )}

          <section className="sec" aria-labelledby="list-h">
            <h2 className="h2" id="list-h">
              Every monitor Khidki reads
            </h2>
            <p className={`body ${s.listLede}`}>
              {stations
                ? `${int(stations.count)} government monitors; ${int(live.length)} with a recent reading. Latest hourly PM2.5, as reported via OpenAQ.`
                : "The monitor list is unreachable right now."}
            </p>
            {stations && (
              <details className={s.all}>
                <summary>Show all {int(stations.count)} monitors by city</summary>
                <div className="table-wrap">
                  <table className="tbl tbl-wide">
                    <thead>
                      <tr>
                        <th>Monitor</th>
                        <th>City</th>
                        <th className="num">PM2.5 µg/m³</th>
                        <th>Category</th>
                        <th>Hour</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupByCity(stations.stations).flatMap(([city, list]) =>
                        list
                          .sort((a, b) => a.name.localeCompare(b.name))
                          .map((st) => (
                            <tr key={st.id}>
                              <td>{st.name}</td>
                              <td>{city}</td>
                              <td className="num mono">{st.latest != null ? ug(st.latest) : "—"}</td>
                              <td>{st.category ?? "no recent reading"}</td>
                              <td className="mono">{st.latest_hour ? dateTimeIST(st.latest_hour).replace(" IST", "") : "—"}</td>
                            </tr>
                          )),
                      )}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </section>
        </div>
      </main>
    </>
  );
}
