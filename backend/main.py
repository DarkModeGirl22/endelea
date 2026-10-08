import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.environ.get("ENDELEA_DB") or ROOT / "endelea.db")
DAY = 86400
MODES = {"day": DAY, "month": 30 * DAY}
WORKOUT_CAP = 1.0      # hours per day, honour mode
MAX_SESSION = 12.0     # hours counted per session
SINGLE_KINDS = ("rug", "shelf", "deskbig")   # only one of each can be shown in the room

app = FastAPI()


@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# key, name, category, tier, m2, description, rent/day, rent/month, buy  (hours, placeholders)
HOMES = [
    ("studio_attic", "The Attic", "Studio (city)", 1, 14, "Old district, sloping roof, a bit worn.", 1.5, 28, 1700),
    ("studio_tram", "Tram Corner", "Studio (city)", 2, 22, "City center, clean and simple.", 2, 40, 2400),
    ("studio_loft", "The Brick Loft", "Studio (city)", 3, 30, "Creative district, big windows.", 3, 60, 3600),
    ("forest_hideaway", "Ground Floor Hideaway", "Flat near the forest", 1, 35, "Quiet, but a bit damp.", 2, 42, 2500),
    ("forest_edge", "Forest Edge Flat", "Flat near the forest", 2, 50, "2 rooms and a balcony.", 3, 60, 3600),
    ("forest_canopy", "The Canopy Flat", "Flat near the forest", 3, 70, "Wood and glass, view over the trees.", 4.5, 90, 5400),
    ("beach_dunes", "Behind the Dunes", "Flat by the beach", 1, 30, "The sea is 10 minutes on foot.", 3, 63, 3800),
    ("beach_balcony", "Balcony Sea View", "Flat by the beach", 2, 55, "2 rooms, balcony facing the sea.", 5, 90, 5400),
    ("beach_sunset", "Sunset Seafront", "Flat by the beach", 3, 90, "A terrace right on the sand.", 7, 135, 8100),
    ("penthouse_oldtown", "Old Town Top Floor", "Luxury penthouse (city)", 1, 80, "City view, older building.", 9, 175, 10500),
    ("penthouse_rooftop", "Rooftop Terrace", "Luxury penthouse (city)", 2, 120, "Modern, with a big terrace.", 13, 250, 15000),
    ("penthouse_skyline", "Skyline Penthouse", "Luxury penthouse (city)", 3, 200, "Private lift and a 360° view.", 19, 375, 22500),
    ("house_little", "Little Suburban House", "House with garden", 1, 70, "Small garden, needs paint.", 5, 105, 6300),
    ("house_family", "Family House", "House with garden", 2, 110, "3 bedrooms and a lawn.", 8, 150, 9000),
    ("house_renovated", "Renovated Villa", "House with garden", 3, 160, "Big garden with trees.", 11, 225, 13500),
    ("villa_gated", "Gated Modern Villa", "Luxury house", 1, 250, "Modern, with a pool.", 14, 280, 16800),
    ("villa_hilltop", "Hilltop Villa", "Luxury house", 2, 350, "Pool and a view over the valley.", 20, 400, 24000),
    ("villa_estate", "The Estate", "Luxury house", 3, 600, "A park and a guest house.", 30, 600, 36000),
]

# Items you start with (always in your room, free)
START_ITEMS = [
    ("shared_room", "Shared room", "start", 0), ("desk", "Desk", "start", 0),
    ("bed", "Bed", "start", 0), ("laptop", "Laptop", "start", 0),
]

