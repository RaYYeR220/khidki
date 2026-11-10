"use client";

import { useState } from "react";
import s from "./Code.module.css";

export default function Code({ code, label }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className={s.box}>
      {label && <p className={s.label}>{label}</p>}
      <pre className={s.pre}>
        <code>{code}</code>
      </pre>
      <button type="button" className={s.copy} onClick={copy} aria-label={`Copy ${label ?? "code"}`}>
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
