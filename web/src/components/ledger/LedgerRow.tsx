"use client";

import { useState } from "react";
import { api, sha256HexBytes, type Commitment } from "@/lib/api";
import { dateTimeIST, dayLabel, int, shortHash } from "@/lib/format";
import s from "./ledger.module.css";

type Check =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "match"; hash: string }
  | { state: "mismatch"; hash: string }
  | { state: "error" };

export default function LedgerRow({ c }: { c: Commitment }) {
  const [check, setCheck] = useState<Check>({ state: "idle" });
  const [copied, setCopied] = useState(false);

  async function verify() {
    setCheck({ state: "checking" });
    try {
      const r = await fetch(api.ledgerPayloadUrl(c.day), { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const hash = await sha256HexBytes(await r.arrayBuffer());
      setCheck(hash === c.sha256.toLowerCase() ? { state: "match", hash } : { state: "mismatch", hash });
    } catch {
      setCheck({ state: "error" });
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(c.sha256);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  const stamp = c.bitcoin_attested ? "Bitcoin-attested" : c.anchor ? "Pending Bitcoin confirmation" : "No timestamp proof";

  return (
    <li className={s.row}>
      <div className={s.rowMain}>
        <p className={s.day}>{dayLabel(c.day, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</p>
        <p className={s.issued}>
          Published <span className="mono">{dateTimeIST(c.issued_at)}</span>
        </p>
      </div>

      <div className={s.hashCell}>
        <p className={s.cellL}>SHA-256</p>
        <button
          type="button"
          className={`${s.hash} mono`}
          onClick={copy}
          title={c.sha256}
          aria-label={`Copy SHA-256 ${c.sha256}`}
        >
          {shortHash(c.sha256, 12)}
          <span className={s.copy}>{copied ? "copied" : "copy"}</span>
        </button>
      </div>

      <dl className={s.counts}>
        <div>
          <dt>Monitors</dt>
          <dd className="mono">{int(c.n_stations)}</dd>
        </div>
        <div>
          <dt>Recommendations</dt>
          <dd className="mono">{int(c.n_recommendations)}</dd>
        </div>
        <div>
          <dt>Timestamp</dt>
          <dd className={c.bitcoin_attested ? s.attested : s.pending}>{stamp}</dd>
        </div>
      </dl>

      <div className={s.actions}>
        <button type="button" className="btn btn-1 btn-sm" onClick={verify} disabled={check.state === "checking"}>
          {check.state === "checking" ? "Checking…" : "Verify in your browser"}
        </button>
        {c.anchor && (
          <a className="btn btn-2 btn-sm" href={api.ledgerOtsUrl(c.day)} download={`khidki-${c.day}.ots`}>
            Download proof (.ots)
          </a>
        )}
        <a className="btn btn-2 btn-sm" href={api.ledgerPayloadUrl(c.day)} target="_blank" rel="noopener">
          Download JSON
        </a>
      </div>

      <div className={s.result} aria-live="polite">
        {check.state === "match" && (
          <p className={s.ok}>
            <span aria-hidden="true">✓</span> Match. Your browser hashed the file to{" "}
            <span className="mono">{shortHash(check.hash, 12)}</span>, the same hash sealed on {dateTimeIST(c.issued_at)}. Not one
            byte has changed.
          </p>
        )}
        {check.state === "mismatch" && (
          <p className={s.bad}>
            <span aria-hidden="true">✗</span> Mismatch. The file now hashes to{" "}
            <span className="mono">{shortHash(check.hash, 12)}</span>, not the published{" "}
            <span className="mono">{shortHash(c.sha256, 12)}</span>.
          </p>
        )}
        {check.state === "error" && <p className={s.bad}>Could not download the file to check it. Try again.</p>}
      </div>
    </li>
  );
}
