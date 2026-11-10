"""Public commitments: what Khidki recommended, fixed before the day began.

Each evening the recommendations for every station are serialised as canonical
JSON (sorted keys, no whitespace), hashed with SHA-256 and published. Anyone can
re-hash the published file and compare. The hash is additionally submitted to
OpenTimestamps calendars so its existence before the day can be proven without
trusting us.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

OTS_CALENDARS = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Commitment:
    day: str
    issued_at: str
    model: str
    payload: str
    sha256: str
    n_stations: int
    n_recommendations: int


def build_commitment(day: str, issued_at: str, model: str, recommendations: Iterable[dict]) -> Commitment:
    recs = sorted(recommendations, key=lambda r: (r["station"], r["scenario"]))
    body = {
        "schema": "khidki.commitment/1",
        "day": day,
        "timezone": "Asia/Kolkata",
        "issued_at": issued_at,
        "model": model,
        "method": "Window = start time minimising forecast inhaled PM2.5 within the scenario's allowed times.",
        "recommendations": recs,
    }
    payload = canonical_json(body)
    return Commitment(
        day=day,
        issued_at=issued_at,
        model=model,
        payload=payload,
        sha256=sha256_hex(payload),
        n_stations=len({r["station"] for r in recs}),
        n_recommendations=len(recs),
    )


def verify_payload(payload: str, expected_sha256: str) -> bool:
    return sha256_hex(payload) == expected_sha256


def submit_opentimestamps(sha256: str, client: httpx.Client | None = None) -> dict[str, bytes]:
    """Submit a digest to OpenTimestamps calendars. Returns calendar → pending
    proof bytes for those that accepted. Failures are skipped, never faked."""
    client = client or httpx.Client(timeout=20.0, headers={"user-agent": "khidki/0.1"})
    digest = bytes.fromhex(sha256)
    out: dict[str, bytes] = {}
    for cal in OTS_CALENDARS:
        try:
            r = client.post(
                f"{cal}/digest",
                content=digest,
                headers={"Accept": "application/vnd.opentimestamps.v1", "Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code == 200 and r.content:
                out[cal] = r.content
        except httpx.HTTPError:
            continue
    return out


# OpenTimestamps detached-proof file layout: magic header, version, file-hash
# op (sha256 = 0x08), the 32-byte digest, then the calendar's timestamp bytes.
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"


def ots_file(sha256: str, calendar_proofs: dict[str, bytes]) -> bytes | None:
    """Assemble a .ots file from one or more pending calendar proofs.

    With several calendars, the timestamp forks: 0xff precedes every branch but
    the last. Returns None when no calendar accepted the digest."""
    proofs = list(calendar_proofs.values())
    if not proofs:
        return None
    body = b""
    for i, p in enumerate(proofs):
        if i < len(proofs) - 1:
            body += b"\xff"
        body += p
    return OTS_MAGIC + b"\x01" + b"\x08" + bytes.fromhex(sha256) + body


def upgrade_ots(ots: bytes, timeout: float = 15.0) -> tuple[bytes, bool]:
    """Ask the calendars for the finished (Bitcoin-attested) proof.

    Returns the possibly-upgraded .ots bytes and whether it now carries a
    Bitcoin block-header attestation. Calendars that have not committed yet are
    left pending; nothing is changed if every calendar is unreachable."""
    from opentimestamps.calendar import CommitmentNotFoundError, RemoteCalendar
    from opentimestamps.core.notary import (
        BitcoinBlockHeaderAttestation,
        PendingAttestation,
    )
    from opentimestamps.core.serialize import (
        BytesDeserializationContext,
        BytesSerializationContext,
    )
    from opentimestamps.core.timestamp import DetachedTimestampFile

    f = DetachedTimestampFile.deserialize(BytesDeserializationContext(ots))
    for sub in list(_walk(f.timestamp)):
        for att in list(sub.attestations):
            if not isinstance(att, PendingAttestation):
                continue
            try:
                upgraded = RemoteCalendar(att.uri).get_timestamp(sub.msg, timeout=timeout)
            except CommitmentNotFoundError:
                continue  # calendar has not committed this digest to a block yet
            except Exception as e:  # unreachable calendar: keep the pending proof, try next hour
                logging.getLogger("khidki.ledger").info("ots upgrade via %s failed: %r", att.uri, e)
                continue
            sub.merge(upgraded)
    ctx = BytesSerializationContext()
    f.serialize(ctx)
    complete = any(isinstance(a, BitcoinBlockHeaderAttestation) for _, a in f.timestamp.all_attestations())
    return ctx.getbytes(), complete


def _walk(ts):
    yield ts
    for child in ts.ops.values():
        yield from _walk(child)
