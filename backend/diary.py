"""Endelea diary: About me, AI conversation, end-of-day entry, bonus hours, PDF export.

Put this file next to main.py. Needs:  pip install reportlab
and an environment variable GEMINI_API_KEY (the key stays on the server, never in index.html).
"""
import datetime
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from io import BytesIO
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

# Gemini models, tried in this order when one is overloaded (503) or unknown.
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-2.5-flash"]
AI_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
BUSY_CODES = {429, 500, 502, 503, 504}

# ---- rules that the CODE enforces (the AI can only suggest) ----
MAX_BONUS_PER_DAY = 1.0
MAX_BONUS_PER_WEEK = 2.0
MIN_WORK_FOR_BONUS = 1.0      # hours of real work sessions that day
MIN_MESSAGES_FOR_BONUS = 3    # messages you wrote in the diary that day
MAX_MSG_CHARS = 4000
MAX_MESSAGES_PER_DAY = 60
DAY = 86400

TONES = {
    "gentle": "Tone: gentle. Supportive first, honest second.",
    "balanced": "Tone: balanced. Warm and honest in equal parts.",
    "direct": "Tone: direct. Honest first, kind second. No sugar-coating, no cruelty.",
}

SYSTEM = """You are Endelea, a warm, curious companion inside a daily diary app. The person talks to you, usually at the end of their day. You are not a therapist and not a teacher.

How you talk:
- Ask ONE question at a time, never a list. Keep replies short (2 to 4 sentences).
- Build on their exact words, their goals and their recent days. Avoid generic questions.
  Bad: "How was your day?"  Good: "You said the work wasn't productive even though you sat for three hours. What got in the way?"
- Ask about why and how it felt, not only about what happened.
- If they are sad or stressed, be gentle and do not rush to fix things.
- After about 5 or 6 exchanges, offer to wrap up the day.
- About their dreams: be honest, using their real numbers (hours worked, goals from About me). Give a concrete next step. Never shame them and never push them to overwork; if they already work too much, say so.
- You never give or promise hours yourself. Bonus hours are decided separately by the app at the end of the day.
- Reply in the language the person writes in."""

router = APIRouter()
_db = None
_earn = None
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- setup
def setup(app, conn, earn):
    global _db, _earn
    _db, _earn = conn, earn
    with conn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS about (id INTEGER PRIMARY KEY CHECK (id = 1), text TEXT, tone TEXT)")
        con.execute("INSERT OR IGNORE INTO about VALUES (1, '', 'balanced')")
        con.execute("""CREATE TABLE IF NOT EXISTS diary_msgs (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       day TEXT, role TEXT, content TEXT, ts REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS diary_days (day TEXT PRIMARY KEY, summary TEXT, mood TEXT,
                       finished INTEGER DEFAULT 0)""")
        con.execute("""CREATE TABLE IF NOT EXISTS diary_notes (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       day TEXT, author TEXT, text TEXT, ts REAL)""")
        con.execute("CREATE TABLE IF NOT EXISTS bonuses (day TEXT PRIMARY KEY, hours REAL, reason TEXT, ts REAL)")
        con.execute("CREATE TABLE IF NOT EXISTS story_days (day TEXT PRIMARY KEY, text TEXT, ts REAL)")
        con.execute("CREATE TABLE IF NOT EXISTS diary_pages (day TEXT PRIMARY KEY, text TEXT, ts REAL)")
        con.execute("""CREATE TABLE IF NOT EXISTS diary_images (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       day TEXT, mime TEXT, name TEXT, data BLOB, ts REAL)""")
        con.execute("CREATE TABLE IF NOT EXISTS diary_ai_notes (day TEXT PRIMARY KEY, text TEXT, emoji TEXT, ts REAL)")
        try:
            con.execute("ALTER TABLE diary_days ADD COLUMN emoji TEXT DEFAULT ''")
        except Exception:
            pass                  # column already there
    app.include_router(router)


# ---------------------------------------------------------------- helpers
def today():
    return time.strftime("%Y-%m-%d")


def check_day(day):
    if not DAY_RE.match(day):
        raise HTTPException(400, "Bad date")
    try:
        time.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Bad date")


def work_hours(con, day):
    start = time.mktime(time.strptime(day, "%Y-%m-%d"))
    return round(con.execute("SELECT COALESCE(SUM(hours),0) FROM sessions WHERE kind='work' AND ended>=? AND ended<?",
                             (start, start + DAY)).fetchone()[0], 2)


def msgs_of(con, day):
    return [dict(r) for r in con.execute("SELECT role, content, ts FROM diary_msgs WHERE day=? ORDER BY id", (day,))]


def notes_of(con, day):
    return [dict(r) for r in con.execute("SELECT id, author, text, ts FROM diary_notes WHERE day=? ORDER BY id", (day,))]


def day_row(con, day):
    r = con.execute("SELECT summary, mood, finished, emoji FROM diary_days WHERE day=?", (day,)).fetchone()
    if not r:
        return {"summary": "", "mood": "", "finished": 0, "emoji": ""}
    out = dict(r)
    out["emoji"] = out.get("emoji") or ""
    return out


