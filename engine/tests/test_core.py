from datetime import datetime, timedelta, timezone

import pytest

from khidki.aqi import pm10_sub_index, pm25_category, pm25_sub_index
from khidki.exposure import (
    Activity,
    AgeBand,
    indoor_series,
    inhalation_rate,
    interval_dose,
)
from khidki.planner import plan_airing, plan_window
from khidki.verify import verify_choice

IST = timezone(timedelta(hours=5, minutes=30))
D0 = datetime(2026, 11, 11, 0, 0, tzinfo=IST)


def delhi_like_day(base: float = 100.0) -> dict[datetime, float]:
    """Winter-shaped day: high at night and early morning, lowest mid-afternoon."""
    shape = [
        2.2, 2.2, 2.1, 2.1, 2.1, 2.2, 2.4, 2.5, 2.2, 1.8, 1.4, 1.2,
        1.1, 1.0, 0.95, 0.9, 1.0, 1.3, 1.7, 2.0, 2.2, 2.4, 2.4, 2.3,
    ]
    return {D0 + timedelta(hours=i): base * s for i, s in enumerate(shape)}


# --- AQI -------------------------------------------------------------------------

def test_pm25_breakpoints():
    assert pm25_sub_index(0).value == 0
    assert pm25_sub_index(30).category == "Good"
    assert pm25_sub_index(60).value == 100
    assert pm25_sub_index(90).value == 200
    assert pm25_category(121) == "Very Poor"
    assert pm25_sub_index(250).value == 400
    assert pm25_sub_index(380).value == 500
    assert pm25_sub_index(999).value == 500
    assert pm25_sub_index(999).category == "Severe"
    assert pm10_sub_index(100).value == 100


def test_pm25_rejects_negative():
    with pytest.raises(ValueError):
        pm25_sub_index(-1)


# --- exposure --------------------------------------------------------------------

def test_inhalation_rates_from_epa_table():
    assert inhalation_rate(Activity.walk) == pytest.approx(2.7e-2)  # adult moderate
    assert inhalation_rate(Activity.run, AgeBand.child) == pytest.approx(4.2e-2)
    assert inhalation_rate(Activity.yoga, AgeBand.older) == pytest.approx(1.2e-2)


def test_interval_dose_spans_hours():
    s = {D0: 100.0, D0 + timedelta(hours=1): 200.0}
    d = interval_dose(s, D0 + timedelta(minutes=30), 60, 0.01)
    assert d is not None
    assert d.mean_conc == pytest.approx(150.0)
    assert d.dose_ug == pytest.approx(150.0 * 0.01 * 60)


def test_interval_dose_refuses_gaps():
    s = {D0: 100.0}
    assert interval_dose(s, D0 + timedelta(minutes=30), 60, 0.01) is None


def test_indoor_follows_outdoor_and_open_windows_raise_indoor_when_dirty():
    out = {D0 + timedelta(hours=i): 300.0 for i in range(6)}
    hours = sorted(out)
    closed = indoor_series(out, hours, [])
    opened = indoor_series(out, hours, [(D0 + timedelta(hours=2), D0 + timedelta(hours=3))])
    assert closed[hours[-1]] < 300.0
    assert opened[hours[2]] > closed[hours[2]]


# --- planner ---------------------------------------------------------------------

def test_plan_picks_afternoon_over_morning_walk():
    f = delhi_like_day()
    plan = plan_window(
        f,
        activity=Activity.walk,
        minutes=60,
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
        habitual_start=D0 + timedelta(hours=6),
    )
    assert plan.status == "ok"
    assert plan.best.start == D0 + timedelta(hours=15)
    assert plan.habitual.mean_conc == pytest.approx(240.0)
    assert plan.reduction_pct == pytest.approx(100 * (240 - 90) / 240)
    assert plan.dose_avoided_ug == pytest.approx((240 - 90) * 2.7e-2 * 60)
    assert "habitual_is_best" not in plan.flags
    # alternatives never overlap the best slot
    for a in plan.alternatives:
        assert a.end <= plan.best.start or a.start >= plan.best.end