# key, name, tab, sub, kind, shape, color, buy price, rent/day, rent/month   (hours, placeholders)
# buy price None = cannot be bought (rent only). rent None = cannot be rented that way.
CATALOG = [
    # ----- Furniture tab: Furniture -----
    ("rug", "Sunny rug", "furniture", "furniture", "rug", "round", "#FFB627", 5, None, None),
    ("rug_teal", "Teal rug", "furniture", "furniture", "rug", "round", "#1BB5A8", 8, None, None),
    ("rug_coral", "Coral rug", "furniture", "furniture", "rug", "round", "#FF7043", 12, None, None),
    ("rug_persian", "Persian rug", "furniture", "furniture", "rug", "persian", "#9b2d3a", 90, None, 8),
    ("bookshelf", "Bookshelf", "furniture", "furniture", "shelf", "plain", "#8a6a45", 8, None, None),
    ("shelf_bright", "Rainbow shelf", "furniture", "furniture", "shelf", "bright", "#e8d6b0", 25, None, None),
    ("shelf_library", "Library shelf", "furniture", "furniture", "shelf", "library", "#5a3a24", 120, None, 10),
    ("sofa", "Lemon sofa", "furniture", "furniture", "big", "sofa", "#F2C94C", 10, None, None),
    ("sofa_teal", "Teal sofa", "furniture", "furniture", "big", "sofa", "#1BB5A8", 45, None, None),
    ("armchair", "Cozy armchair", "furniture", "furniture", "big", "armchair", "#FF7043", 30, None, None),
    ("sofa_velvet", "Velvet sofa", "furniture", "furniture", "big", "sofa", "#5b3ea6", 220, None, 18),
    ("piano", "Grand piano", "furniture", "furniture", "big", "piano", "#1b1b1b", 900, None, 60),
    ("aquarium", "Aquarium", "furniture", "furniture", "big", "aquarium", "#FF7043", 150, None, 14),
    ("floor_lamp", "Floor lamp", "furniture", "furniture", "floor", "floorlamp", "#FFB627", 6, None, None),
    ("big_plant", "Big plant", "furniture", "furniture", "floor", "bigplant", "#4f9a5a", 9, None, None),
    ("palm", "Palm tree", "furniture", "furniture", "floor", "palm", "#3f9a52", 35, None, None),
    ("guitar", "Guitar", "furniture", "furniture", "floor", "guitar", "#d9822b", 40, 1, 4),
    # ----- Furniture tab: Decoration -----
    ("plant", "Desk plant", "furniture", "decor", "desk", "plant", "#4f9a5a", 2, None, None),
    ("mug", "Coffee mug", "furniture", "decor", "desk", "mug", "#1BB5A8", 2, None, None),
    ("candle", "Candle", "furniture", "decor", "desk", "candle", "#FF7043", 2, None, None),
    ("frame", "Photo frame", "furniture", "decor", "desk", "frame", "#7fd6f5", 3, None, None),
    ("lamp", "Desk lamp", "furniture", "decor", "desk", "lamp", "#FF7043", 3, None, None),
    ("coffee_machine", "Coffee machine", "furniture", "decor", "desk", "coffee", "#FF7043", 6, None, None),
    ("headphones", "Headphones", "furniture", "decor", "desk", "headphones", "#5b3ea6", 8, None, None),
    ("globe", "Globe", "furniture", "decor", "desk", "globe", "#38b6c9", 15, None, None),
    ("trophy", "Golden trophy", "furniture", "decor", "desk", "trophy", "#d4a017", 120, None, 10),
    ("monitor", "Big monitor", "furniture", "decor", "deskbig", "monitor", "#7fd6f5", 12, None, None),
    ("poster", "Sunny poster", "furniture", "decor", "wall", "poster", "#FFB627", 3, None, None),
    ("clock", "Wall clock", "furniture", "decor", "wall", "clock", "#1BB5A8", 4, None, None),
    ("mirror", "Mirror", "furniture", "decor", "wall", "mirror", "#8a6a45", 10, None, None),
    ("neon", "Neon bolt", "furniture", "decor", "wall", "neon", "#FF7043", 30, None, None),
    ("sunpainting", "Sun painting", "furniture", "decor", "wall", "sunpainting", "#FF7043", 40, None, 4),
    ("gallery", "Gallery frames", "furniture", "decor", "wall", "gallery", "#5b3ea6", 60, None, None),
    ("gold_mirror", "Golden mirror", "furniture", "decor", "wall", "goldmirror", "#d4a017", 200, None, 16),
    # ----- Objects tab: Transport -----
    ("bus_card", "Bus pass", "objects", "transport", "obj", "buscard", "#1BB5A8", None, 0.2, 3),
    ("metro_card", "Metro pass", "objects", "transport", "obj", "metrocard", "#7B61FF", None, 0.3, 5),
    ("kick_scooter", "Kick scooter", "objects", "transport", "obj", "kick", "#FF7043", 12, 0.5, 8),
    ("e_scooter", "Electric scooter", "objects", "transport", "obj", "escooter", "#1BB5A8", 45, 1, 18),
    ("bike_city", "City bike", "objects", "transport", "obj", "bike", "#FF7043", 25, 0.8, 12),
    ("bike_mountain", "Mountain bike", "objects", "transport", "obj", "bike", "#5fb36b", 40, 1.2, 18),
    ("bike_electric", "Electric bike", "objects", "transport", "obj", "ebike", "#38b6c9", 90, 2, 35),
    ("moto_small", "Small motorbike", "objects", "transport", "obj", "moto", "#FFB627", 300, 2.5, 28),
    ("moto_road", "Road motorbike", "objects", "transport", "obj", "moto", "#FF7043", 700, 5, 60),
    ("moto_sport", "Sport motorbike", "objects", "transport", "obj", "sportmoto", "#1BB5A8", 1800, 13, 150),
    ("moto_cruiser", "Cruiser", "objects", "transport", "obj", "cruiser", "#8a2b2b", 2600, 18, 215),
    ("car_old", "Old hatchback", "objects", "transport", "obj", "car", "#9a8f80", 450, 4, 40),
    ("car_city", "City car", "objects", "transport", "obj", "car", "#FFB627", 800, 6, 70),
    ("car_family", "Family car", "objects", "transport", "obj", "sedan", "#1BB5A8", 1500, 11, 130),
    ("car_suv", "SUV", "objects", "transport", "obj", "suv", "#5b3ea6", 2400, 17, 200),
    ("car_sport", "Sports car", "objects", "transport", "obj", "sport", "#FF7043", 4500, 32, 380),
    ("car_lux", "Luxury sedan", "objects", "transport", "obj", "sedan", "#2B2A33", 7500, 52, 620),
    ("car_super", "Supercar", "objects", "transport", "obj", "supercar", "#FFB627", 15000, 100, 1250),
    # ----- Objects tab: Clothes -----
    ("tee_sun", "Sunny tee", "objects", "clothes", "obj", "tee", "#FFB627", 2, None, None),
    ("tee_white", "White tee", "objects", "clothes", "obj", "tee", "#f4f1e8", 2, None, None),
    ("jeans", "Jeans", "objects", "clothes", "obj", "pants", "#3b6fb6", 5, None, None),
    ("skirt", "Lilac skirt", "objects", "clothes", "obj", "skirt", "#7B61FF", 6, None, None),
    ("hoodie", "Coral hoodie", "objects", "clothes", "obj", "hoodie", "#FF7043", 8, None, None),
    ("sneakers", "Sneakers", "objects", "clothes", "obj", "sneakers", "#FF7043", 10, None, None),
    ("dress_day", "Teal dress", "objects", "clothes", "obj", "dress", "#1BB5A8", 12, None, None),
    ("jacket_denim", "Denim jacket", "objects", "clothes", "obj", "jacket", "#4a78b8", 20, None, None),
    ("boots", "Leather boots", "objects", "clothes", "obj", "boots", "#6b4a2b", 22, None, None),
    ("coat_wool", "Wool coat", "objects", "clothes", "obj", "coat", "#b5651d", 45, None, None),
    ("suit", "Business suit", "objects", "clothes", "obj", "suit", "#2B2A33", 150, 5, None),
    ("evening_dress", "Evening dress", "objects", "clothes", "obj", "evening", "#7B61FF", 220, 8, None),
    ("designer_coat", "Designer coat", "objects", "clothes", "obj", "coat", "#8a2b2b", 400, 12, None),
    # ----- Objects tab: Accessories -----
    ("cap", "Sunny cap", "objects", "accessories", "obj", "cap", "#FFB627", 3, None, None),
    ("sunglasses", "Sunglasses", "objects", "accessories", "obj", "sunglasses", "#FF7043", 6, None, None),
    ("backpack", "Backpack", "objects", "accessories", "obj", "backpack", "#1BB5A8", 12, None, None),
    ("handbag", "Handbag", "objects", "accessories", "obj", "handbag", "#7B61FF", 20, None, None),
    ("watch", "Everyday watch", "objects", "accessories", "obj", "watch", "#2B2A33", 35, None, None),
    ("necklace", "Pearl necklace", "objects", "accessories", "obj", "necklace", "#f4f1e8", 90, 3, None),
    ("watch_gold", "Golden watch", "objects", "accessories", "obj", "watch", "#d4a017", 300, 6, None),
    ("ring", "Diamond ring", "objects", "accessories", "obj", "ring", "#7fd6f5", 500, 8, None),
]
OLD_HOME_KEYS = ("studio_city", "flat_forest", "flat_beach", "house_garden", "house_luxury")


