"use client";

import DayStrip from "@/components/DayStrip";
import type { Place, Slot, WindowResult } from "@/lib/api";
import { confidenceWords, dateTimeIST, dayLabel, hoursOf, nowIST, signedPct, ug } from "@/lib/format";
import s from "./app.module.css";

interface Props {
  result: WindowResult;
  place: Place;
  noun: string;
  label: string;
  habitual: string;
  onTomorrow: () => void;
}

function span(slot: Slot | null | undefined) {
  return slot ? { start: hoursOf(slot.start), end: hoursOf(slot.end) } : null;
}

export default function ResultCard({ result: r, place, noun, label, habitual, onTomorrow }: Props) {
  const isToday = r.day === nowIST().date;
  const dayText = `${isToday ? "Today" : "Tomorrow"}, ${dayLabel(r.day)}`;

  if (r.status === "window_closed") {
    return (
      <div className={s.state}>
        <p className={s.meta}>
          {label} · {dayText} · {place.name}
        </p>
        <p className={s.stateT}>Today&apos;s hours have passed</p>
        <p className="body">
          The time you allowed for the {noun} is already over for today. Tomorrow&apos;s forecast is ready from about 21:00 IST
          the evening before.
        </p>
        <button type="button" className="btn btn-1 btn-sm" onClick={onTomorrow}>
          Show tomorrow
        </button>
      </div>
    );
  }

  if (r.status === "stale") {
    return (
      <div className={s.state}>
        <p className={s.meta}>
          {label} · {dayText} · {place.name}
        </p>
        <p className={s.stateT}>The forecast here is out of date</p>
        <p className="body">
          The newest forecast for the monitors near {place.name} is too old to trust, so Khidki won&apos;t guess. It refreshes
          every hour as readings arrive.
        </p>
      </div>
    );
  }

  if (r.status === "no_data" || !r.best) {
    return (
      <div className={s.state}>
        <p className={s.meta}>
          {label} · {dayText} · {place.name}
        </p>
        <p className={s.stateT}>No forecast for this place yet</p>
        <p className="body">
          {r.reason ? `${r.reason.charAt(0).toUpperCase()}${r.reason.slice(1)}.` : "There is no forecast for this place and day."}{" "}
          Khidki works within 15 km of a government monitor. Try the nearest city centre.
        </p>
      </div>
    );
  }

  const flags = r.flags ?? [];
  const best = r.best;
  const usual = r.usual ?? null;
  const severe = flags.includes("severe_all_window");
  const habitualBest = flags.includes("habitual_is_best");
  const noUsual = flags.includes("habitual_not_covered") || !usual;
  const curve = [...(r.curve ?? [])].sort((a, b) => a.hour.localeCompare(b.hour));
  const values = curve.map((p) => p.pm25);
  const measured = curve.map((p) => p.measured);
  const conf = confidenceWords(r.confidence);
  const alts = (r.alternatives ?? []).filter((a): a is Slot => !!a);
  const nMeasured = measured.filter(Boolean).length;

  return (
    <div className={s.result}>
      <p className={s.meta}>
        {label} · {r.minutes} min · {dayText} · {place.name}
      </p>
      <p className={s.kicker}>{habitualBest ? "Your usual time is the cleanest" : "Your window"}</p>
      <p className={s.big}>
        {best.start}–{best.end}
      </p>

      {!noUsual && !habitualBest && r.reduction_pct != null && (
        <p className={s.delta}>
          <strong>{signedPct(-r.reduction_pct)} PM2.5</strong> vs your usual {usual!.start}
        </p>
      )}
      {habitualBest && <p className={s.delta}>Your usual time is already the cleanest. Keep it.</p>}

      <p className={s.vals}>
        <span>
          <span className="mono">{ug(best.mean_pm25)} µg/m³</span> in your window
        </span>
        {usual && (
          <span>
            <span className="mono">{ug(usual.mean_pm25)} µg/m³</span> at {usual.start}
          </span>
        )}
        {r.dose_avoided_ug != null && r.dose_avoided_ug > 0 && (
          <span>
            <span className="mono">{r.dose_avoided_ug.toFixed(1)} µg</span> less PM2.5 breathed
          </span>
        )}
      </p>
      {noUsual && (
        <p className="small">There is no forecast for your usual {habitual}, so there is nothing to compare against.</p>
      )}
      {conf && r.confidence != null && (
        <p className={s.conf}>
          {conf} · <span className="mono">{Math.round(r.confidence * 100)}%</span> confidence, from the forecast&apos;s own error
          range
        </p>
      )}

      {severe && (
        <div className={s.alert}>
          <p className={s.alertT}>Severe air at every hour you allowed</p>
          <p>
            Even the cleanest hour is above 250 µg/m³. Move the {noun} indoors today if you can. If you must go out, keep it short
            and gentle, and use a well-fitted N95.
          </p>
        </div>
      )}
      {r.source === "cams_only" && (
        <div className={s.note}>
          <p>
            No monitor near {place.name} has its own forecast for this day yet, so this comes from the CAMS regional forecast
            (Copernicus) alone. Treat it as a rough guide; the monitor-based forecast is published at 21:00 IST.
          </p>
        </div>
      )}
      {flags.includes("partial_coverage") && (
        <p className="small">Some hours have no forecast, so only the covered hours were compared.</p>
      )}

      {values.length === 24 && (
        <div className={s.stripBox}>
          <DayStrip
            interactive
            values={values}
            measured={measured}
            window={span(best)}
            usual={span(usual)}
            label={`PM2.5 by hour for ${dayText}. ${nMeasured} measured hours, ${24 - nMeasured} forecast hours. Your window ${best.start} to ${best.end}${usual ? `, your usual time ${usual.start}` : ""}.`}
          />
          <details className={s.hours}>
            <summary>All 24 hours</summary>
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Hour</th>
                    <th className="num">PM2.5 µg/m³</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {curve.map((p) => (
                    <tr key={p.hour}>
                      <td className="mono">{p.hour}</td>
                      <td className="num mono">{ug(p.pm25)}</td>
                      <td>{p.measured ? "measured" : "forecast"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}

      <dl className={s.facts}>
        {r.health && (
          <div>
            <dt>CPCB health note for {best.category} air</dt>
            <dd>{r.health}</dd>
          </div>
        )}
        {alts.length > 0 && (
          <div>
            <dt>Next best</dt>
            <dd>
              {alts.map((a) => (
                <span key={a.start} className={s.alt}>
                  <span className="mono">
                    {a.start}–{a.end}
                  </span>{" "}
                  · <span className="mono">{ug(a.mean_pm25)}</span> µg/m³
                </span>
              ))}
            </dd>
          </div>
        )}
        {r.worst && (
          <div>
            <dt>Worst time to go</dt>
            <dd>
              <span className="mono">
                {r.worst.start}–{r.worst.end}
              </span>{" "}
              · <span className="mono">{ug(r.worst.mean_pm25)}</span> µg/m³
            </dd>
          </div>
        )}
      </dl>

      {r.neighbours && r.neighbours.length > 0 && (
        <div className={s.monitors}>
          <p className={s.label}>{r.source === "cams_only" ? "Nearest government monitors" : "Monitors behind this forecast"}</p>
          <ul>
            {r.neighbours.map((n) => (
              <li key={n.id}>
                <span>{n.name ?? n.id}</span>
                <span className="mono">{n.km.toFixed(1)} km</span>
                {r.source !== "cams_only" && <span className="mono">{Math.round(n.weight * 100)}%</span>}
              </li>
            ))}
          </ul>
          <p className="small">
            {r.issued_at ? `Forecast issued ${dateTimeIST(r.issued_at)}. ` : ""}
            Measured hours come from CPCB and state-board monitors via OpenAQ; forecast hours combine each monitor&apos;s recent
            daily rhythm with the CAMS weather forecast.
          </p>
        </div>
      )}
    </div>
  );
}
