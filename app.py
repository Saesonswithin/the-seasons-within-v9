from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from pathlib import Path
from datetime import date, datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import json
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

try:
    import stripe
except Exception:
    stripe = None
try:
    import swisseph as swe
except Exception:
    swe = None
try:
    from geopy.geocoders import Nominatim
except Exception:
    Nominatim = None
try:
    from timezonefinder import TimezoneFinder
except Exception:
    TimezoneFinder = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-this-secret-key-before-launch")
DB = Path(__file__).with_name("community_v8.db")
UPLOADS = Path(__file__).with_name("static") / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(__file__).with_name("platform_config.json")

def load_platform_config():
    defaults = {"stripe_secret_key":"", "stripe_webhook_secret":"", "stripe_zodiac_price_id":"", "stripe_business_price_id":"", "public_base_url":"", "allow_dev_upgrades": True}
    if CONFIG_PATH.exists():
        try: defaults.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception: pass
    envmap={"stripe_secret_key":"STRIPE_SECRET_KEY","stripe_webhook_secret":"STRIPE_WEBHOOK_SECRET","stripe_zodiac_price_id":"STRIPE_ZODIAC_PRICE_ID","stripe_business_price_id":"STRIPE_BUSINESS_PRICE_ID","public_base_url":"PUBLIC_BASE_URL"}
    for key, env in envmap.items():
        if os.environ.get(env): defaults[key]=os.environ[env]
    return defaults

def stripe_ready(plan_key=None):
    cfg=load_platform_config()
    if not stripe or not cfg.get("stripe_secret_key"): return False
    if plan_key=="zodiac": return bool(cfg.get("stripe_zodiac_price_id"))
    if plan_key=="business": return bool(cfg.get("stripe_business_price_id"))
    return bool(cfg.get("stripe_zodiac_price_id") and cfg.get("stripe_business_price_id"))

PLANS = {
    "free": {"name": "Meet the Community", "price": "Free", "description": "Create a Basic Community Profile, browse members and join Community Conversations.", "visible": True},
    "zodiac": {"name": "The Seasons Within Membership", "price": "$19.99/mo", "description": "Unlock full dating profiles, compatibility reports, personalized date ideas, messaging tools and compatible-member alerts.", "visible": True},
    "business": {"name": "Business Network", "price": "$49.99/mo", "description": "Monthly business membership with public listing, hosted branded mini-app and marketing tools.", "visible": True},
}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

ZODIAC_ELEMENTS = {
    "Aries":"Fire","Leo":"Fire","Sagittarius":"Fire","Taurus":"Earth","Virgo":"Earth","Capricorn":"Earth",
    "Gemini":"Air","Libra":"Air","Aquarius":"Air","Cancer":"Water","Scorpio":"Water","Pisces":"Water"
}
ZODIAC_MODALITIES = {
    "Aries":"Cardinal","Cancer":"Cardinal","Libra":"Cardinal","Capricorn":"Cardinal","Taurus":"Fixed","Leo":"Fixed",
    "Scorpio":"Fixed","Aquarius":"Fixed","Gemini":"Mutable","Virgo":"Mutable","Sagittarius":"Mutable","Pisces":"Mutable"
}


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def table_columns(c, table):
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(c, table, name, definition):
    if name not in table_columns(c, table):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def hash_password(password):
    return generate_password_hash(password, method="scrypt")


def password_matches(stored, candidate):
    if not stored:
        return False
    if stored.startswith(("scrypt:", "pbkdf2:", "argon2:")):
        try:
            return check_password_hash(stored, candidate)
        except ValueError:
            return False
    # Backward-compatible migration for old prototype plaintext accounts.
    return stored == candidate


