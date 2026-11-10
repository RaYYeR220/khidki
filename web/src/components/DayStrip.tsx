"use client";

import { useState } from "react";
import { hazeColor, hh } from "@/lib/format";
import s from "./DayStrip.module.css";

export interface StripSpan {
  start: number;
  end: number;
}

interface Props {
  values: number[];
  measured?: boolean[];
  window?: StripSpan | null;
  usual?: StripSpan | null;
  size?: "sm" | "lg";
  /** Show the hover/focus readout and legend. */
  interactive?: boolean;
  label: string;
  /** Hour labels under the strip. */
  ticks?: boolean;
}

function pos(span: StripSpan) {
  const a = Math.max(0, Math.min(24, span.start));
  const b = Math.max(a, Math.min(24, span.end));
  return { left: `${(a / 24) * 100}%`, width: `${((b - a) / 24) * 100}%` };
}

export default function DayStrip({
  values,
  measured,
  window: win,
  usual,
  size = "lg",
  interactive = false,
  label,
  ticks = true,
}: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const anyMeasured = !!measured?.some(Boolean);
  const anyForecast = !measured || measured.some((m) => !m);
  // The ramp spans the day's own range so its shape reads; the readout carries the absolute values.
  const hi = Math.max(...values);
  const lo = Math.min(...values) * 0.8;

  const readout =
    hover != null
      ? `${hh(hover)} · ${Math.round(values[hover])} µg/m³ · ${measured?.[hover] ? "measured" : "forecast"}`
      : win
        ? `Your window ${hh(win.start)}–${hh(win.end)}`
        : "Hover an hour";

  return (
    <div className={`${s.strip} ${size === "sm" ? s.sm : s.lg}`}>
      {interactive && (
        <p className={`${s.readout} mono`} aria-hidden="true">
          {readout}
        </p>
      )}
      <div className={s.track} role="img" aria-label={label} onMouseLeave={() => setHover(null)}>
        {values.map((v, i) => (
          <span
            key={i}
            className={`${s.cell} ${measured?.[i] ? s.measured : s.forecast}`}
            style={{ background: hazeColor(v, hi, lo) }}
            onMouseEnter={interactive ? () => setHover(i) : undefined}
            title={interactive ? `${hh(i)} · ${Math.round(v)} µg/m³ · ${measured?.[i] ? "measured" : "forecast"}` : undefined}
          />
        ))}
        {usual && <span className={s.usual} style={pos(usual)} />}
        {win && <span className={s.win} style={pos(win)} />}
      </div>
      {ticks && (
        <div className={`${s.ticks} mono`} aria-hidden="true">
          <span>00</span>
          <span>06</span>
          <span>12</span>
          <span>18</span>
          <span>24</span>
        </div>
      )}
      {interactive && (
        <ul className={s.legend}>
          {win && (
            <li>
              <i className={s.kWin} /> Your window
            </li>
          )}
          {usual && (
            <li>
              <i className={s.kUsual} /> Your usual time
            </li>
          )}
          {anyMeasured && (
            <li>
              <i className={s.kMeasured} /> Measured hour
            </li>
          )}
          {anyForecast && (
            <li>
              <i className={s.kForecast} /> Forecast hour
            </li>
          )}
          <li className={s.scale}>
            <i className={s.kScale} /> lighter = more PM2.5, across this day
          </li>
        </ul>
      )}
    </div>
  );
}
