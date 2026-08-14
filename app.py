import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, request, redirect, url_for, session, flash, abort, render_template_string, send_from_directory
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-render")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PERSISTENT_DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.environ.get("DATABASE_PATH", str(DATA_DIR / "seasons_within.db"))
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOADS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "mov", "m4v"}

# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(conn, table, name, ddl):
    if name not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        dob TEXT,
        adult_confirmed INTEGER NOT NULL DEFAULT 0,
        city TEXT DEFAULT '', headline TEXT DEFAULT '', about TEXT DEFAULT '',
        birth_time TEXT DEFAULT '', birth_city TEXT DEFAULT '', birth_region TEXT DEFAULT '', birth_country TEXT DEFAULT '', exact_time INTEGER DEFAULT 0,
        is_admin INTEGER NOT NULL DEFAULT 0,
        is_host INTEGER NOT NULL DEFAULT 0,
        conscious_paid INTEGER NOT NULL DEFAULT 0,
        business_dev_paid INTEGER NOT NULL DEFAULT 0,
        profile_photo TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Reflections',
        shared_copy INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS community_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        post_type TEXT NOT NULL DEFAULT 'member',
        media_path TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        origin TEXT NOT NULL DEFAULT 'Community',
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(sender_id) REFERENCES users(id),
        FOREIGN KEY(recipient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        target_url TEXT DEFAULT '',
        read_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        owner_title TEXT DEFAULT '', category TEXT DEFAULT '', location TEXT DEFAULT '', tagline TEXT DEFAULT '',
        description TEXT DEFAULT '', story TEXT DEFAULT '', offers TEXT DEFAULT '', features TEXT DEFAULT '',
        logo_path TEXT DEFAULT '', cover_path TEXT DEFAULT '',
        website TEXT DEFAULT '', instagram TEXT DEFAULT '', tiktok TEXT DEFAULT '', youtube TEXT DEFAULT '', facebook TEXT DEFAULT '',
        booking_url TEXT DEFAULT '', store_url TEXT DEFAULT '', podcast_url TEXT DEFAULT '', affiliate_links TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 0,
        is_featured INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connection_profiles (
        user_id INTEGER PRIMARY KEY,
        coordination_types TEXT DEFAULT '', meet_preferences TEXT DEFAULT '', age_range TEXT DEFAULT '', location_preference TEXT DEFAULT '',
        occupation TEXT DEFAULT '', family TEXT DEFAULT '', lifestyle TEXT DEFAULT '', seeking TEXT DEFAULT '',
        overwhelmed TEXT DEFAULT '', regulate TEXT DEFAULT '', other_emotions TEXT DEFAULT '', conflict_style TEXT DEFAULT '', repair TEXT DEFAULT '',
        boundaries TEXT DEFAULT '', trust TEXT DEFAULT '', affection TEXT DEFAULT '', communication TEXT DEFAULT '', values_text TEXT DEFAULT '',
        business_style TEXT DEFAULT '', retreat_style TEXT DEFAULT '', about_me TEXT DEFAULT '', opted_in INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS business_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        version INTEGER NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS retreats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        retreat_type TEXT NOT NULL, season TEXT DEFAULT '', preferred_dates TEXT DEFAULT '', guests TEXT DEFAULT '', budget TEXT DEFAULT '',
        wellness TEXT DEFAULT '', lodging TEXT DEFAULT '', businesses TEXT DEFAULT '', meaning TEXT DEFAULT '', status TEXT DEFAULT 'Draft / Request Submitted',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    # Migrate older deployments safely.
    ensure_column(conn, 'users', 'is_host', "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, 'users', 'profile_photo', "TEXT DEFAULT ''")
    ensure_column(conn, 'community_posts', 'media_path', "TEXT DEFAULT ''")
    ensure_column(conn, 'notifications', 'target_url', "TEXT DEFAULT ''")
    ensure_column(conn, 'businesses', 'logo_path', "TEXT DEFAULT ''")
    ensure_column(conn, 'businesses', 'cover_path', "TEXT DEFAULT ''")
    ensure_column(conn, 'businesses', 'is_featured', "INTEGER NOT NULL DEFAULT 0")

    # Galaxy Eve is an explicitly authorized seeded featured business/host from the master contract.
    ge = conn.execute("SELECT * FROM users WHERE email=?", ("galaxyeve@seasonswithin.local",)).fetchone()
    if not ge:
        cur = conn.execute('''INSERT INTO users(name,email,password_hash,dob,adult_confirmed,is_host,conscious_paid,business_dev_paid,created_at)
                              VALUES(?,?,?,?,1,1,1,1,?)''',
                           ("Galaxy Eve", "galaxyeve@seasonswithin.local", generate_password_hash(uuid4().hex), "1990-01-01", now()))
        ge_id = cur.lastrowid
    else:
        ge_id = ge['id']
        conn.execute("UPDATE users SET is_host=1,conscious_paid=1,business_dev_paid=1 WHERE id=?", (ge_id,))
    gb = conn.execute("SELECT id FROM businesses WHERE lower(name)=lower('Galaxy Eve')").fetchone()
    if not gb:
        conn.execute('''INSERT INTO businesses(owner_id,name,owner_title,category,location,tagline,description,offers,features,active,is_featured,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,1,1,?,?)''',
                     (ge_id, "Galaxy Eve", "Conscious Coordinator • Content Creator", "Content Creator", "", "Content • Collaborations • Creator Experiences",
                      "Creator-led conscious coordination, content, collaborations and shared experiences.",
                      "Content,Collaborations,Creator Experiences,Events,Retreats", "Watch,Events,Retreats,Media Kit,Collaborations,Social Links,Contact", now(), now()))
    else:
        conn.execute("UPDATE businesses SET active=1,is_featured=1,owner_title=?,tagline=? WHERE id=?",
                     ("Conscious Coordinator • Content Creator", "Content • Collaborations • Creator Experiences", gb['id']))
    conn.commit(); conn.close()


@app.before_request
def ensure_db_ready():
    if not getattr(app, '_db_ready', False):
        init_db(); app._db_ready = True


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = db(); row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); conn.close(); return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please log in to open that member area.", "info")
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def safe(v):
    return str(escape(v or ''))


def initials(name):
    return ''.join(p[0] for p in (name or '?').split()[:2]).upper()


def notify(user_id, title, body='', target_url=''):
    conn = db(); conn.execute("INSERT INTO notifications(user_id,title,body,target_url,created_at) VALUES(?,?,?,?,?)", (user_id,title,body,target_url,now())); conn.commit(); conn.close()


def save_upload(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ''
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_UPLOADS:
        return ''
    stored = f"{prefix}_{uuid4().hex}.{ext}"
    file_storage.save(UPLOAD_DIR / stored)
    return stored


def media_html(path, alt='Media'):
    if not path:
        return ''
    url = url_for('uploaded_file', filename=path)
    ext = path.rsplit('.', 1)[-1].lower()
    if ext in {'mp4','mov','m4v'}:
        return f'<video controls style="width:100%;max-height:420px;border-radius:16px"><source src="{url}"></video>'
    return f'<img src="{url}" alt="{safe(alt)}" style="width:100%;max-height:420px;object-fit:cover;border-radius:16px">'

# -----------------------------------------------------------------------------
# Visual contract
# -----------------------------------------------------------------------------
BASE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{{ title }} — The Seasons Within</title>
<style>
:root{--plum:#34204f;--purple:#8f63ba;--purple2:#a978c7;--lav:#f2e9f8;--blush:#fff1ef;--line:#eadff1;--muted:#75677f;--gold:#ddc26f;--white:#fff;--shadow:0 14px 38px rgba(70,45,95,.09)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--plum);background:linear-gradient(180deg,#fcf9fd,#fffaf8 56%,#faf6fc);min-height:100vh}a{text-decoration:none;color:inherit}button,input,textarea,select{font:inherit}button{cursor:pointer}h1,h2,h3{font-family:Georgia,"Times New Roman",serif}h1{font-size:clamp(30px,5vw,48px);line-height:1.05;margin:8px 0 12px}h2{font-size:clamp(22px,3vw,30px);margin:6px 0 12px}.top{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.96);backdrop-filter:blur(18px);border-bottom:1px solid var(--line)}.topin{width:min(1220px,94vw);min-height:76px;margin:auto;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px}.brand{display:flex;align-items:center;gap:11px}.logo{width:49px;height:49px;border-radius:50%;padding:4px;background:#fff}.brand strong{display:block;font:700 19px Georgia}.brand small{display:block;font-size:9px;letter-spacing:1.25px;color:var(--muted);text-transform:uppercase;margin-top:3px}.desktopnav{display:flex;justify-content:center;gap:5px;flex-wrap:wrap}.desktopnav a,.acct a{color:#5e5068;padding:10px 12px;border-radius:999px;font-weight:800}.desktopnav a.on{background:var(--lav);color:#68418c}.acct{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800}.page{width:min(1120px,92vw);margin:26px auto 110px}.hero,.card{border:1px solid var(--line);border-radius:22px;background:#fff;box-shadow:var(--shadow)}.hero{padding:27px;background:linear-gradient(135deg,#f0e2fa,#fff1ed)}.card{padding:20px;margin:15px 0}.paid{border:2px solid var(--gold)}.badge,.chip{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;background:var(--lav);font-size:10px;font-weight:900}.badge.gold{background:#fff8df;border:1px solid var(--gold);color:#765615}.badge.heart{background:#fff0f3;color:#96526b}.actions,.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.btn,.out{display:inline-flex;align-items:center;justify-content:center;border-radius:11px;min-height:41px;padding:9px 14px;font-weight:800;border:1px solid var(--purple)}.btn{background:linear-gradient(135deg,var(--purple),var(--purple2));color:#fff}.out{background:#fff;color:#68418c;border-color:#cdb7dc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:15px}.two{display:grid;grid-template-columns:1fr 1fr;gap:15px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.media{height:220px;border-radius:16px;background:linear-gradient(135deg,#e4d2f0,#f8ded8);display:grid;place-items:center;overflow:hidden}.muted{color:var(--muted);line-height:1.55}.small{font-size:12px}.fact{padding:13px;border:1px solid var(--line);border-radius:14px;background:#fcf9fd;margin:7px 0}.fact small{display:block;color:var(--muted);margin-bottom:4px}.meter{height:10px;background:#eee6f1;border-radius:999px;overflow:hidden;margin:7px 0}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--purple),#c992c4)}.moonrow{display:grid;grid-template-columns:115px 1fr;gap:20px;align-items:center}.moonorb{width:98px;height:98px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,#fff,#d9c4e7 48%,#b795cb);font-size:48px}.post{display:grid;grid-template-columns:52px 1fr;gap:12px}.avatar{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#c89de1,#efbcc6);color:#fff;font-weight:900;overflow:hidden}.avatar img,.portrait img{width:100%;height:100%;object-fit:cover}.profilehero{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center}.portrait{width:118px;height:118px;border-radius:50%;background:linear-gradient(135deg,#d4b9e7,#f0c2cb);display:grid;place-items:center;color:#fff;font-weight:900;font-size:28px;overflow:hidden}.input{width:100%;padding:12px;border:1px solid #dfd1e8;border-radius:12px;background:#fff;margin:5px 0 12px}textarea.input{min-height:110px}.appcard{padding:0;overflow:hidden}.appcard .body{padding:18px}.topspace{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:24px 0 10px}.moregrid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.moreitem{display:block;padding:16px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow);font-weight:800}.moreitem.on{border:2px solid var(--purple);background:var(--lav)}.bottom{display:none}.flash{padding:12px 16px;border-radius:13px;background:#fff8df;border:1px solid var(--gold);margin:12px 0}.empty{padding:22px;text-align:center;border:1px dashed #cdb7dc;border-radius:18px;background:#fff}.steps{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.step{padding:7px 9px;border-radius:999px;background:#eee6f1;font-size:10px;font-weight:900}.step.on{background:var(--purple);color:#fff}.previewbar{position:fixed;right:16px;bottom:88px;z-index:40;background:#34204f;color:#fff;padding:8px 11px;border-radius:999px;font-size:10px;box-shadow:var(--shadow)}.searchrow{display:grid;grid-template-columns:1fr auto;gap:8px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.checkrow{display:flex;gap:8px;align-items:center;margin:8px 0 16px}.sectiontitle{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:24px}
@media(max-width:820px){body{padding-bottom:82px}.topin{min-height:68px;display:flex;justify-content:center}.desktopnav,.acct{display:none}.page{width:94vw;margin-top:18px;margin-bottom:22px}.two,.three{grid-template-columns:1fr}.profilehero{grid-template-columns:1fr}.portrait{width:96px;height:96px}.moonrow{grid-template-columns:82px 1fr}.moonorb{width:76px;height:76px;font-size:38px}.moregrid{grid-template-columns:1fr}.searchrow{grid-template-columns:1fr}.bottom{position:fixed;left:50%;bottom:9px;transform:translateX(-50%);z-index:50;width:95vw;display:grid;grid-template-columns:repeat(5,1fr);padding:7px;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.97);backdrop-filter:blur(18px);box-shadow:0 15px 45px rgba(70,45,95,.18)}.bottom a{padding:7px 4px;border-radius:13px;color:#75677f;font-size:9px;font-weight:900;text-align:center}.bottom a b{display:block;font-size:18px}.bottom a.on{background:var(--lav);color:#68418c}.previewbar{bottom:84px}}
</style></head><body>
<header class="top"><div class="topin"><a class="brand" href="{{url_for('home')}}"><svg class="logo" viewBox="0 0 100 100"><circle cx="50" cy="50" r="47" fill="#f4ebf9"/><path d="M50 6A44 44 0 0 1 94 50H50Z" fill="#d6b8e5"/><path d="M94 50A44 44 0 0 1 50 94V50Z" fill="#efc4cb"/><path d="M50 94A44 44 0 0 1 6 50H50Z" fill="#ead7ad"/><path d="M6 50A44 44 0 0 1 50 6V50Z" fill="#c9b7df"/><circle cx="50" cy="50" r="18" fill="#fff"/></svg><div><strong>The Seasons Within</strong><small>Conscious Coordination</small></div></a><nav class="desktopnav"><a class="{{'on' if active=='home'}}" href="{{url_for('home')}}">Home</a><a class="{{'on' if active=='community'}}" href="{{url_for('community')}}">Community</a><a class="{{'on' if active=='profile'}}" href="{{url_for('profile')}}">My Profile</a><a class="{{'on' if active=='business'}}" href="{{url_for('business_network')}}">Business Network</a><a class="{{'on' if active=='retreats'}}" href="{{url_for('retreats')}}">Retreats</a><a class="{{'on' if active=='membership'}}" href="{{url_for('membership')}}">Membership</a></nav><div class="acct">{% if user %}<a href="{{url_for('inbox')}}">Inbox</a><a href="{{url_for('notifications')}}">Notifications</a><span>{{user['name'].split()[0]}}</span>{% else %}<a href="{{url_for('login')}}">Login</a><a href="{{url_for('join')}}">Join Free</a>{% endif %}</div></div></header>
<main class="page">{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash">{{msg}}</div>{% endfor %}{% endwith %}{{content|safe}}</main>
<nav class="bottom"><a class="{{'on' if active=='home'}}" href="{{url_for('home')}}"><b>⌂</b>Home</a><a class="{{'on' if active=='community'}}" href="{{url_for('community')}}"><b>☼</b>Community</a><a class="{{'on' if active=='profile'}}" href="{{url_for('profile')}}"><b>◉</b>Profile</a><a class="{{'on' if active=='business'}}" href="{{url_for('business_network')}}"><b>◇</b>Business</a><a class="{{'on' if active=='more'}}" href="{{url_for('more')}}"><b>•••</b>More</a></nav><div class="previewbar">Functional build • persisted data</div></body></html>'''


def page(title, content, active=''):
    return render_template_string(BASE, title=title, content=content, active=active, user=current_user())


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# -----------------------------------------------------------------------------
# Accounts
# -----------------------------------------------------------------------------
@app.route('/join', methods=['GET','POST'])
def join():
    if request.method == 'POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); dob=request.form.get('dob',''); adult=1 if request.form.get('adult') else 0
        if not name or not email or len(password)<8 or not dob or not adult:
            flash('Name, email, birth date, 18+ confirmation, and a password of at least 8 characters are required.','error')
        else:
            conn=db()
            try:
                cur=conn.execute('INSERT INTO users(name,email,password_hash,dob,adult_confirmed,created_at) VALUES(?,?,?,?,?,?)',(name,email,generate_password_hash(password),dob,adult,now())); conn.commit(); session['user_id']=cur.lastrowid; conn.close(); return redirect(url_for('community'))
            except sqlite3.IntegrityError:
                conn.close(); flash('An account with that email already exists. Use Login or Forgot Password.','error')
    return page('Join Free','''<div class="hero"><span class="badge">JOIN FREE</span><h1>Create Your Seasons Within Account</h1><p class="muted">Community access is automatic. You can choose deeper features later.</p></div><form class="card" method="post"><label><b>Name</b></label><input class="input" name="name" required><label><b>Email</b></label><input class="input" type="email" name="email" required><label><b>Password</b></label><input class="input" type="password" name="password" minlength="8" required><label><b>Date of Birth</b></label><input class="input" type="date" name="dob" required><label class="checkrow"><input type="checkbox" name="adult" required> I confirm I am 18 or older</label><button class="btn">Create Free Account</button></form>''','home')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        conn=db(); u=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); conn.close()
        if u and check_password_hash(u['password_hash'],password):
            session['user_id']=u['id']; return redirect(request.args.get('next') or url_for('home'))
        flash('Email or password was not recognized.','error')
    return page('Login',f'''<div class="hero"><span class="badge">WELCOME BACK</span><h1>Login</h1></div><form class="card" method="post"><input class="input" type="email" name="email" placeholder="Email" required><input class="input" type="password" name="password" placeholder="Password" required><label class="checkrow"><input type="checkbox" name="remember"> Remember Me</label><button class="btn">Login</button><div class="actions"><a class="out" href="{url_for('forgot_password')}">Forgot Password</a><a class="out" href="{url_for('join')}">Create Free Account</a></div></form>''','home')


@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method=='POST':
        flash('Password recovery email delivery requires your production email provider. This screen will recover the existing account, not create a duplicate.','info')
    return page('Forgot Password','''<div class="hero"><h1>Recover Your Existing Account</h1></div><form class="card" method="post"><input class="input" type="email" name="email" placeholder="Email" required><button class="btn">Send Recovery Link</button></form>''','home')


@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('home'))

# -----------------------------------------------------------------------------
# Home / marketplace
# -----------------------------------------------------------------------------
def business_cards(rows):
    cards=[]
    for b in rows:
        featured=bool(b['is_featured']) or b['name'].lower()=='galaxy eve'
        media = media_html(b['logo_path'], b['name']) if b['logo_path'] else f'<div class="avatar" style="width:90px;height:90px">{initials(b["name"])}</div>'
        cards.append(f'''<article class="card appcard {'paid' if featured else ''}"><div class="media">{media}</div><div class="body"><span class="badge {'gold' if featured else ''}">{'★ FEATURED HOSTED APP' if featured else 'HOSTED APP'}</span><h2>{safe(b['name'])}</h2><p><b>{safe(b['owner_title'] or b['category'])}</b></p><p class="muted">{safe(b['category'])}{' • ' if b['category'] and b['location'] else ''}{safe(b['location'])}</p><p class="muted">{safe(b['tagline'])}</p><a class="btn" href="{url_for('business_app',business_id=b['id'])}">Open App</a></div></article>''')
    return ''.join(cards)


@app.route('/')
def home():
    q=request.args.get('q','').strip()
    conn=db()
    if q:
        like=f'%{q}%'; rows=conn.execute('''SELECT * FROM businesses WHERE active=1 AND (name LIKE ? OR owner_title LIKE ? OR category LIKE ? OR location LIKE ? OR tagline LIKE ? OR offers LIKE ?) ORDER BY is_featured DESC,name''',(like,like,like,like,like,like)).fetchall()
    else:
        rows=conn.execute('SELECT * FROM businesses WHERE active=1 ORDER BY is_featured DESC,name').fetchall()
    conn.close()
    cards=business_cards(rows) or '<div class="empty"><h3>Businesses will appear here as they join</h3><p class="muted">Published Hosted Business Apps are shown automatically.</p></div>'
    content=f'''<div class="hero"><span class="badge">THE SEASONS WITHIN</span><h1>Discover Wellness Within the Community</h1><p class="muted">A mobile-first wellness marketplace and member community for businesses, retreats, conscious connection, reflection and shared experiences.</p><div class="actions"><a class="btn" href="{url_for('business_network')}">Explore Businesses & Apps</a><a class="out" href="{url_for('retreats')}">Explore Retreats</a><a class="out" href="{url_for('join')}">Join Free</a><a class="out" href="{url_for('login')}">Login</a></div></div>
    <form class="card searchrow" method="get"><input class="input" style="margin:0" name="q" value="{safe(q)}" placeholder="Search businesses, services, classes, creators or wellness experiences..."><button class="btn">Search</button></form>
    <div class="chips"><span class="chip">Wellness</span><span class="chip">Creators</span><span class="chip">Classes</span><span class="chip">Retreats</span><span class="chip">Services</span><span class="chip">Events</span></div>
    <div class="topspace"><div><span class="badge gold">HOSTED BUSINESS APPS</span><h2>Community Businesses</h2></div></div><div class="grid">{cards}</div>
    <article class="card moonrow"><div class="moonorb">☾</div><div><span class="badge">MOON TODAY</span><h2>Current-sky reflection</h2><p class="muted"><b>Reflection, not prediction.</b> Live planetary positions are displayed only when an ephemeris provider is connected.</p><div class="chips"><span class="chip">Mercury</span><span class="chip">Venus</span><span class="chip">Mars</span><span class="chip">Jupiter</span><span class="chip">Saturn</span></div></div></article>
    <div class="grid"><article class="card"><span class="badge">RETREATS</span><h2>Design Your Own Retreat</h2><a class="btn" href="{url_for('retreat_builder')}">Build My Retreat</a></article><article class="card paid"><span class="badge gold">BUSINESS DEVELOPMENT</span><h2>$79.99 Business Plan Package</h2><p class="muted">Professional questionnaire + editable plan + Marketing Strategy + 90-Day Launch Plan.</p><a class="btn" href="{url_for('startup')}">Start My Business Plan</a></article></div>'''
    return page('Home',content,'home')

# -----------------------------------------------------------------------------
# Community
# -----------------------------------------------------------------------------
@app.route('/community', methods=['GET','POST'])
@login_required
def community():
    u=current_user()
    if request.method=='POST':
        body=request.form.get('body','').strip(); media=save_upload(request.files.get('media'),'community')
        post_as='member'
        if u['is_admin'] and request.form.get('post_as')=='official': post_as='official'
        if u['is_host'] and request.form.get('post_as')=='host': post_as='host'
        if body or media:
            conn=db(); conn.execute('INSERT INTO community_posts(user_id,body,post_type,media_path,created_at) VALUES(?,?,?,?,?)',(u['id'],body,post_as,media,now()));
            if post_as in ('official','host'):
                users=conn.execute('SELECT id FROM users WHERE id<>?',(u['id'],)).fetchall(); title='The Seasons Within Posted — Daily Reflection' if post_as=='official' else 'Galaxy Eve Posted — New Creator Experience'
                for x in users: conn.execute('INSERT INTO notifications(user_id,title,body,target_url,created_at) VALUES(?,?,?,?,?)',(x['id'],title,body[:180],url_for('community'),now()))
            conn.commit(); conn.close(); return redirect(url_for('community'))
    conn=db(); posts=conn.execute('SELECT p.*,u.name,u.profile_photo FROM community_posts p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 100').fetchall(); conn.close()
    out=[]
    for p in posts:
        avatar=f'<img src="{url_for("uploaded_file",filename=p["profile_photo"])}">' if p['profile_photo'] else initials(p['name'])
        badge='';
        if p['post_type']=='official': badge='<span class="badge">THE SEASONS WITHIN</span>'
        elif p['post_type']=='host': badge='<span class="badge gold">GALAXY EVE</span>'
        msg='' if p['user_id']==u['id'] else f'<a class="out" href="{url_for("message_member",recipient_id=p["user_id"],origin="Community")}">Message {safe(p["name"])}</a>'
        out.append(f'''<article class="card"><div class="post"><div class="avatar">{avatar}</div><div>{badge}<h3 style="margin:4px 0">{safe(p['name'])}</h3><p class="muted small">{safe(p['created_at'])}</p><p>{safe(p['body'])}</p>{media_html(p['media_path'],p['name'])}<div class="actions">{msg}</div></div></div></article>''')
    posts_html=''.join(out) or '<div class="empty"><h3>Community posts will appear here</h3><p class="muted">Start a real reflection. There are no fake member posts.</p></div>'
    post_as=''
    if u['is_admin']: post_as='<label><b>Post identity</b></label><select class="input" name="post_as"><option value="member">My Member Profile</option><option value="official">The Seasons Within</option></select>'
    elif u['is_host']: post_as='<label><b>Post identity</b></label><select class="input" name="post_as"><option value="member">My Member Profile</option><option value="host">Galaxy Eve</option></select>'
    content=f'''<div class="hero"><span class="badge">MEMBERS ONLY</span><h1>Community</h1><p class="muted">The daily heart of The Seasons Within: astrology, reflection, wellness and real member posts. Replies are private.</p></div><article class="card moonrow"><div class="moonorb">☾</div><div><span class="badge">DAILY SEASONS WITHIN</span><h2>Current Sky</h2><p class="muted">Live Moon/planet positions are shown only when a provider is connected.</p></div></article><div class="grid"><article class="card"><span class="badge">RELAXATION</span><h3>60-Second Reset</h3><p class="muted">Unclench your jaw. Lower your shoulders. Take three slow breaths and notice what can wait.</p></article><article class="card"><span class="badge">JOURNAL PROMPT</span><h3>What are you carrying today that does not need immediate action?</h3><a class="out" href="{url_for('journal')}">Open My Journal</a></article></div><form class="card" method="post" enctype="multipart/form-data">{post_as}<textarea class="input" name="body" placeholder="Share with the community..."></textarea><label><b>Add Photo or Video</b></label><input class="input" type="file" name="media" accept="image/*,video/*"><button class="btn">Post to Community</button></form>{posts_html}'''
    return page('Community',content,'community')

# -----------------------------------------------------------------------------
# Profile
# -----------------------------------------------------------------------------
def profile_picture_html(u, cls='portrait'):
    if u['profile_photo']:
        return f'<div class="{cls}"><img src="{url_for("uploaded_file",filename=u["profile_photo"])}" alt="Profile photo"></div>'
    return f'<div class="{cls}">{initials(u["name"])}</div>'


@app.route('/profile')
@login_required
def profile():
    u=current_user()
    about = f'<article class="card"><h2>About</h2><p>{safe(u["about"])}</p></article>' if u['about'] else ''
    content=f'''<article class="card"><div class="profilehero"><div><span class="badge {'gold' if u['conscious_paid'] else ''}">{'★ FULL MEMBER / CONSCIOUS COORDINATION' if u['conscious_paid'] else 'FREE MEMBER'}</span><h1>{safe(u['name'])}</h1><p class="muted">{safe(u['city'] or 'Add your city')}{' • ' if u['headline'] else ''}{safe(u['headline'])}</p><div class="actions"><a class="btn" href="{url_for('profile_edit')}">Edit My Profile</a></div></div>{profile_picture_html(u)}</div></article>{about}<div class="grid"><a class="moreitem" href="{url_for('community')}">Community<br><small>Posts + daily reflection</small></a><a class="moreitem" href="{url_for('journal')}">My Private Journal</a><a class="moreitem" href="{url_for('inbox')}">Journal Inbox</a><a class="moreitem" href="{url_for('notifications')}">Notifications</a><a class="moreitem" href="{url_for('connections')}">♡ Conscious Coordination</a><a class="moreitem" href="{url_for('business_dashboard')}">My Business Dashboard</a></div><article class="card"><h2>Member Astrology</h2><p class="muted">Sun • Moon • Mercury • Venus • Mars • Jupiter • Saturn. Rising/houses display only after accurate chart calculation using reliable birth data; they are never guessed.</p></article>'''
    return page('My Profile',content,'profile')


@app.route('/profile/edit', methods=['GET','POST'])
@login_required
def profile_edit():
    u=current_user()
    if request.method=='POST':
        photo=save_upload(request.files.get('profile_photo'),'profile') or u['profile_photo']
        vals=[request.form.get(x,'').strip() for x in ['name','city','headline','about','birth_time','birth_city','birth_region','birth_country']]
        exact=1 if request.form.get('exact_time') else 0
        conn=db(); conn.execute('UPDATE users SET name=?,city=?,headline=?,about=?,birth_time=?,birth_city=?,birth_region=?,birth_country=?,exact_time=?,profile_photo=? WHERE id=?',(*vals,exact,photo,u['id'])); conn.commit(); conn.close(); flash('Profile saved.','success'); return redirect(url_for('profile'))
    content=f'''<div class="hero"><span class="badge">PROFILE EDITING</span><h1>Edit My Profile</h1><p class="muted">Saving returns you to your visible profile and persists after logout/login.</p></div><form class="card" method="post" enctype="multipart/form-data"><label><b>Profile Photo</b></label><input class="input" type="file" name="profile_photo" accept="image/*"><label><b>Name</b></label><input class="input" name="name" value="{safe(u['name'])}" required><label><b>City</b></label><input class="input" name="city" value="{safe(u['city'])}"><label><b>Headline</b></label><input class="input" name="headline" value="{safe(u['headline'])}"><label><b>About</b></label><textarea class="input" name="about">{safe(u['about'])}</textarea><h2>Birth Information</h2><p class="muted">Latitude, longitude, UTC offset and Birth Chart Visibility are not exposed. Rising signs/houses are never guessed.</p><label><b>Birth Date</b></label><input class="input" type="date" value="{safe(u['dob'])}" disabled><label><b>Birth Time</b></label><input class="input" type="time" name="birth_time" value="{safe(u['birth_time'])}"><label class="checkrow"><input type="checkbox" name="exact_time" {'checked' if u['exact_time'] else ''}> Exact time is known</label><label><b>Birth City</b></label><input class="input" name="birth_city" value="{safe(u['birth_city'])}"><label><b>State/Province</b></label><input class="input" name="birth_region" value="{safe(u['birth_region'])}"><label><b>Country</b></label><input class="input" name="birth_country" value="{safe(u['birth_country'])}"><button class="btn">Save Profile</button> <a class="out" href="{url_for('profile')}">Cancel</a></form>'''
    return page('Edit Profile',content,'profile')

# -----------------------------------------------------------------------------
# Journal private command center
# -----------------------------------------------------------------------------
JOURNAL_SECTIONS=['Reflections','Journal Inbox','Business','Retreats','Conscious Coordination','Saved Items']


def journal_nav(section):
    links=[]
    for name in JOURNAL_SECTIONS:
        href=url_for('inbox') if name=='Journal Inbox' else url_for('journal',section=name)
        links.append(f'<a class="moreitem {"on" if section==name else ""}" href="{href}">{name}</a>')
    return '<div class="grid">'+''.join(links)+'</div>'


def journal_entry_card(e):
    share='Private original • Community copy shared' if e['shared_copy'] else 'Private Journal only'
    return f'''<article class="card"><span class="badge">PRIVATE</span><span class="badge">{safe(e['category']).upper()}</span><h3>{safe(e['title'])}</h3><p>{safe(e['body'])}</p><p class="muted small">{share} • {safe(e['updated_at'])}</p><div class="actions"><a class="out" href="{url_for('journal_edit',entry_id=e['id'])}">Edit Entry</a></div></article>'''


@app.route('/journal', methods=['GET','POST'])
@login_required
def journal():
    u=current_user(); section=request.args.get('section','Reflections')
    if section not in JOURNAL_SECTIONS: section='Reflections'
    if request.method=='POST':
        title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); category=request.form.get('category','Reflections'); shared=request.form.get('visibility')=='community'
        if title and body:
            conn=db(); conn.execute('INSERT INTO journal_entries(user_id,title,body,category,shared_copy,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(u['id'],title,body,category,1 if shared else 0,now(),now()))
            if shared: conn.execute('INSERT INTO community_posts(user_id,body,post_type,created_at) VALUES(?,?,?,?)',(u['id'],body,'member',now()))
            conn.commit(); conn.close(); flash('Journal entry saved.' + (' A separate Community copy was created.' if shared else ''),'success'); return redirect(url_for('journal',section=category))
    conn=db()
    q=request.args.get('q','').strip()
    if section in ('Reflections','Saved Items'):
        if q:
            rows=conn.execute('SELECT * FROM journal_entries WHERE user_id=? AND category=? AND (title LIKE ? OR body LIKE ?) ORDER BY id DESC',(u['id'],section,f'%{q}%',f'%{q}%')).fetchall()
        else:
            rows=conn.execute('SELECT * FROM journal_entries WHERE user_id=? AND category=? ORDER BY id DESC',(u['id'],section)).fetchall()
        body_html=''.join(journal_entry_card(e) for e in rows) or f'<div class="empty"><h3>No {safe(section)} saved yet</h3></div>'
    elif section=='Business':
        plans=conn.execute('SELECT id,version,created_at FROM business_plans WHERE user_id=? ORDER BY version DESC',(u['id'],)).fetchall(); notes=conn.execute("SELECT * FROM journal_entries WHERE user_id=? AND category='Business' ORDER BY id DESC",(u['id'],)).fetchall()
        plans_html=''.join(f'<article class="card paid"><span class="badge gold">BUSINESS PLAN</span><h3>Version {p["version"]}</h3><p class="muted">Saved {safe(p["created_at"])}</p><div class="actions"><a class="out" href="{url_for("business_plan")}">Open Plan</a><a class="out" href="{url_for("marketing")}">Marketing Strategy</a><a class="out" href="{url_for("launch_plan")}">90-Day Launch Plan</a></div></article>' for p in plans)
        body_html=(plans_html or '<div class="empty"><h3>No Business Plan yet</h3></div>')+''.join(journal_entry_card(e) for e in notes)
    elif section=='Retreats':
        retreats_rows=conn.execute('SELECT * FROM retreats WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); notes=conn.execute("SELECT * FROM journal_entries WHERE user_id=? AND category='Retreats' ORDER BY id DESC",(u['id'],)).fetchall()
        body_html=''.join(f'''<article class="card"><span class="badge">RETREAT</span><h3>{safe(r['retreat_type'])}</h3><p class="muted">{safe(r['season'])} • {safe(r['preferred_dates'])} • Guests: {safe(r['guests'])}</p><p><b>Budget:</b> {safe(r['budget'])}<br><b>Wellness:</b> {safe(r['wellness'])}<br><b>Lodging:</b> {safe(r['lodging'])}<br><b>Participating / desired businesses:</b> {safe(r['businesses'])}</p></article>''' for r in retreats_rows)+''.join(journal_entry_card(e) for e in notes)
        if not body_html: body_html='<div class="empty"><h3>No Retreat drafts or planning notes yet</h3></div>'
    elif section=='Conscious Coordination':
        notes=conn.execute("SELECT * FROM journal_entries WHERE user_id=? AND category='Conscious Coordination' ORDER BY id DESC",(u['id'],)).fetchall(); body_html=''.join(journal_entry_card(e) for e in notes) or '<div class="empty"><h3>No saved coordination notes or connection ideas yet</h3></div>'
    else: body_html=''
    conn.close()
    new_form=''
    if section!='Journal Inbox':
        new_form=f'''<form class="card" method="post"><h2>New Journal Entry</h2><input class="input" name="title" placeholder="Entry title" required><input type="hidden" name="category" value="{safe(section)}"><textarea class="input" name="body" placeholder="Write your reflection, note, plan or saved idea..." required></textarea><label><b>Visibility</b></label><select class="input" name="visibility"><option value="private">Keep Private</option><option value="community">Share a Copy to Community</option></select><button class="btn">Save Entry</button></form>'''
    search='' if section not in ('Reflections','Saved Items') else f'''<form class="card searchrow" method="get"><input type="hidden" name="section" value="{safe(section)}"><input class="input" style="margin:0" name="q" value="{safe(q)}" placeholder="Search {safe(section)}..."><button class="out">Search</button></form>'''
    content=f'''<div class="hero"><span class="badge">MY JOURNAL</span><h1>Private Command Center</h1><p class="muted">Private by default. Your Journal organizes reflections, private messages, business work, Retreat planning, Conscious Coordination notes and saved items.</p></div>{journal_nav(section)}<div class="sectiontitle"><h2>{safe(section)}</h2></div>{search}{new_form}<div id="entries">{body_html}</div>'''
    return page('My Journal',content,'more')


@app.route('/journal/entry/<int:entry_id>/edit', methods=['GET','POST'])
@login_required
def journal_edit(entry_id):
    u=current_user(); conn=db(); e=conn.execute('SELECT * FROM journal_entries WHERE id=? AND user_id=?',(entry_id,u['id'])).fetchone(); conn.close()
    if not e: abort(404)
    if request.method=='POST':
        title=request.form.get('title','').strip(); body=request.form.get('body','').strip()
        if title and body:
            conn=db(); conn.execute('UPDATE journal_entries SET title=?,body=?,updated_at=? WHERE id=? AND user_id=?',(title,body,now(),entry_id,u['id'])); conn.commit(); conn.close(); return redirect(url_for('journal',section=e['category']))
    return page('Edit Journal Entry',f'''<div class="hero"><span class="badge">PRIVATE JOURNAL</span><h1>Edit Entry</h1></div><form class="card" method="post"><input class="input" name="title" value="{safe(e['title'])}" required><textarea class="input" name="body" required>{safe(e['body'])}</textarea><button class="btn">Save Changes</button> <a class="out" href="{url_for('journal',section=e['category'])}">Cancel</a></form>''','more')

# -----------------------------------------------------------------------------
# Inbox / Notifications
# -----------------------------------------------------------------------------
@app.route('/inbox')
@login_required
def inbox():
    u=current_user(); conn=db(); msgs=conn.execute('''SELECT m.*,s.name sender_name,r.name recipient_name FROM messages m JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.recipient_id WHERE m.sender_id=? OR m.recipient_id=? ORDER BY m.id DESC''',(u['id'],u['id'])).fetchall(); conn.close()
    cards=[]
    for m in msgs:
        reply_to=m['sender_id'] if m['recipient_id']==u['id'] else m['recipient_id']
        cards.append(f'''<article class="card"><span class="badge">{safe(m['origin']).upper()}</span><h3>{safe(m['subject'])}</h3><p class="muted small">From {safe(m['sender_name'])} to {safe(m['recipient_name'])} • {safe(m['created_at'])}</p><p>{safe(m['body'])}</p><a class="out" href="{url_for('message_member',recipient_id=reply_to,origin=m['origin'])}">Reply Privately</a></article>''')
    html=''.join(cards) or '<div class="empty"><h3>No private conversations yet</h3><p class="muted">Community, Conscious Coordination, Business and Retreat conversations will appear here.</p></div>'
    return page('Journal Inbox',f'''<div class="hero"><span class="badge">PRIVATE MESSAGES</span><h1>Journal Inbox</h1><p class="muted">All private conversations live here. Notifications are alerts; Inbox is conversation.</p></div>{journal_nav('Journal Inbox')}{html}''','more')


@app.route('/message/<int:recipient_id>', methods=['GET','POST'])
@login_required
def message_member(recipient_id):
    u=current_user(); conn=db(); recipient=conn.execute('SELECT * FROM users WHERE id=?',(recipient_id,)).fetchone(); conn.close()
    if not recipient: abort(404)
    origin=request.args.get('origin','Community')
    if request.method=='POST':
        body=request.form.get('body','').strip(); origin=request.form.get('origin','Community')
        # Title identifies the origin and the person whose post/profile generated the thread.
        if origin=='Community': subject=f'Community Message from {recipient["name"]}'
        elif origin=='Conscious Coordination': subject=f'Conscious Coordination Message from {recipient["name"]}'
        elif origin=='Business': subject=request.form.get('subject','').strip() or f'Business Inquiry — {recipient["name"]}'
        elif origin=='Retreat': subject=request.form.get('subject','').strip() or f'Retreat Message — {recipient["name"]}'
        else: subject=request.form.get('subject','').strip() or f'{origin} Message from {recipient["name"]}'
        if body:
            conn=db(); conn.execute('INSERT INTO messages(sender_id,recipient_id,origin,subject,body,created_at) VALUES(?,?,?,?,?,?)',(u['id'],recipient_id,origin,subject,body,now())); conn.commit(); conn.close(); notify(recipient_id,'New Private Message',subject,url_for('inbox')); flash('Private message sent to Journal Inbox.','success'); return redirect(url_for('inbox'))
    default_subject = f'{origin} Message from {recipient["name"]}'
    return page('Private Message',f'''<div class="hero"><span class="badge">PRIVATE MESSAGE</span><h1>Message {safe(recipient['name'])}</h1><p class="muted">This conversation is private and saved in Journal Inbox.</p></div><form class="card" method="post"><input type="hidden" name="origin" value="{safe(origin)}"><label><b>Conversation</b></label><input class="input" value="{safe(default_subject)}" disabled><textarea class="input" name="body" placeholder="Write your private message..." required></textarea><button class="btn">Send Private Message</button></form>''','more')


@app.route('/notifications')
@login_required
def notifications():
    u=current_user(); conn=db(); rows=conn.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); conn.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(now(),u['id'])); conn.commit(); conn.close()
    html=''.join(f'''<article class="card"><h3>{safe(n['title'])}</h3><p class="muted">{safe(n['body'])}</p><p class="small muted">{safe(n['created_at'])}</p>{f'<a class="out" href="{safe(n["target_url"])}">Open</a>' if n['target_url'] else ''}</article>''' for n in rows) or '<div class="empty"><h3>No notifications yet</h3><p class="muted">Galaxy Eve Posted, The Seasons Within Posted, New Private Message, Compatibility Update, Business Inquiry, Retreat Update and Business Plan Ready alerts appear here.</p></div>'
    return page('Notifications',f'<div class="hero"><span class="badge">PRIVATE ALERTS</span><h1>Notifications</h1><p class="muted">Notifications are alerts. Journal Inbox is conversation.</p></div>{html}','more')

# -----------------------------------------------------------------------------
# Conscious Coordination
# -----------------------------------------------------------------------------
@app.route('/conscious-coordination')
@login_required
def connections():
    u=current_user(); conn=db(); own=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],)).fetchone(); members=conn.execute('''SELECT cp.*,u.name,u.city,u.conscious_paid,u.profile_photo FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.opted_in=1 AND cp.user_id<>? ORDER BY u.name''',(u['id'],)).fetchall(); conn.close()
    cards=[]
    for m in members:
        pic=f'<img src="{url_for("uploaded_file",filename=m["profile_photo"])}">' if m['profile_photo'] else initials(m['name'])
        cards.append(f'''<article class="card {'paid' if m['conscious_paid'] else ''}"><div class="avatar">{pic}</div><span class="badge {'gold' if m['conscious_paid'] else ''}">{'★ FULL MEMBER' if m['conscious_paid'] else 'BASIC PROFILE'}</span><h3>{safe(m['name'])}</h3><p class="muted">{safe(m['city'] or 'Location not shared')} • {safe(m['coordination_types'] or 'Coordination type not set')}</p><a class="btn" href="{url_for('connection_profile',user_id=m['user_id'])}">View Profile</a></article>''')
    directory=''.join(cards) or '<div class="empty"><h3>Participating members will appear here</h3><p class="muted">The directory does not invent profiles.</p></div>'
    content=f'''<div class="hero"><span class="badge heart">♡ PARTICIPATING MEMBERS ONLY</span><h1>Conscious Coordination</h1><p class="muted">Love/Dating • Friendship • Business/Collaboration • Retreat/Activity Connections.</p><a class="btn" href="{url_for('connection_edit')}">{'Edit' if own else 'Create'} My Coordination Profile</a></div><article class="card paid"><span class="badge gold">HOST</span><h2>Galaxy Eve</h2><p class="muted">Creator prompts, videos, experiences, Retreat invitations and host content.</p></article><div class="topspace"><h2>Discover Participating Members</h2></div><div class="grid">{directory}</div>'''
    return page('Conscious Coordination',content,'more')


@app.route('/conscious-coordination/edit', methods=['GET','POST'])
@login_required
def connection_edit():
    u=current_user(); conn=db(); cp=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],)).fetchone(); conn.close()
    keys=['coordination_types','meet_preferences','age_range','location_preference','occupation','family','lifestyle','seeking','overwhelmed','regulate','other_emotions','conflict_style','repair','boundaries','trust','affection','communication','values_text','business_style','retreat_style','about_me']
    if request.method=='POST':
        vals=[request.form.get(k,'').strip() for k in keys]
        conn=db(); conn.execute('''INSERT INTO connection_profiles(user_id,coordination_types,meet_preferences,age_range,location_preference,occupation,family,lifestyle,seeking,overwhelmed,regulate,other_emotions,conflict_style,repair,boundaries,trust,affection,communication,values_text,business_style,retreat_style,about_me,opted_in,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET coordination_types=excluded.coordination_types,meet_preferences=excluded.meet_preferences,age_range=excluded.age_range,location_preference=excluded.location_preference,occupation=excluded.occupation,family=excluded.family,lifestyle=excluded.lifestyle,seeking=excluded.seeking,overwhelmed=excluded.overwhelmed,regulate=excluded.regulate,other_emotions=excluded.other_emotions,conflict_style=excluded.conflict_style,repair=excluded.repair,boundaries=excluded.boundaries,trust=excluded.trust,affection=excluded.affection,communication=excluded.communication,values_text=excluded.values_text,business_style=excluded.business_style,retreat_style=excluded.retreat_style,about_me=excluded.about_me,opted_in=1,updated_at=excluded.updated_at''',(u['id'],*vals,now())); conn.commit(); conn.close(); return redirect(url_for('connections'))
    def val(k): return safe(cp[k] if cp and cp[k] else '')
    fields=[('coordination_types','Coordination Types','Love/Dating, Friendship, Business/Collaboration, Retreat/Activity Connections'),('meet_preferences','Who would you like to meet?',''),('age_range','Age range',''),('location_preference','Location preference',''),('occupation','Occupation',''),('family','Children / family',''),('lifestyle','Lifestyle',''),('seeking','What are you seeking?',''),('overwhelmed','When overwhelmed, what happens?',''),('regulate','What helps you regulate?',''),('other_emotions','How do you handle another person’s emotions?',''),('conflict_style','Conflict style',''),('repair','Repair & accountability',''),('boundaries','Boundaries',''),('trust','Trust',''),('affection','Love languages / affection',''),('communication','Communication intelligence',''),('values_text','Lifestyle & values',''),('business_style','Business partner style',''),('retreat_style','Retreat coordination preferences',''),('about_me','About me','')]
    inputs=''.join(f'<label><b>{label}</b></label><textarea class="input" name="{name}" placeholder="{ph}">{val(name)}</textarea>' for name,label,ph in fields)
    return page('Coordination Profile',f'''<div class="hero"><span class="badge heart">♡ COORDINATION PROFILE</span><h1>Create / Edit Conscious Coordination Profile</h1><p class="muted">Results are based on self-reported behavior. They are not a mental-health diagnosis or a prediction that a relationship will or will not succeed.</p></div><form class="card" method="post">{inputs}<p class="muted">Free profile: one photo/basic preview. $10.99 Full: up to 7 photos + 2 videos, deeper compatibility and eligible video tools.</p><button class="btn">Save Profile</button></form>''','more')


@app.route('/conscious-coordination/profile/<int:user_id>')
@login_required
def connection_profile(user_id):
    u=current_user(); conn=db(); m=conn.execute('''SELECT cp.*,u.name,u.city,u.conscious_paid FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.user_id=?''',(user_id,)).fetchone(); conn.close()
    if not m: abort(404)
    return page('Coordination Profile',f'''<article class="card {'paid' if m['conscious_paid'] else ''}"><span class="badge {'gold' if m['conscious_paid'] else ''}">{'★ $10.99 FULL CONSCIOUS COORDINATION PROFILE' if m['conscious_paid'] else 'BASIC CONSCIOUS COORDINATION PROFILE'}</span><h1>{safe(m['name'])}</h1><p class="muted">{safe(m['city'])} • {safe(m['coordination_types'])}</p><div class="actions"><a class="btn" href="{url_for('message_member',recipient_id=user_id,origin='Conscious Coordination')}">Message Privately</a><a class="out" href="{url_for('compatibility',user_id=user_id)}">Compatibility</a><a class="out" href="{url_for('birth_chart',user_id=user_id)}">Birth Chart</a><a class="out" href="{url_for('connection_ideas',user_id=user_id)}">Connection Ideas</a><a class="out" href="{url_for('video',user_id=user_id)}">Video</a></div></article><div class="grid"><article class="card"><h2>Communication & Emotions</h2><p>{safe(m['communication'])}</p><p>{safe(m['overwhelmed'])}</p><p>{safe(m['regulate'])}</p></article><article class="card"><h2>Conflict, Repair & Boundaries</h2><p>{safe(m['conflict_style'])}</p><p>{safe(m['repair'])}</p><p>{safe(m['boundaries'])}</p></article><article class="card"><h2>Affection, Lifestyle & Values</h2><p>{safe(m['affection'])}</p><p>{safe(m['values_text'])}</p></article></div>''','more')


def compatibility_score(a,b):
    if not a or not b: return 0
    vals=[]
    for k in ['communication','conflict_style','repair','boundaries','affection','values_text','lifestyle']:
        x=set((a[k] or '').lower().replace(',',' ').split()); y=set((b[k] or '').lower().replace(',',' ').split())
        if x or y: vals.append(int(100*len(x&y)/max(1,len(x|y))))
    return round(sum(vals)/len(vals)) if vals else 0


@app.route('/compatibility/<int:user_id>')
@login_required
def compatibility(user_id):
    u=current_user(); conn=db(); a=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],)).fetchone(); b=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(user_id,)).fetchone(); other=conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not other or not b: abort(404)
    score=compatibility_score(a,b)
    return page('Compatibility',f'''<div class="hero paid"><span class="badge gold">★ COMPATIBILITY</span><h1>Conscious Coordination Report</h1><p class="muted">Based on actual self-reported profiles + a separate astrology layer when chart calculations are available.</p></div><div class="grid"><article class="card"><h3>Overall Coordination — {score}%</h3><div class="meter"><i style="width:{score}%"></i></div></article><article class="card"><h3>Communication</h3><p>{safe(b['communication'])}</p></article><article class="card"><h3>Conflict / Repair</h3><p>{safe(b['conflict_style'])} • {safe(b['repair'])}</p></article><article class="card"><h3>Lifestyle & Values</h3><p>{safe(b['values_text'])}</p></article></div><article class="card"><h2>Psychology Disclaimer</h2><p class="muted">Results are based on self-reported behavior. They are not a mental-health diagnosis or a prediction that a relationship will or will not succeed.</p></article>''','more')


@app.route('/birth-chart/<int:user_id>')
@login_required
def birth_chart(user_id):
    conn=db(); other=conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not other: abort(404)
    return page('Birth Chart Compatibility',f'''<div class="hero paid"><span class="badge gold">★ BIRTH CHART COMPATIBILITY</span><h1>Chart-to-Chart Conscious Coordination</h1></div><div class="two"><article class="card"><h2>Your Chart</h2><div class="chips"><span class="chip">Sun</span><span class="chip">Moon</span><span class="chip">Mercury</span><span class="chip">Venus</span><span class="chip">Mars</span><span class="chip">Jupiter</span><span class="chip">Saturn</span></div></article><article class="card"><h2>{safe(other['name'])}’s Shared Chart</h2><div class="chips"><span class="chip">Sun</span><span class="chip">Moon</span><span class="chip">Mercury</span><span class="chip">Venus</span><span class="chip">Mars</span><span class="chip">Jupiter</span><span class="chip">Saturn</span></div></article></div><article class="card"><h2>Two-Chart Wheel</h2><p class="muted">Displayed when technically supported. Rising, houses and house overlays appear only when accurate birth time/location exists; never guessed.</p></article>''','more')


@app.route('/connection-ideas/<int:user_id>')
@login_required
def connection_ideas(user_id):
    conn=db(); other=conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not other: abort(404)
    return page('Connection Ideas',f'''<div class="hero"><span class="badge heart">CONNECTION IDEAS</span><h1>Ideas for You + {safe(other['name'])}</h1><p class="muted">Ideas should be built from the two actual profiles rather than zodiac alone.</p></div><div class="grid"><article class="card"><h3>Date Ideas</h3><p class="muted">Dining • nature • museums • wellness classes • local events • creator activities — each with “Why this fits.”</p></article><article class="card"><h3>Friendship Ideas</h3><p class="muted">Based on interests, social rhythm and communication style.</p></article><article class="card"><h3>Business Collaboration Ideas</h3><p class="muted">Based on strengths, working style and goals.</p></article><article class="card"><h3>Retreat Ideas</h3><p class="muted">Based on wellness interests, social energy and pace.</p></article></div>''','more')


@app.route('/video/<int:user_id>')
@login_required
def video(user_id):
    conn=db(); other=conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not other: abort(404)
    return page('Private Video Connection',f'''<div class="hero paid"><span class="badge gold">★ PAID VIDEO FEATURE</span><h1>Private Video Connection</h1><p class="muted">Both members must consent/accept. First eligible connection: 5 minutes. Additional 5 minutes: $5. Paid video request/message: sender pays $5; recipient answers free.</p></div><div class="two"><article class="card"><div class="media">Your Camera — provider required</div></article><article class="card"><div class="media">{safe(other['name'])} Camera — provider required</div></article></div><article class="card" style="text-align:center"><h1>05:00</h1><a class="btn" href="{url_for('payment_info',product='video')}">Add 5 Minutes — $5</a></article>''','more')

# -----------------------------------------------------------------------------
# Business Network / Hosted App Builder
# -----------------------------------------------------------------------------
@app.route('/business')
def business_network():
    q=request.args.get('q','').strip(); conn=db()
    if q:
        like=f'%{q}%'; rows=conn.execute('''SELECT * FROM businesses WHERE active=1 AND (name LIKE ? OR owner_title LIKE ? OR category LIKE ? OR location LIKE ? OR tagline LIKE ? OR offers LIKE ?) ORDER BY is_featured DESC,name''',(like,like,like,like,like,like)).fetchall()
    else: rows=conn.execute('SELECT * FROM businesses WHERE active=1 ORDER BY is_featured DESC,name').fetchall()
    conn.close(); cards=business_cards(rows)
    return page('Business Network',f'''<div class="hero"><span class="badge">BUSINESS NETWORK</span><h1>Discover Wellness Within the Community</h1><p class="muted">Businesses join free and receive one Hosted Business App structure after completing the builder.</p><div class="actions"><a class="btn" href="{url_for('business_builder',step=1)}">Create My FREE Hosted App</a><a class="out" href="{url_for('startup')}">Professional Business Development • $79.99</a><a class="out" href="{url_for('business_dashboard')}">My Business Dashboard</a></div></div><form class="card searchrow" method="get"><input class="input" style="margin:0" name="q" value="{safe(q)}" placeholder="Search businesses, services, classes, creators or wellness experiences..."><button class="btn">Search</button></form><div class="grid">{cards or '<div class="empty"><h3>Businesses will appear here as they join</h3></div>'}</div>''','business')


@app.route('/business/builder/<int:step>', methods=['GET','POST'])
@login_required
def business_builder(step):
    if step<1 or step>9: abort(404)
    u=current_user(); conn=db(); b=conn.execute('SELECT * FROM businesses WHERE owner_id=? AND lower(name)<>lower(?) ORDER BY id DESC LIMIT 1',(u['id'],'Galaxy Eve')).fetchone(); conn.close()
    if request.method=='POST':
        data=session.get('business_builder',{})
        for k in request.form: data[k]=request.form.get(k,'').strip()
        session['business_builder']=data
        if step<7: return redirect(url_for('business_builder',step=step+1))
        if step==7: return redirect(url_for('business_builder',step=8))
        if step==8: return redirect(url_for('business_builder',step=9))
        if step==9:
            conn=db(); existing=conn.execute('SELECT id FROM businesses WHERE owner_id=? AND lower(name)<>lower(?) ORDER BY id DESC LIMIT 1',(u['id'],'Galaxy Eve')).fetchone(); t=now()
            vals=(data.get('name') or 'My Business',data.get('owner_title',''),data.get('category',''),data.get('location',''),data.get('tagline',''),data.get('description',''),data.get('story',''),data.get('offers',''),data.get('features',''),data.get('website',''),data.get('instagram',''),data.get('tiktok',''),data.get('youtube',''),data.get('facebook',''),data.get('booking_url',''),data.get('store_url',''),data.get('podcast_url',''),data.get('affiliate_links',''))
            if existing:
                conn.execute('''UPDATE businesses SET name=?,owner_title=?,category=?,location=?,tagline=?,description=?,story=?,offers=?,features=?,website=?,instagram=?,tiktok=?,youtube=?,facebook=?,booking_url=?,store_url=?,podcast_url=?,affiliate_links=?,active=1,updated_at=? WHERE id=?''',(*vals,t,existing['id'])); bid=existing['id']
            else:
                cur=conn.execute('''INSERT INTO businesses(owner_id,name,owner_title,category,location,tagline,description,story,offers,features,website,instagram,tiktok,youtube,facebook,booking_url,store_url,podcast_url,affiliate_links,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',(u['id'],*vals,t,t)); bid=cur.lastrowid
            conn.commit(); conn.close(); session.pop('business_builder',None); flash('Your FREE Hosted Business App is published on Home and Business Network.','success'); return redirect(url_for('business_app',business_id=bid))
    data=session.get('business_builder',{})
    steps=''.join(f'<span class="step {"on" if x==step else ""}">{x}</span>' for x in range(1,10))
    if step==1: form='''<label><b>Business Name</b></label><input class="input" name="name" required><label><b>Owner/Creator Title</b></label><input class="input" name="owner_title"><label><b>Business Type</b></label><input class="input" name="category"><label><b>Location / Service Area</b></label><input class="input" name="location">'''
    elif step==2: form='''<label><b>Description</b></label><textarea class="input" name="description"></textarea><label><b>Founder / Business Story</b></label><textarea class="input" name="story"></textarea><label><b>Tagline</b></label><input class="input" name="tagline">'''
    elif step==3: form='''<label><b>What do you offer?</b></label><textarea class="input" name="offers" placeholder="Services, products, classes, courses, events, Retreats, content, memberships, consultations"></textarea>'''
    elif step==4: form='''<label><b>App Features</b></label><textarea class="input" name="features" placeholder="Booking, Classes, Courses, Shop, Videos, Events, Retreats, Media Kit, Affiliate Links"></textarea>'''
    elif step==5: form='''<p class="muted">Branding media upload is managed from the Business Dashboard after publish in this one-file build. The Hosted App uses The Seasons Within branding as fallback.</p>'''
    elif step==6: form='''<input class="input" name="website" placeholder="Website"><input class="input" name="instagram" placeholder="Instagram"><input class="input" name="tiktok" placeholder="TikTok"><input class="input" name="youtube" placeholder="YouTube"><input class="input" name="facebook" placeholder="Facebook"><input class="input" name="booking_url" placeholder="Booking link"><input class="input" name="store_url" placeholder="Store link"><input class="input" name="podcast_url" placeholder="Podcast"><textarea class="input" name="affiliate_links" placeholder="Affiliate / Resource links"></textarea>'''
    elif step==7: form=f'''<h2>Preview Your Hosted App</h2><p><b>{safe(data.get('name','Business Name'))}</b></p><p>{safe(data.get('owner_title',''))} • {safe(data.get('category',''))}</p><p class="muted">{safe(data.get('tagline',''))}</p>'''
    elif step==8: form='''<h2>Edit Before Publishing</h2><p class="muted">Use Back to return to any earlier step and change the builder answers.</p>'''
    else: form='''<h2>Publish My App</h2><p class="muted">Publishing activates the app and places it on Home and Business Network. Hosted Business Apps are FREE.</p>'''
    next_label='Publish My App' if step==9 else ('Continue to Edit' if step==7 else 'Continue')
    back=f'<a class="out" href="{url_for("business_builder",step=step-1)}">Back</a>' if step>1 else ''
    return page('Hosted App Builder',f'''<div class="hero"><span class="badge">FREE HOSTED APP BUILDER</span><h1>Step {step} of 9</h1>{steps}</div><form class="card" method="post">{form}<div class="actions">{back}<button class="btn">{next_label}</button></div></form>''','business')


@app.route('/business/app/<int:business_id>')
def business_app(business_id):
    conn=db(); b=conn.execute('SELECT * FROM businesses WHERE id=? AND active=1',(business_id,)).fetchone(); conn.close()
    if not b: abort(404)
    modules=[x.strip() for x in (b['features'] or '').split(',') if x.strip()]
    module_html=''.join(f'<article class="card"><h3>{safe(m)}</h3><p class="muted">This module is enabled by the business owner’s builder choices.</p></article>' for m in modules)
    affiliate='<p class="muted small">Affiliate disclosure: some resource links may be affiliate links.</p>' if b['affiliate_links'] else ''
    return page(b['name'],f'''<div class="hero {'paid' if b['is_featured'] else ''}"><span class="badge {'gold' if b['is_featured'] else ''}">★ HOSTED BUSINESS APP</span><h1>{safe(b['name'])}</h1><h3>{safe(b['owner_title'])}</h3><p class="muted">{safe(b['tagline'])} • {safe(b['location'])}</p><div class="chips"><span class="chip">Home</span><span class="chip">About</span><span class="chip">Contact</span>{''.join(f'<span class="chip">{safe(x)}</span>' for x in modules)}</div></div><article class="card"><h2>About</h2><p>{safe(b['description'])}</p><p>{safe(b['story'])}</p></article><div class="grid">{module_html}</div>{affiliate}<article class="card"><h2>Contact & Links</h2><p class="muted">{safe(b['website'])} {safe(b['instagram'])} {safe(b['tiktok'])} {safe(b['youtube'])}</p></article>''','business')


@app.route('/business/dashboard')
@login_required
def business_dashboard():
    u=current_user(); conn=db(); b=conn.execute('SELECT * FROM businesses WHERE owner_id=? AND lower(name)<>lower(?) ORDER BY id DESC LIMIT 1',(u['id'],'Galaxy Eve')).fetchone(); conn.close()
    preview=f'<a class="moreitem" href="{url_for("business_app",business_id=b["id"])}">Preview Hosted App</a>' if b and b['active'] else '<a class="moreitem" href="'+url_for('business_builder',step=1)+'">Create Hosted App</a>'
    return page('Business Dashboard',f'''<div class="hero"><span class="badge">BUSINESS DASHBOARD</span><h1>My Business</h1><p class="muted">Edit Hosted App, Preview Hosted App, Services, Booking, Classes, Events, Media, Links, Retreat Participation, Business Inquiries and Business Journal.</p></div><div class="grid">{preview}<a class="moreitem" href="{url_for('business_builder',step=1)}">Edit Hosted App</a><a class="moreitem" href="{url_for('startup')}">Professional Business Development</a><a class="moreitem" href="{url_for('business_plan')}">My Business Plan</a><a class="moreitem" href="{url_for('journal',section='Business')}">Business Journal</a><a class="moreitem" href="{url_for('retreats')}">Retreat Participation</a><a class="moreitem" href="{url_for('inbox')}">Business Inquiries</a></div>''','business')

# -----------------------------------------------------------------------------
# Professional Business Development
# -----------------------------------------------------------------------------
@app.route('/business-development', methods=['GET','POST'])
@login_required
def startup():
    u=current_user(); keys=['journey','strengths','help_requests','interests','income_style','business_name','concept','serves','problem','solution','mission_inputs','vision_inputs','values','usp','products','pricing','revenue','competitors','operations','compliance','startup_requirements','startup_budget','funding','marketing','goals90','goals1y']
    if request.method=='POST':
        payload={k:request.form.get(k,'').strip() for k in keys}; conn=db(); v=conn.execute('SELECT COALESCE(MAX(version),0)+1 v FROM business_plans WHERE user_id=?',(u['id'],)).fetchone()['v']; conn.execute('INSERT INTO business_plans(user_id,version,payload,created_at) VALUES(?,?,?,?)',(u['id'],v,json.dumps(payload),now())); conn.commit(); conn.close(); notify(u['id'],'Business Plan Ready',f'Business Plan version {v} is saved.',url_for('business_plan')); return redirect(url_for('business_plan'))
    fields=''.join(f'<textarea class="input" name="{k}" placeholder="{label}"></textarea>' for k,label in [('strengths','What are you good at?'),('help_requests','What do people ask for your help with?'),('interests','What interests do you enjoy?'),('income_style','How would you like to make money?'),('business_name','Business name / working name'),('concept','Business concept / overview'),('serves','Who do you want to help?'),('problem','What problem do they have?'),('solution','How will your business help them?'),('mission_inputs','Mission development inputs'),('vision_inputs','Where should the business be in 3–5 years?'),('values','Core values'),('usp','USP / competitive advantage'),('products','Products & services'),('pricing','Pricing'),('revenue','Revenue model'),('competitors','Competitors / market'),('operations','Operations'),('compliance','Certifications / licenses / insurance / compliance'),('startup_requirements','Startup requirements'),('startup_budget','Startup budget'),('funding','Funding source'),('marketing','Marketing channels and strategy'),('goals90','90-day goals'),('goals1y','One-year goals')])
    return page('Professional Business Development',f'''<div class="hero paid"><span class="badge gold">PROFESSIONAL BUSINESS DEVELOPMENT • $79.99 ONE TIME</span><h1>Turn What You Know Into a Business</h1><p class="muted">Separate from free hosting. This deeper consulting questionnaire builds your professional plan.</p></div><form class="card" method="post"><label><b>Where are you starting?</b></label><select class="input" name="journey"><option>Established Business</option><option>Recently Started</option><option>Business Idea</option><option>Hobby to Business</option><option>Skill/Talent to Monetize</option><option>Certification/License</option><option>Content Creator</option><option>Help Me Develop an Idea</option></select>{fields}<button class="btn">Generate & Save Professional Business Plan</button></form>''','business')


@app.route('/business-plan')
@login_required
def business_plan():
    u=current_user(); conn=db(); row=conn.execute('SELECT * FROM business_plans WHERE user_id=? ORDER BY version DESC LIMIT 1',(u['id'],)).fetchone(); conn.close()
    if not row: return page('My Business Plan',f'''<div class="hero paid"><span class="badge gold">MY BUSINESS PLAN</span><h1>No Business Plan Yet</h1><a class="btn" href="{url_for('startup')}">Start $79.99 Business Development</a></div>''','business')
    p=json.loads(row['payload']); sections=[('Executive Summary',p.get('concept')),('Business Description',p.get('concept')),('Founder Story',p.get('strengths')),('Mission',p.get('mission_inputs')),('Vision',p.get('vision_inputs')),('Core Values',p.get('values')),('USP',p.get('usp')),('Products & Services',p.get('products')),('Target Customer',p.get('serves')),('Customer Problem',p.get('problem')),('Business Solution',p.get('solution')),('Market / Competitor Analysis',p.get('competitors')),('Pricing Strategy',p.get('pricing')),('Revenue Streams',p.get('revenue')),('Marketing Strategy',p.get('marketing')),('Operations',p.get('operations')),('Startup Requirements',p.get('startup_requirements')),('Startup Budget / Funding',(p.get('startup_budget') or '')+' '+(p.get('funding') or '')),('90-Day Launch Strategy',p.get('goals90')),('One-Year Goals',p.get('goals1y'))]
    cards=''.join(f'<article class="card"><h3>{n}</h3><p>{safe(v or "Complete this section in an updated version.")}</p></article>' for n,v in sections)
    return page('My Business Plan',f'''<div class="hero paid"><span class="badge gold">MY BUSINESS PLAN • VERSION {row['version']}</span><h1>Editable Business Plan</h1><p class="muted">Stored in Journal → Business. Older versions remain available.</p><div class="actions"><a class="btn" href="{url_for('startup')}">Create Updated Version</a><a class="out" href="{url_for('plan_versions')}">Version History</a><a class="out" href="{url_for('marketing')}">Marketing Strategy</a><a class="out" href="{url_for('launch_plan')}">90-Day Launch Plan</a></div></div><div class="grid">{cards}</div>''','business')


@app.route('/business-plan/versions')
@login_required
def plan_versions():
    u=current_user(); conn=db(); rows=conn.execute('SELECT version,created_at FROM business_plans WHERE user_id=? ORDER BY version DESC',(u['id'],)).fetchall(); conn.close(); html=''.join(f'<article class="card"><h3>{"Original Plan" if r["version"]==1 else "Updated Plan "+str(r["version"]-1)}</h3><p class="muted">{safe(r["created_at"])}</p></article>' for r in rows) or '<div class="empty">No saved versions yet.</div>'; return page('Plan Versions',f'<div class="hero"><h1>Business Plan Version History</h1></div>{html}','business')


@app.route('/marketing')
@login_required
def marketing():
    u=current_user(); conn=db(); row=conn.execute('SELECT payload FROM business_plans WHERE user_id=? ORDER BY version DESC LIMIT 1',(u['id'],)).fetchone(); conn.close(); p=json.loads(row['payload']) if row else {}; return page('Marketing Strategy',f'''<div class="hero paid"><h1>Marketing Strategy</h1></div><div class="grid"><article class="card"><h3>Target Audience</h3><p>{safe(p.get('serves'))}</p></article><article class="card"><h3>Brand Message</h3><p>{safe(p.get('usp'))}</p></article><article class="card"><h3>Channel Strategy</h3><p>{safe(p.get('marketing'))}</p></article><article class="card"><h3>Content Pillars / Community / Partnerships / Promotions</h3><p class="muted">Developed from the saved customer, value, offer and marketing answers.</p></article></div>''','business')


@app.route('/launch-plan')
@login_required
def launch_plan():
    return page('90-Day Launch Plan','''<div class="hero paid"><h1>90-Day Launch Plan</h1></div><div class="three"><article class="card"><span class="badge">DAYS 1–30</span><h3>Foundation</h3></article><article class="card"><span class="badge">DAYS 31–60</span><h3>Visibility / Outreach</h3></article><article class="card"><span class="badge">DAYS 61–90</span><h3>Launch / Learn / Refine</h3></article></div>''','business')

# -----------------------------------------------------------------------------
# Retreats
# -----------------------------------------------------------------------------
@app.route('/retreats')
def retreats():
    conn=db(); biz=conn.execute('SELECT * FROM businesses WHERE active=1 ORDER BY is_featured DESC,name').fetchall(); conn.close(); biz_html=business_cards(biz[:6])
    return page('Retreats',f'''<div class="hero"><span class="badge">RETREATS</span><h1>Upcoming Retreats & Design Your Own</h1><p class="muted">Intentional wellness experiences with participating businesses and providers.</p><a class="btn" href="{url_for('retreat_builder')}">Build My Retreat</a></div><div class="grid"><article class="card"><span class="badge">DESIGN YOUR OWN</span><h2>Build a Private Retreat</h2><p class="muted">Season • dates • group size • budget • lodging preferences • wellness interests.</p><a class="btn" href="{url_for('retreat_builder')}">Start Retreat Builder</a></article><article class="card"><span class="badge gold">PARTICIPATING BUSINESS</span><h3>FREE Hosted Business Apps can participate</h3><p class="muted">Business participation does not require a hosting subscription.</p></article></div><div class="sectiontitle"><h2>Participating Businesses</h2></div><div class="grid">{biz_html}</div>''','retreats')


@app.route('/retreat-builder', methods=['GET','POST'])
@login_required
def retreat_builder():
    u=current_user()
    if request.method=='POST':
        keys=['retreat_type','season','preferred_dates','guests','budget','wellness','lodging','businesses','meaning']; vals=[request.form.get(k,'').strip() for k in keys]; conn=db(); conn.execute('INSERT INTO retreats(user_id,retreat_type,season,preferred_dates,guests,budget,wellness,lodging,businesses,meaning,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u['id'],*vals,now())); conn.commit(); conn.close(); notify(u['id'],'Retreat Update','Your Retreat request was saved.',url_for('journal',section='Retreats')); flash('Retreat request saved to Journal → Retreats.','success'); return redirect(url_for('journal',section='Retreats'))
    return page('Retreat Builder','''<div class="hero"><span class="badge">DESIGN YOUR OWN RETREAT</span><h1>Build Your Retreat</h1><p class="muted">Saved planning information goes to Journal → Retreats.</p></div><form class="card" method="post"><label><b>Retreat Type</b></label><select class="input" name="retreat_type"><option>Solo Renewal</option><option>Couples/Dating</option><option>Women’s Self-Love</option><option>Men’s Renewal</option><option>Family Harmony</option><option>Life Transition</option><option>Custom</option></select><label><b>Season</b></label><input class="input" name="season"><label><b>Preferred Dates</b></label><input class="input" name="preferred_dates"><label><b>Guests</b></label><input class="input" name="guests"><label><b>Budget</b></label><input class="input" name="budget"><label><b>Wellness Interests</b></label><textarea class="input" name="wellness"></textarea><label><b>Lodging Preferences</b></label><textarea class="input" name="lodging"></textarea><label><b>Desired Businesses</b></label><textarea class="input" name="businesses"></textarea><label><b>Goals / What would make this meaningful?</b></label><textarea class="input" name="meaning"></textarea><button class="btn">Save Retreat Plan</button></form>''','retreats')

# -----------------------------------------------------------------------------
# Membership / More / Settings / integrations
# -----------------------------------------------------------------------------
@app.route('/membership')
def membership():
    return page('Membership',f'''<div class="hero"><h1>Membership & Business Packages</h1></div><div class="grid"><article class="card"><span class="badge">FREE</span><h2>Community + Hosted Business App</h2><h1>$0</h1><p class="muted">Member profile • Community • Journal • Inbox • Marketplace • Retreats • basic Conscious Coordination identity • FREE Hosted Business App.</p></article><article class="card paid"><span class="badge gold">★ FULL MEMBERSHIP</span><h2>Conscious Coordination</h2><h1>$10.99/mo</h1><a class="btn" href="{url_for('payment_info',product='conscious-coordination')}">Upgrade</a></article><article class="card paid"><span class="badge gold">BUSINESS DEVELOPMENT</span><h2>Professional Business Development</h2><h1>$79.99 one time</h1><a class="btn" href="{url_for('startup')}">Start</a></article><article class="card paid"><span class="badge gold">VIDEO ADD-ON</span><h2>Add 5 Minutes</h2><h1>$5</h1></article></div>''','membership')


@app.route('/more')
@login_required
def more():
    return page('More',f'''<div class="hero"><span class="badge">MEMBER MENU</span><h1>Everything in One Place</h1></div><div class="moregrid"><a class="moreitem" href="{url_for('journal')}">My Journal</a><a class="moreitem" href="{url_for('inbox')}">Journal Inbox</a><a class="moreitem" href="{url_for('notifications')}">Notifications</a><a class="moreitem" href="{url_for('connections')}">Conscious Coordination</a><a class="moreitem" href="{url_for('business_dashboard')}">Business Dashboard</a><a class="moreitem" href="{url_for('retreats')}">Retreats</a><a class="moreitem" href="{url_for('membership')}">Membership</a><a class="moreitem" href="{url_for('settings')}">Settings</a><a class="moreitem" href="{url_for('logout')}">Log Out</a></div>''','more')


@app.route('/settings')
@login_required
def settings():
    return page('Settings',f'''<div class="hero"><h1>Settings</h1></div><div class="grid"><a class="moreitem" href="{url_for('profile_edit')}">Edit Profile</a><a class="moreitem" href="{url_for('connection_edit')}">Conscious Coordination Profile</a><a class="moreitem" href="{url_for('logout')}">Log Out</a></div>''','more')


@app.route('/payment/<product>')
def payment_info(product):
    products={'conscious-coordination':('$10.99/month','Conscious Coordination'),'business-development':('$79.99 one time','Professional Business Development'),'video':('$5','Video Add-on')}; price,name=products.get(product,('','Payment'))
    return page('Payment Setup',f'''<div class="hero paid"><span class="badge gold">PAYMENT INTEGRATION</span><h1>{name}</h1><h2>{price}</h2><p class="muted">No charge is fabricated. Connect Stripe or another approved processor and verify successful webhooks before granting paid access.</p></div>''','membership')


@app.route('/health')
def health():
    return {'ok':True,'app':'The Seasons Within','version':'fixed-master-151'}


@app.errorhandler(404)
def not_found(e):
    return page('Not Found','<div class="hero"><h1>Page Not Found</h1><p class="muted">Use the navigation to return to The Seasons Within.</p></div>'),404


if __name__=='__main__':
    init_db(); app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=os.environ.get('FLASK_DEBUG')=='1')
