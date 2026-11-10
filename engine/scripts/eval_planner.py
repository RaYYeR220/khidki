"""Graded evaluation of the planner agent against a pre-registered answer key,
with the same model WITHOUT tools as the baseline.

usage: KHIDKI_DB=data/dev.db VENICE_API_KEY=... uv run python scripts/eval_planner.py [--limit N]

Writes results/agent-eval.json. Grading is mechanical (no model grades a model):
  * args      – the find_window / save_routine arguments match the key
  * best      – the reply names the start time the engine computed for the key
  * grounded  – every number in the reply appears in the tool results or the
                person's own message (or a small allow-list: PM2.5, N95, 112)
  * script    – the reply uses the person's script (Devanagari, Tamil, Bengali,
                Latin for English and Hinglish)
  * behaviour – the case-specific expectation (ask for location, refuse outside
                India, point to medical care, call the right tool)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import litellm

from khidki import people, service
from khidki.agents.models import DEFAULT_BASE
from khidki.agents.runtime import run_turn
from khidki.exposure import Activity, AgeBand
from khidki.jobs import now_ist
from khidki.store import Store

LOC = {"lodhi": (28.5931, 77.2197)}
ALLOWED = {"2.5", "95", "112", "24"}
DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯௦௧௨௩௪௫௬௭௮௯", "0123456789" * 3)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(DIGITS)


def script_ok(lang: str, text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False

    def share(lo: int, hi: int) -> float:
        return sum(lo <= ord(c) <= hi for c in letters) / len(letters)

    if lang == "hi":
        return share(0x0900, 0x097F) > 0.5
    if lang == "ta":
        return share(0x0B80, 0x0BFF) > 0.5
    if lang == "bn":
        return share(0x0980, 0x09FF) > 0.5
    return share(0x0041, 0x024F) > 0.8  # en, hinglish: Latin


def collect_numbers(obj) -> set[str]:
    out: set[str] = set()
    s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    s = norm(s)
    for h, m in TIME_RE.findall(s):
        out.add(f"{int(h):02d}:{m}")
    for n in NUM_RE.findall(s):
        out.add(n)
        try:
            f = float(n)
            out.add(str(round(f)))
            out.add(str(int(f)))
        except ValueError:
            pass
    return out


def ungrounded(reply: str, sources: set[str]) -> list[str]:
    r = norm(reply)
    bad = []
    for h, m in TIME_RE.findall(r):
        t = f"{int(h):02d}:{m}"
        if t not in sources:
            bad.append(t)
    r_wo_times = TIME_RE.sub(" ", r)
    for n in NUM_RE.findall(r_wo_times):
        if n in sources or n in ALLOWED:
            continue
        try:
            if str(round(float(n))) in sources:
                continue
        except ValueError:
            pass
        bad.append(n)
    return bad


def args_match(call_args: dict, key: dict) -> tuple[int, int, list[str]]:
    hit, total, miss = 0, 0, []
    for k, allowed in key.items():
        total += 1
        v = call_args.get(k)
        if k in ("earliest", "latest_end", "usual_time") and v is not None:
            try:
                v = service.parse_time(str(v)).strftime("%H:%M")
            except ValueError:
                pass
        if k == "minutes" and v is not None:
            v = int(v)
        if v in allowed or (k == "day" and isinstance(v, str) and v.lower() in allowed):
            hit += 1
        else:
            miss.append(f"{k}={v!r}")
    return hit, total, miss


def engine_best(store: Store, loc, key: dict) -> str | None:
    w = service.compute_window(
        store,
        lat=loc[0],
        lon=loc[1],
        activity=Activity(key["activity"][0]),
        minutes=key["minutes"][0],
        earliest=key.get("earliest", ["05:00"])[0],
        latest_end=key.get("latest_end", ["21:00"])[0],
        habitual=key["usual_time"][0],
        age=AgeBand(key.get("age", ["adult"])[0]),
        day="tomorrow",
        log_event=False,
    )
    return (w.get("best") or {}).get("start")


BASELINE_SYSTEM = (
    "You are a helpful clean-air assistant for people in India. Help them choose when to do outdoor activities "
    "so they breathe less air pollution. Reply in the person's language and script, 2-5 lines, and write clock "
    "times as 24-hour HH:MM with ASCII digits. {where}"
)


def baseline_reply(model: str, text: str, loc) -> str:
    where = f"The person lives near Lodhi Garden, New Delhi ({loc[0]}, {loc[1]})." if loc else ""
    r = litellm.completion(
        model=f"openai/{model}",
        api_base=os.environ.get("KHIDKI_LLM_BASE", DEFAULT_BASE),
        api_key=os.environ.get("KHIDKI_LLM_KEY") or os.environ["VENICE_API_KEY"],
        messages=[{"role": "system", "content": BASELINE_SYSTEM.format(where=where)}, {"role": "user", "content": text}],
        max_tokens=500,
        extra_body={"venice_parameters": {"disable_thinking": True, "strip_thinking_response": True}},
    )
    return r.choices[0].message.content or ""


def behaviour(expect: str, reply: str, calls: list[dict]) -> bool:
    names = [c["name"] for c in calls]
    low = norm(reply).lower()
    if expect == "window":
        return "find_window" in names
    if expect == "airing":
        return "find_airing_time" in names
    if expect == "air_now":
        return "air_now" in names
    if expect == "save_routine":
        return "save_routine" in names
    if expect == "ask_location":
        return "find_window" not in names and any(w in low for w in ("location", "area", "where", "share"))
    if expect == "refuse_outside":
        return not TIME_RE.search(norm(reply)) and "india" in low
    if expect == "medical":
        return any(w in low for w in ("doctor", "medical", "112", "emergency")) and "go at" not in low
    return False


def baseline_behaviour(expect: str, reply: str) -> bool | None:
    low = norm(reply).lower()
    if expect in ("window", "airing"):
        return bool(TIME_RE.search(norm(reply)))  # it at least gave a time
    if expect == "ask_location":
        return any(w in low for w in ("location", "area", "where", "city"))
    if expect == "refuse_outside":
        return not TIME_RE.search(norm(reply)) and "india" in low
    if expect == "medical":
        return any(w in low for w in ("doctor", "medical", "112", "emergency"))
    return None  # air_now / save_routine need tools by definition


async def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    store = Store(os.environ.get("KHIDKI_DB", "data/dev.db"))
    cases = json.loads(Path("evals/planner_cases.json").read_text(encoding="utf-8"))["cases"][:limit]
    model = os.environ.get("KHIDKI_CHAT_MODEL", "claude-haiku-5-5")
    stamp = now_ist().strftime("%Y%m%d%H%M")
    rows = []
    for c in cases:
        loc = LOC.get(c["loc"])
        pid = people.get_or_create_person(store, "eval", f"{stamp}-{c['id']}", c["lang"])
        state = {"person_id": pid}
        if loc:
            state.update(lat=loc[0], lon=loc[1])
        t0 = time.time()
        turn = await run_turn("planner", f"eval-{stamp}-{c['id']}", c["text"], state=state)
        dt = time.time() - t0
        sources = collect_numbers(c["text"]) | collect_numbers([r["response"] for r in turn.tool_results])
        best = engine_best(store, loc, c["key"]) if c["expect"] == "window" and loc else None
        call = next((x["args"] for x in turn.tool_calls if x["name"] in ("find_window", "save_routine")), None)
        a_hit, a_tot, a_miss = args_match(call or {}, c.get("key", {})) if c.get("key") else (0, 0, [])
        bad = ungrounded(turn.text, sources) + [n for n in c.get("forbid_numbers", []) if re.search(rf"\b{n}\b", norm(turn.text))]
        base = baseline_reply(model, c["text"], loc)
        base_bad = ungrounded(base, collect_numbers(c["text"]))
        row = {
            "id": c["id"],
            "lang": c["lang"],
            "expect": c["expect"],
            "khidki": {
                "reply": turn.text,
                "tools": [x["name"] for x in turn.tool_calls],
                "args_hit": a_hit,
                "args_total": a_tot,
                "args_miss": a_miss,
                "engine_best": best,
                "states_best": (best in norm(turn.text)) if best else None,
                "ungrounded": bad,
                "script_ok": script_ok(c["lang"], turn.text),
                "behaviour_ok": behaviour(c["expect"], turn.text, turn.tool_calls),
                "seconds": round(dt, 1),
            },
            "baseline": {
                "reply": base,
                "states_best": (best in norm(base)) if best else None,
                "ungrounded": base_bad,
                "script_ok": script_ok(c["lang"], base),
                "behaviour_ok": baseline_behaviour(c["expect"], base),
            },
        }
        rows.append(row)
        k = row["khidki"]
        print(f"{c['id']:18s} args {a_hit}/{a_tot} best {k['states_best']} ungrounded {len(bad)} script {k['script_ok']} beh {k['behaviour_ok']} | base best {row['baseline']['states_best']} ungrounded {len(base_bad)} beh {row['baseline']['behaviour_ok']}")

    def rate(side: str, field: str, only: str | None = None) -> str:
        vals = [r[side][field] for r in rows if r[side][field] is not None and (only is None or r["expect"] == only)]
        return f"{sum(bool(v) for v in vals)}/{len(vals)}"

    summary = {
        "model": model,
        "cases": len(rows),
        "khidki": {
            "args_fields_correct": f"{sum(r['khidki']['args_hit'] for r in rows)}/{sum(r['khidki']['args_total'] for r in rows)}",
            "states_engine_best_time": rate("khidki", "states_best"),
            "replies_with_ungrounded_numbers": f"{sum(bool(r['khidki']['ungrounded']) for r in rows)}/{len(rows)}",
            "ungrounded_numbers_total": sum(len(r["khidki"]["ungrounded"]) for r in rows),
            "script_matches": rate("khidki", "script_ok"),
            "behaviour_ok": rate("khidki", "behaviour_ok"),
            "median_seconds": sorted(r["khidki"]["seconds"] for r in rows)[len(rows) // 2],
        },
        "baseline_same_model_no_tools": {
            "states_engine_best_time": rate("baseline", "states_best"),
            "replies_with_ungrounded_numbers": f"{sum(bool(r['baseline']['ungrounded']) for r in rows)}/{len(rows)}",
            "ungrounded_numbers_total": sum(len(r["baseline"]["ungrounded"]) for r in rows),
            "script_matches": rate("baseline", "script_ok"),
            "behaviour_ok": rate("baseline", "behaviour_ok"),
        },
    }
    out = {"run_at": now_ist().isoformat(), "summary": summary, "cases": rows}
    Path("results").mkdir(exist_ok=True)
    Path("results/agent-eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    litellm.suppress_debug_info = True
    asyncio.run(main())