def page_of(con, day):
    r = con.execute("SELECT text FROM diary_pages WHERE day=?", (day,)).fetchone()
    return r[0] if r else ""


def bonus_of(con, day):
    r = con.execute("SELECT hours, reason FROM bonuses WHERE day=?", (day,)).fetchone()
    return dict(r) if r else None


def week_bonus(con):
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * DAY))
    return con.execute("SELECT COALESCE(SUM(hours),0) FROM bonuses WHERE day>=?", (since,)).fetchone()[0]


def transcript(msgs, you="You", ai="Endelea"):
    return "\n".join(f"{you if m['role'] == 'user' else ai}: {m['content']}" for m in msgs)


_found = {"t": 0.0, "names": []}


def _discover(key):
    """Ask Google which Gemini 'flash' models this key can really use (names change over time)."""
    if time.time() - _found["t"] < 3600:
        return _found["names"]
    names = []
    try:
        req = urllib.request.Request(AI_URL.rstrip("/") + "?pageSize=200", headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        for m in data.get("models", []):
            n = str(m.get("name", "")).split("/")[-1]
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if not n.startswith("gemini-") or "flash" not in n:
                continue
            if re.search(r"image|tts|live|audio|native|robotics|computer|embedding|thinking|exp|8b|vision", n):
                continue
            names.append(n)
        names.sort(reverse=True)                                           # newest versions first
        names.sort(key=lambda n: ("preview" in n, "lite" in n))            # stable ones first, "lite" last
    except Exception as e:
        print(f"[ai] could not list models: {e}")
    _found.update(t=time.time(), names=names)
    return names


def _models(key):
    first = os.environ.get("ENDELEA_MODEL", "gemini-flash-latest")
    wanted = [first] + FALLBACK_MODELS
    found = _discover(key)
    if found:
        chain = [m for m in wanted if m in found] + found
    else:
        chain = wanted
    out = []
    for m in chain:
        if m not in out:
            out.append(m)
    return out[:4]


def _ask_gemini(model, key, body):
    req = urllib.request.Request(
        f"{AI_URL}{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def _text_of(data):
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError):
        return ""


def demo_mode():
    """Demo mode = no Gemini key (or ENDELEA_DEMO=1). The AI then answers with ready-made examples, nothing is sent anywhere."""
    return os.environ.get("ENDELEA_DEMO", "") == "1" or not os.environ.get("GEMINI_API_KEY", "").strip()


DEMO_ABOUT_QUESTIONS = [
    "Hi, I'm Endelea. What are you working on or studying right now?",
    "That sounds meaningful. What is the one goal you most want to reach this year?",
    "And in the long run, what does your dream life look like?",
    "What is the hardest part of getting there at the moment?",
    "What keeps you going on the days when it is difficult?",
    "Thank you for sharing that. You can press Save to my story whenever you feel done. Is there anything else you want to add?",
]
DEMO_STORIES = [
    "You keep showing up for your goals, one focused hour at a time. That steady effort is quietly building the life you described.",
    "Your curiosity and your discipline make a strong pair. Every session you finish is proof that your dreams are worth the work.",
    "You are building something real, step by step. The care you put into your plans shows how much your future matters to you.",
    "Your determination stands out. Each hour you invest is a promise to yourself that you are keeping.",
]
DEMO_TAG = "(Demo mode: this is an example answer. Add a free Gemini key to get the real, personal Endelea.)"


def _demo_ai(system, messages):
    """Ready-made answers for demo mode, built only from what the person wrote or the real hours in the request."""
    last = messages[-1]["content"] if messages else ""
    if system.startswith("You are Endelea, a warm, curious companion inside a daily diary app. Right now you are getting to know"):
        n = sum(1 for m in messages if m["role"] == "user" and not m["content"].startswith("[The person wants"))
        return DEMO_ABOUT_QUESTIONS[min(n, len(DEMO_ABOUT_QUESTIONS) - 1)]
    if system.startswith("You write notes for a person's About me page"):
        said, who = [], None
        for l in last.split("Conversation:\n")[-1].splitlines():
            if l.startswith("Person:"):
                who = "p"; l = l[len("Person:"):]
            elif l.startswith("Endelea:"):
                who = None
            if who == "p" and l.strip():
                said.append(l.strip())
        text = " ".join(said)[:900] or "I am just getting started."
        return text + " (Demo mode: your own words, not rewritten by the AI.)"
    if system.startswith("You are Endelea. You read one day of a person's diary page"):
        m = re.search(r"Hours of real work logged that day: ([\d.]+) h", last)
        hours = m.group(1) if m else "0"
        page = last.split("THEIR PAGE FOR THIS DAY:")[-1].split("RECENT DAYS")[0].strip()
        words = len(page.split())
        note = (f"Thank you for writing today ({words} words on your page, {hours} h of real focus logged). "
                f"Writing things down is already a good habit. {DEMO_TAG} "
                "The real Endelea reads your page, compares it with your earlier days and your work hours, "
                "tells you honestly whether you are on a good track, and suggests one next step.")
        return json.dumps({"note": note, "emoji": "🌙"})
    return "Thanks for telling me. " + DEMO_TAG


def call_ai(system, messages, max_tokens=600):
    """Free AI through Google Gemini (key from https://aistudio.google.com/apikey).
    If Gemini says "high demand" (503), it waits and retries, then tries the next model."""
    if demo_mode():
        return _demo_ai(system, messages)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in messages]
    seen = []                      # what Gemini answered, shown in the error so we can see what is wrong
    for model in _models(key):
        think_off = True           # thinking off = much faster answers; some models refuse it, then we retry without
        attempt = 0
        while attempt < 3:
            attempt += 1
            cfg = {"maxOutputTokens": max(max_tokens * 3, 1500)}
            if think_off:
                cfg["thinkingConfig"] = {"thinkingBudget": 0}
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": cfg}
            try:
                data = _ask_gemini(model, key, body)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")
                low = detail.lower()
                if e.code in (401, 403) or "api key not valid" in low or "api_key_invalid" in low:
                    raise HTTPException(502, "Gemini refused the API key. Create a new key at aistudio.google.com/apikey, set GEMINI_API_KEY again and restart the server.")
                if e.code == 400 and think_off and "think" in low:
                    think_off = False
                    continue
                print(f"[ai] {model}: HTTP {e.code} (try {attempt}) {detail[:200]!r}")
                if e.code == 429:                      # this model's free limit is used up: go to the next model at once
                    seen.append(f"{e.code} {model}")
                    break
                if e.code in BUSY_CODES:
                    if attempt < 3:
                        time.sleep(1.5 * attempt)
                        continue
                seen.append(f"{e.code} {model}")       # 404 unknown model, 400 bad request, or still busy after 3 tries
                break
            except Exception as e:
                print(f"[ai] {model}: {e}")
                seen.append(f"error {model}")          # timeout or no internet: next model
                break
            text = _text_of(data)
            if text:
                return text
            print(f"[ai] {model}: empty answer")
            seen.append(f"empty {model}")
            break
    hint = " The free limit may be used up: wait a minute." if any(x.startswith("429") for x in seen) else ""
    raise HTTPException(503, f"Endelea's AI is busy right now (Gemini said: {'; '.join(seen) or 'nothing'}).{hint} Try again in a few seconds.")


