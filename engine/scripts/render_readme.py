"""Render README.md from docs/README.template.md and the files in results/.

Every number in the README comes from a results file produced by a script in
this folder; nothing is typed by hand.

usage: uv run python scripts/render_readme.py [--app URL] [--api URL] [--bot URL]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "engine" / "results"


def arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(pattern: str) -> dict:
    files = sorted(RES.glob(pattern))
    if not files:
        raise SystemExit(f"missing results file: {pattern}")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def pct(x: float) -> str:
    return f"{abs(x):.0f}" if x >= 0 else f"+{abs(x):.0f}"


def main() -> None:
    bt = load("backtest-delhi-chanakyapuri-*.json")["summary"]
    di = load("diurnal-delhi-chanakyapuri-*.json")
    gbm = load("exp-gbm-weather-8118-*.json")
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RES.glob("agent-eval-run*.json"))]

    mw = bt["morning_walk"]
    k = mw["blend"]

    def tally(side: str, field: str) -> str:
        num = den = 0
        for r in runs:
            a, b = r["summary"][side][field].split("/")
            num, den = num + int(a), den + int(b)
        return f"{num}/{den}"

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--co"], cwd=ROOT / "engine", capture_output=True, text=True
    ).stdout
    m = re.search(r"(\d+) tests? collected", tests)
    vals = {
        "mw_khidki_pct": f"{k['reduction_vs_habitual_pct']:.0f}",
        "mw_rule_pct": f"{mw['rule_of_thumb']['reduction_vs_habitual_pct']:.0f}",
        "mw_oracle_pct": f"{mw['oracle']['reduction_vs_habitual_pct']:.0f}",
        "mw_days": str(k["station_days"]),
        "mw_worse_days": str(round(k["worse_than_habitual_pct"] * k["station_days"] / 100)),
        "sp_khidki_pct": f"{bt['school_play']['blend']['reduction_vs_habitual_pct']:.0f}",
        "ev_khidki_pct": f"{bt['evening_walk']['blend']['reduction_vs_habitual_pct']:.0f}",
        "bw_khidki_pct": f"{-bt['before_work']['blend']['reduction_vs_habitual_pct']:+.1f}".replace("+-", "−"),
        "gbm_pct": f"−{gbm['morning_walk']['gbm_weather']['reduction_vs_habitual_pct']:.0f}",
        "pm_06": f"{di['pm25_median_by_hour'][6]:.0f}",
        "pm_15": f"{di['pm25_median_by_hour'][15]:.0f}",
        "blh_06": str(di["blh_median_m_by_hour"][6]),
        "blh_15": f"{di['blh_median_m_by_hour'][15]:,}",
        "eval_cases": str(runs[0]["summary"]["cases"]) if runs else "0",
        "eval_best_k": tally("khidki", "states_engine_best_time"),
        "eval_best_b": tally("baseline_same_model_no_tools", "states_engine_best_time"),
        "eval_ungr_k": tally("khidki", "replies_with_ungrounded_numbers"),
        "eval_ungr_b": tally("baseline_same_model_no_tools", "replies_with_ungrounded_numbers"),
        "eval_args_k": tally("khidki", "args_fields_correct"),
        "eval_script_k": tally("khidki", "script_matches"),
        "eval_script_b": tally("baseline_same_model_no_tools", "script_matches"),
        "tests": m.group(1) if m else "?",
        "app_url": arg("--app", "https://khidki.app"),
        "api_url": arg("--api", "https://api.khidki.app"),
        "bot_url": arg("--bot", "https://t.me/KhidkiAirBot"),
    }
    text = (ROOT / "docs" / "README.template.md").read_text(encoding="utf-8")
    missing = set(re.findall(r"\{\{(\w+)\}\}", text)) - vals.keys()
    if missing:
        raise SystemExit(f"no value for {sorted(missing)}")
    for key, v in vals.items():
        text = text.replace("{{" + key + "}}", v)
    (ROOT / "README.md").write_text(text, encoding="utf-8")
    print("README.md rendered:", {k: vals[k] for k in ("mw_khidki_pct", "mw_rule_pct", "eval_best_k", "eval_best_b", "tests")})


if __name__ == "__main__":
    main()
