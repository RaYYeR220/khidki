"use client";

import type { AiringResult } from "@/lib/api";
import { nowIST, ug } from "@/lib/format";
import s from "./app.module.css";

export default function AiringCard({
  airing,
  pending,
  day,
}: {
  airing?: AiringResult;
  pending: boolean;
  day: "today" | "tomorrow";
}) {
  const when = day === "today" ? "today" : "tomorrow";
  let body: React.ReactNode;

  if (!airing) {
    body = (
      <p className={s.cardP}>
        {pending ? "Working out the best time to air the house…" : "Pick a place to see when to open the windows."}
      </p>
    );
  } else if (airing.status !== "ok" || !airing.open_at) {
    body = (
      <p className={s.cardP}>
        No full-day forecast for this place {when} yet, so there is no airing time. It appears once the forecast covers all 24
        hours.
      </p>
    );
  } else {
    const flags = airing.flags ?? [];
    const now = nowIST();
    const passed =
      day === "today" && airing.open_at < `${String(now.hour).padStart(2, "0")}:${String(now.minute).padStart(2, "0")}`;
    body = (
      <>
        <p className={s.airBig}>
          Open them at <span className="mono">{airing.open_at}</span> for {airing.open_minutes ?? 30} minutes
        </p>
        <p className={s.cardP}>
          Outside then: <span className="mono">{ug(airing.outdoor_pm25_then)} µg/m³</span>
          {airing.usual && airing.outdoor_pm25_at_usual != null && (
            <>
              , against <span className="mono">{ug(airing.outdoor_pm25_at_usual)}</span> at {airing.usual}, the usual time to air
            </>
          )}
          .
          {airing.reduction_pct != null && airing.reduction_pct > 0 && (
            <>
              {" "}
              Over the whole day, the air indoors carries <span className="mono">{airing.reduction_pct.toFixed(1)}%</span> less
              PM2.5 than airing at {airing.usual ?? "the usual time"}.
            </>
          )}
        </p>
        {flags.includes("keep_closed_if_possible") && (
          <p className={s.cardWarn}>The air is Severe even then. Keep the windows shut if the room isn&apos;t stuffy.</p>
        )}
        {flags.includes("habitual_is_best") && <p className={s.cardP}>Your usual time is already the best one.</p>}
        {passed && <p className={s.cardWarn}>That time has already passed today. Switch to tomorrow for the next one.</p>}
      </>
    );
  }

  return (
    <section className={s.card}>
      <h2 className={s.cardT}>Windows at home</h2>
      {body}
    </section>
  );
}