def system_prompt(con, day):
    a = con.execute("SELECT text, tone FROM about WHERE id=1").fetchone()
    s = SYSTEM + "\n\n" + TONES.get(a["tone"], TONES["balanced"])
    s += "\n\nAbout the person (written by them):\n" + (a["text"].strip() or "(nothing written yet; you may gently ask them about themselves)")
    s += f"\n\nToday is {day}. Hours of real work logged today: {work_hours(con, day)} h."
    recent = []
    for i in range(1, 8):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * DAY))
        row = day_row(con, d)
        if row["summary"]:
            recent.append(f"- {d} ({row['mood'] or '?'}, {work_hours(con, d)} h worked): {row['summary']}")
    if recent:
        s += "\n\nRecent days:\n" + "\n".join(recent)
    return s


def parse_json(text):
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:
        return {}


# ---------------------------------------------------------------- About me
class AboutBody(BaseModel):
    text: str
    tone: str = "balanced"


@router.get("/about")
def get_about():
    with _db() as con:
        return dict(con.execute("SELECT text, tone FROM about WHERE id=1").fetchone())


@router.post("/about")
def set_about(b: AboutBody):
    tone = b.tone if b.tone in TONES else "balanced"
    with _db() as con:
        con.execute("UPDATE about SET text=?, tone=? WHERE id=1", (b.text.strip()[:8000], tone))
        return {"ok": True}


# ---------------------------------------------------------------- About me: conversation
ABOUT_SYSTEM = """You are Endelea, a warm, curious companion inside a daily diary app. Right now you are getting to know the person so that their "About me" page becomes rich and true. You are not a therapist and not a teacher.

How you talk:
- Ask ONE question at a time, never a list. Keep replies short (1 to 3 sentences). Your words are read aloud, so write plain sentences: no lists, no markdown, no emojis.
- React to what they just said, using their own words, before you ask the next question.
- Over the conversation, gently find out: who they are, what they study or work on, their goals (this year and long term), their dream life and dream home, what is hard for them, and what keeps them going.
- If their About me already has notes, do not ask again what is already written. Ask about what is missing or what has changed.
- After about 8 exchanges, tell them they can press "Save to my story" whenever they feel done, and ask if there is anything else.
- Reply in the language the person writes in."""

ABOUT_SEED = "[The person wants to tell you about themselves. Start with one warm, specific question.]"


class AboutChatBody(BaseModel):
    messages: list[dict] = []


def _clean_msgs(raw):
    out = []
    for m in raw[-40:]:
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        out.append({"role": role, "content": content.strip()[:MAX_MSG_CHARS]})
    return out


@router.post("/about/chat")
def about_chat(b: AboutChatBody):
    msgs = _clean_msgs(b.messages)
    if msgs and msgs[-1]["role"] != "user":
        raise HTTPException(400, "Say something first")
    if not msgs or msgs[0]["role"] != "user":
        msgs.insert(0, {"role": "user", "content": ABOUT_SEED})
    with _db() as con:
        a = con.execute("SELECT text, tone FROM about WHERE id=1").fetchone()
        system = ABOUT_SYSTEM + "\n\n" + TONES.get(a["tone"], TONES["balanced"])
        system += "\n\nWhat their About me already says:\n" + (a["text"].strip() or "(nothing yet)")
    return {"reply": call_ai(system, msgs, 400)}


