import Link from "next/link";
import DayStrip from "@/components/DayStrip";
import Hero from "@/components/hero/Hero";
import { API_BASE, api, settle } from "@/lib/api";
import { dayLabel, hh, int, nowIST, shortHash, signedPct, ug } from "@/lib/format";
import { getHeroData } from "@/lib/hero";
import { HERO_PLACE, MCP_URL, NATIONAL, REPLAY, SITE_URL } from "@/lib/site";
import s from "./landing.module.css";

export const revalidate = 60;

export default async function Home() {
  const [hero, impact, ledger] = await Promise.all([getHeroData(), settle(api.impact()), settle(api.ledger())]);

  const caption =
    hero.kind === "live" ? (
      <>
        <span className={s.capLive}>
          {hero.when} over {HERO_PLACE.name} ·{" "}
          {hero.result.source === "cams_only"
            ? "CAMS regional forecast"
            : hero.measured.some(Boolean)
              ? "forecast + measured"
              : "forecast"}
          .
        </span>{" "}
        {hero.when === "Today" ? "Cleanest hour left today for a walk" : "Cleanest hour for a walk"}:{" "}
        <span className="mono">{ug(hero.result.best!.mean_pm25)} µg/m³</span> from {hh(hero.open)} to {hh(hero.close)}
        {hero.result.usual ? (
          <>
            , <span className="mono">{ug(hero.result.usual.mean_pm25)}</span> at the usual 06:00
          </>
        ) : null}
        .
      </>
    ) : (
      <>
        Winter median by hour, CPCB Chanakyapuri. A typical winter afternoon: <span className="mono">101 µg/m³</span> from 14:00
        to 18:00, 192 from 20:00 to midnight.
      </>
    );

  const latest = ledger?.commitments?.[0] ?? null;
  const days = impact?.days_published_in_advance ?? ledger?.commitments.length ?? null;
  const ist = nowIST();
  const firstLine =
    days === 0 ? (ist.hour < 21 ? "First publication: tonight, 21:00 IST." : "Publication runs every night at 21:00 IST.") : null;

  const stripWin = { start: hero.open, end: hero.close };
  const morning = REPLAY.rows[0];
  const bengaluru = NATIONAL.byCity.find((c) => c.city === "Bengaluru")!;

  return (
    <>
      <Hero data={{ values: hero.values, open: hero.open, close: hero.close, caption }} />

      <main className={s.main}>
        <section className="sec" id="how" aria-labelledby="how-h">
          <div className="wrap">
            <div className={s.head}>
              <h2 className="h2" id="how-h">
                How it works
              </h2>
              <p className="body">
                One question, answered for every hour of tomorrow: when is the air over your street cleanest for the thing you do
                outdoors?
              </p>
            </div>
            <ol className={s.steps}>
              <li>
                <p className={s.stepN}>1</p>
                <h3 className="h3">Tell it your day</h3>
                <p className={s.stepP}>
                  Where you are, what you do outside and when you usually go: a walk, a run, children&apos;s play, a ride, yoga,
                  the commute, or just airing the house.
                </p>
                <div className={s.chips} aria-hidden="true">
                  <span>Walk</span>
                  <span className="mono">60 min</span>
                  <span>
                    usually&nbsp;<span className="mono">06:00</span>
                  </span>
                </div>
              </li>
              <li>
                <p className={s.stepN}>2</p>
                <h3 className="h3">Go at the clean hour</h3>
                <p className={s.stepP}>
                  Khidki forecasts PM2.5 hour by hour from the government monitors around you and moves your hour to the cleanest
                  one that still fits your day.
                </p>
                <div className={s.mini}>
                  <DayStrip
                    size="sm"
                    values={hero.values}
                    measured={hero.measured}
                    window={stripWin}
                    label={`PM2.5 by hour ${hero.kind === "live" ? `${hero.when.toLowerCase()} at ${HERO_PLACE.name}` : "on a typical winter day at Chanakyapuri"}; the clean window is ${hh(hero.open)} to ${hh(hero.close)}.`}
                  />
                </div>
              </li>
              <li>
                <p className={s.stepN}>3</p>
                <h3 className="h3">See what you avoided</h3>
                <p className={s.stepP}>
                  The next day it reads what the monitors measured and tells you how much less smoke you breathed than at your
                  usual time, in µg, misses included.
                </p>
                <p className={s.receipt}>
                  Winter replay: worse than the usual 06:00 on <span className="mono">{morning.worseDays}%</span> of days. Those
                  days are counted, not hidden.
                </p>
              </li>
            </ol>
          </div>
        </section>

        <section className="sec" id="checked" aria-labelledby="checked-h">
          <div className="wrap">
            <div className={s.proofGrid}>
              <div>
                <h2 className="h2" id="checked-h">
                  Published before the day.
                  <br />
                  Checked after it.
                </h2>
                <p className={`body ${s.gap}`}>
                  Every night at 21:00 IST Khidki publishes tomorrow&apos;s recommendations for every monitor it covers, seals the
                  file with SHA-256 and stamps the hash with OpenTimestamps. The next day it scores each one against the measured
                  air. Anyone can check the file was not changed afterwards.
                </p>
                <p className={s.gap}>
                  <Link className="link" href="/ledger">
                    Open the ledger
                  </Link>
                </p>
              </div>
              <div>
                {impact ? (
                  <dl className={s.stats}>
                    <div>
                      <dt>Days published in advance</dt>
                      <dd>{int(impact.days_published_in_advance)}</dd>
                    </div>
                    <div>
                      <dt>Recommendations published</dt>
                      <dd>{int(impact.recommendations_published)}</dd>
                    </div>
                    <div>
                      <dt>Government monitors covered</dt>
                      <dd>{int(impact.stations_covered)}</dd>
                    </div>
                    <div>
                      <dt>Hours of measured readings</dt>
                      <dd>{int(impact.hours_of_readings)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className="empty">The live counters are unavailable right now. The ledger keeps every published day.</p>
                )}
                <p className={`${s.latest} small`}>
                  {latest ? (
                    <>
                      Latest: {dayLabel(latest.day)} · <span className="mono">sha256 {shortHash(latest.sha256, 8)}</span> ·{" "}
                      {int(latest.n_recommendations)} recommendations
                    </>
                  ) : (
                    (firstLine ?? "Publication runs every night at 21:00 IST.")
                  )}
                </p>
              </div>
            </div>

            <div className={s.replay}>
              <p className={s.replayTag}>Replay of winter 2025–26, not published in advance</p>
              <p className={s.replayLine}>
                Same walk, {Math.round(-morning.khidki)}% less smoke: {morning.days} winter days at Chanakyapuri, moving a 06:00
                walk to Khidki&apos;s hour. Across {NATIONAL.monitors} government monitors in {NATIONAL.cities} cities and towns,{" "}
                {Math.round(-NATIONAL.rows[0].khidki)}% less.
              </p>
              <p className="small">
                In a smoggy Delhi winter a fixed 3 pm rule does as well ({signedPct(morning.fixed)}). It does not travel: in
                Bengaluru the same rule made a morning walk {signedPct(bengaluru.fixed)} smokier, where Khidki, which learns each
                monitor&apos;s own day, cut it by {Math.round(-bengaluru.khidki)}%. Nationally the rule left people worse off than at 06:00 on{" "}
                {Math.round(NATIONAL.rows[0].worseFixed)}% of days, Khidki on {Math.round(NATIONAL.rows[0].worseKhidki)}%.{" "}
                <Link className="link" href="/ledger#replay">
                  Full replay
                </Link>
              </p>
            </div>
          </div>
        </section>

        <section className="sec" id="schools" aria-labelledby="schools-h">
          <div className="wrap">
            <div className={s.split}>
              <div>
                <h2 className="h2" id="schools-h">
                  For schools and housing societies
                </h2>
                <p className={`body ${s.gap}`}>
                  Put the day&apos;s cleanest playtime on the school website or the society notice screen. One line of HTML, no
                  account, updated every day from the monitors nearest you.
                </p>
                <pre className={s.code}>
                  <code>{`<iframe src="${SITE_URL}/embed?lat=28.5931&lon=77.2197&activity=play&label=Lodhi%20Road"
  width="360" height="240" style="border:0" title="Khidki"></iframe>`}</code>
                </pre>
                <p className={s.gap}>
                  <Link className="link" href="/developers#embed">
                    Embed options
                  </Link>
                </p>
              </div>
              <div className={s.embedFrame}>
                <iframe
                  src={`/embed?lat=${HERO_PLACE.lat}&lon=${HERO_PLACE.lon}&activity=play&label=${encodeURIComponent("Lodhi Road, New Delhi")}`}
                  title="Khidki card: today's cleanest playtime at Lodhi Road, New Delhi"
                  loading="lazy"
                  width="360"
                  height="240"
                />
                <p className="small">Live card, as a school would embed it.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="sec" id="software" aria-labelledby="software-h">
          <div className="wrap">
            <div className={s.head}>
              <h2 className="h2" id="software-h">
                For other software
              </h2>
              <p className="body">
                The same engine answers over a public HTTP API and as an MCP server, so a health app, a building system or an
                agent can ask for the clean hour.
              </p>
            </div>
            <div className={s.twin}>
              <div className={s.panel}>
                <p className={s.panelT}>HTTP API</p>
                <pre className={s.code}>
                  <code>{`curl "${API_BASE}/v1/window?lat=28.59&lon=77.22&activity=run&minutes=45"`}</code>
                </pre>
                <p className="small">Window, airing, live monitors, ledger, scoreboard, audit. JSON, no key.</p>
              </div>
              <div className={s.panel}>
                <p className={s.panelT}>MCP endpoint</p>
                <pre className={s.code}>
                  <code>{MCP_URL}</code>
                </pre>
                <p className="small">Tools: find_window, find_airing_time, air_now, ledger_day, monitor_health.</p>
              </div>
            </div>
            <p className={s.gap}>
              <Link className="link" href="/developers">
                Developer docs
              </Link>
            </p>
          </div>
        </section>
      </main>
    </>
  );
}
