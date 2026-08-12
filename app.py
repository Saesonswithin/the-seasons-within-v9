from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
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
DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "community_v8.db"
UPLOADS = Path(os.environ.get("UPLOAD_DIR", str(Path(__file__).with_name("static") / "uploads")))
UPLOADS.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(__file__).with_name("platform_config.json")

def media_url(path):
    if not path:
        return ""
    if path.startswith("uploads/"):
        return url_for("uploaded_file", filename=path.split("/",1)[1])
    return url_for("static", filename=path)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOADS, filename)


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
    "zodiac": {"name": "The Seasons Within Membership", "price": "$10.99/mo", "description": "Unlock expanded connection profiles, full natal-chart insights, deeper Conscious Coordination, media, likes, personalized connection ideas and member alerts.", "visible": True},
    "business": {"name": "Business Network", "price": "$29.99/mo", "description": "Build and host your wellness business app inside The Seasons Within with services, classes, events, shop items, memberships and collaboration tools.", "visible": True},
}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "m4v"}
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

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
    CREATE TABLE IF NOT EXISTS dating_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, media_type TEXT NOT NULL, path TEXT NOT NULL, sort_order INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, liker_id INTEGER NOT NULL, liked_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(liker_id, liked_id)
    );
    CREATE TABLE IF NOT EXISTS video_call_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, requester_id INTEGER NOT NULL, recipient_id INTEGER NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            "dating_photo": "TEXT DEFAULT ''", "dating_bio": "TEXT DEFAULT ''", "dating_headline": "TEXT DEFAULT ''", "dating_profile_active": "INTEGER DEFAULT 0",
            "height": "TEXT DEFAULT ''", "weight": "TEXT DEFAULT ''", "connection_intentions": "TEXT DEFAULT ''",
            "age_min": "INTEGER DEFAULT 18", "age_max": "INTEGER DEFAULT 99", "location_preference": "TEXT DEFAULT ''",
            "family_preferences": "TEXT DEFAULT ''", "lifestyle": "TEXT DEFAULT ''", "wellness_interests": "TEXT DEFAULT ''",
            "communication_style": "TEXT DEFAULT ''", "ideal_connection": "TEXT DEFAULT ''", "values_text": "TEXT DEFAULT ''",
            "journey_story": "TEXT DEFAULT ''", "looking_for": "TEXT DEFAULT ''", "dealbreakers": "TEXT DEFAULT ''",
            "friendship_interests": "TEXT DEFAULT ''", "workout_interests": "TEXT DEFAULT ''", "travel_interests": "TEXT DEFAULT ''",
            "creative_interests": "TEXT DEFAULT ''", "business_interests": "TEXT DEFAULT ''", "retreat_interests": "TEXT DEFAULT ''",
            "allow_text_from": "TEXT DEFAULT 'matches'", "allow_video_from": "TEXT DEFAULT 'approved'",
            "show_mercury": "INTEGER DEFAULT 0", "show_height": "INTEGER DEFAULT 1", "show_weight": "INTEGER DEFAULT 0",
            "show_business_interests": "INTEGER DEFAULT 1", "notify_matches": "INTEGER DEFAULT 1", "notify_moon": "INTEGER DEFAULT 1",
            "match_threshold": "INTEGER DEFAULT 75", "last_moon_sign": "TEXT DEFAULT ''"
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
    ensure_column(c, "messages", "media_path", "TEXT DEFAULT ''")
    ensure_column(c, "messages", "media_type", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "instagram", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "facebook", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "affiliate_url", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "booking_url", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "business_type", "TEXT DEFAULT 'business'")
    ensure_column(c, "businesses", "creator_title", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "tiktok", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "youtube", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "media_kit_enabled", "INTEGER DEFAULT 0")
    ensure_column(c, "businesses", "content_categories", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "audience_info", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "featured_content", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "previous_collaborations", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "collaboration_interests", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "social_followers", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "social_likes", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "social_views", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "engagement_rate", "TEXT DEFAULT ''")
    ensure_column(c, "businesses", "show_natal_business", "INTEGER DEFAULT 0")
    ensure_column(c, "businesses", "profile_views", "INTEGER DEFAULT 0")
    ensure_column(c, "users", "complimentary_member", "INTEGER DEFAULT 0")
    ensure_column(c, "users", "complimentary_business", "INTEGER DEFAULT 0")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS business_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'update',
        caption TEXT DEFAULT '',
        media_path TEXT DEFAULT '',
        media_type TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS business_follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(business_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS business_collaboration_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        requester_id INTEGER,
        requester_name TEXT DEFAULT '',
        requester_email TEXT DEFAULT '',
        request_type TEXT DEFAULT '',
        message TEXT DEFAULT '',
        status TEXT DEFAULT 'new',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Secure demo accounts. Existing plaintext accounts are automatically upgraded on next login.
    demo = [
        ("Avery", "avery@example.com", "zodiac", "Book lover, yoga student and weekend traveler looking for a grounded relationship.", "Atlanta", "Libra", "Pisces", "Leo", "Long-term relationship", "", ""),
        ("Jordan", "jordan@example.com", "business", "Creative entrepreneur building community-centered brands.", "Detroit", "Gemini", "Capricorn", "Virgo", "", "Brand Strategist", "Find collaborators and referral partners"),
        ("Morgan", "morgan@example.com", "all_access", "Yoga, travel, business and conscious connection.", "Chicago", "Taurus", "Cancer", "Sagittarius", "Open to dating intentionally", "Wellness Founder", "Partnerships and event collaborations"),
        ("Nia", "nia@example.com", "zodiac", "Nature walks, live music, meditation and honest conversation.", "Atlanta", "Aquarius", "Libra", "Cancer", "A committed partnership", "", ""),
        ("Marcus", "marcus@example.com", "zodiac", "Fitness, cooking, family and building a peaceful life.", "Detroit", "Leo", "Taurus", "Capricorn", "Dating with purpose", "", ""),
    ]
    for name,email,legacy_plan,bio,city,sun,moon,rising,intention,role,goal in []:
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
    for email,(dob,venus,mars,rising2,dbio,dheadline) in {}.items():
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
    for email, body in {}.items():
        row = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row and c.execute("SELECT COUNT(*) FROM posts WHERE user_id=?", (row[0],)).fetchone()[0] == 0:
            c.execute("INSERT INTO posts(user_id,body) VALUES (?,?)", (row[0], body))

    # Extra mock wellness business owners so the public Business Network feels launch-ready.
    biz_demo = [
        ("Sage", "sage@business.demo", "Sound Harmony", "Chicago, IL"),
        ("Maya", "maya@business.demo", "Nature Vibes", "Asheville, NC"),
    ]
    for name,email,bizname,city in []:
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
    for email,name,slug,tagline,desc,category,city,contact in []:
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
    for slug,items in {}.items():
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
    if area == "zodiac" and "complimentary_member" in user.keys() and user["complimentary_member"]:
        return True
    if area == "business" and "complimentary_business" in user.keys() and user["complimentary_business"]:
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



def save_video(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ""
    filename = secure_filename(file_storage.filename)
    if "." not in filename or filename.rsplit(".", 1)[1].lower() not in ALLOWED_VIDEO_EXTENSIONS:
        return ""
    ext = filename.rsplit(".", 1)[1].lower()
    name = f"{prefix}_{int(datetime.now().timestamp())}.{ext}"
    file_storage.save(UPLOADS / name)
    return f"uploads/{name}"


def is_demo_email(email):
    email=(email or "").lower()
    return email.endswith("@example.com") or email.endswith("@business.demo") or email.endswith(".demo")


def overlap_intentions(a, b):
    def parts(v):
        return {x.strip().lower() for x in (v or "").split(",") if x.strip()}
    aa,bb=parts(a),parts(b)
    return aa & bb if aa and bb else set()


def is_match(user_a, user_b):
    c=conn()
    a=c.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",(user_a,user_b)).fetchone()
    b=c.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",(user_b,user_a)).fetchone()
    c.close()
    return bool(a and b)


def current_sky():
    now=datetime.now(timezone.utc)
    if (now.month < 3) or (now.month == 3 and now.day < 20) or (now.month == 12 and now.day >= 21):
        season="Winter"
    elif (now.month < 6) or (now.month == 6 and now.day < 21):
        season="Spring"
    elif (now.month < 9) or (now.month == 9 and now.day < 22):
        season="Summer"
    else:
        season="Autumn"
    info={"season":season,"moon_sign":"","moon_degree":0,"moon_phase":"","positions":{}}
    if swe is None:
        return info
    try:
        jd=swe.julday(now.year,now.month,now.day,now.hour+now.minute/60+now.second/3600)
        bodies={"Moon":swe.MOON,"Sun":swe.SUN,"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN}
        longs={}
        for name,body in bodies.items():
            res=swe.calc_ut(jd,body)
            lon=float(res[0][0])%360
            longs[name]=lon
            sign,within=zodiac_from_degree(lon)
            info["positions"][name]={"sign":sign,"degree":within}
        info["moon_sign"]=info["positions"]["Moon"]["sign"]
        info["moon_degree"]=info["positions"]["Moon"]["degree"]
        angle=(longs["Moon"]-longs["Sun"])%360
        phases=[(22.5,"New Moon"),(67.5,"Waxing Crescent"),(112.5,"First Quarter"),(157.5,"Waxing Gibbous"),(202.5,"Full Moon"),(247.5,"Waning Gibbous"),(292.5,"Last Quarter"),(337.5,"Waning Crescent"),(360,"New Moon")]
        info["moon_phase"]=next(label for limit,label in phases if angle<limit)
    except Exception:
        pass
    return info


MOON_REFLECTIONS={
"Aries":"Notice what wants a direct, honest response. Move with courage without rushing past your own feelings.",
"Taurus":"Return to what feels steady, nourishing and sustainable. Let your body remind you what enough feels like.",
"Gemini":"Name what is moving through your mind. Curiosity can create room for a new way of understanding yourself and others.",
"Cancer":"Make room for what feels tender. Home, belonging and emotional safety may deserve extra attention in your reflection.",
"Leo":"Notice where your heart wants to be seen and expressed. Create without needing every response to validate the expression.",
"Virgo":"Bring gentle attention to the details. Choose one useful adjustment without turning reflection into self-criticism.",
"Libra":"Notice where you are creating harmony and where you may be compromising what you actually need. Hear yourself before balancing everyone else.",
"Scorpio":"Be willing to sit with what is beneath the surface. Honesty and healthy boundaries can create space for deeper trust.",
"Sagittarius":"Look for the larger meaning without skipping over the present moment. What truth is asking for more room in your life?",
"Capricorn":"Consider what you are building and why. Let responsibility support your values rather than becoming a measure of your worth.",
"Aquarius":"Notice where you need freedom, perspective or community. Your difference can be useful without requiring distance from your feelings.",
"Pisces":"Give imagination and sensitivity a container. Rest, creativity and compassionate boundaries can exist together."
}


def daily_seasons_reflection(user):
    sky=current_sky()
    natal_moon=(user["moon"] if user and "moon" in user.keys() else "") or ""
    base=MOON_REFLECTIONS.get(natal_moon,"Notice what your inner world is asking you to acknowledge today.")
    seasonal={
      "Spring":"renewal, movement and what is beginning",
      "Summer":"expression, connection and what is expanding",
      "Autumn":"discernment, gratitude and what is ready to be released",
      "Winter":"rest, restoration and what is becoming clear in stillness"
    }.get(sky["season"],"your current season")
    return {
      "sky":sky,
      "natal_moon":natal_moon,
      "reflection":base,
      "season_text":f"Let the {sky['season']} season invite reflection on {seasonal}. These are reflective prompts, not predictions."
    }


def coordination_categories(viewer, member):
    def sc(a,b):
        return sign_score(a,b) if a and b else 50
    cats={
      "Emotional": round((sc(viewer["moon"],member["moon"])+sc(viewer["moon"],member["sun"]))/2),
      "Communication": sc(viewer["sun"],member["sun"]),
      "Romantic": round((sc(viewer["venus"],member["mars"])+sc(viewer["mars"],member["venus"]))/2),
      "Friendship": round((sc(viewer["sun"],member["sun"])+sc(viewer["moon"],member["moon"]))/2),
      "Business / Creative": round((sc(viewer["sun"],member["sun"])+sc(viewer["mars"],member["mars"]))/2),
      "Lifestyle": round((sc(viewer["rising"],member["rising"])+sc(viewer["sun"],member["sun"]))/2),
      "Growth": round((sc(viewer["sun"],member["moon"])+sc(viewer["moon"],member["sun"]))/2)
    }
    cats["Overall"]=round(sum(cats.values())/len(cats))
    return cats


def best_sign_matches(user, limit=4):
    placements=[user[k] for k in ("sun","moon","venus","mars") if k in user.keys() and user[k]]
    if not placements:
        return []
    ranked=[]
    for sign in ZODIAC_SIGNS:
        score=round(sum(sign_score(p,sign) for p in placements)/len(placements))
        ranked.append((sign,score))
    return sorted(ranked,key=lambda x:x[1],reverse=True)[:limit]


def natal_placement_description(label, sign):
    if not sign:
        return ""
    themes={
      "Sun":"identity and the way you express your core direction",
      "Moon":"emotional needs, instincts and your inner rhythm",
      "Rising":"first impressions, approach to life and how you meet new situations",
      "Venus":"affection, values and the way you relate and attract",
      "Mars":"drive, boundaries, desire and how you take action",
      "Mercury":"thinking, learning and communication style"
    }
    return f"{label} in {sign} reflects {themes.get(label,'a part of your personal pattern')}. Use it as a reflection point, not a rule about who you must be."


def sign_connection_ideas(sign):
    ideas={
      "Aries":["movement class","adventure activity","active coffee walk"],
      "Taurus":["wellness café","massage or spa experience","garden or nature outing"],
      "Gemini":["bookstore or talk","creative workshop","coffee and conversation"],
      "Cancer":["cozy dinner","waterfront walk","home-style wellness experience"],
      "Leo":["live music","art event","creative class"],
      "Virgo":["yoga or wellness class","healthy café","nature walk"],
      "Libra":["art gallery","tea house","beautiful dinner setting"],
      "Scorpio":["sound bath","intimate dinner","deep conversation experience"],
      "Sagittarius":["outdoor adventure","travel-inspired experience","cultural event"],
      "Capricorn":["business lunch","museum","structured wellness workshop"],
      "Aquarius":["community event","unique workshop","technology or creative experience"],
      "Pisces":["waterfront setting","sound healing","art or meditation experience"]
    }
    return ideas.get(sign,["wellness class","nature experience","meaningful conversation"])


def natal_house_signs(user_id):
    chart=get_birth_chart(user_id)
    if not chart:
        return []
    try:
        cusps=json.loads(chart["house_cusps_json"] or "[]")
    except Exception:
        cusps=[]
    out=[]
    for i,deg in enumerate(cusps[:12],1):
        try:
            sign,_=zodiac_from_degree(float(deg))
            out.append((i,sign))
        except Exception:
            pass
    return out


def ensure_dynamic_notifications(user):
    if not user:
        return
    sky=current_sky()
    moon=sky.get("moon_sign") or ""
    if not moon or not user["notify_moon"]:
        return
    c=conn()
    fresh=c.execute("SELECT * FROM users WHERE id=?",(user["id"],)).fetchone()
    last=(fresh["last_moon_sign"] or "") if fresh else ""
    if moon != last:
        c.execute("INSERT INTO notifications(user_id,notification_type,title,body) VALUES (?,?,?,?)",
                  (user["id"],"moon_shift",f"Moon moved into {moon}",
                   f"Your Daily Seasons Within reflection has updated for the Moon in {moon}. Use it as a reflective prompt alongside your natal Moon and current season."))
        c.execute("UPDATE users SET last_moon_sign=? WHERE id=?",(moon,user["id"]))
        c.commit()
    c.close()


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
    if not birth: return False,"Natal information is missing."
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
        return True,"Your natal chart was calculated and saved."
    except Exception as exc: return False,f"Chart calculation could not finish: {exc}"

def create_compatibility_alerts(new_user_id,threshold=None):
    c=conn()
    newcomer=c.execute("SELECT * FROM users WHERE id=?",(new_user_id,)).fetchone()
    if not newcomer or not newcomer["dating_profile_active"]:
        c.close()
        return
    threshold=threshold or int(newcomer["match_threshold"] or 75)
    for other in c.execute("SELECT * FROM users WHERE id<>? AND dating_profile_active=1 AND dating_18_confirmed=1 AND suspended=0 AND email NOT LIKE '%@example.com' AND email NOT LIKE '%@business.demo'",(new_user_id,)).fetchall():
        common=overlap_intentions(newcomer["connection_intentions"],other["connection_intentions"])
        if not common:
            continue
        cats=coordination_categories(other,newcomer)
        score=cats["Overall"]
        needed=max(threshold,int(other["match_threshold"] or 75))
        exists=c.execute("SELECT 1 FROM notifications WHERE user_id=? AND notification_type='coordination_match' AND related_user_id=?",(other["id"],new_user_id)).fetchone()
        if score>=needed and other["notify_matches"] and not exists:
            labels=", ".join(sorted(common)[:3])
            c.execute("INSERT INTO notifications(user_id,notification_type,title,body,related_user_id) VALUES (?,?,?,?,?)",
                      (other["id"],"coordination_match","New Conscious Coordination Match",
                       f"A new member corresponds with your profile at {score}% overall coordination. Shared intentions: {labels}.",new_user_id))
    c.commit()
    c.close()

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
    unread=0
    if u:
        c=conn()
        unread=c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND (read_at IS NULL OR read_at='')",(u["id"],)).fetchone()[0]
        c.close()
    return dict(current_user=u,plans=PLANS,has_access=has_access,age_from_birth_date=age_from_birth_date,
                membership_statuses=statuses,compatibility_summary=compatibility_summary,stripe_ready=stripe_ready,
                platform_config=load_platform_config(),current_sky=current_sky(),unread_notifications=unread,media_url=media_url)


@app.route("/")
def home():
    if current_user():
        return redirect(url_for("community"))
    c=conn()
    businesses=c.execute("""SELECT b.*,u.name owner_name,
           CASE WHEN s.status IN ('active','trialing') OR u.complimentary_business=1 THEN 1 ELSE 0 END AS paid_business
           FROM businesses b JOIN users u ON u.id=b.owner_id
           LEFT JOIN subscriptions s ON s.user_id=b.owner_id AND s.membership_type='business'
           WHERE b.status='active' AND u.suspended=0
           AND u.email NOT LIKE '%@example.com' AND u.email NOT LIKE '%@business.demo'
           ORDER BY paid_business DESC,b.created_at DESC LIMIT 12""").fetchall()
    c.close()
    return render_template("home.html", businesses=businesses, sky=current_sky())


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
    ensure_dynamic_notifications(u)
    c=conn()
    if request.method=="POST":
        body=request.form.get("body","").strip()
        if body:
            c.execute("INSERT INTO posts(user_id,body) VALUES (?,?)",(u["id"],body))
            c.commit()
    posts=c.execute("""SELECT posts.*,users.name,users.photo FROM posts
        JOIN users ON users.id=posts.user_id
        WHERE users.suspended=0 AND users.email NOT LIKE '%@example.com' AND users.email NOT LIKE '%@business.demo'
        ORDER BY posts.id DESC LIMIT 30""").fetchall()
    members=c.execute("""SELECT * FROM users WHERE suspended=0
        AND email NOT LIKE '%@example.com' AND email NOT LIKE '%@business.demo'
        ORDER BY is_creator DESC,name LIMIT 12""").fetchall()
    businesses=c.execute("""SELECT b.*,u.name owner_name FROM businesses b
        JOIN users u ON u.id=b.owner_id
        WHERE b.status='active' AND u.suspended=0
        AND u.email NOT LIKE '%@example.com' AND u.email NOT LIKE '%@business.demo'
        ORDER BY b.created_at DESC LIMIT 6""").fetchall()
    daters=c.execute("""SELECT * FROM users WHERE dating_profile_active=1 AND dating_18_confirmed=1
        AND suspended=0 AND id<>? AND email NOT LIKE '%@example.com' AND email NOT LIKE '%@business.demo'
        ORDER BY id DESC LIMIT 5""",(u["id"],)).fetchall()
    creator=bool(u["is_creator"] or u["is_admin"])
    c.close()
    reflection=daily_seasons_reflection(u)
    return render_template("community.html",posts=posts,members=members,businesses=businesses,daters=daters,
                           creator=creator,reflection=reflection,coordination_categories=coordination_categories)


@app.route("/members")
def members():
    u=current_user()
    if not u: return redirect(url_for("login"))
    q=request.args.get("q","").strip()
    c=conn(); sql="SELECT * FROM users WHERE suspended=0 AND email NOT LIKE '%@example.com' AND email NOT LIKE '%@business.demo'"; params=[]
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
    if not u:
        return redirect(url_for("login"))
    if request.method=="POST":
        city=request.form.get("city","").strip()
        headline=request.form.get("profile_headline","").strip()
        story=request.form.get("journey_story","").strip()
        photo=save_image(request.files.get("photo"),f"user{u['id']}") or u["photo"]
        c=conn()
        c.execute("UPDATE users SET city=?,profile_headline=?,journey_story=?,bio=?,photo=? WHERE id=?",
                  (city,headline,story,story,photo,u["id"]))
        c.commit()
        c.close()
        flash("Community profile updated.")
        return redirect(url_for("profile",user_id=u["id"]))
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
        if not birth_date or not city or not country: flash("Natal date, city and country are required."); return render_template("birth_wizard.html",birth=birth,chart=get_birth_chart(u["id"]),astro_installed=bool(swe))
        if (age_from_birth_date(birth_date) or 0)<18: flash("Conscious Coordination profiles are for adults age 18 and older."); return redirect(url_for("community"))
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
    if not u:
        return redirect(url_for("login"))
    if not get_birth_data(u["id"]):
        return redirect(url_for("birth_wizard"))
    if not dating_eligible(u):
        return render_template("dating_gate.html",user=u)
    premium=has_access(u,"zodiac")
    if request.method=="POST":
        fields=["dating_headline","dating_bio","gender","interested_in","connection_intentions","location_preference",
                "family_preferences","lifestyle","wellness_interests","communication_style","ideal_connection","values_text",
                "journey_story","looking_for","dealbreakers","friendship_interests","workout_interests","travel_interests",
                "creative_interests","business_interests","retreat_interests","height","weight","allow_text_from","allow_video_from"]
        vals=[request.form.get(f,"").strip() for f in fields]
        try:
            age_min=max(18,int(request.form.get("age_min") or 18))
            age_max=max(age_min,int(request.form.get("age_max") or 99))
        except ValueError:
            age_min,age_max=18,99
        active=1 if request.form.get("dating_profile_active") else 0
        show_mercury=1 if request.form.get("show_mercury") else 0
        show_height=1 if request.form.get("show_height") else 0
        show_weight=1 if request.form.get("show_weight") else 0
        show_business=1 if request.form.get("show_business_interests") else 0
        try:
            threshold=max(60,min(95,int(request.form.get("match_threshold") or 75)))
        except ValueError:
            threshold=75
        main=save_image(request.files.get("dating_photo"),f"dating{u['id']}") or u["dating_photo"]
        c=conn()
        assignments=",".join(f"{f}=?" for f in fields)
        c.execute(f"""UPDATE users SET {assignments},age_min=?,age_max=?,dating_profile_active=?,dating_photo=?,
                   show_mercury=?,show_height=?,show_weight=?,show_business_interests=?,match_threshold=? WHERE id=?""",
                  (*vals,age_min,age_max,active,main,show_mercury,show_height,show_weight,show_business,threshold,u["id"]))
        if premium:
            photo_count=c.execute("SELECT COUNT(*) FROM dating_media WHERE user_id=? AND media_type='photo'",(u["id"],)).fetchone()[0]
            video_count=c.execute("SELECT COUNT(*) FROM dating_media WHERE user_id=? AND media_type='video'",(u["id"],)).fetchone()[0]
            for f in request.files.getlist("photos"):
                if photo_count>=7:
                    break
                path=save_image(f,f"dater{u['id']}_p")
                if path:
                    c.execute("INSERT INTO dating_media(user_id,media_type,path,sort_order) VALUES (?,'photo',?,?)",
                              (u["id"],path,photo_count))
                    photo_count+=1
            for f in request.files.getlist("videos"):
                if video_count>=2:
                    break
                path=save_video(f,f"dater{u['id']}_v")
                if path:
                    c.execute("INSERT INTO dating_media(user_id,media_type,path,sort_order) VALUES (?,'video',?,?)",
                              (u["id"],path,video_count))
                    video_count+=1
        c.commit()
        c.close()
        if active:
            create_compatibility_alerts(u["id"])
        flash("Your Conscious Coordination profile was saved.")
        return redirect(url_for("zodiac_profile",user_id=u["id"]))
    c=conn()
    media=c.execute("SELECT * FROM dating_media WHERE user_id=? ORDER BY media_type,sort_order,id",(u["id"],)).fetchall()
    c.close()
    return render_template("dating_profile_builder.html",user=u,birth=get_birth_data(u["id"]),premium=premium,media=media)


@app.route("/zodiac")
def zodiac():
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    q=request.args.get("q","").strip()
    city=request.args.get("city","").strip()
    sign=request.args.get("sign","").strip()
    intention=request.args.get("intention","").strip()
    try:
        min_age=int(request.args.get("min_age") or 18)
        max_age=int(request.args.get("max_age") or 99)
    except ValueError:
        min_age,max_age=18,99
    sql="""SELECT u.* FROM users u WHERE u.dating_profile_active=1 AND u.dating_18_confirmed=1
           AND u.suspended=0 AND u.id<>? AND u.email NOT LIKE '%@example.com' AND u.email NOT LIKE '%@business.demo'"""
    params=[u["id"]]
    if q:
        sql+=" AND (u.name LIKE ? OR u.dating_bio LIKE ? OR u.looking_for LIKE ? OR u.connection_intentions LIKE ?)"
        params += [f"%{q}%"]*4
    if city:
        sql+=" AND u.city LIKE ?"
        params.append(f"%{city}%")
    if sign:
        sql+=" AND (u.sun LIKE ? OR u.moon LIKE ? OR u.rising LIKE ?)"
        params += [f"%{sign}%"]*3
    if intention:
        sql+=" AND u.connection_intentions LIKE ?"
        params.append(f"%{intention}%")
    sql+=" ORDER BY u.id DESC"
    c=conn()
    rows=c.execute(sql,params).fetchall()
    likes_from={r[0] for r in c.execute("SELECT liker_id FROM likes WHERE liked_id=?",(u["id"],)).fetchall()}
    c.close()
    members=[m for m in rows if min_age <= (age_from_birth_date(m["birth_date"]) or 0) <= max_age]
    compat={m["id"]:coordination_categories(u,m) for m in members}
    return render_template("zodiac.html",members=members,q=q,city=city,sign=sign,intention=intention,
                           compat=compat,premium=has_access(u,"zodiac"),likes_from=likes_from,
                           min_age=min_age,max_age=max_age)


@app.route("/zodiac/profile/<int:user_id>")
def zodiac_profile(user_id):
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    c=conn()
    member=c.execute("SELECT * FROM users WHERE id=? AND dating_profile_active=1 AND dating_18_confirmed=1 AND suspended=0",(user_id,)).fetchone()
    if not member or (age_from_birth_date(member["birth_date"]) or 0)<18:
        c.close()
        return "Connection profile not found",404
    media=c.execute("SELECT * FROM dating_media WHERE user_id=? ORDER BY media_type,sort_order,id",(user_id,)).fetchall()
    more=c.execute("""SELECT * FROM users WHERE dating_profile_active=1 AND suspended=0
                      AND id NOT IN (?,?) AND email NOT LIKE '%@example.com' AND email NOT LIKE '%@business.demo'
                      ORDER BY id DESC LIMIT 6""",(u["id"],user_id)).fetchall()
    liked=bool(c.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",(u["id"],user_id)).fetchone())
    c.close()
    matched=is_match(u["id"],user_id)
    cats=coordination_categories(u,member)
    premium=has_access(u,"zodiac")
    placements=[(x,member[x.lower()]) for x in ("Sun","Moon","Rising","Venus","Mars") if member[x.lower()]]
    if member["show_mercury"]:
        chart=get_birth_chart(member["id"])
        placements.append(("Mercury",chart["mercury"] if chart else ""))
    descriptions={label:natal_placement_description(label,sign) for label,sign in placements if sign}
    chart_all=get_birth_chart(member["id"])
    all_planets=[]
    if chart_all:
        for key in ("mercury","jupiter","saturn","uranus","neptune","pluto"):
            if chart_all[key] and (key!="mercury" or member["show_mercury"]):
                all_planets.append((key.title(),chart_all[key]))
    c=conn()
    business_ideas=c.execute("""SELECT b.* FROM businesses b JOIN users owner ON owner.id=b.owner_id
                                WHERE b.status='active' AND owner.suspended=0
                                AND owner.email NOT LIKE '%@example.com' AND owner.email NOT LIKE '%@business.demo'
                                ORDER BY b.created_at DESC LIMIT 4""").fetchall()
    c.close()
    return render_template("zodiac_profile.html",member=member,premium=premium,media=media,more=more,liked=liked,
                           matched=matched,cats=cats,placements=placements,descriptions=descriptions,
                           best_matches=best_sign_matches(member),viewer=u,house_signs=natal_house_signs(member["id"]),
                           sign_ideas=sign_connection_ideas(member["sun"]),business_ideas=business_ideas,all_planets=all_planets)


@app.route("/compatibility/<int:user_id>")
def compatibility(user_id):
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    if not get_birth_data(u["id"]):
        flash("Add your natal information before running Conscious Coordination.")
        return redirect(url_for("birth_wizard"))
    c=conn()
    member=c.execute("SELECT * FROM users WHERE id=? AND suspended=0",(user_id,)).fetchone()
    c.close()
    if not member:
        return "Member not found",404
    premium=has_access(u,"zodiac")
    return render_template("compatibility.html",member=member,cats=coordination_categories(u,member),
                           result=full_compatibility_report(u,member) if premium else None,premium=premium)


@app.route("/like/<int:user_id>",methods=["POST"])
def like_member(user_id):
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    if user_id==u["id"]:
        return redirect(request.referrer or url_for("zodiac"))
    c=conn()
    c.execute("INSERT OR IGNORE INTO likes(liker_id,liked_id) VALUES (?,?)",(u["id"],user_id))
    mutual=bool(c.execute("SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?",(user_id,u["id"])).fetchone())
    if mutual:
        c.execute("INSERT INTO notifications(user_id,notification_type,title,body,related_user_id) VALUES (?,?,?,?,?)",
                  (u["id"],"match","You matched","You both chose to connect. Private text messaging is now open.",user_id))
        c.execute("INSERT INTO notifications(user_id,notification_type,title,body,related_user_id) VALUES (?,?,?,?,?)",
                  (user_id,"match","You matched",f"You and {u['name']} both chose to connect. Private text messaging is now open.",u["id"]))
    c.commit()
    c.close()
    flash("You matched — private messaging is open." if mutual else "Connection saved.")
    return redirect(request.referrer or url_for("zodiac"))


@app.route("/likes")
def likes_you():
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    if not has_access(u,"zodiac"):
        return render_template("locked.html",area="See Everyone Who Likes You",plan_key="zodiac")
    c=conn()
    rows=c.execute("""SELECT users.* FROM likes JOIN users ON users.id=likes.liker_id
                      WHERE likes.liked_id=? AND users.suspended=0 ORDER BY likes.id DESC""",(u["id"],)).fetchall()
    c.close()
    return render_template("likes.html",members=rows)


@app.route("/video-call/request/<int:user_id>",methods=["POST"])
def video_call_request(user_id):
    u=current_user()
    if not u:
        return redirect(url_for("login"))
    if not is_match(u["id"],user_id):
        flash("Video calling opens after both members choose to connect.")
        return redirect(request.referrer or url_for("zodiac"))
    c=conn()
    other=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    if not other or other["allow_video_from"]=="nobody":
        c.close()
        flash("This member is not accepting video call requests.")
        return redirect(request.referrer or url_for("zodiac"))
    c.execute("INSERT INTO video_call_requests(requester_id,recipient_id) VALUES (?,?)",(u["id"],user_id))
    c.execute("INSERT INTO notifications(user_id,notification_type,title,body,related_user_id) VALUES (?,?,?,?,?)",
              (user_id,"video_call","Video call request",
               f"{u['name']} would like to video call. A live video provider must be connected before a room can open.",u["id"]))
    c.commit()
    c.close()
    flash("Video call request sent.")
    return redirect(request.referrer or url_for("zodiac_profile",user_id=user_id))


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
    if not u:
        return redirect(url_for("login"))
    if not is_match(u["id"],user_id):
        flash("Private messaging opens after you both choose to connect.")
        return redirect(url_for("zodiac_profile",user_id=user_id))
    c=conn()
    other=c.execute("SELECT * FROM users WHERE id=? AND suspended=0",(user_id,)).fetchone()
    if not other:
        c.close()
        return "Member not found",404
    if request.method=="POST":
        body=request.form.get("body","").strip()
        media_path=""
        media_type=""
        video=request.files.get("video_message")
        if video and has_access(u,"zodiac"):
            media_path=save_video(video,f"msg{u['id']}_{user_id}")
            media_type="video" if media_path else ""
        if body or media_path:
            c.execute("INSERT INTO messages(sender_id,recipient_id,body,media_path,media_type) VALUES (?,?,?,?,?)",
                      (u["id"],user_id,body,media_path,media_type))
            c.commit()
    thread=c.execute("""SELECT m.*,s.name sender_name FROM messages m JOIN users s ON s.id=m.sender_id
        WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?) ORDER BY m.id""",
        (u["id"],user_id,user_id,u["id"])).fetchall()
    c.close()
    return render_template("message_thread.html",other=other,thread=thread,premium=has_access(u,"zodiac"))


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
    u=current_user()
    q=request.args.get("q","").strip()
    category=request.args.get("category","").strip()
    c=conn()
    own=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone() if u else None
    sql="""SELECT b.*,u.name owner_name,
           CASE WHEN s.status IN ('active','trialing') OR u.complimentary_business=1 THEN 1 ELSE 0 END AS paid_business
           FROM businesses b JOIN users u ON u.id=b.owner_id
           LEFT JOIN subscriptions s ON s.user_id=b.owner_id AND s.membership_type='business'
           WHERE b.status='active' AND u.suspended=0
           AND u.email NOT LIKE '%@example.com' AND u.email NOT LIKE '%@business.demo'"""
    params=[]
    if q:
        sql+=" AND (b.business_name LIKE ? OR b.description LIKE ? OR b.city LIKE ? OR b.category LIKE ?)"
        params += [f"%{q}%"]*4
    if category:
        sql+=" AND b.category LIKE ?"
        params.append(f"%{category}%")
    sql+=" ORDER BY paid_business DESC,b.business_name"
    businesses=c.execute(sql,params).fetchall()
    c.close()
    return render_template("business.html",businesses=businesses,own=own,q=q,category=category,preview=False)


@app.route("/business/setup",methods=["GET","POST"])
def business_setup():
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    paid_access=has_access(u,"business")
    if request.method=="POST":
        name=request.form.get("business_name","").strip()
        if not name: flash("Business name is required."); c.close(); return redirect(url_for("business_setup"))
        logo=save_image(request.files.get("logo"),f"biz{u['id']}_logo") or (business["logo"] if business else "")
        hero=save_image(request.files.get("hero_image"),f"biz{u['id']}_hero") or (business["hero_image"] if business else "")
        basevals=[name,request.form.get("tagline","").strip(),request.form.get("description","").strip(),request.form.get("category","").strip(),request.form.get("city","").strip(),request.form.get("website","").strip(),request.form.get("contact_email","").strip(),request.form.get("phone","").strip(),logo,hero,request.form.get("accent","#b99ad6").strip(),request.form.get("instagram","").strip(),request.form.get("facebook","").strip(),request.form.get("affiliate_url","").strip(),request.form.get("booking_url","").strip()]
        provals=[request.form.get("business_type","business").strip(),request.form.get("creator_title","").strip(),request.form.get("tiktok","").strip(),request.form.get("youtube","").strip(),1 if request.form.get("media_kit_enabled") and paid_access else 0,request.form.get("content_categories","").strip(),request.form.get("audience_info","").strip(),request.form.get("featured_content","").strip(),request.form.get("previous_collaborations","").strip(),request.form.get("collaboration_interests","").strip(),request.form.get("social_followers","").strip(),request.form.get("social_likes","").strip(),request.form.get("social_views","").strip(),request.form.get("engagement_rate","").strip(),1 if request.form.get("show_natal_business") and paid_access else 0]
        if business:
            c.execute("""UPDATE businesses SET business_name=?,tagline=?,description=?,category=?,city=?,website=?,contact_email=?,phone=?,logo=?,hero_image=?,accent=?,instagram=?,facebook=?,affiliate_url=?,booking_url=?,business_type=?,creator_title=?,tiktok=?,youtube=?,media_kit_enabled=?,content_categories=?,audience_info=?,featured_content=?,previous_collaborations=?,collaboration_interests=?,social_followers=?,social_likes=?,social_views=?,engagement_rate=?,show_natal_business=?,status='active' WHERE owner_id=?""",(*basevals,*provals,u["id"])); slug=business["slug"]
        else:
            slug=slugify(name)
            c.execute("""INSERT INTO businesses(owner_id,slug,business_name,tagline,description,category,city,website,contact_email,phone,logo,hero_image,accent,instagram,facebook,affiliate_url,booking_url,business_type,creator_title,tiktok,youtube,media_kit_enabled,content_categories,audience_info,featured_content,previous_collaborations,collaboration_interests,social_followers,social_likes,social_views,engagement_rate,show_natal_business,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active')""",(u["id"],slug,*basevals,*provals))
        c.commit(); c.close()
        if paid_access:
            flash("Business profile saved. Your hosted app tools are open.")
            return redirect(url_for("business_items"))
        flash("Free business profile saved. Upgrade when you want the hosted Business App tools.")
        return redirect(url_for("business"))
    c.close(); return render_template("business_setup.html",business=business,paid_access=paid_access)


@app.route("/business/items",methods=["GET","POST"])
def business_items():
    u=current_user()
    if not u: return redirect(url_for("login"))
    if not has_access(u,"business"): return render_template("locked.html",area="Business Network",plan_key="business")
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    if not business: c.close(); return redirect(url_for("business_setup"))
    if request.method=="POST":
        section=request.form.get("section","offer")
        if section=="content":
            caption=request.form.get("caption","").strip(); upload=request.files.get("content_media"); path=""; mtype=""
            if upload and upload.filename:
                path=save_image(upload,f"bizcontent{business['id']}")
                mtype="image" if path else ""
                if not path:
                    path=save_video(upload,f"bizcontent{business['id']}")
                    mtype="video" if path else ""
            if caption or path:
                c.execute("INSERT INTO business_content(business_id,content_type,caption,media_path,media_type) VALUES (?,?,?,?,?)",(business["id"],request.form.get("content_type","update"),caption,path,mtype)); c.commit(); flash("Content published to your Business App.")
        else:
            title=request.form.get("title","").strip()
            if title:
                c.execute("INSERT INTO business_items(business_id,item_type,title,description,price,action_url) VALUES (?,?,?,?,?,?)",(business["id"],request.form.get("item_type","service"),title,request.form.get("description","").strip(),request.form.get("price","").strip(),request.form.get("action_url","").strip())); c.commit(); flash("Added to your hosted app.")
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall()
    content=c.execute("SELECT * FROM business_content WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall()
    requests=c.execute("SELECT * FROM business_collaboration_requests WHERE business_id=? ORDER BY id DESC LIMIT 50",(business["id"],)).fetchall()
    c.close()
    return render_template("business_items.html",business=business,items=items,content=content,collab_requests=requests)


@app.route("/business/item/<int:item_id>/delete",methods=["POST"])
def delete_business_item(item_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); c.execute("UPDATE business_items SET active=0 WHERE id=? AND business_id IN (SELECT id FROM businesses WHERE owner_id=?)",(item_id,u["id"])); c.commit(); c.close(); return redirect(url_for("business_items"))


@app.route("/business/content/<int:content_id>/delete",methods=["POST"])
def delete_business_content(content_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); c.execute("UPDATE business_content SET active=0 WHERE id=? AND business_id IN (SELECT id FROM businesses WHERE owner_id=?)",(content_id,u["id"])); c.commit(); c.close(); return redirect(url_for("business_items"))


@app.route("/business/my-app")
def my_business_app():
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); business=c.execute("SELECT * FROM businesses WHERE owner_id=?",(u["id"],)).fetchone()
    if not business: c.close(); return redirect(url_for("business_setup"))
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall()
    content=c.execute("SELECT * FROM business_content WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall()
    followers=c.execute("SELECT COUNT(*) FROM business_follows WHERE business_id=?",(business["id"],)).fetchone()[0]
    c.close()
    chart=get_birth_chart(u["id"]); balance={}
    if chart:
        try: balance=json.loads(chart["element_balance_json"] or "{}")
        except Exception: balance={}
    return render_template("business_app.html",business=business,items=items,content=content,owner_preview=True,paid=has_access(u,"business"),business_coord=None,premium_business_view=True,owner=u,owner_chart=chart,owner_balance=balance,followers=followers,is_following=False)

@app.route("/app/<slug>",methods=["GET","POST"])
def business_app(slug):
    u=current_user()
    c=conn()
    business=c.execute("""SELECT b.*,u.name owner_name FROM businesses b
       JOIN users u ON u.id=b.owner_id
       WHERE b.slug=? AND b.status='active' AND u.suspended=0""",(slug,)).fetchone()
    if not business:
        c.close(); return render_template("business_inactive.html"),404
    paid=membership_status(business["owner_id"],"business") in ("active","trialing")
    owner=c.execute("SELECT * FROM users WHERE id=?",(business["owner_id"],)).fetchone()
    if owner and owner["complimentary_business"]: paid=True
    c.execute("UPDATE businesses SET profile_views=COALESCE(profile_views,0)+1 WHERE id=?",(business["id"],)); c.commit()
    items=c.execute("SELECT * FROM business_items WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall() if paid else []
    content=c.execute("SELECT * FROM business_content WHERE business_id=? AND active=1 ORDER BY id DESC",(business["id"],)).fetchall() if paid else []
    followers=c.execute("SELECT COUNT(*) FROM business_follows WHERE business_id=?",(business["id"],)).fetchone()[0]
    is_following=bool(u and c.execute("SELECT 1 FROM business_follows WHERE business_id=? AND user_id=?",(business["id"],u["id"])).fetchone())
    if request.method=="POST" and request.form.get("collaboration_request"):
        rtype=request.form.get("request_type","").strip(); message=request.form.get("message","").strip(); rname=(u["name"] if u else request.form.get("requester_name","").strip()); remail=(u["email"] if u else request.form.get("requester_email","").strip())
        if rname and remail and rtype:
            c.execute("INSERT INTO business_collaboration_requests(business_id,requester_id,requester_name,requester_email,request_type,message) VALUES (?,?,?,?,?,?)",(business["id"],u["id"] if u else None,rname,remail,rtype,message)); c.commit(); flash("Collaboration request sent.")
        else: flash("Please include your name, email and collaboration type.")
    c.close()
    business_coord=coordination_categories(u,owner) if u and owner and get_birth_data(u["id"]) and get_birth_data(owner["id"]) else None
    chart=get_birth_chart(owner["id"]) if owner else None; balance={}
    if chart:
        try: balance=json.loads(chart["element_balance_json"] or "{}")
        except Exception: balance={}
    return render_template("business_app.html",business=business,items=items,content=content,paid=paid,owner=owner,
                           business_coord=business_coord,premium_business_view=bool(u and has_access(u,"business")),owner_chart=chart,owner_balance=balance,followers=followers,is_following=is_following)


@app.route("/business/<int:business_id>/follow",methods=["POST"])
def follow_business(business_id):
    u=current_user()
    if not u: return redirect(url_for("login"))
    c=conn(); existing=c.execute("SELECT id FROM business_follows WHERE business_id=? AND user_id=?",(business_id,u["id"])).fetchone()
    if existing: c.execute("DELETE FROM business_follows WHERE id=?",(existing["id"],))
    else: c.execute("INSERT OR IGNORE INTO business_follows(business_id,user_id) VALUES (?,?)",(business_id,u["id"]))
    c.commit(); b=c.execute("SELECT slug FROM businesses WHERE id=?",(business_id,)).fetchone(); c.close(); return redirect(url_for("business_app",slug=b["slug"]) if b else url_for("business"))


@app.route("/retreats")
def retreats(): return render_template("retreats.html")


@app.route("/admin")
def admin():
    u=current_user()
    if not u or not u["is_admin"]: return "Admin access required",403
    c=conn(); reports=c.execute("""SELECT r.*,a.name reporter_name,b.name reported_name FROM reports r JOIN users a ON a.id=r.reporter_id LEFT JOIN users b ON b.id=r.reported_user_id ORDER BY r.id DESC""").fetchall(); users=c.execute("SELECT * FROM users ORDER BY id DESC").fetchall(); subs=c.execute("SELECT s.*,u.name,u.email FROM subscriptions s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC").fetchall(); c.close(); return render_template("admin.html",reports=reports,users=users,subscriptions=subs)


@app.route("/admin/create-profile",methods=["POST"])
def admin_create_profile():
    admin_user=current_user()
    if not admin_user or not admin_user["is_admin"]: return "Admin access required",403
    name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
    role=request.form.get("role","free")
    if len(name)<2 or "@" not in email or len(password)<8:
        flash("Profile needs a name, valid email and password with at least 8 characters."); return redirect(url_for("admin"))
    cm=1 if role in ("full","galaxy") else 0; cb=1 if role in ("business","full","galaxy") else 0; creator=1 if role=="galaxy" else 0
    c=conn()
    try:
        c.execute("INSERT INTO users(name,email,password,plan,complimentary_member,complimentary_business,is_creator) VALUES (?,?,?,'free',?,?,?)",(name,email,hash_password(password),cm,cb,creator)); c.commit(); flash(f"{name} profile created. Complimentary access is ready where selected.")
    except sqlite3.IntegrityError: flash("That email already exists.")
    c.close(); return redirect(url_for("admin"))


@app.route("/admin/access/<int:user_id>",methods=["POST"])
def admin_access(user_id):
    admin_user=current_user()
    if not admin_user or not admin_user["is_admin"]: return "Admin access required",403
    c=conn(); c.execute("UPDATE users SET complimentary_member=?,complimentary_business=?,is_creator=?,is_admin=? WHERE id=?",(1 if request.form.get("complimentary_member") else 0,1 if request.form.get("complimentary_business") else 0,1 if request.form.get("is_creator") else 0,1 if request.form.get("is_admin") else 0,user_id)); c.commit(); c.close(); flash("Access updated."); return redirect(url_for("admin"))


@app.route("/admin/suspend/<int:user_id>",methods=["POST"])
def admin_suspend(user_id):
    u=current_user()
    if not u or not u["is_admin"]: return "Admin access required",403
    c=conn(); c.execute("UPDATE users SET suspended=CASE WHEN suspended=1 THEN 0 ELSE 1 END WHERE id=?",(user_id,)); c.commit(); c.close(); return redirect(url_for("admin"))


init_db()
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5055)