import type { Metadata } from "next";
import Code from "@/components/Code";
import Nav from "@/components/Nav";
import s from "@/components/developers/developers.module.css";
import { API_BASE } from "@/lib/api";
import { GITHUB_URL, MCP_URL, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Developers",
  description:
    "Khidki's public HTTP API, MCP endpoint and embeddable card: the cleanest hour for any place in India, from government air monitors.",
  alternates: { canonical: "/developers" },
};

const ENDPOINTS: { method: string; path: string; what: string }[] = [
  {
    method: "GET",
    path: "/v1/window",
    what: "Cleanest start time for an activity: lat, lon, activity, minutes, earliest, latest_end, habitual, age, day.",
  },
  { method: "GET", path: "/v1/airing", what: "When to open the windows at home: lat, lon, open_minutes, habitual, day." },
  { method: "GET", path: "/v1/air-now", what: "Latest measured PM2.5 at the monitors within 15 km of a point." },
  { method: "GET", path: "/v1/stations", what: "Every monitor Khidki reads, with its latest reading." },
  {
    method: "GET",
    path: "/v1/stations/{id}",
    what: "One monitor: forecast, measured hours, published recommendations, audit flags.",
  },
  { method: "GET", path: "/v1/ledger", what: "Every published day with its SHA-256, counts and timestamp status." },
  { method: "GET", path: "/v1/ledger/{day}.json", what: "The exact bytes that were hashed for that day." },
  { method: "GET", path: "/v1/ledger/{day}.ots", what: "The OpenTimestamps proof for that day's hash." },
  { method: "GET", path: "/v1/scoreboard", what: "Published hours scored against measured air, per scenario and policy." },
  { method: "GET", path: "/v1/audit", what: "Monitor data-quality flags for a day (?day=YYYY-MM-DD)." },
  { method: "GET", path: "/v1/impact", what: "Live counters from the production database." },
  { method: "GET", path: "/v1/geocode", what: "Place search inside India (?q=…), rate-limited." },
  { method: "POST", path: "/v1/chat", what: "Ask the planner in English or Hindi: {text, session (UUIDv4), lat, lon, lang}." },
];