@router.post("/about/finish")
def about_finish(b: AboutChatBody):
    msgs = _clean_msgs(b.messages)
    if sum(1 for m in msgs if m["role"] == "user") < 2:
        raise HTTPException(400, "Talk a little more with Endelea first.")
    with _db() as con:
        old = (con.execute("SELECT text FROM about WHERE id=1").fetchone()[0] or "").strip()
    system = ("You write notes for a person's About me page from a conversation. Write ONLY the notes, in the first person (\"I\"), "
              "3 to 8 short sentences, using only facts the person said themselves (studies, goals, dreams, what is hard, what motivates them). "
              "Do not invent or interpret. No title, no list, no markdown. Write in the language the person used. "
              "Leave out anything that is already in the existing text.")
    user = f"Existing About me:\n{old or '(nothing yet)'}\n\nConversation:\n{transcript(msgs, 'Person', 'Endelea')}"
    added = call_ai(system, [{"role": "user", "content": user}], 500).strip()
    if not added:
        raise HTTPException(502, "The AI could not write the notes. Try again.")
    new = (old + "\n\n" if old else "") + f"[{today()}] " + added
    if len(new) > 8000:
        new = new[-8000:]         # keep the most recent notes
    with _db() as con:
        con.execute("UPDATE about SET text=? WHERE id=1", (new,))
    return {"text": new, "added": added}


# ---------------------------------------------------------------- today's conversation
class ChatBody(BaseModel):
    message: str


@router.get("/diary/today")
def diary_today():
    d = today()
    with _db() as con:
        row = day_row(con, d)
        return {"day": d, "hours_worked": work_hours(con, d), "messages": msgs_of(con, d), "finished": bool(row["finished"]),
                "summary": row["summary"], "mood": row["mood"], "bonus": bonus_of(con, d),
                "bonus_left_week": round(MAX_BONUS_PER_WEEK - week_bonus(con), 2)}


def _save(con, day, role, content):
    con.execute("INSERT INTO diary_msgs (day, role, content, ts) VALUES (?,?,?,?)", (day, role, content, time.time()))


@router.post("/diary/open")
def diary_open():
    d = today()
    with _db() as con:
        if msgs_of(con, d):
            raise HTTPException(400, "Today's check-in already started")
        reply = call_ai(system_prompt(con, d),
                        [{"role": "user", "content": "[The person just opened the diary. Start with one good, specific question.]"}])
        _save(con, d, "assistant", reply)
        return {"reply": reply}


@router.post("/diary/chat")
def diary_chat(b: ChatBody):
    text = b.message.strip()
    if not text:
        raise HTTPException(400, "Write or say something first")
    if len(text) > MAX_MSG_CHARS:
        raise HTTPException(400, "That message is too long")
    d = today()
    with _db() as con:
        hist = msgs_of(con, d)
        if len(hist) >= MAX_MESSAGES_PER_DAY:
            raise HTTPException(429, "That is enough talking for today. Come back tomorrow.")
        messages = [{"role": m["role"], "content": m["content"]} for m in hist] + [{"role": "user", "content": text}]
        if messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": "[The person opened the diary.]"})
        reply = call_ai(system_prompt(con, d), messages)
        _save(con, d, "user", text)
        _save(con, d, "assistant", reply)
        return {"reply": reply}


# ---------------------------------------------------------------- end of day + bonus
def bonus_decision(con, day, asked, n_user_msgs):
    """The AI only suggests. These rules decide."""
    work = work_hours(con, day)
    if asked <= 0:
        return 0.0, ""
    if work < MIN_WORK_FOR_BONUS:
        return 0.0, f"Bonus needs at least {MIN_WORK_FOR_BONUS:g} h of logged work that day."
    if n_user_msgs < MIN_MESSAGES_FOR_BONUS:
        return 0.0, f"Bonus needs at least {MIN_MESSAGES_FOR_BONUS} messages from you in the diary."
    room = MAX_BONUS_PER_WEEK - week_bonus(con)
    amount = math.floor(min(asked, MAX_BONUS_PER_DAY, room) * 2) / 2
    if amount <= 0:
        return 0.0, "Weekly bonus limit reached."
    return amount, ""


