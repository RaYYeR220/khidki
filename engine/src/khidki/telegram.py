"""Telegram bot: webhook handling, nudges and next-day check-ins."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import httpx

from . import people
from .jobs import now_ist
from .store import Store

log = logging.getLogger("khidki.telegram")

ACTIVITY_WORD = {
    "en": {"walk": "walk", "run": "run", "cycle": "ride", "yoga": "yoga", "play": "outdoor play", "commute_walk": "walk to work",
           "commute_two_wheeler": "ride", "errand": "errand", "outdoor_work": "outdoor work"},
    "hi": {"walk": "सैर", "run": "दौड़", "cycle": "साइकिल", "yoga": "योग", "play": "बाहर खेल", "commute_walk": "पैदल दफ़्तर",
           "commute_two_wheeler": "सवारी", "errand": "काम", "outdoor_work": "बाहर का काम"},
}

TEXT = {
    "en": {
        "welcome": (
            "Hi, I'm Khidki. Every day the air over Indian cities has cleaner and dirtier hours. "
            "Tell me what you do outdoors (a walk, a run, your child's play time) and when, and I'll find the cleanest time "
            "inside your day, remind you before it, and next day show what you avoided, measured at the monitors near you.\n\n"
            "First, share your location (button below) or type your area."
        ),
        "share": "📍 Share my location",
        "saved_loc": "Saved your location. Now tell me your routine, e.g. “I walk an hour at 6 am, I could go any time before 9 pm”.",
        "nudge": "⏰ Your clean window for the {act} starts at {start} (forecast PM2.5 ≈ {fc} vs ≈ {fh} at your usual {usual}).",
        "checkin": "Yesterday I suggested {start} for your {act} (usual {usual}). When did you go?",
        "b_planned": "At {start}",
        "b_usual": "At my usual {usual}",
        "b_skip": "Didn't go",
        "thanks": "Got it. I'll check the measured readings and tell you what you breathed.",
        "result": "✅ Measured: at {went} the air near you averaged {wm} µg/m³ vs {hm} at your usual {usual} — {pct}% less PM2.5 for the same {act}.",
        "result_worse": "Measured: at {went} the air averaged {wm} µg/m³ vs {hm} at {usual}. This time the usual hour would have been cleaner; the forecast missed. I log every miss.",
        "unverifiable": "The monitors near you didn't report enough readings yesterday to measure it. I won't guess.",
        "error": "Something went wrong on my side. Please try again in a minute.",
    },
    "hi": {
        "welcome": (
            "नमस्ते, मैं खिड़की हूँ। हर दिन शहर की हवा में कुछ घंटे साफ़ और कुछ ज़्यादा गंदे होते हैं। "
            "बताइए आप बाहर क्या करते हैं (सैर, दौड़, बच्चों का खेल) और कब, मैं आपके दिन के भीतर सबसे साफ़ समय ढूँढूँगा, "
            "उससे पहले याद दिलाऊँगा, और अगले दिन पास के मॉनिटर की माप से बताऊँगा कि आपने कितना कम धुआँ लिया।\n\n"
            "पहले अपना स्थान भेजें (नीचे बटन) या अपना इलाका लिखें।"
        ),
        "share": "📍 मेरा स्थान भेजें",
        "saved_loc": "आपका स्थान सेव हो गया। अब अपनी दिनचर्या बताइए, जैसे “मैं सुबह 6 बजे एक घंटा टहलता हूँ, रात 9 बजे से पहले कभी भी जा सकता हूँ”।",
        "nudge": "⏰ आपकी {act} के लिए साफ़ हवा का समय {start} बजे शुरू होता है (अनुमानित PM2.5 ≈ {fc}, आपके सामान्य समय {usual} पर ≈ {fh})।",
        "checkin": "कल मैंने आपकी {act} के लिए {start} बजे सुझाया था (सामान्य समय {usual})। आप कब गए?",
        "b_planned": "{start} बजे",
        "b_usual": "सामान्य समय {usual}",
        "b_skip": "नहीं गया",
        "thanks": "ठीक है। मैं मापी गई रीडिंग देखकर बताऊँगा कि आपने कितनी हवा में कितना धुआँ लिया।",
        "result": "✅ माप: {went} बजे आपके पास औसत {wm} µg/m³ था, जबकि सामान्य समय {usual} पर {hm} — उसी {act} में {pct}% कम PM2.5।",
        "result_worse": "माप: {went} बजे औसत {wm} µg/m³ था, {usual} पर {hm}। इस बार सामान्य समय बेहतर रहता; पूर्वानुमान चूक गया। मैं हर चूक दर्ज करता हूँ।",
        "unverifiable": "कल आपके पास के मॉनिटर ने पर्याप्त रीडिंग नहीं दी, इसलिए माप नहीं हो सका। मैं अनुमान नहीं लगाऊँगा।",
        "error": "मेरी तरफ़ से कुछ गड़बड़ हुई। कृपया एक मिनट बाद फिर कोशिश करें।",
    },
}


def lang_of(code: str | None) -> str:
    return "hi" if (code or "").lower().startswith("hi") else "en"


def t(lang: str, key: str, **kw: Any) -> str:
    return TEXT.get(lang, TEXT["en"])[key].format(**kw)


class Sender(Protocol):
    def send(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None: ...
    def answer_callback(self, callback_id: str) -> None: ...


class BotApi:
    def __init__(self, token: str | None = None, client: httpx.Client | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        self.client = client or httpx.Client(timeout=20.0)

    def _call(self, method: str, payload: dict) -> dict:
        r = self.client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload)
        if r.status_code != 200:
            log.warning("telegram %s failed: %s %s", method, r.status_code, r.text[:200])
        return r.json() if r.content else {}

    def send(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._call("sendMessage", payload)

    def answer_callback(self, callback_id: str) -> None:
        self._call("answerCallbackQuery", {"callback_query_id": callback_id})

    def set_webhook(self, url: str, secret: str) -> dict:
        return self._call("setWebhook", {"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query"]})


@dataclass
class Outbox:
    """Test double that records what would be sent."""

    sent: list[tuple[str, str, dict | None]] = field(default_factory=list)

    def send(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        self.sent.append((chat_id, text, reply_markup))

    def answer_callback(self, callback_id: str) -> None:
        pass


def location_keyboard(lang: str) -> dict:
    return {"keyboard": [[{"text": t(lang, "share"), "request_location": True}]], "resize_keyboard": True, "one_time_keyboard": True}


AgentFn = Any  # async (person_id, lat, lon, text) -> str


async def handle_update(store: Store, sender: Sender, update: dict, agent: AgentFn) -> None:
    if "callback_query" in update:
        cq = update["callback_query"]
        sender.answer_callback(cq["id"])
        chat_id = str(cq["message"]["chat"]["id"])
        pid = people.get_or_create_person(store, "telegram", chat_id)
        lang = people.person(store, pid)["lang"]
        try:
            kind, plan_id, answer = cq.get("data", "").split(":", 2)
            if kind == "ci":
                owner = store.one(
                    "SELECT r.person_id FROM plans pl JOIN routines r ON r.id=pl.routine_id WHERE pl.id=?", (int(plan_id),)
                )
                if owner and owner["person_id"] == pid:
                    people.record_answer(store, int(plan_id), answer)
                    sender.send(chat_id, t(lang, "thanks"))
        except ValueError:
            sender.send(chat_id, t(lang, "error"))
        return

    msg = update.get("message")
    if not msg:
        return
    chat_id = str(msg["chat"]["id"])
    lang = lang_of((msg.get("from") or {}).get("language_code"))
    pid = people.get_or_create_person(store, "telegram", chat_id, lang)
    lang = people.person(store, pid)["lang"]
    if "location" in msg:
        loc = msg["location"]
        try:
            people.set_location(store, pid, loc["latitude"], loc["longitude"])
            sender.send(chat_id, t(lang, "saved_loc"), {"remove_keyboard": True})
        except ValueError as e:
            sender.send(chat_id, str(e))
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text.startswith("/start"):
        sender.send(chat_id, t(lang, "welcome"), location_keyboard(lang))
        return
    if text.startswith("/hindi"):
        people.set_lang(store, pid, "hi")
        sender.send(chat_id, t("hi", "welcome"), location_keyboard("hi"))
        return
    if text.startswith("/english"):
        people.set_lang(store, pid, "en")
        sender.send(chat_id, t("en", "welcome"), location_keyboard("en"))
        return
    p = people.person(store, pid)
    try:
        reply = await agent(pid, p["lat"], p["lon"], text)
    except Exception:  # the person gets a clear message; the error goes to logs
        log.exception("agent turn failed")
        reply = t(lang, "error")
    sender.send(chat_id, reply or t(lang, "error"))


def send_nudges(store: Store, sender: Sender, now: datetime | None = None) -> int:
    now = now or now_ist()
    n = 0
    for d in people.due_nudges(store, now):
        if d["channel"] != "telegram":
            continue
        lang = d["lang"] if d["lang"] in TEXT else "en"
        sender.send(
            d["external_id"],
            t(lang, "nudge", act=ACTIVITY_WORD[lang].get(d["activity"], d["activity"]), start=d["start"],
              usual=d["habitual"], fc=round(d["forecast_mean"] or 0), fh=round(d["forecast_habitual_mean"] or 0)),
        )
        people.mark_nudged(store, d["plan_id"], now)
        n += 1
    return n


def send_checkins(store: Store, sender: Sender, day: date) -> int:
    n = 0
    for c in people.pending_checkins(store, day):
        if c["channel"] != "telegram":
            continue
        lang = c["lang"] if c["lang"] in TEXT else "en"
        act = ACTIVITY_WORD[lang].get(c["activity"], c["activity"])
        kb = {
            "inline_keyboard": [
                [{"text": t(lang, "b_planned", start=c["start"]), "callback_data": f"ci:{c['plan_id']}:went_planned"}],
                [{"text": t(lang, "b_usual", usual=c["habitual"]), "callback_data": f"ci:{c['plan_id']}:went_usual"}],
                [{"text": t(lang, "b_skip"), "callback_data": f"ci:{c['plan_id']}:skipped"}],
            ]
        }
        sender.send(c["external_id"], t(lang, "checkin", start=c["start"], usual=c["habitual"], act=act), kb)
        store.event("checkin_sent", now_ist().isoformat(), {"plan_id": c["plan_id"]})
        n += 1
    return n


def send_results(store: Store, sender: Sender, day: date, *, final: bool = False) -> int:
    """Tell people their measured result. Unverifiable days are only reported
    once ``final`` (two days later), in case late readings still arrive."""
    rows = store.q(
        """SELECT pl.id, pl.went_at, pl.habitual, o.status, o.went_mean, o.habitual_mean, o.reduction_pct,
                  pe.external_id, pe.lang, pe.channel, r.activity
           FROM outcomes o JOIN plans pl ON pl.id=o.plan_id JOIN routines r ON r.id=pl.routine_id
           JOIN people pe ON pe.id=r.person_id
           WHERE pl.day=? AND pe.channel='telegram' AND (o.status='verified' OR ?)
             AND pl.id NOT IN (SELECT CAST(json_extract(meta,'$.plan_id') AS INTEGER) FROM events WHERE kind='result_sent')""",
        (day.isoformat(), 1 if final else 0),
    )
    n = 0
    for r in rows:
        lang = r["lang"] if r["lang"] in TEXT else "en"
        act = ACTIVITY_WORD[lang].get(r["activity"], r["activity"])
        if r["status"] != "verified":
            msg = t(lang, "unverifiable")
        elif (r["reduction_pct"] or 0) > 0:
            msg = t(lang, "result", went=r["went_at"], wm=round(r["went_mean"]), hm=round(r["habitual_mean"]),
                    usual=r["habitual"], pct=round(r["reduction_pct"]), act=act)
        else:
            msg = t(lang, "result_worse", went=r["went_at"], wm=round(r["went_mean"]), hm=round(r["habitual_mean"]), usual=r["habitual"])
        sender.send(r["external_id"], msg)
        store.event("result_sent", now_ist().isoformat(), {"plan_id": r["id"]})
        n += 1
    return n


def daily_people_jobs(store: Store, sender: Sender | None, now: datetime | None = None, cams_fallback=None) -> dict:
    """Plan today for everyone with routines (from 04:00 IST), send due nudges,
    ask yesterday's check-ins from 08:00, verify and report outcomes."""
    now = now or now_ist()
    out: dict = {}
    if now.hour >= 4:
        planned = 0
        for r in store.q("SELECT DISTINCT person_id FROM routines WHERE active=1"):
            planned += len(people.plan_day(store, r["person_id"], now.date(), now=now, cams_fallback=cams_fallback))
        out["planned"] = planned
    if sender is not None:
        out["nudged"] = send_nudges(store, sender, now)
    yesterday = now.date() - timedelta(days=1)
    if sender is not None and now.hour >= 8 and not store.one(
        "SELECT 1 FROM events WHERE kind='checkins_done' AND meta=?", (f'{{"day": "{yesterday.isoformat()}"}}',)
    ):
        out["checkins"] = send_checkins(store, sender, yesterday)
        store.event("checkins_done", now.isoformat(), {"day": yesterday.isoformat()})
    out["outcomes"] = people.verify_outcomes(store, yesterday)
    two_days = now.date() - timedelta(days=2)
    out["outcomes_late"] = people.verify_outcomes(store, two_days)
    if sender is not None:
        out["results_sent"] = send_results(store, sender, yesterday) + send_results(store, sender, two_days, final=True)
    return out
