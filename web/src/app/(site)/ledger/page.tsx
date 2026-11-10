import type { Metadata } from "next";
import Nav from "@/components/Nav";
import LedgerRow from "@/components/ledger/LedgerRow";
import s from "@/components/ledger/ledger.module.css";
import { api, settle, type ScoreRow } from "@/lib/api";
import { dayLabel, int, nowIST, signedPct } from "@/lib/format";
import { REPLAY } from "@/lib/site";

export const revalidate = 120;

export const metadata: Metadata = {
  title: "Ledger",
  description:
    "Every Khidki recommendation is published the night before, sealed with SHA-256 and OpenTimestamps, then scored against measured air. Verify any day in your browser.",
  alternates: { canonical: "/ledger" },
};

const SCENARIOS: Record<string, string> = {
  morning_walk: "Daily walk, 60 min · usually 06:00",
  runner: "Run, 45 min · usually 06:00",
  school_play: "School outdoor play, 45 min · usually 08:00, school hours",
  evening_walk: "Evening walk, 60 min · usually 18:30, 15:00–22:00",
  before_work: "Walk that must end by 10:00, 45 min · usually 06:30",
};

const ORDER = ["morning_walk", "school_play", "evening_walk", "before_work", "runner"];

function change(row?: ScoreRow) {
  if (!row || row.reduction_vs_habitual_pct == null) return "—";
  return signedPct(-row.reduction_vs_habitual_pct, 1);
}