export default function DevelopersPage() {
  return (
    <>
      <div className="wrap">
        <Nav />
      </div>
      <main id="main">
        <div className="wrap">
          <header className="page-head">
            <h1>Build on the clean hour</h1>
            <p className="lede">
              The engine behind this site is public: a JSON API, an MCP server for agents and tools, and a card any school or
              housing society can embed. No key, no sign-up. Open source under MIT.
            </p>
          </header>

          <section className="sec" aria-labelledby="api-h">
            <div className={s.cols}>
              <div>
                <h2 className="h2" id="api-h">
                  HTTP API
                </h2>
                <p className={`body ${s.gap}`}>
                  Base URL <span className="mono">{API_BASE}</span>. Times are IST. Concentrations are PM2.5 in µg/m³; doses are
                  µg inhaled, from US EPA inhalation rates by activity and age.
                </p>
                <p className={s.gap}>
                  <a className="link" href={`${API_BASE}/docs`} rel="noopener">
                    Interactive OpenAPI docs
                  </a>
                </p>
              </div>
              <div className={s.stack}>
                <Code
                  label="Cleanest 45 minutes for a run tomorrow, Lodhi Road"
                  code={`curl "${API_BASE}/v1/window?lat=28.5931&lon=77.2197&activity=run&minutes=45&habitual=06:00&day=tomorrow"`}
                />
                <Code
                  label="When to air the house"
                  code={`curl "${API_BASE}/v1/airing?lat=19.0760&lon=72.8777&open_minutes=30&day=tomorrow"`}
                />
                <Code
                  label="Check a published day yourself"
                  code={`curl -so 2026-11-11.json ${API_BASE}/v1/ledger/2026-11-11.json
sha256sum 2026-11-11.json        # compare with the hash in /v1/ledger
curl -so 2026-11-11.json.ots ${API_BASE}/v1/ledger/2026-11-11.ots
ots verify 2026-11-11.json.ots   # OpenTimestamps client`}
                />
              </div>
            </div>

            <div className={`table-wrap ${s.table}`}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Path</th>
                    <th>What it returns</th>
                  </tr>
                </thead>
                <tbody>
                  {ENDPOINTS.map((e) => (
                    <tr key={e.path}>
                      <td className="mono">{e.method}</td>
                      <td className="mono">{e.path}</td>
                      <td>{e.what}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={`small ${s.gap}`}>
              Activities: walk, run, cycle, yoga, play, commute_walk, commute_two_wheeler, errand, outdoor_work. Ages: child,
              adult, older. Window statuses: ok, no_data, stale, window_closed. A <span className="mono">source</span> of{" "}
              <span className="mono">cams_only</span> means no nearby monitor had a forecast and the answer comes from the CAMS
              model alone.
            </p>
          </section>

          <section className="sec" aria-labelledby="mcp-h">
            <div className={s.cols}>
              <div>
                <h2 className="h2" id="mcp-h">
                  MCP endpoint
                </h2>
                <p className={`body ${s.gap}`}>
                  Streamable HTTP, stateless, no auth. Point any MCP client at it and the clean hour becomes a tool an agent can
                  call.
                </p>
                <ul className={s.tools}>
                  <li>
                    <span className="mono">find_window</span> the cleanest start time for an activity
                  </li>
                  <li>
                    <span className="mono">find_airing_time</span> when to open the windows at home
                  </li>
                  <li>
                    <span className="mono">air_now</span> latest measured PM2.5 near a place
                  </li>
                  <li>
                    <span className="mono">ledger_day</span> a published day and its hash
                  </li>
                  <li>
                    <span className="mono">monitor_health</span> the day&apos;s data-quality flags
                  </li>
                </ul>
              </div>
              <div className={s.stack}>
                <Code label="Endpoint" code={MCP_URL} />
                <Code
                  label="Client config"
                  code={`{
  "mcpServers": {
    "khidki": { "type": "http", "url": "${MCP_URL}" }
  }
}`}
                />
              </div>
            </div>
          </section>

          <section className="sec" id="embed" aria-labelledby="embed-h">
            <div className={s.cols}>
              <div>
                <h2 className="h2" id="embed-h">
                  Embed card
                </h2>
                <p className={`body ${s.gap}`}>
                  A small card with the day&apos;s cleanest window for one place, for a school website, a housing-society notice
                  screen or a clinic. It updates itself from the monitors nearest that point.
                </p>
                <dl className={s.params}>
                  <div>
                    <dt className="mono">lat, lon</dt>
                    <dd>The place, in India. Required.</dd>
                  </div>
                  <div>
                    <dt className="mono">activity</dt>
                    <dd>walk, run, play, cycle, yoga or commute_walk. Default walk; play uses school hours (08:00–14:00).</dd>
                  </div>
                  <div>
                    <dt className="mono">label</dt>
                    <dd>The name shown on the card, for example your school&apos;s name.</dd>
                  </div>
                  <div>
                    <dt className="mono">minutes, habitual, day</dt>
                    <dd>Optional: duration, the usual start time to compare with, and today or tomorrow.</dd>
                  </div>
                </dl>
              </div>
              <div className={s.stack}>
                <Code
                  label="HTML"
                  code={`<iframe
  src="${SITE_URL}/embed?lat=28.5931&lon=77.2197&activity=play&label=Our%20school"
  width="360" height="240" style="border:0" loading="lazy"
  title="Today's cleanest playtime, by Khidki"></iframe>`}
                />
                <div className={s.preview}>
                  <iframe
                    src="/embed?lat=28.5931&lon=77.2197&activity=play&label=Our%20school"
                    width="360"
                    height="240"
                    loading="lazy"
                    title="Today's cleanest playtime, by Khidki"
                  />
                </div>
              </div>
            </div>
          </section>

          <section className="sec" aria-labelledby="src-h">
            <h2 className="h2" id="src-h">
              Source and data
            </h2>
            <p className={`body ${s.gap}`}>
              Engine, site and replay results are in one public repository under the MIT licence. PM2.5 comes from CPCB and state
              pollution-control boards via OpenAQ; the weather-driven forecast from CAMS (ECMWF/Copernicus) via Open-Meteo.
            </p>
            <p className={s.gap}>
              <a className="link" href={GITHUB_URL} rel="noopener">
                {GITHUB_URL.replace("https://", "")}
              </a>
            </p>
          </section>
        </div>
      </main>
    </>
  );
}