def test_plan_respects_constraints():
    f = delhi_like_day()
    plan = plan_window(
        f,
        activity=Activity.walk,
        minutes=30,
        earliest=D0 + timedelta(hours=6),
        latest_end=D0 + timedelta(hours=9),
        habitual_start=D0 + timedelta(hours=7),
    )
    assert D0 + timedelta(hours=6) <= plan.best.start
    assert plan.best.end <= D0 + timedelta(hours=9)
    # inside a morning-only window the least-bad half hour starts at 08:00 (ties go early)
    assert plan.best.start == D0 + timedelta(hours=8)


def test_plan_fails_closed_on_stale_forecast():
    f = delhi_like_day()
    plan = plan_window(
        f,
        activity=Activity.walk,
        minutes=60,
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
        issued_at=D0 - timedelta(days=3),
        now=D0,
    )
    assert plan.status == "stale"
    assert plan.best is None


def test_plan_fails_closed_without_data():
    plan = plan_window(
        {},
        activity=Activity.walk,
        minutes=60,
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
    )
    assert plan.status == "no_data"
    assert plan.best is None


def test_plan_flags_severe_and_habitual_best():
    f = {D0 + timedelta(hours=i): 400.0 for i in range(24)}
    plan = plan_window(
        f,
        activity=Activity.walk,
        minutes=60,
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
        habitual_start=D0 + timedelta(hours=5),
    )
    assert "severe_all_window" in plan.flags
    assert "habitual_is_best" in plan.flags


def test_confidence_reflects_uncertainty():
    f = delhi_like_day()
    tight = {h: 0.05 for h in f}
    wide = {h: 1.5 for h in f}
    kw = dict(
        activity=Activity.walk,
        minutes=60,
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
        habitual_start=D0 + timedelta(hours=6),
    )
    c_tight = plan_window(f, sigma_log=tight, **kw).confidence
    c_wide = plan_window(f, sigma_log=wide, **kw).confidence
    assert c_tight > 0.99
    assert 0.5 < c_wide < c_tight


def test_airing_prefers_clean_afternoon():
    f = delhi_like_day()
    plan = plan_airing(
        f,
        day_start=D0,
        open_minutes=30,
        earliest=D0 + timedelta(hours=6),
        latest_end=D0 + timedelta(hours=22),
        habitual_start=D0 + timedelta(hours=7),
    )
    assert plan.status == "ok"
    # never during the morning peak, and better than airing at 07:00
    assert not 6 <= plan.best_start.hour <= 8
    assert plan.dose_avoided_ug > 0


def test_airing_best_when_outdoor_falls_below_indoor():
    # Outdoor drops sharply at 10:00 while the room still holds the night's air:
    # opening then flushes dirty indoor air out, which beats a clean-but-flat hour.
    f = {D0 + timedelta(hours=i): (300.0 if i < 10 else 80.0) for i in range(24)}
    plan = plan_airing(
        f,
        day_start=D0,
        open_minutes=30,
        earliest=D0 + timedelta(hours=6),
        latest_end=D0 + timedelta(hours=22),
    )
    assert plan.best_start == D0 + timedelta(hours=10)


# --- verify ----------------------------------------------------------------------

def test_verify_measures_gain_and_oracle_capture():
    observed = delhi_like_day(base=120.0)
    v = verify_choice(
        observed,
        chosen_start=D0 + timedelta(hours=14),
        minutes=60,
        rate_m3_per_min=2.7e-2,
        habitual_start=D0 + timedelta(hours=6),
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
    )
    assert v.status == "verified"
    assert v.oracle_start == D0 + timedelta(hours=15)
    assert v.beat_habitual is True
    hab, cho, ora = 120 * 2.4, 120 * 0.95, 120 * 0.9
    assert v.reduction_pct == pytest.approx(100 * (hab - cho) / hab)
    assert v.captured_fraction == pytest.approx((hab - cho) / (hab - ora))


def test_verify_is_unverifiable_without_measurements():
    observed = {D0 + timedelta(hours=6): 200.0}
    v = verify_choice(
        observed,
        chosen_start=D0 + timedelta(hours=14),
        minutes=60,
        rate_m3_per_min=2.7e-2,
        habitual_start=D0 + timedelta(hours=6),
        earliest=D0 + timedelta(hours=5),
        latest_end=D0 + timedelta(hours=21),
    )
    assert v.status == "unverifiable"
    assert v.reduction_pct is None
