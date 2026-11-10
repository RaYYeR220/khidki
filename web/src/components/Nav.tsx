"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import s from "./Nav.module.css";

const LINKS = [
  { href: "/app", label: "Your window" },
  { href: "/ledger", label: "Ledger" },
  { href: "/monitors", label: "Monitors" },
  { href: "/developers", label: "Developers" },
];

export function Mark() {
  return (
    <Link className={s.mark} href="/" aria-label="Khidki home">
      Khidki{" "}
      <span className={s.hi} lang="hi">
        खिड़की
      </span>
    </Link>
  );
}

function Menu({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={s.menu}>
      <button
        type="button"
        className={s.menuBtn}
        aria-expanded={open}
        aria-controls="site-menu"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Close" : "Menu"}
      </button>
      {open && (
        <div id="site-menu" className={s.sheet}>
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined} onClick={() => setOpen(false)}>
              {l.label}
            </Link>
          ))}
          <Link href="/impact" aria-current={path === "/impact" ? "page" : undefined} onClick={() => setOpen(false)}>
            Impact
          </Link>
        </div>
      )}
    </div>
  );
}

export default function Nav() {
  const path = usePathname();
  return (
    <nav className={s.nav} aria-label="Main">
      <Mark />
      <div className={s.links}>
        {LINKS.map((l) => (
          <Link key={l.href} className={s.opt} href={l.href} aria-current={path === l.href ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
        {path !== "/app" && (
          <Link className={s.cta} href="/app">
            Open the app
          </Link>
        )}
        <Menu key={path} path={path} />
      </div>
    </nav>
  );
}