@router.post("/diary/finish")
def diary_finish():
    d = today()
    with _db() as con:
        row = day_row(con, d)
        if row["finished"]:
            return {"summary": row["summary"], "mood": row["mood"], "bonus": (bonus_of(con, d) or {}).get("hours", 0),
                    "bonus_note": "This day was already wrapped up.", "already": True}
        msgs = msgs_of(con, d)
        n_user = sum(1 for m in msgs if m["role"] == "user")
        if n_user < 2:
            raise HTTPException(400, "Talk a little more with Endelea before ending the day.")
        work = work_hours(con, d)
        system = ("You write the end-of-day diary entry. Reply with ONLY a JSON object, no other text:\n"
                  '{"summary": "3 to 5 sentences in the second person (\\"you\\") about how the day went and felt, and why",'
                  ' "mood": "one or two words", "emoji": "ONE emoji that fits the mood of the day", "bonus_hours": 0 or 0.5 or 1, "bonus_reason": "one short sentence"}\n'
                  "Bonus hours reward a genuinely productive and focused day, not just a long one. Be selective: most days get 0. "
                  "Write in the language the person used.")
        user = f"Date: {d}\nHours of real work logged: {work}\n\nAbout the person:\n{con.execute('SELECT text FROM about WHERE id=1').fetchone()[0]}\n\nConversation:\n{transcript(msgs)}"
        data = parse_json(call_ai(system, [{"role": "user", "content": user}], 700))
        summary = str(data.get("summary", "")).strip() or "(No summary could be written.)"
        mood = str(data.get("mood", "")).strip()[:40]
        emoji = str(data.get("emoji", "")).strip()[:8]
        try:
            asked = float(data.get("bonus_hours", 0))
        except (TypeError, ValueError):
            asked = 0.0
        amount, why_not = bonus_decision(con, d, asked, n_user)
        con.execute("INSERT OR REPLACE INTO diary_days (day, summary, mood, finished, emoji) VALUES (?,?,?,1,?)", (d, summary, mood, emoji))
        note = why_not
        if amount > 0:
            _earn(con, amount)
            reason = str(data.get("bonus_reason", "")).strip()
            con.execute("INSERT OR REPLACE INTO bonuses VALUES (?,?,?,?)", (d, amount, reason, time.time()))
            note = reason
        return {"summary": summary, "mood": mood, "emoji": emoji, "bonus": amount, "bonus_note": note, "already": False}


# ---------------------------------------------------------------- past days, notes, reflections
@router.get("/diary/days")
def diary_days():
    with _db() as con:
        days = {r[0] for r in con.execute("SELECT DISTINCT day FROM diary_msgs")}
        days |= {r[0] for r in con.execute("SELECT DISTINCT day FROM diary_notes")}
        days |= {r[0] for r in con.execute("SELECT day FROM diary_days")}
        days |= {r[0] for r in con.execute("SELECT day FROM diary_pages WHERE text<>''")}
        days |= {r[0] for r in con.execute("SELECT DISTINCT day FROM diary_images")}
        days |= {r[0] for r in con.execute("SELECT day FROM diary_ai_notes")}
        out = []
        for d in sorted(days, reverse=True):
            row = day_row(con, d)
            page = page_of(con, d)
            an = con.execute("SELECT emoji FROM diary_ai_notes WHERE day=?", (d,)).fetchone()
            n_img = con.execute("SELECT COUNT(*) FROM diary_images WHERE day=?", (d,)).fetchone()[0]
            out.append({"day": d, "page": bool(page), "snippet": " ".join(page.split())[:90], "images": n_img, "ai_note": bool(an),
                        "mood": row["mood"], "emoji": (an[0] if an and an[0] else row["emoji"]), "finished": bool(row["finished"]),
                        "hours": work_hours(con, d), "bonus": (bonus_of(con, d) or {}).get("hours", 0),
                        "messages": len(msgs_of(con, d)), "notes": len(notes_of(con, d))})
        return out


@router.get("/diary/day/{day}")
def diary_day(day: str):
    check_day(day)
    with _db() as con:
        row = day_row(con, day)
        return {"day": day, "hours_worked": work_hours(con, day), "messages": msgs_of(con, day), "notes": notes_of(con, day),
                "summary": row["summary"], "mood": row["mood"], "emoji": row["emoji"], "finished": bool(row["finished"]),
                "bonus": bonus_of(con, day), "page": page_of(con, day),
                "images": [dict(r) for r in con.execute("SELECT id, name FROM diary_images WHERE day=? ORDER BY id", (day,))],
                "ai_note": (lambda r: dict(r) if r else None)(con.execute("SELECT text, emoji, ts FROM diary_ai_notes WHERE day=?", (day,)).fetchone()), "story": (con.execute("SELECT text FROM story_days WHERE day=?", (day,)).fetchone() or [""])[0]}


class PageBody(BaseModel):
    day: str
    text: str


@router.post("/diary/page")
def save_page(b: PageBody):
    """The free page of one day: write as much as you like, come back and add to it."""
    check_day(b.day)
    if b.day > today():
        raise HTTPException(400, "You cannot write on a day that has not come yet.")
    text = b.text.rstrip()
    if len(text) > 60000:
        raise HTTPException(400, "That page is too long (60 000 characters maximum).")
    with _db() as con:
        if text.strip():
            con.execute("INSERT OR REPLACE INTO diary_pages (day, text, ts) VALUES (?,?,?)", (b.day, text, time.time()))
        else:
            con.execute("DELETE FROM diary_pages WHERE day=?", (b.day,))
        return {"ok": True}


IMG_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMG_BYTES = 10 * 1024 * 1024
MAX_IMAGES_PER_DAY = 24