def init_db():
    c = conn()
    c.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free',
        bio TEXT DEFAULT '', city TEXT DEFAULT '', sun TEXT DEFAULT '', moon TEXT DEFAULT '', rising TEXT DEFAULT '',
        dating_intention TEXT DEFAULT '', business_role TEXT DEFAULT '', business_goal TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        membership_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'inactive',
        provider TEXT DEFAULT 'development',
        provider_customer_id TEXT DEFAULT '',
        provider_subscription_id TEXT DEFAULT '',
        current_period_end TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, membership_type),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS birth_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        birth_date TEXT NOT NULL,
        birth_time TEXT DEFAULT '',
        time_known INTEGER DEFAULT 1,
        birth_city TEXT NOT NULL,
        birth_state TEXT DEFAULT '',
        birth_country TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        timezone TEXT DEFAULT '',
        calculation_status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS birth_charts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        sun TEXT DEFAULT '', moon TEXT DEFAULT '', rising TEXT DEFAULT '', mercury TEXT DEFAULT '', venus TEXT DEFAULT '', mars TEXT DEFAULT '',
        jupiter TEXT DEFAULT '', saturn TEXT DEFAULT '', uranus TEXT DEFAULT '', neptune TEXT DEFAULT '', pluto TEXT DEFAULT '',
        houses_json TEXT DEFAULT '', aspects_json TEXT DEFAULT '', element_balance_json TEXT DEFAULT '',
        calculation_status TEXT DEFAULT 'pending', calculated_at TEXT DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL,
        reported_user_id INTEGER,
        post_id INTEGER,
        reason TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        business_name TEXT NOT NULL,
        tagline TEXT DEFAULT '', description TEXT DEFAULT '', category TEXT DEFAULT '', city TEXT DEFAULT '',
        website TEXT DEFAULT '', contact_email TEXT DEFAULT '', phone TEXT DEFAULT '', logo TEXT DEFAULT '', hero_image TEXT DEFAULT '',
        accent TEXT DEFAULT '#b99ad6', status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS business_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '', price TEXT DEFAULT '', action_url TEXT DEFAULT '', active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, notification_type TEXT NOT NULL, title TEXT NOT NULL, body TEXT DEFAULT '', related_user_id INTEGER, read_at TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    additions = {
        "users": {
            "birth_date": "TEXT DEFAULT ''", "birth_time": "TEXT DEFAULT ''", "birth_city": "TEXT DEFAULT ''",
            "venus": "TEXT DEFAULT ''", "mars": "TEXT DEFAULT ''", "relationship_style": "TEXT DEFAULT ''",
            "gender": "TEXT DEFAULT ''", "interested_in": "TEXT DEFAULT ''", "photo": "TEXT DEFAULT ''",
            "dating_18_confirmed": "INTEGER DEFAULT 0", "is_admin": "INTEGER DEFAULT 0", "suspended": "INTEGER DEFAULT 0",
            "is_creator": "INTEGER DEFAULT 0", "profile_headline": "TEXT DEFAULT ''",
            "show_headline": "INTEGER DEFAULT 1", "show_city": "INTEGER DEFAULT 1", "show_bio": "INTEGER DEFAULT 1", "show_zodiac_basic": "INTEGER DEFAULT 0",
            "dating_photo": "TEXT DEFAULT ''", "dating_bio": "TEXT DEFAULT ''", "dating_headline": "TEXT DEFAULT ''", "dating_profile_active": "INTEGER DEFAULT 0"
        }
    }
    for table, cols in additions.items():
        for name, definition in cols.items():
            ensure_column(c, table, name, definition)
    ensure_column(c, "birth_data", "utc_offset", "REAL")
    ensure_column(c, "birth_charts", "planet_degrees_json", "TEXT DEFAULT ''")
    ensure_column(c, "birth_charts", "house_cusps_json", "TEXT DEFAULT ''")
    ensure_column(c, "subscriptions", "price_id", "TEXT DEFAULT ''")
    ensure_column(c, "subscriptions", "checkout_session_id", "TEXT DEFAULT ''")

    # Secure demo accounts. Existing plaintext accounts are automatically upgraded on next login.
    demo = [
        ("Avery", "avery@example.com", "zodiac", "Book lover, yoga student and weekend traveler looking for a grounded relationship.", "Atlanta", "Libra", "Pisces", "Leo", "Long-term relationship", "", ""),
        ("Jordan", "jordan@example.com", "business", "Creative entrepreneur building community-centered brands.", "Detroit", "Gemini", "Capricorn", "Virgo", "", "Brand Strategist", "Find collaborators and referral partners"),
        ("Morgan", "morgan@example.com", "all_access", "Yoga, travel, business and conscious connection.", "Chicago", "Taurus", "Cancer", "Sagittarius", "Open to dating intentionally", "Wellness Founder", "Partnerships and event collaborations"),
        ("Nia", "nia@example.com", "zodiac", "Nature walks, live music, meditation and honest conversation.", "Atlanta", "Aquarius", "Libra", "Cancer", "A committed partnership", "", ""),
        ("Marcus", "marcus@example.com", "zodiac", "Fitness, cooking, family and building a peaceful life.", "Detroit", "Leo", "Taurus", "Capricorn", "Dating with purpose", "", ""),
    ]
    for name,email,legacy_plan,bio,city,sun,moon,rising,intention,role,goal in demo:
        try:
            cur = c.execute("""INSERT INTO users(name,email,password,plan,bio,city,sun,moon,rising,dating_intention,business_role,business_goal)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (name,email,hash_password("demo"),legacy_plan,bio,city,sun,moon,rising,intention,role,goal))
            uid = cur.lastrowid
        except sqlite3.IntegrityError:
            uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
        if legacy_plan in ("zodiac", "all_access"):
            c.execute("INSERT OR IGNORE INTO subscriptions(user_id,membership_type,status) VALUES (?, 'zodiac', 'active')", (uid,))
        if legacy_plan in ("business", "all_access"):
            c.execute("INSERT OR IGNORE INTO subscriptions(user_id,membership_type,status) VALUES (?, 'business', 'active')", (uid,))

    # Demo dating profiles make the freemium Zodiac directory feel populated from day one.
    dating_seed = {
        "avery@example.com": ("1993-10-12", "Pisces", "Leo", "Scorpio", "Grounded, curious and ready to build something real.", "Long-term • Wellness • Travel"),
        "morgan@example.com": ("1990-05-08", "Cancer", "Sagittarius", "Aries", "Creative wellness founder who values honesty, adventure and emotional depth.", "Intentional dating • Growth"),
        "nia@example.com": ("1994-02-04", "Libra", "Cancer", "Sagittarius", "Nature, music, meditation and meaningful conversation are my favorite ways to connect.", "Committed partnership"),
        "marcus@example.com": ("1989-08-17", "Taurus", "Capricorn", "Libra", "Family-minded, active and building a peaceful life with purpose.", "Dating with purpose"),
    }
    for email,(dob,venus,mars,rising2,dbio,dheadline) in dating_seed.items():
        row=c.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()
        if row:
            c.execute("""UPDATE users SET birth_date=?,dating_18_confirmed=1,venus=?,mars=?,rising=?,dating_bio=?,dating_headline=?,dating_profile_active=1 WHERE id=?""",
                      (dob,venus,mars,rising2,dbio,dheadline,row[0]))
            c.execute("""INSERT OR IGNORE INTO birth_data(user_id,birth_date,birth_time,time_known,birth_city,birth_state,birth_country,calculation_status)
                         VALUES (?,?,?,1,?,?,?,'demo')""", (row[0],dob,"12:00",c.execute("SELECT city FROM users WHERE id=?",(row[0],)).fetchone()[0],"","USA"))

    creator_email = "creator@theseasonswithin.local"
    try:
        cur = c.execute("""INSERT INTO users(name,email,password,plan,bio,city,sun,moon,rising,business_role,business_goal,is_admin,is_creator,profile_headline)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,1,1,?)""",
                        ("The Seasons Within",creator_email,hash_password("demo"),"all_access",
                         "Wellness, self-awareness, relationships and Conscious Coordination through every season of life.",
                         "Community","Libra","Sagittarius","Leo","Community Host","Build meaningful connections",
                         "Conscious Coordination • Wellness • Community"))
        creator_id = cur.lastrowid
    except sqlite3.IntegrityError:
        creator_id = c.execute("SELECT id FROM users WHERE email=?", (creator_email,)).fetchone()[0]
    c.execute("INSERT OR IGNORE INTO subscriptions(user_id,membership_type,status) VALUES (?, 'zodiac', 'active')", (creator_id,))
    c.execute("INSERT OR IGNORE INTO subscriptions(user_id,membership_type,status) VALUES (?, 'business', 'active')", (creator_id,))

    if c.execute("SELECT COUNT(*) FROM posts WHERE user_id=?", (creator_id,)).fetchone()[0] == 0:
        for body in [
            "Welcome to Community Conversations. This is where I’ll share The Seasons Within journey topics, reflections and new blog posts.",
            "Today’s reflection: growth does not always look like movement. Sometimes your season is asking for rest, observation and a clearer next step.",
        ]:
            c.execute("INSERT INTO posts(user_id,body) VALUES (?,?)", (creator_id,body))

    # Seed a few community-member posts so the Home Feed looks like a living network on first launch.
    community_seed_posts = {
        "nia@example.com": "Morning reflection: I took a quiet walk before checking my phone today. I’m learning that peace can be part of the plan, not just a break from it.",
        "morgan@example.com": "This week I’m focusing on consistency instead of intensity — a little movement, a little journaling, and more room to listen to myself.",
        "marcus@example.com": "Today’s question for the community: what habit has helped you feel more grounded lately? Mine has been cooking dinner without rushing.",
        "avery@example.com": "I’m in a season of choosing relationships that feel mutual, clear and peaceful. Curious what intentional connection means to everyone else here."
    }
    for email, body in community_seed_posts.items():
        row = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row and c.execute("SELECT COUNT(*) FROM posts WHERE user_id=?", (row[0],)).fetchone()[0] == 0:
            c.execute("INSERT INTO posts(user_id,body) VALUES (?,?)", (row[0], body))

    # Extra mock wellness business owners so the public Business Network feels launch-ready.
    biz_demo = [
        ("Sage", "sage@business.demo", "Sound Harmony", "Chicago, IL"),
        ("Maya", "maya@business.demo", "Nature Vibes", "Asheville, NC"),
    ]
    for name,email,bizname,city in biz_demo:
        try:
            cur=c.execute("INSERT INTO users(name,email,password,plan,bio,city,is_admin) VALUES (?,?,?,'business',?,?,0)",(name,email,hash_password('demo'),f'Owner of {bizname}',city))
            uid=cur.lastrowid
        except sqlite3.IntegrityError:
            uid=c.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()[0]
        c.execute("INSERT OR IGNORE INTO subscriptions(user_id,membership_type,status) VALUES (?, 'business', 'active')",(uid,))

    # Seed public businesses only when the matching demo owner exists.
    seeds = [
        ("jordan@example.com","Rise & Flow Yoga","rise-flow-yoga","Flow. Breathe. Connect.","Yoga classes, workshops, private sessions and a welcoming wellness community for all levels.","Yoga","Detroit, MI","hello@riseflow.demo"),
        ("morgan@example.com","Sacred Soul Reiki","sacred-soul-reiki","Restore. Release. Reconnect.","Private Reiki-inspired relaxation sessions, guided reflection and seasonal wellness circles.","Reiki","Atlanta, GA","hello@sacredsoul.demo"),
        ("sage@business.demo","Sound Harmony","sound-harmony","Sound. Stillness. Transformation.","Sound baths, meditation experiences and restorative group sessions.","Sound Therapy","Chicago, IL","hello@soundharmony.demo"),
        ("maya@business.demo","Nature Vibes","nature-vibes","Move outside. Come back to yourself.","Guided nature experiences, mindful hiking and retreat-friendly outdoor activities.","Retreats","Asheville, NC","hello@naturevibes.demo"),
    ]
    for email,name,slug,tagline,desc,category,city,contact in seeds:
        owner = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if owner:
            try:
                c.execute("""INSERT INTO businesses(owner_id,slug,business_name,tagline,description,category,city,contact_email,accent)
                             VALUES (?,?,?,?,?,?,?,?,?)""", (owner[0],slug,name,tagline,desc,category,city,contact,"#b99ad6"))
            except sqlite3.IntegrityError:
                pass

    # Give demo hosted apps realistic offerings.
    demo_items = {
        'rise-flow-yoga':[('class','Morning Flow','60 minutes • All levels','$25'),('service','Private Yoga Session','One-to-one personalized session','$80'),('membership','Monthly Wellness Circle','Classes + member content + community','$39/mo')],
        'sacred-soul-reiki':[('service','60-Minute Reiki Session','Private relaxation and reflection session','$75'),('class','Reiki Reflection Circle','Small-group guided experience','$35'),('membership','Monthly Reiki Community','Monthly session + community content','$29/mo')],
        'sound-harmony':[('class','Sound Bath','Restorative sound experience','$40'),('event','Evening Sound Journey','90-minute community event','$55'),('membership','Sound & Stillness Membership','Two experiences each month','$49/mo')],
        'nature-vibes':[('service','Guided Nature Walk','Mindful outdoor experience','$35'),('event','Waterfall Reflection Day','Half-day guided retreat experience','$95'),('membership','Outdoor Wellness Club','Monthly community adventures','$39/mo')]
    }
    for slug,items in demo_items.items():
        b=c.execute('SELECT id FROM businesses WHERE slug=?',(slug,)).fetchone()
        if b and c.execute('SELECT COUNT(*) FROM business_items WHERE business_id=?',(b[0],)).fetchone()[0]==0:
            for typ,title,desc,price in items:
                c.execute('INSERT INTO business_items(business_id,item_type,title,description,price) VALUES (?,?,?,?,?)',(b[0],typ,title,desc,price))

    c.commit(); c.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    c = conn(); u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); c.close()
    return u


def membership_status(user_id, membership_type):
    c = conn(); row = c.execute("SELECT status FROM subscriptions WHERE user_id=? AND membership_type=?", (user_id,membership_type)).fetchone(); c.close()
    return row["status"] if row else "inactive"


def has_access(user, area):
    if not user or user["suspended"]:
        return False
    if area == "free":
        return True
    return membership_status(user["id"], area) in ("active", "trialing")


def age_from_birth_date(value):
    try:
        born = datetime.strptime(value, "%Y-%m-%d").date(); today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


def get_birth_data(user_id):
    c=conn(); row=c.execute("SELECT * FROM birth_data WHERE user_id=?",(user_id,)).fetchone(); c.close(); return row


def dating_eligible(user):
    birth = get_birth_data(user["id"])
    age = age_from_birth_date(birth["birth_date"] if birth else user["birth_date"])
    return bool(user["dating_18_confirmed"] and age is not None and age >= 18)


def save_image(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ""
    filename = secure_filename(file_storage.filename)
    if "." not in filename or filename.rsplit(".", 1)[1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return ""
    ext = filename.rsplit(".", 1)[1].lower(); name = f"{prefix}_{int(datetime.now().timestamp())}.{ext}"
    file_storage.save(UPLOADS / name); return f"uploads/{name}"


def slugify(text):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "wellness-business"
    c = conn(); slug = base; i = 2
    while c.execute("SELECT 1 FROM businesses WHERE slug=?", (slug,)).fetchone():
        slug = f"{base}-{i}"; i += 1
    c.close(); return slug


ZODIAC_SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

def zodiac_from_degree(deg):
    deg=float(deg)%360; idx=int(deg//30)
    return ZODIAC_SIGNS[idx], round(deg-(idx*30),2)


def media_url(path):
    """Return a browser-safe URL for locally uploaded media or an external URL."""
    if not path:
        return ""
    path = str(path).strip()
    if path.startswith(("http://", "https://", "/")):
        return path
    return url_for("static", filename=path)


def current_season_name(moment=None):
    """Northern-hemisphere seasonal label used by The Seasons Within."""
    moment = moment or datetime.now(timezone.utc)
    month_day = (moment.month, moment.day)
    if (3, 20) <= month_day < (6, 20):
        return "Spring"
    if (6, 20) <= month_day < (9, 22):
        return "Summer"
    if (9, 22) <= month_day < (12, 21):
        return "Autumn"
    return "Winter"


def current_sky_snapshot():
    """Calculate the current Moon, lunar phase, season, and selected planets."""
    now = datetime.now(timezone.utc)
    sky = {
        "moon_sign": "",
        "moon_degree": None,
        "moon_phase": "",
        "positions": {},
        "season": current_season_name(now),
        "updated_at": now.isoformat(),
    }

    if swe is None:
        return sky

    try:
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0
        jd_ut = swe.julday(now.year, now.month, now.day, hour, swe.GREG_CAL)

        bodies = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
        }

        longitudes = {}
        for name, body in bodies.items():
            xx = swe.calc_ut(jd_ut, body)[0]
            longitude = float(xx[0]) % 360.0
            sign, degree = zodiac_from_degree(longitude)
            longitudes[name] = longitude
            sky["positions"][name] = {
                "sign": sign,
                "degree": degree,
                "longitude": round(longitude, 4),
            }

        sky["moon_sign"] = sky["positions"]["Moon"]["sign"]
        sky["moon_degree"] = sky["positions"]["Moon"]["degree"]

        elongation = (longitudes["Moon"] - longitudes["Sun"]) % 360.0
        if elongation < 22.5 or elongation >= 337.5:
            phase = "New Moon"
        elif elongation < 67.5:
            phase = "Waxing Crescent"
        elif elongation < 112.5:
            phase = "First Quarter"
        elif elongation < 157.5:
            phase = "Waxing Gibbous"
        elif elongation < 202.5:
            phase = "Full Moon"
        elif elongation < 247.5:
            phase = "Waning Gibbous"
        elif elongation < 292.5:
            phase = "Last Quarter"
        else:
            phase = "Waning Crescent"

        sky["moon_phase"] = phase
    except Exception:
        # The page must remain usable even if astronomy data cannot be calculated.
        pass

    return sky


def daily_seasons_reflection(user=None):
    """Public/current-sky reflection data used by the member Home page."""
    return {"sky": current_sky_snapshot()}


def coordination_categories(viewer, member):
    """Small compatibility summary used by Community profile cards."""
    try:
        result = compatibility_summary(viewer, member)
        return {"Overall": result.get("score", 50)}
    except Exception:
        return {"Overall": 50}

def geocode_birthplace(city,state,country):
    if not Nominatim: return None
    try:
        loc=Nominatim(user_agent="the-seasons-within-birth-chart").geocode(", ".join([x for x in (city,state,country) if x]),timeout=10)
        if loc: return float(loc.latitude),float(loc.longitude)
    except Exception: return None
    return None

def timezone_for_coordinates(lat,lon):
    if not TimezoneFinder: return ""
    try: return TimezoneFinder().timezone_at(lat=lat,lng=lon) or ""
    except Exception: return ""

def get_birth_chart(user_id):
    c=conn(); row=c.execute("SELECT * FROM birth_charts WHERE user_id=?",(user_id,)).fetchone(); c.close(); return row

def calculate_birth_chart(user_id):
    if swe is None: return False,"Swiss Ephemeris is not installed yet. Run the one-click launcher again after installing the astrology package."
    birth=get_birth_data(user_id)
    if not birth: return False,"Birth information is missing."
    try:
        lat=birth["latitude"]; lon=birth["longitude"]; tzname=birth["timezone"] or ""
        if lat is None or lon is None:
            coords=geocode_birthplace(birth["birth_city"],birth["birth_state"],birth["birth_country"])
            if not coords: return False,"We could not locate that birthplace automatically. Open Advanced Birth Location and add latitude/longitude."
            lat,lon=coords
        if not tzname: tzname=timezone_for_coordinates(lat,lon)
        y,m,d=map(int,birth["birth_date"].split("-")); time_known=bool(birth["time_known"]); hh,mm=12,0
        if time_known and birth["birth_time"]: hh,mm=map(int,birth["birth_time"].split(":")[:2])
        local_dt=datetime(y,m,d,hh,mm)
        if tzname:
            utc_dt=local_dt.replace(tzinfo=ZoneInfo(tzname)).astimezone(timezone.utc)
        elif birth["utc_offset"] is not None:
            utc_dt=local_dt.replace(tzinfo=timezone(timedelta(hours=float(birth["utc_offset"])))).astimezone(timezone.utc)
        else:
            return False,"Timezone could not be determined. Add the UTC offset at birth in Advanced Birth Location."
        jd_ut,jd_tt=swe.utc_to_jd(utc_dt.year,utc_dt.month,utc_dt.day,utc_dt.hour,utc_dt.minute,utc_dt.second)
        planets={"sun":swe.SUN,"moon":swe.MOON,"mercury":swe.MERCURY,"venus":swe.VENUS,"mars":swe.MARS,"jupiter":swe.JUPITER,"saturn":swe.SATURN,"uranus":swe.URANUS,"neptune":swe.NEPTUNE,"pluto":swe.PLUTO}
        placements={}; degrees={}
        for key,body in planets.items():
            calc_result=swe.calc_ut(jd_ut,body); xx=calc_result[0]; sign,within=zodiac_from_degree(xx[0]); placements[key]=sign; degrees[key]={"longitude":round(float(xx[0])%360,4),"sign":sign,"degree":within}
        rising=""; cusps=[]
        if time_known:
            house_cusps,ascmc=swe.houses(jd_tt,float(lat),float(lon),b'P'); rising=zodiac_from_degree(ascmc[0])[0]; cusps=[round(float(x),4) for x in house_cusps[1:13]]; degrees["rising"]={"longitude":round(float(ascmc[0])%360,4),"sign":rising,"degree":zodiac_from_degree(ascmc[0])[1]}
        balance={"Fire":0,"Earth":0,"Air":0,"Water":0}
        for key in planets:
            el=ZODIAC_ELEMENTS.get(placements[key]);
            if el: balance[el]+=1
        status="calculated" if time_known else "partial_no_time"
        c=conn(); c.execute("UPDATE birth_data SET latitude=?,longitude=?,timezone=?,calculation_status=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(lat,lon,tzname,status,user_id))
        sql="""INSERT INTO birth_charts(user_id,sun,moon,rising,mercury,venus,mars,jupiter,saturn,uranus,neptune,pluto,houses_json,element_balance_json,planet_degrees_json,house_cusps_json,calculation_status,calculated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET sun=excluded.sun,moon=excluded.moon,rising=excluded.rising,mercury=excluded.mercury,venus=excluded.venus,mars=excluded.mars,jupiter=excluded.jupiter,saturn=excluded.saturn,uranus=excluded.uranus,neptune=excluded.neptune,pluto=excluded.pluto,houses_json=excluded.houses_json,element_balance_json=excluded.element_balance_json,planet_degrees_json=excluded.planet_degrees_json,house_cusps_json=excluded.house_cusps_json,calculation_status=excluded.calculation_status,calculated_at=CURRENT_TIMESTAMP"""
        c.execute(sql,(user_id,placements["sun"],placements["moon"],rising,placements["mercury"],placements["venus"],placements["mars"],placements["jupiter"],placements["saturn"],placements["uranus"],placements["neptune"],placements["pluto"],json.dumps(cusps),json.dumps(balance),json.dumps(degrees),json.dumps(cusps),status))
        c.execute("UPDATE users SET sun=?,moon=?,rising=?,venus=?,mars=?,birth_date=?,birth_time=?,birth_city=? WHERE id=?",(placements["sun"],placements["moon"],rising,placements["venus"],placements["mars"],birth["birth_date"],birth["birth_time"],birth["birth_city"],user_id)); c.commit(); c.close()
        create_compatibility_alerts(user_id)
        return True,"Your real birth chart was calculated and saved."
    except Exception as exc: return False,f"Chart calculation could not finish: {exc}"

def create_compatibility_alerts(new_user_id,threshold=80):
    c=conn(); newcomer=c.execute("SELECT * FROM users WHERE id=?",(new_user_id,)).fetchone()
    if not newcomer or not newcomer["dating_profile_active"]: c.close(); return
    for other in c.execute("SELECT * FROM users WHERE id<>? AND dating_profile_active=1 AND dating_18_confirmed=1 AND suspended=0",(new_user_id,)).fetchall():
        score=compatibility_summary(other,newcomer).get("score",0)
        if score>=threshold and not c.execute("SELECT 1 FROM notifications WHERE user_id=? AND notification_type='compatible_join' AND related_user_id=?",(other["id"],new_user_id)).fetchone():
            c.execute("INSERT INTO notifications(user_id,notification_type,title,body,related_user_id) VALUES (?,?,?,?,?)",(other["id"],"compatible_join","A compatible member just joined",f"{newcomer['name']} is a {score}% potential match. Open their profile to learn more.",new_user_id))
    c.commit(); c.close()

def sign_score(a, b):
    if not a or not b: return 50
    a=a.title(); b=b.title()
    if a==b: return 82
    ea,eb=ZODIAC_ELEMENTS.get(a),ZODIAC_ELEMENTS.get(b)
    if {ea,eb} in ({"Fire","Air"},{"Earth","Water"}): base=86
    elif ea==eb: base=78
    elif {ea,eb} in ({"Fire","Water"},{"Air","Earth"}): base=58
    else: base=68
    if ZODIAC_MODALITIES.get(a)==ZODIAC_MODALITIES.get(b): base-=4
    return max(40,min(95,base))


def compatibility_summary(viewer, member):
    pairs=[("Sun",viewer["sun"],member["sun"],25),("Moon",viewer["moon"],member["moon"],30),("Rising",viewer["rising"],member["rising"],15),("Venus",viewer["venus"],member["venus"],20),("Mars",viewer["mars"],member["mars"],10)]
    available=[p for p in pairs if p[1] and p[2]]
    if not available: return {"score":50,"label":"Add chart placements","details":[]}
    tw=sum(p[3] for p in available); details=[]; total=0
    for label,a,b,w in available:
        sc=sign_score(a,b); total+=sc*w; details.append({"label":label,"you":a,"them":b,"score":sc})
    score=round(total/tw); label="Strong flow" if score>=82 else "Promising balance" if score>=70 else "Growth connection" if score>=58 else "More contrast"
    return {"score":score,"label":label,"details":details}

def full_compatibility_report(viewer, member):
    c=conn(); va=c.execute("SELECT * FROM birth_charts WHERE user_id=?",(viewer["id"],)).fetchone(); mb=c.execute("SELECT * FROM birth_charts WHERE user_id=?",(member["id"],)).fetchone(); c.close()
    def val(row,key,fallback=""):
        return (row[key] if row and key in row.keys() else "") or fallback
    sun1,val_sun2=val(va,"sun",viewer["sun"]),val(mb,"sun",member["sun"]); moon1,moon2=val(va,"moon",viewer["moon"]),val(mb,"moon",member["moon"]); ven1,ven2=val(va,"venus",viewer["venus"]),val(mb,"venus",member["venus"]); mars1,mars2=val(va,"mars",viewer["mars"]),val(mb,"mars",member["mars"]); rise1,rise2=val(va,"rising",viewer["rising"]),val(mb,"rising",member["rising"]); mer1,mer2=val(va,"mercury"),val(mb,"mercury"); jup1,jup2=val(va,"jupiter"),val(mb,"jupiter"); sat1,sat2=val(va,"saturn"),val(mb,"saturn")
    def avg(*nums):
        vals=[n for n in nums if n is not None]; return round(sum(vals)/len(vals)) if vals else 50
    def ss(a,b): return sign_score(a,b) if a and b else None
    categories=[
      ("Emotional Connection",avg(ss(moon1,moon2),ss(sun1,moon2),ss(moon1,val_sun2)),"How your emotional needs, instinctive reactions and sense of being understood may fit."),
      ("Communication",avg(ss(mer1,mer2),ss(mer1,moon2),ss(moon1,mer2)),"How naturally your thinking, listening and emotional communication styles may connect."),
      ("Romantic Chemistry",avg(ss(ven1,ven2),ss(ven1,mars2),ss(mars1,ven2)),"Affection style, attraction, romance and how each person tends to give and receive interest."),
      ("Physical Attraction",avg(ss(mars1,mars2),ss(ven1,mars2),ss(mars1,ven2)),"Drive, sensual rhythm, pursuit style and physical chemistry themes."),
      ("Shared Values",avg(ss(sun1,val_sun2),ss(jup1,jup2),ss(ven1,ven2)),"Identity, priorities, generosity and what each person may value in a relationship."),
      ("Lifestyle Rhythm",avg(ss(rise1,rise2),ss(sun1,val_sun2),ss(moon1,moon2)),"Daily pace, social style, habits and how the relationship may feel in ordinary life."),
      ("Conflict Style",avg(ss(mars1,mars2),ss(mer1,mer2),ss(sat1,sat2)),"How you may approach disagreement, boundaries, pressure and repair."),
      ("Long-Term Potential",avg(ss(sat1,val_sun2),ss(sun1,sat2),ss(sat1,sat2),ss(sun1,val_sun2)),"Stability, responsibility, patience and themes that may support sustained commitment."),
      ("Element Balance",avg(ss(sun1,val_sun2),ss(moon1,moon2),ss(ven1,ven2),ss(mars1,mars2)),"How Fire, Earth, Air and Water patterns may complement or challenge each other.")
    ]
    overall=round(sum(x[1] for x in categories)/len(categories)); label="Strong match" if overall>=82 else "Promising connection" if overall>=70 else "Growth connection" if overall>=58 else "More contrast"
    strongest=sorted(categories,key=lambda x:x[1],reverse=True)[:2]; watch=sorted(categories,key=lambda x:x[1])[:2]
    return {"score":overall,"label":label,"categories":[{"label":a,"score":b,"text":c} for a,b,c in categories],"strongest":strongest,"watch":watch,"chart_complete":bool(va and mb)}


@app.context_processor
def inject_globals():
    u=current_user()
    statuses={}
    if u:
        statuses={k:membership_status(u["id"],k) for k in ("zodiac","business")}
    return dict(
        current_user=u,
        plans=PLANS,
        has_access=has_access,
        age_from_birth_date=age_from_birth_date,
        membership_statuses=statuses,
        compatibility_summary=compatibility_summary,
        coordination_categories=coordination_categories,
        media_url=media_url,
        stripe_ready=stripe_ready,
        platform_config=load_platform_config()
    )


@app.route("/")
def home():
    if current_user():
        return redirect(url_for("community"))

    c=conn()
    businesses=c.execute("""SELECT b.*,u.name owner_name
        FROM businesses b
        JOIN users u ON u.id=b.owner_id
        LEFT JOIN subscriptions s
          ON s.user_id=b.owner_id
         AND s.membership_type='business'
         AND s.status IN ('active','trialing')
        WHERE b.status='active' AND u.suspended=0
        ORDER BY CASE WHEN s.id IS NOT NULL THEN 0 ELSE 1 END, b.created_at DESC
        LIMIT 12""").fetchall()
    c.close()

    return render_template(
        "home.html",
        businesses=businesses,
        sky=current_sky_snapshot()
    )


@app.route("/join", methods=["GET","POST"])
def join():
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); agreed=bool(request.form.get("agree_terms"))
        if len(name)<2 or "@" not in email or len(password)<8:
            flash("Use your name, a valid email, and a password with at least 8 characters."); return render_template("join.html")
        if not agreed:
            flash("Please confirm the community terms and privacy notice before creating an account."); return render_template("join.html")
        c=conn()
        try:
            cur=c.execute("INSERT INTO users(name,email,password,plan) VALUES (?,?,?,'free')",(name,email,hash_password(password)))
            c.commit(); session["user_id"]=cur.lastrowid; return redirect(url_for("community"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.")
        finally: c.close()
    return render_template("join.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        c=conn(); u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if u and password_matches(u["password"],password):
            if not u["password"].startswith(("scrypt:","pbkdf2:","argon2:")):
                c.execute("UPDATE users SET password=? WHERE id=?",(hash_password(password),u["id"])); c.commit()
            if u["suspended"]: flash("This account is currently unavailable.")
            else: session.clear(); session["user_id"]=u["id"]; c.close(); return redirect(url_for("community"))
        else: flash("Invalid email or password.")
        c.close()
    return render_template("login.html")


@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("home"))


@app.route("/community", methods=["GET","POST"])
def community():
    u=current_user()
    if not u:
        return redirect(url_for("login"))

    c=conn()

    if request.method=="POST":
        body=request.form.get("body","").strip()
        if body:
            c.execute(
                "INSERT INTO posts(user_id,body) VALUES (?,?)",
                (u["id"],body)
            )
            c.commit()

    posts=c.execute("""SELECT posts.*,users.name,users.photo
        FROM posts
        JOIN users ON users.id=posts.user_id
        WHERE users.suspended=0
        ORDER BY posts.id DESC
        LIMIT 40""").fetchall()

    members=c.execute("""SELECT id,name,photo,profile_headline,bio,city,sun,
        show_headline,show_city,show_bio,show_zodiac_basic
        FROM users
        WHERE suspended=0
        ORDER BY is_creator DESC,name
        LIMIT 24""").fetchall()

    businesses=c.execute("""SELECT b.*,u.name owner_name
        FROM businesses b
        JOIN users u ON u.id=b.owner_id
        LEFT JOIN subscriptions s
          ON s.user_id=b.owner_id
         AND s.membership_type='business'
         AND s.status IN ('active','trialing')
        WHERE b.status='active' AND u.suspended=0
        ORDER BY CASE WHEN s.id IS NOT NULL THEN 0 ELSE 1 END, b.created_at DESC
        LIMIT 6""").fetchall()

    daters=c.execute("""SELECT *
        FROM users
        WHERE dating_profile_active=1
          AND dating_18_confirmed=1
          AND suspended=0
          AND id<>?
        ORDER BY id DESC
        LIMIT 6""",(u["id"],)).fetchall()

    creator=bool(u["is_creator"] or u["is_admin"])
    c.close()

    reflection=daily_seasons_reflection(u)

    return render_template(
        "community.html",
        posts=posts,
        members=members,
        businesses=businesses,
        daters=daters,
        creator=creator,
        reflection=reflection
    )


@app.route("/members")
def members():
    u=current_user()
    if not u: return redirect(url_for("login"))
    q=request.args.get("q","").strip()
    c=conn(); sql="SELECT * FROM users WHERE suspended=0"; params=[]
    if q:
        sql+=" AND (name LIKE ? OR city LIKE ? OR bio LIKE ? OR profile_headline LIKE ?)"; params += [f"%{q}%"]*4
    sql+=" ORDER BY is_creator DESC,name"
    rows=c.execute(sql,params).fetchall(); c.close()
    return render_template("members.html",members=rows,q=q)


@app.route("/profile/<int:user_id>")
def profile(user_id):
    viewer=current_user()
    if not viewer: return redirect(url_for("login"))
    c=conn(); member=c.execute("SELECT * FROM users WHERE id=? AND suspended=0",(user_id,)).fetchone(); c.close()
    if not member: return "Member not found",404
    return render_template("profile.html",member=member,viewer=viewer)


@app.route("/edit-profile", methods=["GET","POST"])
def edit_profile():
    u=current_user()
    if not u: return redirect(url_for("login"))
    if request.method=="POST":
        bio=request.form.get("bio","").strip(); city=request.form.get("city","").strip(); headline=request.form.get("profile_headline","").strip()
        photo=save_image(request.files.get("photo"),f"user{u['id']}") or u["photo"]
        show_headline=1 if request.form.get("show_headline") else 0; show_city=1 if request.form.get("show_city") else 0
        show_bio=1 if request.form.get("show_bio") else 0; show_zodiac_basic=1 if request.form.get("show_zodiac_basic") else 0
        c=conn(); c.execute("UPDATE users SET bio=?,city=?,profile_headline=?,photo=?,show_headline=?,show_city=?,show_bio=?,show_zodiac_basic=? WHERE id=?",
                            (bio,city,headline,photo,show_headline,show_city,show_bio,show_zodiac_basic,u["id"]))
        creator_post=request.form.get("creator_post","").strip()
        if (u["is_creator"] or u["is_admin"]) and creator_post: c.execute("INSERT INTO posts(user_id,body) VALUES (?,?)",(u["id"],creator_post))
        c.commit(); c.close(); flash("Profile updated."); return redirect(url_for("community" if creator_post else "profile",user_id=u["id"]))
    return render_template("edit_profile.html",user=u)


@app.route("/memberships")
@app.route("/plans")
def plans():
    return render_template("plans.html",visible_plans=PLANS)


@app.route("/dev/upgrade/<plan_key>")
def dev_upgrade(plan_key):
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not load_platform_config().get("allow_dev_upgrades",True): return "Development upgrades are disabled.",403
    if plan_key not in ("zodiac","business"): return "Unknown plan",404
    c=conn(); c.execute("INSERT INTO subscriptions(user_id,membership_type,status,provider,updated_at) VALUES (?,?,'active','development',CURRENT_TIMESTAMP) ON CONFLICT(user_id,membership_type) DO UPDATE SET status='active',provider='development',updated_at=CURRENT_TIMESTAMP",(u["id"],plan_key)); c.commit(); c.close(); flash("Development membership activated.")
    return redirect(url_for("birth_wizard") if plan_key=="zodiac" else url_for("business_setup"))

@app.route("/upgrade/<plan_key>")
@app.route("/checkout/<plan_key>")
def upgrade(plan_key):
    u=current_user()
    if not u: return redirect(url_for("login"))
    if plan_key not in ("zodiac","business"): return "Unknown plan",404
    cfg=load_platform_config()
    if not stripe_ready(plan_key): return render_template("payment_setup_needed.html",plan_key=plan_key,is_admin=bool(u["is_admin"]))
    try:
        stripe.api_key=cfg["stripe_secret_key"]; price_id=cfg["stripe_zodiac_price_id"] if plan_key=="zodiac" else cfg["stripe_business_price_id"]; base=cfg.get("public_base_url") or request.url_root.rstrip("/")
        checkout=stripe.checkout.Session.create(mode="subscription",line_items=[{"price":price_id,"quantity":1}],success_url=base+url_for("billing_success")+"?session_id={CHECKOUT_SESSION_ID}",cancel_url=base+url_for("plans"),customer_email=u["email"],client_reference_id=str(u["id"]),metadata={"user_id":str(u["id"]),"membership_type":plan_key},subscription_data={"metadata":{"user_id":str(u["id"]),"membership_type":plan_key}},allow_promotion_codes=True)
        c=conn(); c.execute("INSERT INTO subscriptions(user_id,membership_type,status,provider,price_id,checkout_session_id,updated_at) VALUES (?,?,'pending','stripe',?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,membership_type) DO UPDATE SET status='pending',provider='stripe',price_id=excluded.price_id,checkout_session_id=excluded.checkout_session_id,updated_at=CURRENT_TIMESTAMP",(u["id"],plan_key,price_id,checkout.id)); c.commit(); c.close(); return redirect(checkout.url,code=303)
    except Exception as exc: flash(f"Stripe Checkout could not start: {exc}"); return redirect(url_for("plans"))

@app.route("/billing/success")
def billing_success():
    if not current_user(): return redirect(url_for("login"))
    return render_template("billing_success.html")

@app.route("/stripe/webhook",methods=["POST"])
def stripe_webhook():
    cfg=load_platform_config()
    if not stripe or not cfg.get("stripe_webhook_secret"): return "Stripe webhook is not configured",400
    stripe.api_key=cfg.get("stripe_secret_key","")
    try: event=stripe.Webhook.construct_event(request.data,request.headers.get("Stripe-Signature",""),cfg["stripe_webhook_secret"])
    except Exception: return "Invalid webhook",400
    obj=event["data"]["object"]; typ=event["type"]; c=conn()
    if typ=="checkout.session.completed":
        meta=obj.get("metadata",{}); uid=meta.get("user_id") or obj.get("client_reference_id"); plan=meta.get("membership_type")
        if uid and plan in ("zodiac","business"):
            c.execute("INSERT INTO subscriptions(user_id,membership_type,status,provider,provider_customer_id,provider_subscription_id,checkout_session_id,updated_at) VALUES (?,?,'active','stripe',?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,membership_type) DO UPDATE SET status='active',provider='stripe',provider_customer_id=excluded.provider_customer_id,provider_subscription_id=excluded.provider_subscription_id,checkout_session_id=excluded.checkout_session_id,updated_at=CURRENT_TIMESTAMP",(int(uid),plan,obj.get("customer","") or "",obj.get("subscription","") or "",obj.get("id","") or ""))
    elif typ in ("customer.subscription.updated","customer.subscription.deleted"):
        raw=obj.get("status","canceled") if typ.endswith("updated") else "canceled"; app_status="active" if raw in ("active","trialing") else ("past_due" if raw in ("past_due","unpaid") else "canceled"); c.execute("UPDATE subscriptions SET status=?,provider='stripe',updated_at=CURRENT_TIMESTAMP WHERE provider_subscription_id=?",(app_status,obj.get("id","")))
    elif typ=="invoice.payment_failed": c.execute("UPDATE subscriptions SET status='past_due',updated_at=CURRENT_TIMESTAMP WHERE provider_subscription_id=?",(obj.get("subscription",""),))
    elif typ=="invoice.paid": c.execute("UPDATE subscriptions SET status='active',updated_at=CURRENT_TIMESTAMP WHERE provider_subscription_id=?",(obj.get("subscription",""),))
    c.commit(); c.close(); return jsonify(received=True)

@app.route("/admin/platform-setup",methods=["GET","POST"])
def platform_setup():
    u=current_user()
    if not u or not u["is_admin"]: return "Admin only",403
    cfg=load_platform_config()
    if request.method=="POST":
        new={"stripe_secret_key":request.form.get("stripe_secret_key","").strip(),"stripe_webhook_secret":request.form.get("stripe_webhook_secret","").strip(),"stripe_zodiac_price_id":request.form.get("stripe_zodiac_price_id","").strip(),"stripe_business_price_id":request.form.get("stripe_business_price_id","").strip(),"public_base_url":request.form.get("public_base_url","").strip(),"allow_dev_upgrades":bool(request.form.get("allow_dev_upgrades"))}; CONFIG_PATH.write_text(json.dumps(new,indent=2),encoding="utf-8"); flash("Platform settings saved locally."); return redirect(url_for("platform_setup"))
    return render_template("platform_setup.html",cfg=cfg,stripe_installed=bool(stripe),astro_installed=bool(swe))

@app.route("/birth-info",methods=["GET","POST"])
def birth_wizard():
    u=current_user()
    if not u: return redirect(url_for("login"))
    birth=get_birth_data(u["id"])
    if request.method=="POST":
        birth_date=request.form.get("birth_date","").strip(); birth_time=request.form.get("birth_time","").strip(); time_known=1 if request.form.get("time_known") else 0; city=request.form.get("birth_city","").strip(); state=request.form.get("birth_state","").strip(); country=request.form.get("birth_country","").strip(); lat=request.form.get("latitude","").strip(); lon=request.form.get("longitude","").strip(); tzname=request.form.get("timezone","").strip(); offset=request.form.get("utc_offset","").strip()
        if not birth_date or not city or not country: flash("Birth date, city and country are required."); return render_template("birth_wizard.html",birth=birth,chart=get_birth_chart(u["id"]),astro_installed=bool(swe))
        if (age_from_birth_date(birth_date) or 0)<18: flash("Zodiac Dater is for adults age 18 and older."); return redirect(url_for("community"))
        c=conn(); c.execute("INSERT INTO birth_data(user_id,birth_date,birth_time,time_known,birth_city,birth_state,birth_country,latitude,longitude,timezone,utc_offset,calculation_status,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET birth_date=excluded.birth_date,birth_time=excluded.birth_time,time_known=excluded.time_known,birth_city=excluded.birth_city,birth_state=excluded.birth_state,birth_country=excluded.birth_country,latitude=excluded.latitude,longitude=excluded.longitude,timezone=excluded.timezone,utc_offset=excluded.utc_offset,calculation_status='pending',updated_at=CURRENT_TIMESTAMP",(u["id"],birth_date,birth_time,time_known,city,state,country,float(lat) if lat else None,float(lon) if lon else None,tzname,float(offset) if offset else None)); c.execute("UPDATE users SET birth_date=?,birth_time=?,birth_city=?,dating_18_confirmed=1 WHERE id=?",(birth_date,birth_time,city,u["id"])); c.commit(); c.close(); ok,msg=calculate_birth_chart(u["id"]); flash(msg); return redirect(url_for("birth_chart_result") if ok else url_for("birth_wizard"))
    return render_template("birth_wizard.html",birth=birth,chart=get_birth_chart(u["id"]),astro_installed=bool(swe))

@app.route("/birth-chart")
def birth_chart_result():
    u=current_user()
    if not u: return redirect(url_for("login"))
    chart=get_birth_chart(u["id"]); birth=get_birth_data(u["id"])
    if not chart: return redirect(url_for("birth_wizard"))
    try: degrees=json.loads(chart["planet_degrees_json"] or "{}")
    except Exception: degrees={}
    try: balance=json.loads(chart["element_balance_json"] or "{}")
    except Exception: balance={}
    return render_template("birth_chart_result.html",chart=chart,birth=birth,degrees=degrees,balance=balance)

@app.route("/dating-profile", methods=["GET","POST"])
def dating_profile_builder():
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not get_birth_data(u["id"]): return redirect(url_for("birth_wizard"))
    if not dating_eligible(u): return render_template("dating_gate.html",user=u)
    if request.method=="POST":
        vals=[request.form.get("dating_intention","").strip(),request.form.get("relationship_style","").strip(),
              request.form.get("gender","").strip(),request.form.get("interested_in","").strip(),
              request.form.get("dating_headline","").strip(),request.form.get("dating_bio","").strip()]
        dating_photo=save_image(request.files.get("dating_photo"),f"dating{u['id']}") or u["dating_photo"]
        active=1 if request.form.get("dating_profile_active") else 0
        c=conn(); c.execute("""UPDATE users SET dating_intention=?,relationship_style=?,gender=?,interested_in=?,dating_headline=?,dating_bio=?,dating_photo=?,dating_profile_active=? WHERE id=?""",
                            (*vals,dating_photo,active,u["id"])); c.commit(); c.close()
        if active: create_compatibility_alerts(u["id"])
        flash("Dating profile saved. Your dating profile is free to create and browse; The Seasons Within Membership unlocks full profiles, compatibility, personalized date ideas and alerts.")
        return redirect(url_for("zodiac"))
    return render_template("dating_profile_builder.html",user=u,birth=get_birth_data(u["id"]))


@app.route("/zodiac")
def zodiac():
    u=current_user()
    if not u: return redirect(url_for("login"))
    q=request.args.get("q","").strip(); city=request.args.get("city","").strip(); sign=request.args.get("sign","").strip()
    sql="""SELECT u.* FROM users u WHERE u.dating_profile_active=1 AND u.dating_18_confirmed=1 AND u.suspended=0 AND u.id<>?"""; params=[u["id"]]
    if q: sql+=" AND (u.name LIKE ? OR u.dating_bio LIKE ? OR u.dating_intention LIKE ? OR u.dating_headline LIKE ?)"; params += [f"%{q}%"]*4
    if city: sql+=" AND u.city LIKE ?"; params.append(f"%{city}%")
    if sign: sql+=" AND (u.sun LIKE ? OR u.moon LIKE ? OR u.rising LIKE ?)"; params += [f"%{sign}%"]*3
    sql+=" ORDER BY u.name"
    c=conn(); rows=c.execute(sql,params).fetchall(); c.close(); members=[m for m in rows if (age_from_birth_date(m["birth_date"]) or 0)>=18]
    premium=has_access(u,"zodiac")
    compat={m["id"]:compatibility_summary(u,m) for m in members} if premium else {}
    return render_template("zodiac.html",members=members,q=q,city=city,sign=sign,compat=compat,premium=premium)


@app.route("/zodiac/profile/<int:user_id>")
def zodiac_profile(user_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); member=c.execute("SELECT * FROM users WHERE id=? AND dating_profile_active=1 AND dating_18_confirmed=1 AND suspended=0",(user_id,)).fetchone(); c.close()
    if not member or (age_from_birth_date(member["birth_date"]) or 0)<18: return "Dating profile not found",404
    premium=has_access(u,"zodiac")
    return render_template("zodiac_profile.html",member=member,premium=premium)


@app.route("/compatibility/<int:user_id>")
def compatibility(user_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not has_access(u,"zodiac"): return render_template("locked.html",area="Full Compatibility & Date Ideas",plan_key="zodiac")
    if not get_birth_data(u["id"]): flash("Add your birth information before running compatibility."); return redirect(url_for("birth_wizard"))
    c=conn(); member=c.execute("SELECT * FROM users WHERE id=? AND suspended=0",(user_id,)).fetchone(); c.close()
    if not member: return "Member not found",404
    return render_template("compatibility.html",member=member,result=full_compatibility_report(u,member),preview=False)


@app.route("/messages")
def messages():
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); threads=c.execute("""SELECT other.id,other.name,other.photo,MAX(m.created_at) last_time FROM messages m
        JOIN users other ON other.id=CASE WHEN m.sender_id=? THEN m.recipient_id ELSE m.sender_id END
        WHERE (m.sender_id=? OR m.recipient_id=?) AND other.suspended=0 GROUP BY other.id ORDER BY last_time DESC""",(u["id"],u["id"],u["id"])).fetchall(); c.close()
    return render_template("messages.html",threads=threads)


@app.route("/messages/<int:user_id>",methods=["GET","POST"])
def message_thread(user_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); other=c.execute("SELECT * FROM users WHERE id=? AND suspended=0",(user_id,)).fetchone()
    if not other: c.close(); return "Member not found",404
    if request.method=="POST":
        body=request.form.get("body","").strip()
        if body: c.execute("INSERT INTO messages(sender_id,recipient_id,body) VALUES (?,?,?)",(u["id"],user_id,body)); c.commit()
    thread=c.execute("""SELECT m.*,s.name sender_name FROM messages m JOIN users s ON s.id=m.sender_id
        WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?) ORDER BY m.id""",(u["id"],user_id,user_id,u["id"])).fetchall(); c.close()
    return render_template("message_thread.html",other=other,thread=thread)


@app.route("/report/<int:user_id>",methods=["POST"])
def report_user(user_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    reason=request.form.get("reason","").strip() or "Member report"; c=conn(); c.execute("INSERT INTO reports(reporter_id,reported_user_id,reason) VALUES (?,?,?)",(u["id"],user_id,reason)); c.commit(); c.close(); flash("Report submitted for admin review."); return redirect(request.referrer or url_for("community"))


@app.route("/notifications")
def notifications():
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); rows=c.execute("SELECT n.*,u.name related_name,u.dating_photo,u.photo FROM notifications n LEFT JOIN users u ON u.id=n.related_user_id WHERE n.user_id=? ORDER BY n.id DESC LIMIT 100",(u["id"],)).fetchall(); c.close(); return render_template("notifications.html",notifications=rows)

@app.route("/notifications/read/<int:notification_id>")
def notification_read(notification_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); n=c.execute("SELECT * FROM notifications WHERE id=? AND user_id=?",(notification_id,u["id"])).fetchone()
    if n: c.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=?",(notification_id,)); c.commit()
    c.close(); return redirect(url_for("zodiac_profile",user_id=n["related_user_id"]) if n and n["related_user_id"] else url_for("notifications"))

@app.route("/business")
def business():
    u=current_user(); q=request.args.get("q","").strip(); category=request.args.get("category","").strip(); c=conn()
    own=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone() if u else None
    sql="""SELECT b.*,u.name owner_name FROM businesses b JOIN users u ON u.id=b.owner_id
           JOIN subscriptions s ON s.user_id=b.owner_id AND s.membership_type='business' AND s.status IN ('active','trialing')
           WHERE b.status='active' AND u.suspended=0"""; params=[]
    if q: sql+=" AND (b.business_name LIKE ? OR b.description LIKE ? OR b.city LIKE ?)"; params += [f"%{q}%"]*3
    if category: sql+=" AND b.category LIKE ?"; params.append(f"%{category}%")
    sql+=" ORDER BY b.business_name"; businesses=c.execute(sql,params).fetchall(); c.close()
    return render_template("business.html",businesses=businesses,own=own,q=q,category=category,preview=False)


@app.route("/business/setup",methods=["GET","POST"])
def business_setup():
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not has_access(u,"business"): return render_template("locked.html",area="Business Network",plan_key="business")
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    if request.method=="POST":
        name=request.form.get("business_name","").strip()
        if not name: flash("Business name is required."); c.close(); return redirect(url_for("business_setup"))
        logo=save_image(request.files.get("logo"),f"biz{u['id']}_logo") or (business["logo"] if business else "")
        hero=save_image(request.files.get("hero_image"),f"biz{u['id']}_hero") or (business["hero_image"] if business else "")
        vals=[name,request.form.get("tagline","").strip(),request.form.get("description","").strip(),request.form.get("category","").strip(),request.form.get("city","").strip(),request.form.get("website","").strip(),request.form.get("contact_email","").strip(),request.form.get("phone","").strip(),logo,hero,request.form.get("accent","#b99ad6").strip()]
        if business:
            c.execute("""UPDATE businesses SET business_name=?,tagline=?,description=?,category=?,city=?,website=?,contact_email=?,phone=?,logo=?,hero_image=?,accent=?,status='active' WHERE owner_id=?""",(*vals,u["id"])); slug=business["slug"]
        else:
            slug=slugify(name); c.execute("""INSERT INTO businesses(owner_id,slug,business_name,tagline,description,category,city,website,contact_email,phone,logo,hero_image,accent,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",(u["id"],slug,*vals))
        c.commit(); c.close(); flash("Business identity saved. Now add services, classes, products or memberships."); return redirect(url_for("business_items"))
    c.close(); return render_template("business_setup.html",business=business)


@app.route("/business/items",methods=["GET","POST"])
def business_items():
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not has_access(u,"business"): return render_template("locked.html",area="Business Network",plan_key="business")
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    if not business: c.close(); return redirect(url_for("business_setup"))
    if request.method=="POST":
        title=request.form.get("title","").strip()
        if title:
            c.execute("INSERT INTO business_items(business_id,item_type,title,description,price,action_url) VALUES (?,?,?,?,?,?)",(business["id"],request.form.get("item_type","service"),title,request.form.get("description","").strip(),request.form.get("price","").strip(),request.form.get("action_url","").strip())); c.commit(); flash("Added to your hosted app.")
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall(); c.close()
    return render_template("business_items.html",business=business,items=items)


@app.route("/business/item/<int:item_id>/delete",methods=["POST"])
def delete_business_item(item_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); c.execute("UPDATE business_items SET active=0 WHERE id=? AND business_id IN (SELECT id FROM businesses WHERE owner_id=?)",(item_id,u["id"])); c.commit(); c.close(); return redirect(url_for("business_items"))


@app.route("/business/my-app")
def my_business_app():
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    if not business: c.close(); return redirect(url_for("business_setup"))
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall(); c.close(); return render_template("business_app.html",business=business,items=items,owner_preview=True)

@app.route("/app/<slug>")
def business_app(slug):
    c=conn(); business=c.execute("""SELECT b.*,u.name owner_name FROM businesses b JOIN users u ON u.id=b.owner_id
       JOIN subscriptions s ON s.user_id=b.owner_id AND s.membership_type='business' AND s.status IN ('active','trialing')
       WHERE b.slug=? AND b.status='active'""",(slug,)).fetchone()
    if not business: c.close(); return render_template("business_inactive.html"),503
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall(); c.close(); return render_template("business_app.html",business=business,items=items)


@app.route("/retreats")
def retreats(): return render_template("retreats.html")


@app.route("/admin")
def admin():
    u=current_user()
    if not u or not u["is_admin"]: return "Admin access required",403
    c=conn(); reports=c.execute("""SELECT r.*,a.name reporter_name,b.name reported_name FROM reports r JOIN users a ON a.id=r.reporter_id LEFT JOIN users b ON b.id=r.reported_user_id ORDER BY r.id DESC""").fetchall(); users=c.execute("SELECT * FROM users ORDER BY id DESC").fetchall(); subs=c.execute("SELECT s.*,u.name,u.email FROM subscriptions s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC").fetchall(); c.close(); return render_template("admin.html",reports=reports,users=users,subscriptions=subs)


@app.route("/admin/suspend/<int:user_id>",methods=["POST"])
def admin_suspend(user_id):
    u=current_user()
    if not u or not u["is_admin"]: return "Admin access required",403
    c=conn(); c.execute("UPDATE users SET suspended=CASE WHEN suspended=1 THEN 0 ELSE 1 END WHERE id=?",(user_id,)); c.commit(); c.close(); return redirect(url_for("admin"))


init_db()
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5055)