import type { Metadata } from "next";
import Link from "next/link";
import Nav from "@/components/Nav";
import s from "@/components/impact/impact.module.css";
import { api, settle } from "@/lib/api";
import { dateTimeIST, int } from "@/lib/format";
import { TELEGRAM_HANDLE, TELEGRAM_URL } from "@/lib/site";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "Impact",
  description:
    "Live counters from Khidki's production database: monitors read, days published, recommendations checked, and people reached. Zeros shown as zeros.",
  alternates: { canonical: "/impact" },
};

interface Counter {
  n: number;
  label: string;
  def: string;
  zero: string;
  unit?: string;
}

function Grid({ items }: { items: Counter[] }) {
  return (
    <dl className={s.grid}>
      {items.map((c) => (
        <div key={c.label} className={c.n === 0 ? s.isZero : undefined}>
          <dt>{c.label}</dt>
          <dd className={s.n}>
            {int(c.n)}
            {c.unit && <span className={s.unit}> {c.unit}</span>}
          </dd>
          <dd className={s.def}>{c.n === 0 ? c.zero : c.def}</dd>
        </div>
      ))}
    </dl>
  );
}

export default async function ImpactPage() {
  const impact = await settle(api.impact());
  const people = impact ? Object.values(impact.people).reduce((a, b) => a + b, 0) : 0;
  const channels = impact ? Object.entries(impact.people) : [];

  return (
    <>
      <div className="wrap">
        <Nav />
      </div>
      <main id="main">
        <div className="wrap">
          <header className="page-head">
            <h1>What it has done so far</h1>
            <p className="lede">
              Live counts from the production database. Nothing here is estimated, projected or rounded up, and a zero is shown as
              a zero.
              {impact ? ` As of ${dateTimeIST(impact.as_of)}.` : ""}
            </p>
          </header>

          {!impact ? (
            <section className="sec">
              <div className="empty">
                <strong>The counters are unreachable right now</strong>
                Try again in a minute.
              </div>
            </section>
          ) : (
            <>
              <section className="sec" aria-labelledby="system-h">
                <h2 className="h2" id="system-h">
                  The public record
                </h2>
                <Grid
                  items={[
                    {
                      n: impact.stations_covered,
                      label: "Government monitors covered",
                      def: "CPCB and state-board PM2.5 monitors Khidki reads every hour.",
                      zero: "No monitors connected yet.",
                    },
                    {
                      n: impact.hours_of_readings,
                      label: "Hours of measured readings",
                      def: "Hourly PM2.5 values stored from those monitors.",
                      zero: "No readings stored yet.",
                    },
                    {
                      n: impact.days_published_in_advance,
                      label: "Days published in advance",
                      def: "Nights a sealed file of next-day recommendations went out at 21:00 IST.",
                      zero: "None yet. The first file is sealed at 21:00 IST.",
                    },
                    {
                      n: impact.recommendations_published,
                      label: "Recommendations published",
                      def: "Monitor-by-scenario recommended hours inside those files.",
                      zero: "None yet: they arrive with the first published day.",
                    },
                    {
                      n: impact.recommendations_verified,
                      label: "Recommendations checked",
                      def: "Published hours scored against what the monitors measured.",
                      zero: "None yet. A day is checked the morning after it ends.",
                    },
                    {
                      n: impact.audit_flags_raised,
                      label: "Data-quality flags raised",
                      def: "Monitor gaps and odd values found by the daily audit.",
                      zero: "None yet. The audit runs each morning for the day before.",
                    },
                  ]}
                />
                <p className={s.links}>
                  <Link className="link" href="/ledger">
                    The ledger
                  </Link>
                  <Link className="link" href="/monitors">
                    Monitor health
                  </Link>
                </p>
              </section>

              <section className="sec" aria-labelledby="people-h">
                <h2 className="h2" id="people-h">
                  People
                </h2>
                <Grid
                  items={[
                    {
                      n: impact.window_lookups,
                      label: "Window lookups",
                      def: "Times someone asked for a clean window, on this site, the API or the bot.",
                      zero: "Nobody has asked yet.",
                    },
                    {
                      n: people,
                      label: "People with a saved routine",
                      def: channels.length
                        ? `By channel: ${channels.map(([k, v]) => `${k} ${v}`).join(", ")}.`
                        : "People who saved a daily routine.",
                      zero: `Nobody yet. Routines are saved through ${TELEGRAM_HANDLE}.`,
                    },
                    {
                      n: impact.plans_made_for_people,
                      label: "Personal plans sent",
                      def: "Daily windows worked out for those people.",
                      zero: "None yet: plans start once someone saves a routine.",
                    },
                    {
                      n: impact.people_outcomes_verified,
                      label: "Personal plans checked",
                      def: "Plans scored against the measured air the next day.",
                      zero: "None yet.",
                    },
                    {
                      n: impact.people_dose_avoided_ug,
                      unit: "µg",
                      label: "PM2.5 avoided by those people",
                      def: "Measured PM2.5 not breathed, against each person's usual time.",
                      zero: "Zero so far. This only counts measured, checked days.",
                    },
                  ]}
                />
                <p className={s.links}>
                  <a className="link" href={TELEGRAM_URL} rel="noopener">
                    Start on Telegram
                  </a>
                  <Link className="link" href="/app">
                    Find your window
                  </Link>
                </p>
              </section>
            </>
          )}
        </div>
      </main>
    </>
  );
}