@router.post("/diary/image")
async def add_image(request: Request, day: str = "", name: str = ""):
    """A picture for one day's page. The browser sends the raw picture as the request body."""
    check_day(day)
    if day > today():
        raise HTTPException(400, "You cannot add pictures to a day that has not come yet.")
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime not in IMG_TYPES:
        raise HTTPException(400, "Only JPG, PNG, GIF or WEBP pictures.")
    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty picture.")
    if len(data) > MAX_IMG_BYTES:
        raise HTTPException(400, "That picture is too big (10 MB maximum).")
    with _db() as con:
        if con.execute("SELECT COUNT(*) FROM diary_images WHERE day=?", (day,)).fetchone()[0] >= MAX_IMAGES_PER_DAY:
            raise HTTPException(400, f"That is enough pictures for one day ({MAX_IMAGES_PER_DAY} maximum).")
        cur = con.execute("INSERT INTO diary_images (day, mime, name, data, ts) VALUES (?,?,?,?,?)",
                          (day, mime, name[:120], data, time.time()))
        return {"id": cur.lastrowid, "name": name[:120]}


@router.get("/diary/image/{image_id}")
def get_image(image_id: int):
    with _db() as con:
        r = con.execute("SELECT mime, data FROM diary_images WHERE id=?", (image_id,)).fetchone()
    if not r:
        raise HTTPException(404, "No such picture")
    return Response(bytes(r["data"]), media_type=r["mime"],
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.post("/diary/image/{image_id}/delete")
def delete_image(image_id: int):
    with _db() as con:
        con.execute("DELETE FROM diary_images WHERE id=?", (image_id,))
        return {"ok": True}


NOTE_SYSTEM = """You are Endelea. You read one day of a person's diary page, together with their recent days as your memory, and write the note that is saved under that day.
Write 5 to 8 sentences, in the second person ("you"), warm but honest:
1. What you think of this day and of their work today (use the real hours and tasks you are given).
2. What they have been going through: the feelings and events they wrote.
3. Compare with their recent days: is the trend good, stable or worrying? Be specific (dates, hours, habits that come back).
4. Say honestly whether what they are doing looks good or not for the goals they wrote about, and give ONE concrete next step.
Rules: use only facts from the text, never invent. Never shame them and never push them to overwork; if they already work too much, say so. If they were sad or stressed, be gentle first. Never promise or give hours.
Reply with ONLY a JSON object: {"note": "...", "emoji": "ONE emoji that fits the mood of the day"}. Write in the language of the page."""


@router.post("/diary/endelea-note/{day}")
def endelea_note(day: str):
    """Endelea's note for one day (new or updated), with the recent days as memory. Shown in yellow under the page and in the PDF."""
    check_day(day)
    if day > today():
        raise HTTPException(400, "That day has not come yet.")
    with _db() as con:
        page = page_of(con, day).strip()
        if len(page) < 20:
            raise HTTPException(400, "Write a few lines on the page first, then ask Endelea for her note.")
        about = (con.execute("SELECT text FROM about WHERE id=1").fetchone()[0] or "").strip()
        start = time.mktime(time.strptime(day, "%Y-%m-%d"))
        tasks = [f"{r[0] or 'work'} ({round(r[1], 2)} h)" for r in con.execute(
            "SELECT task, hours FROM sessions WHERE kind='work' AND ended>=? AND ended<? ORDER BY ended", (start, start + DAY))]
        recent = []
        for i in range(1, 15):
            dd = time.strftime("%Y-%m-%d", time.localtime(start + 12 * 3600 - i * DAY))
            pg, h = page_of(con, dd).strip(), work_hours(con, dd)
            old = con.execute("SELECT text FROM diary_ai_notes WHERE day=?", (dd,)).fetchone()
            if pg or h or old:
                recent.append(f"[{dd}] worked {h} h. " + (f"Page: {pg[-500:]} " if pg else "") + (f"Your note then: {old[0][:350]}" if old else ""))
        mine = con.execute("SELECT text FROM diary_ai_notes WHERE day=?", (day,)).fetchone()
        hours = work_hours(con, day)
    user = (f"DAY: {day}\nHours of real work logged that day: {hours} h. Tasks: {'; '.join(tasks) or '(none logged)'}\n\n"
            f"ABOUT THE PERSON (written by them):\n{about[:2500] or '(nothing)'}\n\n"
            f"THEIR PAGE FOR THIS DAY:\n{page[:7000]}\n\n"
            f"RECENT DAYS (your memory):\n{chr(10).join(recent)[-7000:] or '(this is the first day)'}")
    if mine:
        user += f"\n\nYour previous note for this same day (update it, do not repeat it word for word):\n{mine[0]}"
    raw = call_ai(NOTE_SYSTEM, [{"role": "user", "content": user}], 700)
    data = parse_json(raw)
    note = str(data.get("note", "")).strip()
    if not note:
        if raw.lstrip().startswith("{"):
            raise HTTPException(503, "Endelea's AI is busy right now (the note came back broken). Try again in a few seconds.")
        note = raw.strip()
    emoji = str(data.get("emoji", "")).strip()[:8]
    now = time.time()
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO diary_ai_notes (day, text, emoji, ts) VALUES (?,?,?,?)", (day, note, emoji, now))
    return {"text": note, "emoji": emoji, "ts": now}


class NoteBody(BaseModel):
    day: str
    text: str


@router.post("/diary/note")
def add_note(b: NoteBody):
    check_day(b.day)
    text = b.text.strip()
    if not text:
        raise HTTPException(400, "Write a note first")
    with _db() as con:
        con.execute("INSERT INTO diary_notes (day, author, text, ts) VALUES (?,?,?,?)", (b.day, "you", text[:4000], time.time()))
        return {"ok": True}


@router.post("/diary/reflect/{day}")
def reflect(day: str):
    """Endelea reads one old day plus everything written after it, and adds a dated note under that day."""
    check_day(day)
    with _db() as con:
        msgs = msgs_of(con, day)
        if not msgs:
            raise HTTPException(400, "Nothing was said on that day")
        later = []
        for d in sorted(r[0] for r in con.execute("SELECT DISTINCT day FROM diary_msgs WHERE day>? ", (day,))):
            row = day_row(con, d)
            said = " | ".join(m["content"][:300] for m in msgs_of(con, d) if m["role"] == "user")
            later.append(f"[{d}] mood: {row['mood'] or '?'}. Summary: {row['summary'] or '-'}. You said: {said}")
            later += [f"[{d}] your own note: {n['text']}" for n in notes_of(con, d) if n["author"] == "you"]
        later_text = "\n".join(later)[-7000:] or "(nothing written after this day yet)"
        mine = [f"[{n['author']}] {n['text']}" for n in notes_of(con, day)]
        row = day_row(con, day)
        system = ("You are Endelea. You are re-reading an old day of the person's diary together with what they wrote afterwards. "
                  "Write ONE short note (3 to 6 sentences, second person) that will be saved under that old day. "
                  "Say how they felt, how long it lasted if later entries show it, what caused it, and what changed or what they realised later "
                  "(mention dates). Only use facts that appear in the text. If later entries contradict that day, say so kindly. "
                  "Write in the language the person used.")
        user = (f"OLD DAY {day} (mood: {row['mood'] or '?'}, {work_hours(con, day)} h worked)\n{transcript(msgs)}\n\n"
                f"EXISTING NOTES ON THIS DAY:\n{chr(10).join(mine) or '(none)'}\n\nWHAT CAME AFTER:\n{later_text}")
        text = call_ai(system, [{"role": "user", "content": user}], 500)
        con.execute("INSERT INTO diary_notes (day, author, text, ts) VALUES (?,?,?,?)", (day, "endelea", text, time.time()))
        return {"ok": True, "note": text}


# ---------------------------------------------------------------- Profile: "My story" (new every day, only positive)
STORY_ANGLES = ["the effort you put in lately", "your dreams and the future you are building", "a strength you showed",
                "something you can be proud of", "what keeps you going", "how far you have already come",
                "the things that make you, you"]

STORY_SYSTEM = """You write the short "My story" text on a person's profile page in a self-growth app.
Rules:
- 2 or 3 short sentences, at most 55 words, written to the person in the second person ("you").
- ONLY positive things: their strengths, effort, progress, goals, dreams and what brings them joy.
- NEVER mention struggles, difficulties, health, body, weight, fears, sadness, failures or anything negative. If the material contains such things, simply leave them out.
- Use only facts from the material. Do not invent anything.
- It must feel different from the previous texts: take the angle you are given.
- Warm and sincere, no flattery overload. No title, no list, no markdown, no emojis.
- Write in the language the person mostly used in the material."""


@router.get("/story")
def story():
    """Not interactive: one short positive text per day, written from About me and the recent diary days."""
    d = today()
    with _db() as con:
        row = con.execute("SELECT text FROM story_days WHERE day=?", (d,)).fetchone()
        if demo_mode():       # example text, not saved, so a real one can be written once a key is added
            return {"day": d, "text": DEMO_STORIES[int(time.strftime("%j")) % len(DEMO_STORIES)], "demo": True}
        if row:
            return {"day": d, "text": row[0]}
        about = (con.execute("SELECT text FROM about WHERE id=1").fetchone()[0] or "").strip()
        recent, said = [], []
        for i in range(0, 7):
            dd = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * DAY))
            r = day_row(con, dd)
            if r["summary"]:
                recent.append(f"- {dd}: {r['summary']}")
            if i < 3:
                said += [m["content"][:300] for m in msgs_of(con, dd) if m["role"] == "user"]
        prev = [r[0] for r in con.execute("SELECT text FROM story_days WHERE day<? ORDER BY day DESC LIMIT 3", (d,))]
    if not about and not recent and not said:
        return {"day": d, "text": ""}
    angle = STORY_ANGLES[int(time.strftime("%j")) % len(STORY_ANGLES)]
    material = (f"Angle for today: {angle}\n\nAbout the person (written by them):\n{about[:3000] or '(nothing)'}\n\n"
                f"Recent diary days:\n{chr(10).join(recent) or '(none)'}\n\nWhat they said lately:\n{' | '.join(said)[-1500:] or '(nothing)'}\n\n"
                f"Previous texts (do not repeat them):\n{chr(10).join('- ' + p for p in prev) or '(none)'}")
    try:
        text = " ".join(call_ai(STORY_SYSTEM, [{"role": "user", "content": material}], 200).split())
    except HTTPException:
        return {"day": d, "text": prev[0] if prev else "", "stale": True}    # AI busy: show yesterday's, try again next time
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO story_days (day, text, ts) VALUES (?,?,?)", (d, text, time.time()))
    return {"day": d, "text": text}