export default async function LedgerPage() {
  const [ledger, score] = await Promise.all([settle(api.ledger()), settle(api.scoreboard())]);
  const commitments = ledger?.commitments ?? null;
  const scen = score
    ? ORDER.filter((k) => score.by_scenario[k]).concat(Object.keys(score.by_scenario).filter((k) => !ORDER.includes(k)))
    : [];
  const before21 = nowIST().hour < 21;

  return (
    <>
      <div className="wrap">
        <Nav />
      </div>
      <main id="main">
        <div className="wrap">
          <header className="page-head">
            <h1>Published before the day. Checked after it.</h1>
            <p className="lede">
              Every night at 21:00 IST Khidki writes tomorrow&apos;s recommended hours for every monitor it covers into one file,
              seals it with SHA-256 and stamps the hash with OpenTimestamps. The next day each call is scored against what the
              monitors measured. Nothing can be quietly edited afterwards.
            </p>
          </header>

          <section className="sec" aria-labelledby="days-h">
            <div className={s.secHead}>
              <h2 className="h2" id="days-h">
                Published days
              </h2>
              <div className={s.how}>
                <p>
                  <span className="mono">1</span> Download a day&apos;s JSON. It is served byte for byte as it was hashed.
                </p>
                <p>
                  <span className="mono">2</span> Hash it: <span className="mono">sha256sum 2026-11-11.json</span>, or press
                  Verify and your browser does it.
                </p>
                <p>
                  <span className="mono">3</span> Check the .ots proof with <span className="mono">ots verify</span> or
                  opentimestamps.org: it proves the hash existed before the day began.
                </p>
              </div>
            </div>

            {commitments === null ? (
              <div className="empty">
                <strong>The ledger is unreachable right now</strong>
                Nothing is lost: every day is stored with its hash. Try again in a minute.
              </div>
            ) : commitments.length === 0 ? (
              <div className="empty">
                <strong>{before21 ? "First publication: tonight, 21:00 IST" : "Publication runs nightly at 21:00 IST"}</strong>
                The first file will hold tomorrow&apos;s recommended hours for every covered monitor, with its SHA-256 and
                timestamp proof. It will appear here the moment it is sealed.
              </div>
            ) : (
              <ul className={s.list}>
                {commitments.map((c) => (
                  <LedgerRow key={c.day} c={c} />
                ))}
              </ul>
            )}
          </section>

          <section className="sec" aria-labelledby="score-h">
            <div className={s.secHead}>
              <h2 className="h2" id="score-h">
                Scoreboard
              </h2>
              <p className="body">
                Each published hour against three others on the same measured air: the person&apos;s usual time, a fixed 15:00
                rule (or the latest start the hours allow), and the best hour in hindsight. Change in PM2.5 breathed vs the usual
                time; misses stay in.
              </p>
            </div>
            {score === null ? (
              <div className="empty">
                <strong>The scoreboard is unreachable right now</strong>
                Try again in a minute.
              </div>
            ) : scen.length === 0 ? (
              <div className="empty">
                <strong>Nothing checked yet</strong>A published day is scored the morning after it ends, once the monitors have
                reported every hour.
                {commitments && commitments.length > 0
                  ? ` The first is ${dayLabel(commitments[commitments.length - 1].day)}.`
                  : ""}
              </div>
            ) : (
              <div className="table-wrap">
                <table className="tbl tbl-wide">
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th className="num">Monitor-days</th>
                      <th className="num">Khidki</th>
                      <th className="num">Fixed 15:00</th>
                      <th className="num">Best in hindsight</th>
                      <th className="num">Khidki worse than usual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scen.map((k) => {
                      const r = score.by_scenario[k];
                      return (
                        <tr key={k}>
                          <td>{SCENARIOS[k] ?? k}</td>
                          <td className="num mono">{int(r.khidki?.station_days)}</td>
                          <td className="num mono">{change(r.khidki)}</td>
                          <td className="num mono">{change(r.rule_of_thumb)}</td>
                          <td className="num mono">{change(r.oracle)}</td>
                          <td className="num mono">{r.khidki ? `${r.khidki.worse_than_habit_pct}% of days` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {score.days.length > 0 && (
                  <p className={`small ${s.after}`}>Checked days: {score.days.map((d) => dayLabel(d.day)).join(", ")}.</p>
                )}
              </div>
            )}
          </section>

          <section className="sec" id="replay" aria-labelledby="replay-h">
            <div className={s.secHead}>
              <div>
                <p className={s.tag}>Replay, not published in advance</p>
                <h2 className="h2" id="replay-h">
                  Winter 2025–26 at Chanakyapuri
                </h2>
              </div>
              <p className="body">
                Before going live, the same forecast and planner were replayed day by day on {REPLAY.station} ({REPLAY.period}),
                using only data available the evening before. Change in PM2.5 breathed vs the usual time.
              </p>
            </div>
            <div className="table-wrap">
              <table className="tbl tbl-wide">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Usual · allowed</th>
                    <th className="num">Days</th>
                    <th className="num">Khidki</th>
                    <th className="num">Fixed 15:00</th>
                    <th className="num">Best in hindsight</th>
                    <th className="num">Khidki worse than usual</th>
                  </tr>
                </thead>
                <tbody>
                  {REPLAY.rows.map((r) => (
                    <tr key={r.scenario} className={r.khidki > 0 ? s.miss : undefined}>
                      <td>{r.scenario}</td>
                      <td className="mono">
                        {r.usual} · {r.allowed}
                      </td>
                      <td className="num mono">{r.days}</td>
                      <td className="num mono">{signedPct(r.khidki, 1)}</td>
                      <td className="num mono">{signedPct(r.fixed, 1)}</td>
                      <td className="num mono">{signedPct(r.hindsight, 1)}</td>
                      <td className="num mono">{r.worseDays}% of days</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={s.plain}>
              <p>
                Said plainly: in a smoggy Delhi winter, a fixed 3 pm rule does as well as Khidki (
                {signedPct(REPLAY.rows[0].fixed)} vs {signedPct(REPLAY.rows[0].khidki)} for the morning walk). When the walk must
                end by 10:00, Khidki made it slightly worse ({signedPct(REPLAY.rows[3].khidki, 1)}). A weather-aware
                machine-learning model did no better ({signedPct(REPLAY.mlModel)} on the morning walk).
              </p>
              <p className="small">
                Fixed 15:00 is clamped to the latest start the allowed hours permit (13:15 for school play, 09:15 for the 10:00
                deadline). Source: engine/results in the public repository.
              </p>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
