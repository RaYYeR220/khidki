"use client";

import dynamic from "next/dynamic";
import s from "./app.module.css";

function Skeleton() {
  return (
    <div className="wrap">
      <div className={s.layout}>
        <div className={s.head}>
          <h1 className={s.title}>Your window</h1>
          <p className={s.lede}>The cleanest hour over your street, from the government monitors around you.</p>
        </div>
        <div className={s.results}>
          <div className={`${s.card} ${s.skel}`} aria-busy="true">
            <p className="small">Loading…</p>
          </div>
        </div>
      </div>
    </div>
  );
}

const WindowApp = dynamic(() => import("./WindowApp"), { ssr: false, loading: Skeleton });

export default function AppLoader() {
  return <WindowApp />;
}