# ---------------------------------------------------------------- status + demo community
@router.get("/status")
def status():
    return {"demo": demo_mode()}


# Sample people (invented, NOT real users). A real community needs online accounts and a shared server.
SAMPLE_PEOPLE = [   # name, all-time hours, hours this week
    ("Amina", 412, 31), ("Lucas", 336, 27), ("Yuki", 281, 24), ("Sofia", 205, 19), ("Omar", 167, 16),
    ("Chloé", 124, 12), ("Mateo", 88, 9), ("Lena", 61, 6), ("Noah", 37, 4), ("Inès", 19, 2.5),
]


def _level(hours):
    return 1 + int((hours / 2) ** 0.5)


@router.get("/community")
def community(scope: str = "all"):
    """Leaderboard by focus hours: you + invented sample people. Labeled as a demo in the app."""
    week = scope == "week"
    with _db() as con:
        since = time.time() - 7 * DAY
        mine = con.execute("SELECT COALESCE(SUM(hours),0) FROM sessions WHERE ended IS NOT NULL" + (" AND ended>=?" if week else ""),
                           (since,) if week else ()).fetchone()[0]
        total = con.execute("SELECT COALESCE(SUM(hours),0) FROM sessions WHERE ended IS NOT NULL").fetchone()[0]
    rows = [{"name": n, "hours": (w if week else a), "level": _level(a), "you": False} for n, a, w in SAMPLE_PEOPLE]
    rows.append({"name": "You", "hours": round(mine, 2), "level": _level(total), "you": True})
    rows.sort(key=lambda r: (-r["hours"], r["you"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"scope": "week" if week else "all", "sample": True, "people": rows}


# ---------------------------------------------------------------- PDF
_FIX = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " "})


