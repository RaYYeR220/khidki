"use client";

import { useState } from "react";
import { api, ApiError, type Place } from "@/lib/api";
import { PRESETS } from "@/lib/site";
import s from "./app.module.css";

type SearchState = "idle" | "loading" | "done" | "unavailable" | "limited" | "error";
type GeoState = "idle" | "locating" | "denied" | "outside" | "error" | "unsupported";

function inIndia(lat: number, lon: number) {
  return lat >= 6 && lat <= 37.5 && lon >= 68 && lon <= 97.5;
}

function shortName(full: string) {
  const parts = full
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  return parts.slice(0, 2).join(", ") || full;
}

export default function PlacePicker({ place, onPick }: { place: Place | null; onPick: (p: Place) => void }) {
  const [q, setQ] = useState("");
  const [state, setState] = useState<SearchState>("idle");
  const [results, setResults] = useState<Place[]>([]);
  const [geo, setGeo] = useState<GeoState>("idle");

  async function search(e: React.FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (text.length < 2) return;
    setState("loading");
    try {
      const r = await api.geocode(text);
      setResults(r.results ?? []);
      setState("done");
    } catch (err) {
      setResults([]);
      if (err instanceof ApiError && err.status === 404) setState("unavailable");
      else if (err instanceof ApiError && err.status === 429) setState("limited");
      else setState("error");
    }
  }

  function locate() {
    if (!("geolocation" in navigator)) {
      setGeo("unsupported");
      return;
    }
    setGeo("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        if (!inIndia(lat, lon)) {
          setGeo("outside");
          return;
        }
        setGeo("idle");
        onPick({ name: "Your location", lat, lon });
      },
      (err) => setGeo(err.code === err.PERMISSION_DENIED ? "denied" : "error"),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 },
    );
  }

  function pick(p: Place) {
    onPick(p);
    setResults([]);
    setState("idle");
    setQ("");
  }

  const geoMsg: Record<GeoState, string | null> = {
    idle: null,
    locating: "Finding you…",
    denied: "Location permission was declined. Search for a place or pick a city instead.",
    outside: "That location is outside India. Khidki covers India only.",
    error: "Could not get your location. Search for a place or pick a city instead.",
    unsupported: "This browser can't share a location. Search for a place or pick a city instead.",
  };

  return (
    <div className={s.field}>
      <p className={s.label} id="where">
        Where
      </p>
      {place && (
        <p className={s.placeNow}>
          <span>{place.name}</span>
          <span className="mono">
            {place.lat.toFixed(4)}, {place.lon.toFixed(4)}
          </span>
        </p>
      )}
      <form role="search" className={s.search} onSubmit={search} aria-labelledby="where">
        <input
          className={s.input}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a street, area or city"
          aria-label="Search a place in India"
          autoComplete="off"
          minLength={2}
          maxLength={120}
        />
        <button className="btn btn-2 btn-sm" type="submit" disabled={state === "loading"}>
          {state === "loading" ? "Searching" : "Search"}
        </button>
      </form>

      {state === "done" &&
        (results.length ? (
          <ul className={s.found} aria-label="Places found">
            {results.map((r) => (
              <li key={`${r.lat},${r.lon},${r.name}`}>
                <button type="button" onClick={() => pick({ name: shortName(r.name), lat: r.lat, lon: r.lon })}>
                  <span>{shortName(r.name)}</span>
                  <span className={s.foundSub}>{r.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={s.hint}>No place in India matched. Try a nearby landmark or the city name.</p>
        ))}
      {state === "unavailable" && (
        <p className={s.hint}>Place search is not available yet. Use your location or pick a city below.</p>
      )}
      {state === "limited" && <p className={s.hint}>Too many searches. Wait a moment, or pick a city below.</p>}
      {state === "error" && <p className={s.hint}>Place search failed. Use your location or pick a city below.</p>}

      <button type="button" className={s.locate} onClick={locate} disabled={geo === "locating"}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="7" cy="7" r="5.25" fill="none" stroke="currentColor" strokeWidth="1" />
          <circle cx="7" cy="7" r="1.6" fill="currentColor" />
        </svg>
        Use my location
      </button>
      {geoMsg[geo] && <p className={s.hint}>{geoMsg[geo]}</p>}

      <div className={s.presets} role="group" aria-label="Cities">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            type="button"
            className={s.preset}
            aria-pressed={place?.name === p.name && place.lat === p.lat}
            onClick={() => pick(p)}
          >
            {p.name}
          </button>
        ))}
      </div>
    </div>
  );
}