def init():
    with conn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS items (key TEXT PRIMARY KEY, name TEXT, category TEXT, price REAL)")
        con.execute("CREATE TABLE IF NOT EXISTS inventory (key TEXT PRIMARY KEY)")
        con.execute("CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY, hours REAL)")
        con.execute("INSERT OR IGNORE INTO wallet (id, hours) VALUES (1, 0)")
        con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        con.execute("INSERT OR IGNORE INTO meta VALUES ('created', ?)", (str(time.time()),))
        con.executemany("INSERT OR IGNORE INTO items VALUES (?,?,?,?)", START_ITEMS)
        con.executemany("INSERT OR IGNORE INTO inventory VALUES (?)", [(k,) for k, _, _, _ in START_ITEMS])
        con.execute("DELETE FROM items WHERE price > 0")
        for k in OLD_HOME_KEYS:
            con.execute("DELETE FROM inventory WHERE key=?", (k,))
        # shop catalog (rebuilt at every start, so changes in this file apply)
        con.execute("DROP TABLE IF EXISTS catalog")
        con.execute("""CREATE TABLE IF NOT EXISTS shop (key TEXT PRIMARY KEY, name TEXT, tab TEXT, sub TEXT, kind TEXT,
                       shape TEXT, color TEXT, price REAL, rent_day REAL, rent_month REAL)""")
        con.execute("DELETE FROM shop")
        con.executemany("INSERT INTO shop VALUES (?,?,?,?,?,?,?,?,?,?)", CATALOG)
        con.execute("CREATE TABLE IF NOT EXISTS placed (key TEXT PRIMARY KEY)")
        con.execute("DELETE FROM placed WHERE key IN (SELECT key FROM shop WHERE kind='obj')")
        con.execute("CREATE TABLE IF NOT EXISTS rentals (key TEXT PRIMARY KEY, expires REAL)")
        con.execute("""CREATE TABLE IF NOT EXISTS homes (key TEXT PRIMARY KEY, name TEXT, category TEXT,
                       tier INTEGER, m2 INTEGER, descr TEXT, day REAL, month REAL, buy REAL)""")
        con.executemany("INSERT OR REPLACE INTO homes VALUES (?,?,?,?,?,?,?,?,?)", HOMES)
        con.execute("""CREATE TABLE IF NOT EXISTS residence (id INTEGER PRIMARY KEY CHECK (id = 1),
                       home_key TEXT, mode TEXT, expires REAL)""")
        con.execute("CREATE TABLE IF NOT EXISTS owned_homes (home_key TEXT PRIMARY KEY)")
        con.execute("""CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       kind TEXT, task TEXT, started REAL, ended REAL, hours REAL)""")


