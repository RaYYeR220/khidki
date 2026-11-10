"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import Nav from "@/components/Nav";
import s from "./Hero.module.css";

export interface PaneData {
  /** PM2.5 by hour of day, 24 values, µg/m³. */
  values: number[];
  /** Window opens / closes, fractional hours (17.5 = 17:30). */
  open: number;
  close: number;
  /** Caption under the pane. */
  caption: React.ReactNode;
}

const SEC_PER_HOUR = 1.25; // a 30 s day
const SLOW_IN_WINDOW = 3; // the clean hour lingers so the opening can be seen
const HAZE = ["#3a3833", "#6e6a62", "#a9a39a"];

function fmt(h: number) {
  const hr = Math.floor(h) % 24;
  const mi = Math.round((h - Math.floor(h)) * 60) % 60;
  return `${String(hr).padStart(2, "0")}:${String(mi).padStart(2, "0")}`;
}

function rnd(v: number) {
  const f = Math.floor(v);
  const d = v - f;
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 ? f + 1 : f;
}

export default function Hero({ data }: { data: PaneData }) {
  const heroRef = useRef<HTMLElement>(null);
  const pwRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const cvRef = useRef<HTMLCanvasElement>(null);
  const readRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLDivElement>(null);
  const sashL = useRef<HTMLButtonElement>(null);
  const sashR = useRef<HTMLButtonElement>(null);

  const { values, open: OPEN_AT, close: CLOSE_AT } = data;

  useEffect(() => {
    const hero = heroRef.current;
    const pw = pwRef.current;
    const pane = paneRef.current;
    const cv = cvRef.current;
    const read = readRef.current;
    const note = noteRef.current;
    if (!hero || !pw || !pane || !cv || !read || !note) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
    const whole = (x: number) => Math.abs(x - Math.round(x)) < 1e-6;
    const gran = whole(OPEN_AT) && whole(CLOSE_AT) ? 1 : whole(OPEN_AT * 2) && whole(CLOSE_AT * 2) ? 0.5 : 0.25;
    const pmAt = (h: number) => {
      const i = Math.floor(h) % 24;
      const j = (i + 1) % 24;
      const f = h - Math.floor(h);
      return values[i] + (values[j] - values[i]) * f;
    };
    const inWindow = (h: number) => h >= OPEN_AT && h < CLOSE_AT;
    // daylight through the glass is an illustration (no numbers drawn from it)
    const sun = (h: number) => Math.pow(clamp(Math.sin((Math.PI * (h - 6.9)) / (17.6 - 6.9)), 0, 1), 0.6);

    const N = 900;
    const PX = new Float32Array(N);
    const PY = new Float32Array(N);
    const PS = new Float32Array(N);
    const PT = new Float32Array(N);
    const PA = new Float32Array(N);
    let seed = 1402;
    const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < N; i++) {
      PX[i] = rand();
      PY[i] = rand();
      PS[i] = rand();
      PT[i] = rand();
      PA[i] = rand();
    }
    const blobs = Array.from({ length: 5 }, () => ({
      x: rand(),
      y: 0.2 + rand() * 0.7,
      r: 0.35 + rand() * 0.4,
      s: 0.004 + rand() * 0.008,
    }));

    let W = 0;
    let H = 0;
    let perUnit = 3.2;
    let sky: [number, number, number][] = [];
    let dirty = true;

    function layout() {
      if (!cv || !ctx || !hero || !pane) return;
      const r = cv.getBoundingClientRect();
      W = r.width;
      H = r.height;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      cv.width = Math.round(W * dpr);
      cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      perUnit = (4.4 * (W * H)) / (420 * 560); // dots per µg/m³, scaled to the pane's area (fewer on phones)
      sky = [];
      let sd = 11;
      let x = -4;
      const rb = () => (sd = (sd * 16807) % 2147483647) / 2147483647;
      while (x < W + 4) {
        const w = 14 + rb() * 34;
        sky.push([x, w, H * (0.06 + rb() * 0.12)]);
        x += w + (rb() < 0.3 ? 4 : 0);
      }
      const hr = hero.getBoundingClientRect();
      const pr = pane.getBoundingClientRect();
      hero.style.setProperty("--px", (((pr.left + pr.width / 2 - hr.left) / hr.width) * 100).toFixed(1) + "%");
      dirty = true;
    }

    let hour = reduce ? OPEN_AT + (CLOSE_AT - OPEN_AT) / 2 : (OPEN_AT - 0.7 + 24) % 24;
    let override: boolean | null = null;
    let isOpen = false;
    let shownKey = "";
    let noteTimer = 0;

    function setOpen(v: boolean) {
      if (v === isOpen) return;
      isOpen = v;
      pane!.classList.toggle(s.open, v);
      pw!.classList.toggle(s.open, v);
      hero!.classList.toggle(s.lit, v);
    }

    function updateRead() {
      const slot = Math.floor(hour / gran + 1e-9) * gran;
      const key = `${slot}|${isOpen}`;
      if (key === shownKey) return;
      shownKey = key;
      const win = inWindow(slot);
      const st = win ? (isOpen ? "open" : "open now") : "keep closed";
      read!.textContent = `${fmt(slot)} · ${rnd(values[Math.floor(slot) % 24])} µg/m³ · `;
      const span = document.createElement("span");
      span.className = win ? `${s.st} ${s.go}` : s.st;
      span.textContent = st;
      read!.appendChild(span);
    }

    function draw(t: number) {
      if (!ctx) return;
      const pm = pmAt(hour);
      const d = clamp((pm - 90) / (205 - 90), 0, 1); // haze density 0..1 from the measured value
      const sn = sun(hour);
      ctx.clearRect(0, 0, W, H);
      const g = ctx.createLinearGradient(0, 0, 0, H);
      const top = [19 + 52 * sn, 17 + 43 * sn, 14 + 30 * sn];
      const bot = [26 + 78 * sn, 23 + 62 * sn, 19 + 40 * sn];
      g.addColorStop(0, `rgb(${top.map(Math.round).join(",")})`);
      g.addColorStop(1, `rgb(${bot.map(Math.round).join(",")})`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      if (isOpen || sn > 0) {
        const lg = ctx.createRadialGradient(W * 0.78, H * 0.78, 0, W * 0.78, H * 0.78, W * 1.1);
        lg.addColorStop(0, `rgba(242,176,74,${((0.06 + (isOpen ? 0.12 : 0)) * sn).toFixed(3)})`);
        lg.addColorStop(1, "rgba(242,176,74,0)");
        ctx.fillStyle = lg;
        ctx.fillRect(0, 0, W, H);
      }
      const tt = reduce ? 0 : t;
      for (const b of blobs) {
        const x = (((b.x + tt * b.s) % 1.4) - 0.2) * W;
        const y = b.y * H;
        const r = b.r * W;
        const bg = ctx.createRadialGradient(x, y, 0, x, y, r);
        bg.addColorStop(0, `rgba(169,163,154,${(0.02 + 0.12 * d).toFixed(3)})`);
        bg.addColorStop(1, "rgba(169,163,154,0)");
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);
      }
      ctx.fillStyle = `rgba(10,9,7,${0.55 - 0.25 * d})`;
      for (const b of sky) ctx.fillRect(b[0], H - b[2], b[1], b[2]);
      // measured haze particles: PM2.5 for the hour × perUnit
      const n = Math.min(N, pm * perUnit);
      for (let k = 0; k < 3; k++) {
        ctx.fillStyle = HAZE[k];
        for (let i = 0; i < n; i++) {
          if (((PT[i] * 3) | 0) !== k) continue;
          const x = ((PX[i] * W + tt * (3 + 8 * PS[i])) % (W + 6)) - 3;
          const y = PY[i] * H + Math.sin(tt * (0.3 + 0.5 * PS[i]) + PA[i] * 6.28) * 3;
          ctx.globalAlpha = 0.55 + 0.45 * PA[i];
          const z = 1 + PS[i] * 1.3;
          ctx.fillRect(x, y, z, z);
        }
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = `rgba(110,106,98,${(0.02 + 0.09 * d).toFixed(3)})`;
      ctx.fillRect(0, 0, W, H);
    }

    function step(dt: number) {
      if (!reduce) hour = (hour + dt / (SEC_PER_HOUR * (inWindow(hour) ? SLOW_IN_WINDOW : 1))) % 24;
      const win = inWindow(hour);
      if (!win) override = null;
      setOpen(win ? (override === null ? true : override) : false);
      updateRead();
    }

    const openT = fmt(OPEN_AT);
    const closeT = fmt(CLOSE_AT);
    function clickSash() {
      const v = rnd(values[Math.floor(hour) % 24]);
      window.clearTimeout(noteTimer);
      if (inWindow(hour)) {
        override = !isOpen;
        setOpen(override);
        note!.textContent = isOpen
          ? `Open. Outside now: ${v}. Shut it at ${closeT}.`
          : `Closed. The air is at its cleanest until ${closeT}.`;
      } else {
        note!.textContent =
          hour < OPEN_AT
            ? `Not yet. Opens at ${openT}. Outside now: ${v}.`
            : `Not now. Opens again at ${openT}. Outside now: ${v}.`;
      }
      updateRead();
      dirty = true;
      noteTimer = window.setTimeout(() => {
        note!.textContent = "Click the window.";
      }, 4200);
    }
    const sashes = [sashL.current, sashR.current].filter(Boolean) as HTMLButtonElement[];
    sashes.forEach((b) => b.addEventListener("click", clickSash));

    let visible = true;
    const io =
      "IntersectionObserver" in window
        ? new IntersectionObserver((es) => {
            visible = es.some((e) => e.isIntersecting);
          })
        : null;
    io?.observe(pane);

    let raf = 0;
    let prev = performance.now();
    const t0 = prev;
    function frame(now: number) {
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      if (visible) {
        step(dt);
        if (!reduce || dirty) {
          draw((now - t0) / 1000);
          dirty = false;
        }
      }
      raf = requestAnimationFrame(frame);
    }
    layout();
    const ro = "ResizeObserver" in window ? new ResizeObserver(layout) : null;
    if (ro) ro.observe(cv);
    else window.addEventListener("resize", layout);
    document.fonts?.ready.then(layout).catch(() => {});
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(noteTimer);
      ro?.disconnect();
      io?.disconnect();
      window.removeEventListener("resize", layout);
      sashes.forEach((b) => b.removeEventListener("click", clickSash));
    };
  }, [values, OPEN_AT, CLOSE_AT]);

  return (
    <header className={s.hero} ref={heroRef}>
      <div className={s.pool} aria-hidden="true" />
      <div className="wrap">
        <Nav />
        <div className={s.grid} id="main">
          <h1 className={`${s.h} rise`}>Open the window when the air does.</h1>

          <div className={`${s.obj} ${s.riseo}`}>
            <div className={s.paneWrap} ref={pwRef}>
              <div className={s.pane} ref={paneRef}>
                <canvas ref={cvRef} aria-hidden="true" />
                <button ref={sashL} className={`${s.sash} ${s.sashL}`} type="button" aria-label="Window, left sash" />
                <button
                  ref={sashR}
                  className={`${s.sash} ${s.sashR}`}
                  type="button"
                  aria-label="Window, right sash: open or close"
                />
              </div>
              <div className={s.sill}>
                <div className={s.spill} />
              </div>
              <div
                className={s.read}
                ref={readRef}
                aria-live="polite"
                dangerouslySetInnerHTML={{
                  __html: `${fmt(OPEN_AT)} · ${rnd(values[Math.floor(OPEN_AT) % 24])} µg/m³ · <span class="${s.st} ${s.go}">open now</span>`,
                }}
              />
              <div className={s.note} ref={noteRef} dangerouslySetInnerHTML={{ __html: "Click the window." }} />
              <p className={s.cap}>{data.caption}</p>
            </div>
          </div>

          <div className={s.rest}>
            <p className={`${s.sub} rise d1`}>
              Khidki tells you when the air over your street is cleanest: for your walk, your run, your children&apos;s playtime
              and the windows at home. Every recommendation is published the night before and checked against the measured air the
              next day.
            </p>
            <div className={`${s.ctas} rise d2`}>
              <Link className="btn btn-1" href="/app">
                Find my window
              </Link>
              <Link className="btn btn-2" href="#checked">
                How it&apos;s checked
              </Link>
            </div>
            <p className={`${s.proof} rise d3`}>
              Same walk, 40% less smoke: replayed on 113 winter days at Chanakyapuri, New Delhi, against the usual 6:00 walk. CPCB
              data via OpenAQ.
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}