def _t(s):
    s = str(s).translate(_FIX).encode("latin-1", "replace").decode("latin-1")   # built-in fonts: Latin-1 only
    return escape(s).replace("\n", "<br/>")


def _pdf_image(data):
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    w, h = ImageReader(BytesIO(data)).getSize()
    k = min(13 * cm / w, 9 * cm / h)
    img = Image(BytesIO(data), width=w * k, height=h * k)
    img.hAlign = "LEFT"
    return img


@router.get("/diary/pdf")
def diary_pdf():
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        raise HTTPException(503, "Run: pip install reportlab")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=colors.HexColor("#FF7043"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], spaceBefore=14, textColor=colors.HexColor("#2B2A33"))
    body = ss["BodyText"]
    you = ParagraphStyle("you", parent=body, leftIndent=0, textColor=colors.HexColor("#2B2A33"))
    ai = ParagraphStyle("ai", parent=body, leftIndent=14, textColor=colors.HexColor("#0e8a80"))
    note = ParagraphStyle("note", parent=body, leftIndent=0, backColor=colors.HexColor("#FFE08A"), borderPadding=7, spaceBefore=12, spaceAfter=6,
                          textColor=colors.HexColor("#2B2A33"))
    small = ParagraphStyle("small", parent=body, fontSize=9, textColor=colors.HexColor("#6b6672"))

    story = [Paragraph("My Endelea diary", h1), Paragraph(_t("Exported on " + time.strftime("%Y-%m-%d")), small)]
    with _db() as con:
        a = con.execute("SELECT text FROM about WHERE id=1").fetchone()[0].strip()
        if a:
            story += [Paragraph("About me", h2), Paragraph(_t(a), body)]
        days = {r[0] for r in con.execute("SELECT day FROM diary_pages WHERE text<>''")}
        days |= {r[0] for r in con.execute("SELECT DISTINCT day FROM diary_images")}
        days |= {r[0] for r in con.execute("SELECT day FROM diary_ai_notes")}
        for d in sorted(days):
            y, m, dn = (int(x) for x in d.split("-"))
            nice = datetime.date(y, m, dn).strftime("%A %d %B %Y")
            story += [Spacer(1, 6), HRFlowable(width="100%", color=colors.HexColor("#2B2A33")), Paragraph(_t(nice), h2)]
            hrs = work_hours(con, d)
            if hrs:
                story.append(Paragraph(_t(f"Hours worked: {hrs} h"), small))
            page = page_of(con, d)
            if page:
                story.append(Paragraph(_t(page), body))
            for im in con.execute("SELECT data FROM diary_images WHERE day=? ORDER BY id", (d,)).fetchall():
                try:
                    story += [Spacer(1, 6), _pdf_image(bytes(im["data"]))]
                except Exception:
                    pass          # a picture the PDF cannot read is skipped
            n = con.execute("SELECT text FROM diary_ai_notes WHERE day=?", (d,)).fetchone()
            if n:
                story.append(Paragraph("<b>Endelea's note:</b> " + _t(n["text"]), note))
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title="Endelea diary").build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="endelea-diary.pdf"'})