init()


# ---------- helpers ----------
def get_hours(con):
    return con.execute("SELECT hours FROM wallet WHERE id=1").fetchone()[0]


def spend(con, amount):
    if get_hours(con) < amount:
        raise HTTPException(400, "Not enough hours")
    con.execute("UPDATE wallet SET hours = hours - ? WHERE id=1", (amount,))


def earn(con, amount):
    con.execute("UPDATE wallet SET hours = hours + ? WHERE id=1", (amount,))


def get_home(con, key):
    h = con.execute("SELECT * FROM homes WHERE key=?", (key,)).fetchone()
    if not h:
        raise HTTPException(404, "Unknown home")
    return h


def get_item(con, key):
    it = con.execute("SELECT * FROM shop WHERE key=?", (key,)).fetchone()
    if not it:
        raise HTTPException(404, "Unknown item")
    return it


def expire_rentals(con):
    """Rented items whose time is over disappear (also from the room)."""
    keys = [r[0] for r in con.execute("SELECT key FROM rentals WHERE expires < ?", (time.time(),))]
    for k in keys:
        con.execute("DELETE FROM rentals WHERE key=?", (k,))
        con.execute("DELETE FROM placed WHERE key=?", (k,))


def has_item(con, key):
    if con.execute("SELECT 1 FROM inventory WHERE key=?", (key,)).fetchone():
        return True
    return con.execute("SELECT 1 FROM rentals WHERE key=? AND expires > ?", (key, time.time())).fetchone() is not None


def residence_info(con):
    r = con.execute("SELECT * FROM residence WHERE id=1").fetchone()
    if not r:
        return None
    home = dict(get_home(con, r["home_key"]))
    expired = r["mode"] != "owned" and r["expires"] < time.time()
    return {"home": home, "mode": r["mode"], "expires": r["expires"], "expired": expired}


def set_residence(con, home_key, mode, expires):
    con.execute("INSERT OR REPLACE INTO residence (id, home_key, mode, expires) VALUES (1,?,?,?)",
                (home_key, mode, expires))


def workout_used_today(con):
    start_of_day = time.time() - (time.time() % DAY)
    return con.execute("SELECT COALESCE(SUM(hours),0) FROM sessions WHERE kind='workout' AND ended >= ?",
                       (start_of_day,)).fetchone()[0]


def stats(con):
    total = con.execute("SELECT COALESCE(SUM(hours),0) FROM sessions WHERE ended IS NOT NULL").fetchone()[0]
    created = float(con.execute("SELECT v FROM meta WHERE k='created'").fetchone()[0])
    return {"total_hours": round(total, 2),
            "level": 1 + int((total / 2) ** 0.5),
            "days": int((time.time() - created) // DAY) + 1,
            "created": created}


# ---------- me ----------
@app.get("/me")
def me():
    with conn() as con:
        expire_rentals(con)
        items = [dict(r) for r in con.execute(
            "SELECT key, name, category FROM items WHERE key IN (SELECT key FROM inventory)")]
        return {"hours": round(get_hours(con), 2), "items": items,
                "residence": residence_info(con), "stats": stats(con)}


# ---------- shops, closet, my stuff ----------
@app.get("/catalog")
def catalog():
    with conn() as con:
        expire_rentals(con)
        inv = {r[0] for r in con.execute("SELECT key FROM inventory")}
        placed = {r[0] for r in con.execute("SELECT key FROM placed")}
        rented = {r["key"]: r["expires"] for r in con.execute("SELECT key, expires FROM rentals")}
        rows = con.execute("""SELECT * FROM shop
                              ORDER BY COALESCE(price, rent_month * 12, rent_day * 40), name""").fetchall()
        return [dict(r, owned=r["key"] in inv, placed=r["key"] in placed, rented_until=rented.get(r["key"]))
                for r in rows]


@app.post("/buy/{key}")
def buy(key: str):
    with conn() as con:
        item = get_item(con, key)
        if item["price"] is None:
            raise HTTPException(400, "This one cannot be bought, only rented")
        if con.execute("SELECT 1 FROM inventory WHERE key=?", (key,)).fetchone():
            raise HTTPException(400, "Already owned")
        spend(con, item["price"])
        con.execute("INSERT INTO inventory VALUES (?)", (key,))
        con.execute("DELETE FROM rentals WHERE key=?", (key,))
        return {"ok": True, "hours_left": round(get_hours(con), 2)}


@app.post("/rent-item/{key}/{mode}")
def rent_item(key: str, mode: str):
    if mode not in MODES:
        raise HTTPException(400, "Mode must be day or month")
    with conn() as con:
        expire_rentals(con)
        item = get_item(con, key)
        if con.execute("SELECT 1 FROM inventory WHERE key=?", (key,)).fetchone():
            raise HTTPException(400, "You already own this")
        cost = item["rent_day"] if mode == "day" else item["rent_month"]
        if cost is None:
            raise HTTPException(400, f"This cannot be rented by the {mode}")
        spend(con, cost)
        r = con.execute("SELECT expires FROM rentals WHERE key=?", (key,)).fetchone()
        start = max(time.time(), r["expires"]) if r else time.time()   # renting again extends it
        con.execute("INSERT OR REPLACE INTO rentals VALUES (?,?)", (key, start + MODES[mode]))
        return {"ok": True, "hours_left": round(get_hours(con), 2)}


@app.post("/place/{key}")
def place(key: str):
    with conn() as con:
        expire_rentals(con)
        item = get_item(con, key)
        if not has_item(con, key):
            raise HTTPException(400, "You don't have this item")
        if item["kind"] == "obj":
            raise HTTPException(400, "Objects do not go in the room")
        if item["kind"] in SINGLE_KINDS:   # only one shown: the new one replaces the old one
            con.execute("DELETE FROM placed WHERE key IN (SELECT key FROM shop WHERE kind=?)", (item["kind"],))
        con.execute("INSERT OR IGNORE INTO placed VALUES (?)", (key,))
        return {"ok": True}


@app.post("/unplace/{key}")
def unplace(key: str):
    with conn() as con:
        con.execute("DELETE FROM placed WHERE key=?", (key,))
        return {"ok": True}


# ---------- homes: rent / buy / renew / leave ----------
@app.get("/homes")
def homes():
    with conn() as con:
        owned = {r[0] for r in con.execute("SELECT home_key FROM owned_homes")}
        rows = con.execute("SELECT * FROM homes ORDER BY category, tier").fetchall()
        return [dict(r, owned=r["key"] in owned) for r in rows]


@app.post("/rent/{key}/{mode}")
def rent(key: str, mode: str):
    if mode not in MODES:
        raise HTTPException(400, "Mode must be day or month")
    with conn() as con:
        home = get_home(con, key)
        if con.execute("SELECT 1 FROM owned_homes WHERE home_key=?", (key,)).fetchone():
            raise HTTPException(400, "You own this home, just move in")
        cur = residence_info(con)
        extending = bool(cur and cur["mode"] != "owned" and cur["home"]["key"] == key)
        if cur and cur["mode"] != "owned" and not cur["expired"] and not extending:
            raise HTTPException(400, "You already rent a home. Wait until it ends, or leave it first.")
        spend(con, home[mode])
        start = cur["expires"] if extending and not cur["expired"] else time.time()
        set_residence(con, key, mode, start + MODES[mode])
        return {"ok": True, "hours_left": round(get_hours(con), 2)}
        
@app.post("/buy-home/{key}")
def buy_home(key: str):
    with conn() as con:
        home = get_home(con, key)
        if con.execute("SELECT 1 FROM owned_homes WHERE home_key=?", (key,)).fetchone():
            raise HTTPException(400, "Already owned")
        spend(con, home["buy"])
        con.execute("INSERT INTO owned_homes VALUES (?)", (key,))
        set_residence(con, key, "owned", None)
        return {"ok": True, "hours_left": round(get_hours(con), 2)}


@app.post("/move/{key}")
def move(key: str):
    with conn() as con:
        get_home(con, key)
        if not con.execute("SELECT 1 FROM owned_homes WHERE home_key=?", (key,)).fetchone():
            raise HTTPException(400, "You don't own this home")
        set_residence(con, key, "owned", None)
        return {"ok": True}


@app.post("/renew")
def renew():
    with conn() as con:
        cur = residence_info(con)
        if not cur or not cur["expired"]:
            raise HTTPException(400, "Nothing to renew")
        spend(con, cur["home"][cur["mode"]])
        set_residence(con, cur["home"]["key"], cur["mode"], time.time() + MODES[cur["mode"]])
        return {"ok": True, "hours_left": round(get_hours(con), 2)}


@app.post("/leave")
def leave():
    with conn() as con:
        con.execute("DELETE FROM residence WHERE id=1")
        return {"ok": True}


# ---------- work sessions ----------
class StartBody(BaseModel):
    task: str


class WorkoutBody(BaseModel):
    hours: float


@app.get("/sessions")
def sessions():
    with conn() as con:
        active = con.execute("SELECT id, task, started FROM sessions WHERE ended IS NULL").fetchone()
        history = con.execute("""SELECT kind, task, hours, ended FROM sessions
                                 WHERE ended IS NOT NULL ORDER BY id DESC LIMIT 20""").fetchall()
        return {"active": dict(active) if active else None,
                "history": [dict(r) for r in history],
                "workout_left_today": round(WORKOUT_CAP - workout_used_today(con), 2)}


@app.post("/sessions/start")
def start_session(body: StartBody):
    task = body.task.strip()
    if not task:
        raise HTTPException(400, "Say what you will work on")
    with conn() as con:
        if con.execute("SELECT 1 FROM sessions WHERE ended IS NULL").fetchone():
            raise HTTPException(400, "A session is already running")
        con.execute("INSERT INTO sessions (kind, task, started) VALUES ('work', ?, ?)", (task[:200], time.time()))
        return {"ok": True}


@app.post("/sessions/stop")
def stop_session():
    with conn() as con:
        s = con.execute("SELECT * FROM sessions WHERE ended IS NULL").fetchone()
        if not s:
            raise HTTPException(400, "No session running")
        now = time.time()
        hours = round(min((now - s["started"]) / 3600, MAX_SESSION), 2)
        con.execute("UPDATE sessions SET ended=?, hours=? WHERE id=?", (now, hours, s["id"]))
        earn(con, hours)
        return {"ok": True, "hours_earned": hours, "hours": round(get_hours(con), 2)}


@app.post("/workout")
def workout(body: WorkoutBody):
    if body.hours <= 0:
        raise HTTPException(400, "Hours must be positive")
    with conn() as con:
        left = WORKOUT_CAP - workout_used_today(con)
        if left <= 0:
            raise HTTPException(400, "Daily workout limit reached (1 h)")
        credited = round(min(body.hours, left), 2)
        now = time.time()
        con.execute("INSERT INTO sessions (kind, task, started, ended, hours) VALUES ('workout','Workout',?,?,?)",
                    (now, now, credited))
        earn(con, credited)
        return {"ok": True, "hours_earned": credited, "hours": round(get_hours(con), 2)}


from backend import diary
diary.setup(app, conn, earn)

# ---------- web app (must stay LAST) ----------
app.mount("/", StaticFiles(directory=ROOT / "webapp", html=True), name="webapp")