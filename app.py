import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, request, redirect, url_for, session, flash, abort, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-render')
DB_PATH = os.environ.get('DATABASE_PATH', str(Path(__file__).with_name('seasons_within.db')))

# -----------------------------------------------------------------------------
# Data layer
# -----------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


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
        conscious_paid INTEGER NOT NULL DEFAULT 0,
        business_dev_paid INTEGER NOT NULL DEFAULT 0,
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
        title TEXT NOT NULL DEFAULT 'Community Post',
        category TEXT NOT NULL DEFAULT 'Reflection',
        body TEXT NOT NULL,
        post_type TEXT NOT NULL DEFAULT 'member',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        origin TEXT NOT NULL DEFAULT 'Profile',
        subject TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Reflection',
        community_post_id INTEGER,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(sender_id) REFERENCES users(id),
        FOREIGN KEY(recipient_id) REFERENCES users(id),
        FOREIGN KEY(community_post_id) REFERENCES community_posts(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        read_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        owner_title TEXT DEFAULT '',
        category TEXT DEFAULT '',
        location TEXT DEFAULT '',
        tagline TEXT DEFAULT '',
        description TEXT DEFAULT '',
        story TEXT DEFAULT '',
        offers TEXT DEFAULT '',
        features TEXT DEFAULT '',
        website TEXT DEFAULT '',
        instagram TEXT DEFAULT '', tiktok TEXT DEFAULT '', youtube TEXT DEFAULT '', facebook TEXT DEFAULT '',
        booking_url TEXT DEFAULT '', store_url TEXT DEFAULT '', podcast_url TEXT DEFAULT '', affiliate_links TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connection_profiles (
        user_id INTEGER PRIMARY KEY,
        coordination_types TEXT DEFAULT '',
        meet_preferences TEXT DEFAULT '', age_range TEXT DEFAULT '', location_preference TEXT DEFAULT '', occupation TEXT DEFAULT '', family TEXT DEFAULT '', lifestyle TEXT DEFAULT '', seeking TEXT DEFAULT '',
        overwhelmed TEXT DEFAULT '', regulate TEXT DEFAULT '', other_emotions TEXT DEFAULT '', conflict_style TEXT DEFAULT '', repair TEXT DEFAULT '', boundaries TEXT DEFAULT '', trust TEXT DEFAULT '', affection TEXT DEFAULT '', communication TEXT DEFAULT '', values_text TEXT DEFAULT '',
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
        retreat_type TEXT NOT NULL,
        season TEXT DEFAULT '', preferred_dates TEXT DEFAULT '', guests TEXT DEFAULT '', budget TEXT DEFAULT '', wellness TEXT DEFAULT '', lodging TEXT DEFAULT '', businesses TEXT DEFAULT '', meaning TEXT DEFAULT '', status TEXT DEFAULT 'Draft / Request Submitted',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')
    # Safe migrations for existing Render databases.
    def add_column_if_missing(table, column, ddl):
        cols = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        if column not in cols:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')
    add_column_if_missing('community_posts','title',"title TEXT NOT NULL DEFAULT 'Community Post'")
    add_column_if_missing('community_posts','category',"category TEXT NOT NULL DEFAULT 'Reflection'")
    add_column_if_missing('community_posts','updated_at',"updated_at TEXT NOT NULL DEFAULT ''")
    add_column_if_missing('messages','category',"category TEXT NOT NULL DEFAULT 'Reflection'")
    add_column_if_missing('messages','community_post_id',"community_post_id INTEGER")
    conn.execute("UPDATE journal_entries SET category='Reflection' WHERE category='Reflections'")
    conn.execute("UPDATE journal_entries SET category='Retreat' WHERE category='Retreats'")
    conn.execute("UPDATE community_posts SET category='Reflection' WHERE category IS NULL OR trim(category)='' OR category='Reflections'")
    conn.execute("UPDATE community_posts SET category='Retreat' WHERE category='Retreats'")
    conn.execute("UPDATE community_posts SET updated_at=created_at WHERE updated_at IS NULL OR trim(updated_at)=''")
    conn.commit()
    conn.close()


@app.before_request
def ensure_db():
    if not getattr(app, '_db_ready', False):
        init_db()
        app._db_ready = True


def now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = db(); row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone(); conn.close()
    return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to open that member area.', 'info')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def notify(user_id, title, body=''):
    conn = db()
    conn.execute('INSERT INTO notifications(user_id,title,body,created_at) VALUES(?,?,?,?)', (user_id,title,body,now()))
    conn.commit(); conn.close()


def esc_json_list(value):
    if not value:
        return []
    try:
        x=json.loads(value)
        return x if isinstance(x,list) else []
    except Exception:
        return [v.strip() for v in value.split(',') if v.strip()]

# -----------------------------------------------------------------------------
# Visual contract — adapted directly from the corrected master preview
# -----------------------------------------------------------------------------
BASE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{{ title }} — The Seasons Within</title>
<style>
:root{--plum:#34204f;--purple:#8f63ba;--purple2:#a978c7;--lav:#f2e9f8;--blush:#fff1ef;--line:#eadff1;--muted:#75677f;--gold:#ddc26f;--white:#fff;--shadow:0 14px 38px rgba(70,45,95,.09)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--plum);background:linear-gradient(180deg,#fcf9fd,#fffaf8 56%,#faf6fc);min-height:100vh}a{text-decoration:none;color:inherit}button,input,textarea,select{font:inherit}button{cursor:pointer}h1,h2,h3{font-family:Georgia,"Times New Roman",serif}h1{font-size:clamp(30px,5vw,48px);line-height:1.05;margin:8px 0 12px}h2{font-size:clamp(22px,3vw,30px);margin:6px 0 12px}.top{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.96);backdrop-filter:blur(18px);border-bottom:1px solid var(--line)}.topin{width:min(1220px,94vw);min-height:76px;margin:auto;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px}.brand{display:flex;align-items:center;gap:11px}.logo{width:49px;height:49px;border-radius:50%;padding:4px;background:#fff}.brand strong{display:block;font:700 19px Georgia}.brand small{display:block;font-size:9px;letter-spacing:1.25px;color:var(--muted);text-transform:uppercase;margin-top:3px}.desktopnav{display:flex;justify-content:center;gap:5px;flex-wrap:wrap}.desktopnav a,.acct a{border:0;background:transparent;color:#5e5068;padding:10px 12px;border-radius:999px;font-weight:800}.desktopnav a.on{background:var(--lav);color:#68418c}.acct{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800}.page{width:min(1120px,92vw);margin:26px auto 110px}.hero,.card{border:1px solid var(--line);border-radius:22px;background:#fff;box-shadow:var(--shadow)}.hero{padding:27px;background:linear-gradient(135deg,#f0e2fa,#fff1ed)}.card{padding:20px;margin:15px 0}.paid{border:2px solid var(--gold)}.badge,.chip{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;background:var(--lav);font-size:10px;font-weight:900}.badge.gold{background:#fff8df;border:1px solid var(--gold);color:#765615}.badge.heart{background:#fff0f3;color:#96526b}.actions,.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.btn,.out{display:inline-flex;align-items:center;justify-content:center;border-radius:11px;min-height:41px;padding:9px 14px;font-weight:800;border:1px solid var(--purple)}.btn{background:linear-gradient(135deg,var(--purple),var(--purple2));color:#fff}.out{background:#fff;color:#68418c;border-color:#cdb7dc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:15px}.two{display:grid;grid-template-columns:1fr 1fr;gap:15px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.media{height:220px;border-radius:16px;background:linear-gradient(135deg,#e4d2f0,#f8ded8);display:grid;place-items:center;overflow:hidden}.muted{color:var(--muted);line-height:1.55}.small{font-size:12px}.fact{padding:13px;border:1px solid var(--line);border-radius:14px;background:#fcf9fd;margin:7px 0}.fact small{display:block;color:var(--muted);margin-bottom:4px}.meter{height:10px;background:#eee6f1;border-radius:999px;overflow:hidden;margin:7px 0}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--purple),#c992c4)}.moonrow{display:grid;grid-template-columns:115px 1fr;gap:20px;align-items:center}.moonorb{width:98px;height:98px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,#fff,#d9c4e7 48%,#b795cb);font-size:48px}.post{display:grid;grid-template-columns:52px 1fr;gap:12px}.avatar{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#c89de1,#efbcc6);color:#fff;font-weight:900;overflow:hidden}.profilehero{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center}.portrait{width:118px;height:118px;border-radius:50%;background:linear-gradient(135deg,#d4b9e7,#f0c2cb);display:grid;place-items:center;color:#fff;font-weight:900;font-size:28px}.input{width:100%;padding:12px;border:1px solid #dfd1e8;border-radius:12px;background:#fff;margin:5px 0 12px}textarea.input{min-height:110px}.appcard{padding:0;overflow:hidden}.appcard .body{padding:18px}.locked{background:linear-gradient(135deg,#fffaf0,#fff);border:1px dashed var(--gold)}.topspace{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:24px 0 10px}.moregrid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.moreitem{display:block;padding:16px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow);font-weight:800}.bottom{display:none}.flash{padding:12px 16px;border-radius:13px;background:#fff8df;border:1px solid var(--gold);margin:12px 0}.empty{padding:22px;text-align:center;border:1px dashed #cdb7dc;border-radius:18px;background:#fff}.steps{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.step{padding:7px 9px;border-radius:999px;background:#eee6f1;font-size:10px;font-weight:900}.step.on{background:var(--purple);color:#fff}.splitlabel{display:flex;justify-content:space-between;gap:10px;align-items:center}.danger{border-color:#b95767;color:#9b3c4c}.checkboxes label{display:block;padding:7px 0}.previewbar{position:fixed;right:16px;bottom:88px;z-index:40;background:#34204f;color:#fff;padding:8px 11px;border-radius:999px;font-size:10px;box-shadow:var(--shadow)}
@media(max-width:820px){body{padding-bottom:82px}.topin{min-height:68px;display:flex;justify-content:center}.desktopnav,.acct{display:none}.page{width:94vw;margin-top:18px;margin-bottom:22px}.two,.three{grid-template-columns:1fr}.profilehero{grid-template-columns:1fr}.portrait{width:96px;height:96px}.moonrow{grid-template-columns:82px 1fr}.moonorb{width:76px;height:76px;font-size:38px}.bottom{position:fixed;left:50%;bottom:9px;transform:translateX(-50%);z-index:50;width:95vw;display:grid;grid-template-columns:repeat(5,1fr);padding:7px;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.97);backdrop-filter:blur(18px);box-shadow:0 15px 45px rgba(70,45,95,.18)}.bottom a{border:0;background:transparent;padding:7px 4px;border-radius:13px;color:#75677f;font-size:9px;font-weight:900;text-align:center}.bottom a b{display:block;font-size:18px;line-height:1.1}.bottom a.on{background:var(--lav);color:#68418c}.previewbar{bottom:84px}}
</style></head><body>
<header class="top"><div class="topin"><a class="brand" href="{{ url_for('home') }}"><svg class="logo" viewBox="0 0 100 100"><circle cx="50" cy="50" r="47" fill="#f4ebf9"/><path d="M50 6A44 44 0 0 1 94 50H50Z" fill="#d6b8e5"/><path d="M94 50A44 44 0 0 1 50 94V50Z" fill="#efc4cb"/><path d="M50 94A44 44 0 0 1 6 50H50Z" fill="#ead7ad"/><path d="M6 50A44 44 0 0 1 50 6V50Z" fill="#c9b7df"/><circle cx="50" cy="50" r="18" fill="#fff"/></svg><div><strong>The Seasons Within</strong><small>Conscious Coordination</small></div></a><nav class="desktopnav"><a class="{{'on' if active=='home'}}" href="{{url_for('home')}}">Home</a><a class="{{'on' if active=='community'}}" href="{{url_for('community')}}">Community</a><a class="{{'on' if active=='profile'}}" href="{{url_for('profile')}}">My Profile</a><a class="{{'on' if active=='business'}}" href="{{url_for('business_network')}}">Business Network</a><a class="{{'on' if active=='retreats'}}" href="{{url_for('retreats')}}">Retreats</a><a class="{{'on' if active=='membership'}}" href="{{url_for('membership')}}">Membership</a></nav><div class="acct">{% if user %}<a href="{{url_for('inbox')}}">Inbox</a><a href="{{url_for('notifications')}}">Notifications</a><span>{{user['name'].split()[0]}}</span>{% else %}<a href="{{url_for('login')}}">Login</a><a href="{{url_for('join')}}">Join Free</a>{% endif %}</div></div></header>
<main class="page">{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash">{{msg}}</div>{% endfor %}{% endwith %}{{ content|safe }}</main>
<nav class="bottom"><a class="{{'on' if active=='home'}}" href="{{url_for('home')}}"><b>⌂</b>Home</a><a class="{{'on' if active=='community'}}" href="{{url_for('community')}}"><b>☼</b>Community</a><a class="{{'on' if active=='profile'}}" href="{{url_for('profile')}}"><b>◉</b>Profile</a><a class="{{'on' if active=='business'}}" href="{{url_for('business_network')}}"><b>◇</b>Business</a><a class="{{'on' if active=='more'}}" href="{{url_for('more')}}"><b>•••</b>More</a></nav><div class="previewbar">Functional build • persisted data</div></body></html>'''


def page(title, content, active=''):
    return render_template_string(BASE, title=title, content=content, active=active, user=current_user())


def initials(name):
    return ''.join(p[0] for p in (name or '?').split()[:2]).upper()

# -----------------------------------------------------------------------------
# Public + account routes
# -----------------------------------------------------------------------------
def galaxy_eve_card():
    return f'''<article class="card paid appcard"><div class="media"><div style="text-align:center"><div class="avatar" style="width:90px;height:90px;margin:auto">GE</div><p><b>Galaxy Eve</b></p></div></div><div class="body"><span class="badge gold">★ Featured Hosted App</span><h2>Galaxy Eve</h2><p><b>Conscious Coordinator • Content Creator</b></p><p class="muted">Content • Collaborations • Creator Experiences</p><a class="btn" href="{url_for('galaxy_eve_app')}">Open App</a></div></article>'''


def regular_business_cards(rows):
    if not rows:
        return '<div class="empty"><h3>Businesses will appear here as they join</h3><p class="muted">Published Hosted Business Apps appear automatically after their owners publish them.</p></div>'
    return ''.join(f'''<article class="card appcard"><div class="media"><div class="avatar" style="width:90px;height:90px">{initials(b['name'])}</div></div><div class="body"><span class="badge">Hosted App</span><h2>{b['name']}</h2><p><b>{b['owner_title'] or b['category']}</b></p><p class="muted">{b['location']} • {b['tagline']}</p><a class="btn" href="{url_for('business_app',business_id=b['id'])}">Open App</a></div></article>''' for b in rows)


@app.route('/')
def home():
    q=request.args.get('q','').strip()
    conn=db()
    businesses=conn.execute("SELECT b.*,u.name owner_name FROM businesses b JOIN users u ON u.id=b.owner_id WHERE b.active=1 AND lower(b.name)<>lower('Galaxy Eve') ORDER BY b.name").fetchall()
    conn.close()
    if q:
        needle=q.lower()
        businesses=[b for b in businesses if needle in ' '.join(str(b[k] or '') for k in ('name','owner_title','category','location','tagline','offers')).lower()]
    galaxy_match=(not q) or (q.lower() in 'galaxy eve conscious coordinator content creator content collaborations creator experiences'.lower())
    galaxy=galaxy_eve_card() if galaxy_match else ''
    other=regular_business_cards(businesses)
    content=f'''<div class="hero"><span class="badge">THE SEASONS WITHIN</span><h1>Discover Wellness Within the Community</h1><p class="muted">A mobile-first wellness marketplace and member community for businesses, retreats, conscious connection, reflection and shared experiences.</p><div class="actions"><a class="btn" href="{url_for('business_network')}">Explore Businesses & Apps</a><a class="out" href="{url_for('retreats')}">Explore Retreats</a><a class="out" href="{url_for('join')}">Join Free</a></div></div>
    <form method="get" class="card"><input class="input" name="q" value="{q}" placeholder="Search businesses, services, classes, creators or wellness experiences..."><button class="btn">Search</button></form>
    <div class="topspace"><div><span class="badge gold">★ FEATURED HOSTED APP</span><h2>Galaxy Eve</h2></div></div><div class="grid">{galaxy}</div>
    <div class="topspace"><div><span class="badge gold">HOSTED BUSINESS APPS</span><h2>Community Businesses</h2></div></div><div class="grid">{other}</div>
    <article class="card moonrow"><div class="moonorb">☾</div><div><span class="badge">MOON TODAY</span><h2>Current-sky reflection</h2><p class="muted"><b>Reflection, not prediction.</b> Connect an astronomy/ephemeris provider when you are ready to publish live planetary positions.</p><div class="chips"><span class="chip">Mercury</span><span class="chip">Venus</span><span class="chip">Mars</span><span class="chip">Jupiter</span><span class="chip">Saturn</span></div></div></article>
    <div class="grid"><article class="card"><span class="badge">RETREATS</span><h2>Design Your Own Retreat</h2><a class="btn" href="{url_for('retreat_builder')}">Build My Retreat</a></article><article class="card paid"><span class="badge gold">BUSINESS DEVELOPMENT</span><h2>$79.99 Business Plan Package</h2><p class="muted">Professional questionnaire + editable plan content + Marketing Strategy + 90-Day Launch Plan.</p><a class="btn" href="{url_for('startup')}">Start My Business Plan</a></article></div>'''
    return page('Home',content,'home')

@app.route('/join', methods=['GET','POST'])
def join():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); dob=request.form.get('dob',''); adult=1 if request.form.get('adult') else 0
        if not name or not email or len(password)<8 or not dob or not adult:
            flash('Name, email, birth date, 18+ confirmation, and a password of at least 8 characters are required.','error')
        else:
            conn=db()
            try:
                cur=conn.execute('INSERT INTO users(name,email,password_hash,dob,adult_confirmed,created_at) VALUES(?,?,?,?,?,?)',(name,email,generate_password_hash(password),dob,adult,now())); conn.commit(); session['user_id']=cur.lastrowid; flash('Welcome to The Seasons Within. Your free account is ready.','success'); return redirect(url_for('community'))
            except sqlite3.IntegrityError: flash('An account with that email already exists. Use Login or Forgot Password.','error')
            finally: conn.close()
    return page('Join Free',f'''<div class="hero"><span class="badge">JOIN FREE</span><h1>Create Your Permanent Account</h1><p class="muted">One login keeps your profile, Journal, Inbox, business work, Retreats and access in one place.</p></div><form class="card" method="post"><label><b>Name</b></label><input class="input" name="name" required><label><b>Email</b></label><input class="input" type="email" name="email" required><label><b>Password</b></label><input class="input" type="password" name="password" minlength="8" required><label><b>Date of Birth</b></label><input class="input" type="date" name="dob" required><label><input type="checkbox" name="adult" required> I confirm I am 18 or older.</label><div class="actions"><button class="btn">Create Free Account</button><a class="out" href="{url_for('login')}">I Already Have an Account</a></div></form>''')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); conn=db(); u=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); conn.close()
        if u and check_password_hash(u['password_hash'],password): session['user_id']=u['id']; flash('Welcome back.','success'); return redirect(request.args.get('next') or url_for('home'))
        flash('Email or password did not match.','error')
    return page('Login',f'''<div class="hero"><span class="badge">MEMBER LOGIN</span><h1>Welcome Back</h1></div><form class="card" method="post"><label><b>Email</b></label><input class="input" type="email" name="email" required><label><b>Password</b></label><input class="input" type="password" name="password" required><label><input type="checkbox" name="remember"> Remember Me</label><div class="actions"><button class="btn">Login</button><a class="out" href="{url_for('forgot_password')}">Forgot Password</a><a class="out" href="{url_for('join')}">Create Free Account</a></div></form>''')

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method=='POST':
        flash('Password reset email delivery requires an email provider/API. No duplicate account was created.','info')
    return page('Forgot Password','''<div class="hero"><span class="badge">ACCOUNT RECOVERY</span><h1>Recover Your Existing Account</h1><p class="muted">Enter your email. Production reset delivery can be connected to your email provider without creating a second account.</p></div><form method="post" class="card"><label><b>Email</b></label><input class="input" type="email" name="email" required><button class="btn">Request Password Reset</button></form>''')

@app.route('/logout')
def logout():
    session.clear(); flash('You are logged out. Your saved data remains in your account.','success'); return redirect(url_for('home'))

# -----------------------------------------------------------------------------
# Community, profile, journal, inbox, notifications
# -----------------------------------------------------------------------------
@app.route('/community', methods=['GET','POST'])
@login_required
def community():
    u=current_user()
    categories=['Reflection','Business','Retreat','Conscious Coordination','Saved Items']
    if request.method=='POST':
        title=request.form.get('title','').strip()
        category=request.form.get('category','Reflection').strip()
        body=request.form.get('body','').strip()
        if category not in categories: category='Reflection'
        if title and body:
            conn=db(); conn.execute('INSERT INTO community_posts(user_id,title,category,body,created_at,updated_at) VALUES(?,?,?,?,?,?)',(u['id'],title,category,body,now(),now())); conn.commit(); conn.close(); flash('Posted to Community.','success'); return redirect(url_for('community'))
    conn=db(); posts=conn.execute('SELECT p.*,u.name FROM community_posts p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 50').fetchall(); conn.close()
    cards=[]
    for p in posts:
        owner=p['user_id']==u['id']
        owner_actions=f'''<div class="actions"><a class="out" href="{url_for('edit_community_post',post_id=p['id'])}">Edit Post</a><form method="post" action="{url_for('delete_community_post',post_id=p['id'])}" onsubmit="return confirm('Delete this Community post?');" style="display:inline"><button class="out danger" type="submit">Delete Post</button></form></div>''' if owner else ''
        private_message='' if owner else f'''<a class="out" href="{url_for('message_member',recipient_id=p['user_id'],origin='Community',post_id=p['id'])}">Message {p['name']} Privately</a>'''
        cards.append(f'''<article class="card"><div class="post"><div class="avatar">{initials(p['name'])}</div><div><div class="chips"><span class="badge">{p['category']}</span></div><h2 style="margin:6px 0">{p['title']}</h2><p class="muted small"><a href="{url_for('member_profile',user_id=p['user_id'])}"><b>{p['name']}</b></a> - {p['created_at']}</p><p>{p['body']}</p><div class="actions"><a class="out" href="{url_for('member_profile',user_id=p['user_id'])}">View Profile</a>{private_message}</div>{owner_actions}</div></div></article>''')
    post_html=''.join(cards) or '<div class="empty"><h3>Community posts will appear here</h3><p class="muted">Start with a real reflection. There are no fake member posts.</p></div>'
    opts=''.join(f'<option>{c}</option>' for c in categories)
    content=f'''<div class="hero"><span class="badge">MEMBERS ONLY</span><h1>Community</h1><p class="muted">The daily heart of The Seasons Within: reflection, wellness and real member posts. Private messages go directly to the member who created the post and are filed in that member's Journal Inbox.</p></div><article class="card moonrow"><div class="moonorb">☾</div><div><span class="badge">DAILY SEASONS WITHIN</span><h2>Current Sky</h2><p class="muted">Live ephemeris data is intentionally not fabricated. Connect a provider before displaying live Moon/planet positions.</p></div></article><div class="grid"><article class="card"><span class="badge">RELAXATION</span><h3>60-Second Reset</h3><p class="muted">Unclench your jaw. Lower your shoulders. Take three slow breaths and notice what can wait.</p></article><article class="card"><span class="badge">JOURNAL PROMPT</span><h3>What deserves your conscious attention today?</h3><a class="out" href="{url_for('journal')}">Open My Journal</a></article></div><form class="card" method="post"><h2>Create Community Post</h2><label><b>Title</b></label><input class="input" name="title" placeholder="Post title" required><label><b>Category</b></label><select class="input" name="category">{opts}</select><label><b>Post</b></label><textarea class="input" name="body" placeholder="Write and review your post before publishing..." required></textarea><button class="btn">Post to Community</button></form>{post_html}'''
    return page('Community',content,'community')

@app.route('/community/post/<int:post_id>/edit', methods=['GET','POST'])
@login_required
def edit_community_post(post_id):
    u=current_user(); conn=db(); post=conn.execute('SELECT * FROM community_posts WHERE id=?',(post_id,)).fetchone(); conn.close()
    if not post: abort(404)
    if post['user_id']!=u['id']: abort(403)
    categories=['Reflection','Business','Retreat','Conscious Coordination','Saved Items']
    if request.method=='POST':
        title=request.form.get('title','').strip(); category=request.form.get('category','Reflection').strip(); body=request.form.get('body','').strip()
        if category not in categories: category='Reflection'
        if title and body:
            conn=db(); conn.execute('UPDATE community_posts SET title=?,category=?,body=?,updated_at=? WHERE id=? AND user_id=?',(title,category,body,now(),post_id,u['id'])); conn.commit(); conn.close(); flash('Community post updated.','success'); return redirect(url_for('community'))
    opts=''.join(f'''<option {'selected' if c==post['category'] else ''}>{c}</option>''' for c in categories)
    return page('Edit Community Post',f'''<div class="hero"><span class="badge">COMMUNITY</span><h1>Edit Your Post</h1></div><form class="card" method="post"><label><b>Title</b></label><input class="input" name="title" value="{post['title']}" required><label><b>Category</b></label><select class="input" name="category">{opts}</select><label><b>Post</b></label><textarea class="input" name="body" required>{post['body']}</textarea><button class="btn">Save Changes</button> <a class="out" href="{url_for('community')}">Cancel</a></form>''','community')

@app.route('/community/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_community_post(post_id):
    u=current_user(); conn=db(); post=conn.execute('SELECT user_id FROM community_posts WHERE id=?',(post_id,)).fetchone()
    if not post: conn.close(); abort(404)
    if post['user_id']!=u['id']: conn.close(); abort(403)
    conn.execute('DELETE FROM community_posts WHERE id=?',(post_id,)); conn.commit(); conn.close(); flash('Community post deleted.','success'); return redirect(url_for('community'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    u=current_user()
    if request.method=='POST':
        fields=['name','city','headline','about','birth_time','birth_city','birth_region','birth_country']; values=[request.form.get(x,'').strip() for x in fields]; exact=1 if request.form.get('exact_time') else 0
        conn=db(); conn.execute('UPDATE users SET name=?,city=?,headline=?,about=?,birth_time=?,birth_city=?,birth_region=?,birth_country=?,exact_time=? WHERE id=?',(*values,exact,u['id'])); conn.commit(); conn.close(); flash('Profile saved.','success'); return redirect(url_for('profile'))
    content=f'''<article class="card"><div class="profilehero"><div><span class="badge">{'★ FULL MEMBER / CONSCIOUS COORDINATION' if u['conscious_paid'] else 'FREE MEMBER'}</span><h1>{u['name']}</h1><p class="muted">{u['city'] or 'Add your city'} • {u['headline'] or 'Add a headline'}</p><div class="actions"><a class="btn" href="#edit">Edit My Profile</a></div></div><div class="portrait">{initials(u['name'])}</div></div></article><div class="grid"><a class="moreitem" href="{url_for('community')}">Community<br><small>Posts + daily reflection</small></a><a class="moreitem" href="{url_for('journal')}">My Private Journal</a><a class="moreitem" href="{url_for('inbox')}">Journal Inbox</a><a class="moreitem" href="{url_for('notifications')}">Notifications</a><a class="moreitem" href="{url_for('connections')}">♡ Conscious Coordination</a><a class="moreitem" href="{url_for('business_dashboard')}">My Business Dashboard</a></div><form class="card" id="edit" method="post"><h2>Edit Profile</h2><label><b>Name</b></label><input class="input" name="name" value="{u['name']}" required><label><b>City</b></label><input class="input" name="city" value="{u['city'] or ''}"><label><b>Headline</b></label><input class="input" name="headline" value="{u['headline'] or ''}"><label><b>About</b></label><textarea class="input" name="about">{u['about'] or ''}</textarea><h2>Birth Information</h2><p class="muted">Rising signs and houses are never guessed.</p><label><b>Birth Time</b></label><input class="input" type="time" name="birth_time" value="{u['birth_time'] or ''}"><label><input type="checkbox" name="exact_time" {'checked' if u['exact_time'] else ''}> Exact time is known</label><label><b>Birth City</b></label><input class="input" name="birth_city" value="{u['birth_city'] or ''}"><label><b>State/Province</b></label><input class="input" name="birth_region" value="{u['birth_region'] or ''}"><label><b>Country</b></label><input class="input" name="birth_country" value="{u['birth_country'] or ''}"><button class="btn">Save Profile</button></form>'''
    return page('My Profile',content,'profile')

@app.route('/journal', methods=['GET','POST'])
@login_required
def journal():
    u=current_user()
    if request.method=='POST':
        title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); category=request.form.get('category','Reflection'); shared=request.form.get('visibility')=='community'
        if title and body:
            conn=db(); cur=conn.execute('INSERT INTO journal_entries(user_id,title,body,category,shared_copy,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(u['id'],title,body,category,1 if shared else 0,now(),now()))
            if shared: conn.execute('INSERT INTO community_posts(user_id,title,category,body,created_at,updated_at) VALUES(?,?,?,?,?,?)',(u['id'],title,category,body,now(),now()))
            conn.commit(); conn.close(); flash('Journal entry saved.' + (' A separate copy was shared to Community.' if shared else ''),'success'); return redirect(url_for('journal'))
    conn=db(); entries=conn.execute('SELECT * FROM journal_entries WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); conn.close()
    entries_html=''.join(f'''<article class="card"><span class="badge">{e['category'].upper()}</span><h3>{e['title']}</h3><p>{e['body']}</p><p class="muted small">{'Private original • community copy shared' if e['shared_copy'] else 'Private Journal only'} • {e['created_at']}</p></article>''' for e in entries) or '<div class="empty"><h3>Your Journal is private and ready</h3><p class="muted">Reflections, business notes, Retreat planning and saved coordination ideas can live here.</p></div>'
    content=f'''<div class="hero"><span class="badge">MY JOURNAL</span><h1>Private Command Center</h1><p class="muted">Private by default. Sharing creates a separate Community copy while the original remains private.</p></div><div class="grid"><a class="moreitem" href="#new">Reflections</a><a class="moreitem" href="{url_for('inbox')}">Journal Inbox</a><a class="moreitem" href="{url_for('business_plan')}">Business</a><a class="moreitem" href="{url_for('retreats')}">Retreats</a><a class="moreitem" href="{url_for('connections')}">Conscious Coordination</a><a class="moreitem" href="#entries">Saved Items</a></div><form class="card" id="new" method="post"><input class="input" name="title" placeholder="Entry title" required><select class="input" name="category"><option>Reflection</option><option>Business</option><option>Retreat</option><option>Conscious Coordination</option><option>Saved Items</option></select><textarea class="input" name="body" placeholder="Write your reflection..." required></textarea><label><b>Visibility</b></label><select class="input" name="visibility"><option value="private">Keep Private</option><option value="community">Share a Copy to Community</option></select><button class="btn">Save Entry</button></form><div id="entries">{entries_html}</div>'''
    return page('My Journal',content,'more')

@app.route('/inbox')
@login_required
def inbox():
    u=current_user(); conn=db(); msgs=conn.execute('''SELECT m.*,s.name sender_name,r.name recipient_name FROM messages m JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.recipient_id WHERE m.sender_id=? OR m.recipient_id=? ORDER BY m.id DESC''',(u['id'],u['id'])).fetchall(); conn.close()
    html=[]
    for m in msgs:
        other_id=m['sender_id'] if m['recipient_id']==u['id'] else m['recipient_id']
        reply=f'''<a class="out" href="{url_for('message_member',recipient_id=other_id,origin=m['origin'],category=m['category'],subject=m['subject'],post_id=m['community_post_id'] or '')}">Reply</a>'''
        html.append(f'''<article class="card"><div class="chips"><span class="badge">{m['category']}</span><span class="chip">{m['origin']}</span></div><h3>{m['subject']}</h3><p class="muted small">From {m['sender_name']} to {m['recipient_name']} - {m['created_at']}</p><p>{m['body']}</p>{reply}</article>''')
    rendered=''.join(html) or '<div class="empty"><h3>No private conversations yet</h3><p class="muted">Private member messages are filed here by Reflection, Business, Retreat, Conscious Coordination or Saved Items.</p></div>'
    return page('Journal Inbox',f'''<div class="hero"><span class="badge">PRIVATE MESSAGES</span><h1>Journal Inbox</h1><p class="muted">Each private message keeps its Journal category so conversations stay organized.</p></div>{rendered}''','more')

@app.route('/message/<int:recipient_id>', methods=['GET','POST'])
@login_required
def message_member(recipient_id):
    u=current_user(); conn=db(); recipient=conn.execute('SELECT * FROM users WHERE id=?',(recipient_id,)).fetchone(); conn.close()
    if not recipient: abort(404)
    if recipient_id==u['id']:
        flash('You cannot send a private message to yourself.','info'); return redirect(url_for('profile'))
    categories=['Reflection','Business','Retreat','Conscious Coordination','Saved Items']
    origin=request.args.get('origin','Profile')
    post_id=request.args.get('post_id',type=int)
    post=None
    if post_id:
        conn=db(); post=conn.execute('SELECT * FROM community_posts WHERE id=? AND user_id=?',(post_id,recipient_id)).fetchone(); conn.close()
        if post: origin='Community'
    locked_category=post['category'] if post else request.args.get('category','Reflection')
    if locked_category not in categories: locked_category='Reflection'
    if request.method=='POST':
        body=request.form.get('body','').strip(); posted_post_id=request.form.get('community_post_id',type=int)
        if posted_post_id:
            conn=db(); source=conn.execute('SELECT * FROM community_posts WHERE id=? AND user_id=?',(posted_post_id,recipient_id)).fetchone(); conn.close()
            if not source: abort(400)
            subject=source['title']; category=source['category']; origin='Community'; post_id=source['id']
        else:
            subject='Journal Private Entry'; category=request.form.get('category','Reflection')
            if category not in categories: category='Reflection'
            post_id=None; origin='Profile'
        if body:
            conn=db(); conn.execute('INSERT INTO messages(sender_id,recipient_id,origin,subject,category,community_post_id,body,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],recipient_id,origin,subject,category,post_id,body,now())); conn.commit(); conn.close(); notify(recipient_id,'New Private Message',f'{subject} - {category}'); flash("Private message sent to the member's Journal Inbox.",'success'); return redirect(url_for('inbox'))
    if post:
        details=f'''<div class="fact"><small>Title</small><b>{post['title']}</b></div><div class="fact"><small>Category</small><b>{post['category']}</b></div><input type="hidden" name="community_post_id" value="{post['id']}">'''
        helper="This message came from a Community post, so its title and category are carried into the recipient's Journal Inbox automatically."
    else:
        opts=''.join(f'''<option {'selected' if c==locked_category else ''}>{c}</option>''' for c in categories)
        details=f'''<div class="fact"><small>Title</small><b>Journal Private Entry</b></div><label><b>Journal Category</b></label><select class="input" name="category">{opts}</select>'''
        helper="Choose the Journal category so the recipient can find this private message in the right part of their Journal Inbox."
    return page('Private Message',f'''<div class="hero"><span class="badge">PRIVATE MESSAGE</span><h1>Message {recipient['name']}</h1><p class="muted">{helper}</p></div><form class="card" method="post">{details}<label><b>Private Message</b></label><textarea class="input" name="body" placeholder="Write your private message..." required></textarea><button class="btn">Send Private Message</button></form>''','more')

@app.route('/member/<int:user_id>')
@login_required
def member_profile(user_id):
    me=current_user(); conn=db(); member=conn.execute('SELECT id,name,city,headline,about,conscious_paid FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not member: abort(404)
    if member['id']!=me['id']:
        actions=f'''<a class="btn" href="{url_for('message_member',recipient_id=member['id'],origin='Profile')}">Message {member['name']}</a>'''
    else:
        actions=f'''<a class="btn" href="{url_for('profile')}">Edit My Profile</a>'''
    return page(member['name'],f'''<article class="card"><div class="profilehero"><div><span class="badge">{'★ FULL MEMBER / CONSCIOUS COORDINATION' if member['conscious_paid'] else 'MEMBER'}</span><h1>{member['name']}</h1><p class="muted">{member['city'] or 'City not added'} - {member['headline'] or 'No headline yet'}</p><p>{member['about'] or 'No About information added yet.'}</p><div class="actions">{actions}</div></div><div class="portrait">{initials(member['name'])}</div></div></article>''','community')

@app.route('/notifications')
@login_required
def notifications():
    u=current_user(); conn=db(); rows=conn.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); conn.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(now(),u['id'])); conn.commit(); conn.close()
    html=''.join(f'<article class="card"><h3>{n["title"]}</h3><p class="muted">{n["body"]}</p><p class="small muted">{n["created_at"]}</p></article>' for n in rows) or '<div class="empty"><h3>No notifications yet</h3><p class="muted">Alerts for private messages, compatibility, business inquiries and Retreat updates appear here.</p></div>'
    return page('Notifications',f'<div class="hero"><span class="badge">PRIVATE ALERTS</span><h1>Notifications</h1></div>{html}','more')

# -----------------------------------------------------------------------------
# Conscious Coordination
# -----------------------------------------------------------------------------
@app.route('/conscious-coordination')
@login_required
def connections():
    u=current_user(); conn=db(); own=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],)).fetchone(); members=conn.execute('''SELECT cp.*,u.name,u.city,u.conscious_paid FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.opted_in=1 AND cp.user_id<>? ORDER BY u.name''',(u['id'],)).fetchall(); conn.close()
    cards=''.join(f'''<article class="card {'paid' if m['conscious_paid'] else ''}"><span class="badge {'gold' if m['conscious_paid'] else ''}">{'★ FULL MEMBER' if m['conscious_paid'] else 'BASIC PROFILE'}</span><h3>{m['name']}</h3><p class="muted">{m['city'] or 'Location not shared'} • {m['coordination_types'] or 'Coordination type not set'}</p><a class="btn" href="{url_for('connection_profile',user_id=m['user_id'])}">View Profile</a></article>''' for m in members) or '<div class="empty"><h3>Participating members will appear here</h3><p class="muted">The directory does not invent profiles.</p></div>'
    content=f'''<div class="hero"><span class="badge heart">♡ PARTICIPATING MEMBERS ONLY</span><h1>Conscious Coordination</h1><p class="muted">Relationship, friendship, business collaboration, Retreat/activity connections and shared wellness experiences.</p><a class="btn" href="{url_for('connection_edit')}">{'Edit' if own else 'Create'} My Coordination Profile</a></div><article class="card"><span class="badge">HOST AREA</span><h2>Galaxy Eve / Authorized Hosts</h2><p class="muted">Host content appears here only from authorized real accounts.</p></article><div class="topspace"><h2>Discover Participating Members</h2></div><div class="grid">{cards}</div>'''
    return page('Conscious Coordination',content,'more')

@app.route('/conscious-coordination/edit', methods=['GET','POST'])
@login_required
def connection_edit():
    u=current_user(); conn=db(); cp=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],)).fetchone(); conn.close()
    if request.method=='POST':
        keys=['coordination_types','meet_preferences','age_range','location_preference','occupation','family','lifestyle','seeking','overwhelmed','regulate','other_emotions','conflict_style','repair','boundaries','trust','affection','communication','values_text','business_style','retreat_style','about_me']; vals=[request.form.get(k,'').strip() for k in keys]
        conn=db(); conn.execute('''INSERT INTO connection_profiles(user_id,coordination_types,meet_preferences,age_range,location_preference,occupation,family,lifestyle,seeking,overwhelmed,regulate,other_emotions,conflict_style,repair,boundaries,trust,affection,communication,values_text,business_style,retreat_style,about_me,opted_in,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET coordination_types=excluded.coordination_types,meet_preferences=excluded.meet_preferences,age_range=excluded.age_range,location_preference=excluded.location_preference,occupation=excluded.occupation,family=excluded.family,lifestyle=excluded.lifestyle,seeking=excluded.seeking,overwhelmed=excluded.overwhelmed,regulate=excluded.regulate,other_emotions=excluded.other_emotions,conflict_style=excluded.conflict_style,repair=excluded.repair,boundaries=excluded.boundaries,trust=excluded.trust,affection=excluded.affection,communication=excluded.communication,values_text=excluded.values_text,business_style=excluded.business_style,retreat_style=excluded.retreat_style,about_me=excluded.about_me,opted_in=1,updated_at=excluded.updated_at''',(u['id'],*vals,now())); conn.commit(); conn.close(); flash('Conscious Coordination profile saved.','success'); return redirect(url_for('connections'))
    def val(k): return cp[k] if cp and cp[k] else ''
    content=f'''<div class="hero"><span class="badge heart">♡ COORDINATION PROFILE</span><h1>Create / Edit Conscious Coordination Profile</h1><p class="muted">Self-reported behavior supports reflection and compatibility. It is not a mental-health diagnosis or a prediction of relationship success.</p></div><form class="card" method="post"><label><b>Coordination Types</b></label><input class="input" name="coordination_types" value="{val('coordination_types')}" placeholder="Love/Dating, Friendship, Business/Collaboration, Retreat/Activity"><label><b>Who would you like to meet?</b></label><input class="input" name="meet_preferences" value="{val('meet_preferences')}"><label><b>Age range</b></label><input class="input" name="age_range" value="{val('age_range')}"><label><b>Location preference</b></label><input class="input" name="location_preference" value="{val('location_preference')}"><label><b>Occupation</b></label><input class="input" name="occupation" value="{val('occupation')}"><label><b>Children / family</b></label><input class="input" name="family" value="{val('family')}"><label><b>Lifestyle</b></label><textarea class="input" name="lifestyle">{val('lifestyle')}</textarea><label><b>What are you seeking?</b></label><textarea class="input" name="seeking">{val('seeking')}</textarea><h2>Emotional & Communication Intelligence</h2><label><b>When overwhelmed...</b></label><textarea class="input" name="overwhelmed">{val('overwhelmed')}</textarea><label><b>What helps you regulate?</b></label><textarea class="input" name="regulate">{val('regulate')}</textarea><label><b>How do you handle another person's emotions?</b></label><textarea class="input" name="other_emotions">{val('other_emotions')}</textarea><label><b>Conflict style</b></label><textarea class="input" name="conflict_style">{val('conflict_style')}</textarea><label><b>Repair & accountability</b></label><textarea class="input" name="repair">{val('repair')}</textarea><label><b>Boundaries</b></label><textarea class="input" name="boundaries">{val('boundaries')}</textarea><label><b>Trust</b></label><textarea class="input" name="trust">{val('trust')}</textarea><label><b>Love languages / affection</b></label><textarea class="input" name="affection">{val('affection')}</textarea><label><b>Communication style</b></label><textarea class="input" name="communication">{val('communication')}</textarea><label><b>Lifestyle & values</b></label><textarea class="input" name="values_text">{val('values_text')}</textarea><label><b>Business partner style</b></label><textarea class="input" name="business_style">{val('business_style')}</textarea><label><b>Retreat coordination style</b></label><textarea class="input" name="retreat_style">{val('retreat_style')}</textarea><label><b>About Me</b></label><textarea class="input" name="about_me">{val('about_me')}</textarea><button class="btn">Save Profile</button></form>'''
    return page('Edit Coordination Profile',content,'more')

@app.route('/conscious-coordination/profile/<int:user_id>')
@login_required
def connection_profile(user_id):
    me=current_user(); conn=db(); row=conn.execute('SELECT cp.*,u.name,u.city,u.conscious_paid FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.user_id=? AND cp.opted_in=1',(user_id,)).fetchone(); conn.close()
    if not row: abort(404)
    content=f'''<article class="card {'paid' if row['conscious_paid'] else ''}"><div class="profilehero"><div><span class="badge {'gold' if row['conscious_paid'] else ''}">{'★ $10.99 FULL CONSCIOUS COORDINATION PROFILE' if row['conscious_paid'] else 'BASIC CONSCIOUS COORDINATION PROFILE'}</span><h1>{row['name']}</h1><p class="muted">{row['city'] or 'Location not shared'} • {row['coordination_types']}</p><div class="actions"><a class="btn" href="{url_for('message_member',recipient_id=user_id,origin='Profile',category='Conscious Coordination')}">Message Member</a><a class="out" href="{url_for('compatibility',user_id=user_id)}">Compatibility</a></div></div><div class="portrait">{initials(row['name'])}</div></div></article><div class="grid"><article class="card"><h2>How They Connect</h2><div class="fact"><small>Communication</small><b>{row['communication'] or 'Not answered'}</b></div><div class="fact"><small>Conflict</small><b>{row['conflict_style'] or 'Not answered'}</b></div><div class="fact"><small>Affection</small><b>{row['affection'] or 'Not answered'}</b></div></article><article class="card"><h2>Lifestyle & Values</h2><p>{row['values_text'] or 'Not answered'}</p><h3>About</h3><p>{row['about_me'] or 'Not added'}</p></article></div>'''
    return page('Coordination Profile',content,'more')

@app.route('/compatibility/<int:user_id>')
@login_required
def compatibility(user_id):
    me=current_user(); conn=db(); a=conn.execute('SELECT * FROM connection_profiles WHERE user_id=?',(me['id'],)).fetchone(); b=conn.execute('SELECT cp.*,u.name FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.user_id=?',(user_id,)).fetchone(); conn.close()
    if not a or not b: flash('Both members need a Conscious Coordination profile before a comparison can be generated.','info'); return redirect(url_for('connections'))
    # Transparent, simple answer-overlap score. No psychology diagnosis and no fake precision.
    pairs=[('Communication','communication'),('Conflict','conflict_style'),('Repair & Accountability','repair'),('Emotional Rhythm','regulate'),('Affection / Love Language','affection'),('Lifestyle & Values','values_text'),('Boundaries','boundaries')]
    rows=[]
    for label,key in pairs:
        av=(a[key] or '').strip().lower(); bv=(b[key] or '').strip().lower();
        aw=set(av.replace('/',' ').replace(',',' ').split()); bw=set(bv.replace('/',' ').replace(',',' ').split());
        score=round(100*len(aw&bw)/max(1,len(aw|bw))) if aw and bw else None
        rows.append((label,score))
    metrics=''.join(f'''<article class="card"><h3>{label} — {str(score)+'%' if score is not None else 'Needs answers'}</h3>{f'<div class="meter"><i style="width:{score}%"></i></div>' if score is not None else '<p class="muted">Complete both profiles to compare this area.</p>'}</article>''' for label,score in rows)
    return page('Conscious Coordination Report',f'''<div class="hero paid"><span class="badge gold">★ COMPATIBILITY</span><h1>Conscious Coordination Report</h1><p class="muted">Compares self-reported profile language. It is not a diagnosis and does not predict whether a relationship will succeed.</p></div><div class="grid">{metrics}</div><article class="card"><h2>Astrology Layer</h2><p class="muted">Birth-chart compatibility requires a real astrology calculation provider. Rising, houses and overlays are never guessed.</p><a class="btn" href="{url_for('birth_chart',user_id=user_id)}">Open Birth Chart Compatibility</a></article><article class="card"><h2>Connection Ideas</h2><a class="out" href="{url_for('connection_ideas',user_id=user_id)}">View Ideas</a></article>''','more')

@app.route('/birth-chart/<int:user_id>')
@login_required
def birth_chart(user_id):
    me=current_user(); conn=db(); other=conn.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); conn.close()
    if not other: abort(404)
    me_ok=bool(me['dob'] and me['birth_city'] and me['birth_country']); other_ok=bool(other['dob'] and other['birth_city'] and other['birth_country'])
    return page('Birth Chart Compatibility',f'''<div class="hero paid"><span class="badge gold">★ BIRTH CHART COMPATIBILITY</span><h1>Chart-to-Chart Conscious Coordination</h1></div><div class="two"><article class="card"><h2>Your Birth Data</h2><p class="muted">{'Ready for calculation provider' if me_ok else 'Add birth city/country in Profile.'}</p></article><article class="card"><h2>{other['name']}'s Shared Birth Data</h2><p class="muted">{'Ready for calculation provider' if other_ok else 'Required birth data is incomplete.'}</p></article></div><article class="card"><div class="media" style="height:320px"><b>Two-Chart Wheel appears after real ephemeris/chart integration</b></div><p class="muted">Sun, Moon, Mercury, Venus, Mars, Jupiter and Saturn can be calculated from birth data. Rising, houses and house overlays must only appear when reliable birth time/location support them.</p></article>''','more')

@app.route('/connection-ideas/<int:user_id>')
@login_required
def connection_ideas(user_id):
    conn=db(); other=conn.execute('SELECT cp.*,u.name FROM connection_profiles cp JOIN users u ON u.id=cp.user_id WHERE cp.user_id=?',(user_id,)).fetchone(); conn.close()
    if not other: abort(404)
    text=(other['values_text'] or other['lifestyle'] or '').strip()
    why='Based on the interests and values actually entered in the profile.' if text else 'Complete more profile answers to personalize this suggestion.'
    return page('Connection Ideas',f'''<div class="hero"><span class="badge">CONNECTION IDEAS</span><h1>Ideas for You & {other['name']}</h1><p class="muted">Built from real profile answers, not zodiac alone.</p></div><div class="grid"><article class="card"><h3>Conversation</h3><p>Compare what helps each of you feel understood during a stressful week.</p><p class="muted"><b>Why this fits:</b> {why}</p></article><article class="card"><h3>Shared Experience</h3><p>Choose a low-pressure local wellness, nature, museum or dining experience that matches both members' pace.</p><p class="muted"><b>Why this fits:</b> {why}</p></article><article class="card"><h3>Retreat Idea</h3><p>Create a private Retreat request and choose the pace, wellness interests and space preferences together.</p><a class="out" href="{url_for('retreat_builder')}">Build Retreat</a></article></div>''','more')

@app.route('/video/<int:user_id>')
@login_required
def video(user_id):
    u=current_user();
    return page('Private Video Connection',f'''<div class="hero paid"><span class="badge gold">★ PAID VIDEO FEATURE</span><h1>Private Video Connection</h1><p class="muted">Both members must consent. The first eligible connection is 5 minutes; additional 5-minute blocks are $5. Live video requires a video-provider integration and a payment processor; this build does not fabricate a call or charge.</p></div><div class="two"><article class="card"><div class="media">Your Camera — provider not connected</div></article><article class="card"><div class="media">Member Camera — provider not connected</div></article></div><article class="card" style="text-align:center"><h1>05:00</h1><a class="btn" href="{url_for('payment_info',product='video')}">Add 5 Minutes — $5</a></article>''','more')

# -----------------------------------------------------------------------------
# Business Network + free Hosted App Builder
# -----------------------------------------------------------------------------
@app.route('/business')
def business_network():
    q=request.args.get('q','').strip()
    conn=db(); rows=conn.execute("SELECT b.*,u.name owner_name FROM businesses b JOIN users u ON u.id=b.owner_id WHERE b.active=1 AND lower(b.name)<>lower('Galaxy Eve') ORDER BY b.name").fetchall(); conn.close()
    if q:
        needle=q.lower()
        rows=[b for b in rows if needle in ' '.join(str(b[k] or '') for k in ('name','owner_title','category','location','tagline','offers')).lower()]
    galaxy_match=(not q) or (q.lower() in 'galaxy eve conscious coordinator content creator content collaborations creator experiences'.lower())
    galaxy=galaxy_eve_card() if galaxy_match else ''
    cards=regular_business_cards(rows)
    create=url_for('business_builder',step=1) if session.get('user_id') else url_for('join')
    return page('Business Network',f'''<div class="hero"><span class="badge">BUSINESS NETWORK</span><h1>Discover Wellness Within the Community</h1><p class="muted">Businesses join free and receive one Hosted Business App structure after completing the builder.</p><div class="actions"><a class="btn" href="{create}">Create My FREE Hosted App</a><a class="out" href="{url_for('startup')}">Professional Business Development • $79.99</a>{f'<a class="out" href="{url_for("business_dashboard")}">My Business Dashboard</a>' if session.get('user_id') else ''}</div></div><form method="get" class="card"><input class="input" name="q" value="{q}" placeholder="Search businesses, services, classes, creators or wellness experiences..."><button class="btn">Search</button></form><div class="topspace"><div><span class="badge gold">★ FEATURED HOSTED APP</span><h2>Galaxy Eve</h2></div></div><div class="grid">{galaxy}</div><div class="topspace"><h2>Community Businesses</h2></div><div class="grid">{cards}</div>''','business')

@app.route('/business/galaxy-eve')
def galaxy_eve_app():
    return page('Galaxy Eve',f'''<div class="hero paid"><span class="badge gold">★ HOSTED BUSINESS APP</span><h1>Galaxy Eve</h1><h3>Conscious Coordinator • Content Creator</h3><p class="muted">Content • Collaborations • Creator Experiences</p></div><div class="chips"><span class="chip">Home</span><span class="chip">About</span><span class="chip">Watch</span><span class="chip">Events</span><span class="chip">Retreats</span><span class="chip">Media Kit</span><span class="chip">Collaborations</span><span class="chip">Social Links</span><span class="chip">Contact</span></div><div class="grid"><article class="card"><h2>Creator Media</h2><div class="media"><div style="text-align:center"><div class="avatar" style="width:100px;height:100px;margin:auto">GE</div><p class="muted">Authorized Galaxy Eve photos and videos appear here when added.</p></div></div></article><article class="card"><h2>Creator Experiences</h2><p class="muted">Content, collaborations, events, Retreat invitations and creator experiences.</p></article></div>''','business')

@app.route('/business/builder/<int:step>', methods=['GET','POST'])
@login_required
def business_builder(step):
    if step<1 or step>9: abort(404)
    draft=session.get('business_draft',{})
    fields={1:['name','owner_title','category','location'],2:['description','story','tagline'],3:['offers'],4:['features'],5:[],6:['website','instagram','tiktok','youtube','facebook','booking_url','store_url','podcast_url','affiliate_links']}
    if request.method=='POST':
        for k in fields.get(step,[]): draft[k]=request.form.get(k,'').strip()
        session['business_draft']=draft; session.modified=True
        if step==9:
            name=draft.get('name','').strip()
            if not name: flash('Business Name is required. Return to Step 1.','error'); return redirect(url_for('business_builder',step=1))
            u=current_user(); conn=db(); existing=conn.execute('SELECT id FROM businesses WHERE owner_id=? ORDER BY id LIMIT 1',(u['id'],)).fetchone(); vals=[draft.get(k,'') for k in ['name','owner_title','category','location','tagline','description','story','offers','features','website','instagram','tiktok','youtube','facebook','booking_url','store_url','podcast_url','affiliate_links']]
            if existing:
                conn.execute('''UPDATE businesses SET name=?,owner_title=?,category=?,location=?,tagline=?,description=?,story=?,offers=?,features=?,website=?,instagram=?,tiktok=?,youtube=?,facebook=?,booking_url=?,store_url=?,podcast_url=?,affiliate_links=?,active=1,updated_at=? WHERE id=?''',(*vals,now(),existing['id'])); bid=existing['id']
            else:
                cur=conn.execute('''INSERT INTO businesses(owner_id,name,owner_title,category,location,tagline,description,story,offers,features,website,instagram,tiktok,youtube,facebook,booking_url,store_url,podcast_url,affiliate_links,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',(u['id'],*vals,now(),now())); bid=cur.lastrowid
            conn.commit(); conn.close(); session.pop('business_draft',None); flash('Your FREE Hosted Business App is published to Home and the Business Network.','success'); return redirect(url_for('business_app',business_id=bid))
        return redirect(url_for('business_builder',step=min(9,step+1)))
    steps=''.join(f'<span class="step {"on" if i==step else ""}">{i}</span>' for i in range(1,10))
    if step==1: body=f'''<label><b>Business Name</b></label><input class="input" name="name" value="{draft.get('name','')}" required><label><b>Owner/Creator Title</b></label><input class="input" name="owner_title" value="{draft.get('owner_title','')}"><label><b>Business Type</b></label><input class="input" name="category" value="{draft.get('category','')}"><label><b>Location / Service Area</b></label><input class="input" name="location" value="{draft.get('location','')}">'''
    elif step==2: body=f'''<label><b>Description</b></label><textarea class="input" name="description">{draft.get('description','')}</textarea><label><b>Founder / Business Story</b></label><textarea class="input" name="story">{draft.get('story','')}</textarea><label><b>Tagline</b></label><input class="input" name="tagline" value="{draft.get('tagline','')}">'''
    elif step==3: body=f'''<label><b>What Do You Offer?</b></label><textarea class="input" name="offers" placeholder="Services, products, classes, courses, events, Retreats, content, memberships, consultations">{draft.get('offers','')}</textarea>'''
    elif step==4: body=f'''<label><b>App Features</b></label><textarea class="input" name="features" placeholder="Booking, Classes, Courses, Shop, Videos, Events, Retreats, Media Kit, Affiliate Links">{draft.get('features','')}</textarea>'''
    elif step==5: body='''<h2>Branding</h2><p class="muted">Logo and cover photo/video upload storage requires an object-storage provider in production. Until connected, the Seasons Within brand mark is used as the safe fallback.</p>'''
    elif step==6: body=''.join(f'<label><b>{label}</b></label><input class="input" name="{k}" value="{draft.get(k,"")}">' for k,label in [('website','Website'),('instagram','Instagram'),('tiktok','TikTok'),('youtube','YouTube'),('facebook','Facebook'),('booking_url','Booking'),('store_url','Store'),('podcast_url','Podcast'),('affiliate_links','Affiliate / Resource Links')])
    elif step==7: body=f'''<h2>Preview</h2><article class="card appcard"><div class="media"><div class="avatar" style="width:90px;height:90px">{initials(draft.get('name','Business'))}</div></div><div class="body"><span class="badge">Hosted App</span><h2>{draft.get('name','Your Business')}</h2><p><b>{draft.get('owner_title','')}</b></p><p class="muted">{draft.get('category','')} • {draft.get('location','')}<br>{draft.get('tagline','')}</p></div></article>'''
    elif step==8: body='<h2>Edit</h2><p class="muted">Use the Back buttons to change any builder answer before publishing.</p>'
    else: body='<h2>Publish My App</h2><p class="muted">Publishing activates this Hosted App and places it on Home and the Business Network. Hosting is FREE.</p>'
    back=f'<a class="out" href="{url_for("business_builder",step=step-1)}">Back</a>' if step>1 else ''
    submit='Publish My App' if step==9 else 'Continue'
    return page('Hosted App Builder',f'''<div class="hero"><span class="badge">FREE HOSTED APP BUILDER</span><h1>Step {step} of 9</h1><div class="steps">{steps}</div></div><form class="card" method="post">{body}<div class="actions">{back}<button class="btn">{submit}</button></div></form>''','business')

@app.route('/business/app/<int:business_id>')
def business_app(business_id):
    conn=db(); b=conn.execute('SELECT b.*,u.name owner_name FROM businesses b JOIN users u ON u.id=b.owner_id WHERE b.id=? AND b.active=1',(business_id,)).fetchone(); conn.close()
    if not b: abort(404)
    links=''.join(f'<a class="chip" href="{url}" target="_blank" rel="noopener">{label}</a>' for label,url in [('Website',b['website']),('Instagram',b['instagram']),('TikTok',b['tiktok']),('YouTube',b['youtube']),('Facebook',b['facebook'])] if url)
    featurechips=''.join(f'<span class="chip">{x.strip()}</span>' for x in (b['features'] or '').split(',') if x.strip())
    affiliate=f'<article class="card"><h2>Affiliate / Resource Links</h2><p>{b["affiliate_links"]}</p><p class="muted small"><b>Disclosure:</b> Some resource links may be affiliate links. The business owner is responsible for accurate disclosures.</p></article>' if b['affiliate_links'] else ''
    return page(b['name'],f'''<div class="hero paid"><span class="badge gold">★ HOSTED BUSINESS APP</span><h1>{b['name']}</h1><h3>{b['owner_title'] or b['category']}</h3><p class="muted">{b['location']} • {b['tagline']}</p><div class="chips">{links}</div></div><div class="chips"><span class="chip">Home</span><span class="chip">About</span><span class="chip">Contact</span>{featurechips}</div><div class="grid"><article class="card"><h2>About</h2><p>{b['description'] or 'Business description coming soon.'}</p><p class="muted">{b['story']}</p></article><article class="card"><h2>What We Offer</h2><p>{b['offers'] or 'Offers will appear here after the owner adds them.'}</p></article></div>{affiliate}''','business')

@app.route('/business/dashboard')
@login_required
def business_dashboard():
    u=current_user(); conn=db(); b=conn.execute('SELECT * FROM businesses WHERE owner_id=? ORDER BY id LIMIT 1',(u['id'],)).fetchone(); conn.close()
    app_link=f'<a class="moreitem" href="{url_for("business_app",business_id=b["id"])}">Preview Hosted App</a>' if b and b['active'] else f'<a class="moreitem" href="{url_for("business_builder",step=1)}">Build My FREE Hosted App</a>'
    return page('Business Dashboard',f'''<div class="hero"><span class="badge">BUSINESS DASHBOARD</span><h1>My Business</h1><p class="muted">Manage the free Hosted App and the separate Professional Business Development package.</p></div><div class="grid">{app_link}<a class="moreitem" href="{url_for('business_builder',step=1)}">Edit Hosted App</a><a class="moreitem" href="{url_for('startup')}">Professional Business Development • $79.99</a><a class="moreitem" href="{url_for('business_plan')}">My Business Plan</a><a class="moreitem" href="{url_for('marketing')}">Marketing Strategy</a><a class="moreitem" href="{url_for('launch_plan')}">90-Day Launch Plan</a><a class="moreitem" href="{url_for('plan_versions')}">Plan Versions</a><a class="moreitem" href="{url_for('inbox')}">Business Inquiries</a><a class="moreitem" href="{url_for('journal')}">Business Journal</a></div>''','business')

# -----------------------------------------------------------------------------
# $79.99 Professional Business Development
# -----------------------------------------------------------------------------
@app.route('/business-development', methods=['GET','POST'])
@login_required
def startup():
    u=current_user()
    if request.method=='POST':
        payload={k:request.form.get(k,'').strip() for k in ['journey','strengths','help_requests','interests','income_style','business_name','concept','serves','problem','solution','mission_inputs','vision_inputs','values','usp','products','pricing','revenue','competitors','operations','compliance','startup_requirements','startup_budget','funding','marketing','goals90','goals1y']}
        conn=db(); v=conn.execute('SELECT COALESCE(MAX(version),0)+1 v FROM business_plans WHERE user_id=?',(u['id'],)).fetchone()['v']; conn.execute('INSERT INTO business_plans(user_id,version,payload,created_at) VALUES(?,?,?,?)',(u['id'],v,json.dumps(payload),now())); conn.commit(); conn.close(); flash(f'Business Plan version {v} generated and saved to Journal → Business.','success'); return redirect(url_for('business_plan'))
    return page('Professional Business Development',f'''<div class="hero paid"><span class="badge gold">PROFESSIONAL BUSINESS DEVELOPMENT • $79.99</span><h1>Turn What You Know Into a Business</h1><p class="muted">This questionnaire creates a saved plan structure. Production payment checkout must be connected before treating access as purchased.</p><a class="out" href="{url_for('payment_info',product='business-development')}">Payment / Access Setup</a></div><form class="card" method="post"><label><b>Where are you starting?</b></label><select class="input" name="journey"><option>Established Business</option><option>Recently Started</option><option>Business Idea</option><option>Hobby to Business</option><option>Skill/Talent to Monetize</option><option>Certification/License</option><option>Content Creator</option><option>Help Me Develop an Idea</option></select><textarea class="input" name="strengths" placeholder="What are you good at?"></textarea><textarea class="input" name="help_requests" placeholder="What do people ask for your help with?"></textarea><textarea class="input" name="interests" placeholder="What interests do you enjoy?"></textarea><textarea class="input" name="income_style" placeholder="How would you like to make money?"></textarea><input class="input" name="business_name" placeholder="Business name / working name"><textarea class="input" name="concept" placeholder="Business concept — what does it do?"></textarea><textarea class="input" name="serves" placeholder="Who does it serve?"></textarea><textarea class="input" name="problem" placeholder="What problem do they have?"></textarea><textarea class="input" name="solution" placeholder="How will your business help them?"></textarea><textarea class="input" name="mission_inputs" placeholder="Mission inputs: who, problem, how you help"></textarea><textarea class="input" name="vision_inputs" placeholder="Vision: where should the business be in 3–5 years and what impact should it have?"></textarea><textarea class="input" name="values" placeholder="Core values"></textarea><textarea class="input" name="usp" placeholder="What makes the business different?"></textarea><textarea class="input" name="products" placeholder="Products, services, classes, experiences"></textarea><textarea class="input" name="pricing" placeholder="Pricing, cost to deliver, desired income, package opportunities"></textarea><textarea class="input" name="revenue" placeholder="Revenue streams"></textarea><textarea class="input" name="competitors" placeholder="Competitors / alternatives / local and online market"></textarea><textarea class="input" name="operations" placeholder="Hours, appointments, staffing, suppliers, support and systems"></textarea><textarea class="input" name="compliance" placeholder="Certifications, licenses, insurance and compliance requirements"></textarea><textarea class="input" name="startup_requirements" placeholder="Equipment, software, supplies, branding, space, inventory, contractors"></textarea><textarea class="input" name="startup_budget" placeholder="Known startup costs"></textarea><textarea class="input" name="funding" placeholder="Self-funding, grants, loans, investors, donations or other"></textarea><textarea class="input" name="marketing" placeholder="Marketing channels: social, search, local, events, referrals, partnerships, ads"></textarea><textarea class="input" name="goals90" placeholder="90-day goals"></textarea><textarea class="input" name="goals1y" placeholder="One-year goals"></textarea><button class="btn">Generate & Save Professional Business Plan</button></form>''','business')

@app.route('/business-plan')
@login_required
def business_plan():
    u=current_user(); conn=db(); row=conn.execute('SELECT * FROM business_plans WHERE user_id=? ORDER BY version DESC LIMIT 1',(u['id'],)).fetchone(); conn.close()
    if not row: content=f'''<div class="hero paid"><span class="badge gold">MY BUSINESS PLAN</span><h1>No Business Plan Yet</h1><p class="muted">Complete Professional Business Development to create your first version.</p><a class="btn" href="{url_for('startup')}">Start $79.99 Business Development</a></div>'''
    else:
        p=json.loads(row['payload']); sections=[('Executive Summary',p.get('concept')),('Business Description',p.get('concept')),('Founder Story',p.get('strengths')),('Mission',p.get('mission_inputs')),('Vision',p.get('vision_inputs')),('Core Values',p.get('values')),('USP / Competitive Advantage',p.get('usp')),('Products & Services',p.get('products')),('Target Customer',p.get('serves')),('Customer Problem',p.get('problem')),('Business Solution',p.get('solution')),('Competitor Analysis',p.get('competitors')),('Pricing Strategy',p.get('pricing')),('Revenue Streams',p.get('revenue')),('Marketing Strategy',p.get('marketing')),('Operations',p.get('operations')),('Startup Requirements',p.get('startup_requirements')),('Startup Budget / Funding',(p.get('startup_budget') or '')+' '+(p.get('funding') or '')),('90-Day Launch Strategy',p.get('goals90')),('One-Year Goals',p.get('goals1y'))]
        cards=''.join(f'<article class="card"><h3>{name}</h3><p>{value or "Complete this section in a future revision."}</p></article>' for name,value in sections)
        content=f'''<div class="hero paid"><span class="badge gold">MY BUSINESS PLAN • VERSION {row['version']}</span><h1>Editable Business Plan</h1><p class="muted">Saved in your account. PDF/email/share require a PDF/email integration layer; the data itself is persisted now.</p><div class="actions"><a class="btn" href="{url_for('startup')}">Create Updated Version</a><a class="out" href="{url_for('plan_versions')}">Version History</a></div></div><div class="grid">{cards}</div>'''
    return page('My Business Plan',content,'business')

@app.route('/business-plan/versions')
@login_required
def plan_versions():
    u=current_user(); conn=db(); rows=conn.execute('SELECT id,version,created_at FROM business_plans WHERE user_id=? ORDER BY version DESC',(u['id'],)).fetchall(); conn.close()
    html=''.join(f'<article class="card"><h3>Version {r["version"]}</h3><p class="muted">Saved {r["created_at"]}</p></article>' for r in rows) or '<div class="empty">No saved versions yet.</div>'
    return page('Business Plan Library',f'<div class="hero"><span class="badge">BUSINESS PLAN LIBRARY</span><h1>Saved Business Plan Copies</h1></div><div class="grid">{html}</div>','business')

@app.route('/marketing')
@login_required
def marketing():
    u=current_user(); conn=db(); row=conn.execute('SELECT payload FROM business_plans WHERE user_id=? ORDER BY version DESC LIMIT 1',(u['id'],)).fetchone(); conn.close(); p=json.loads(row['payload']) if row else {}
    return page('Marketing Strategy',f'''<div class="hero paid"><span class="badge gold">BUSINESS PACKAGE</span><h1>Marketing Strategy</h1></div><div class="grid"><article class="card"><h3>Ideal Audience</h3><p>{p.get('serves') or 'Complete your plan to populate this section.'}</p></article><article class="card"><h3>Brand Positioning</h3><p>{p.get('usp') or 'Complete your plan to populate this section.'}</p></article><article class="card"><h3>Channels</h3><p>{p.get('marketing') or 'Complete your plan to populate this section.'}</p></article><article class="card"><h3>Content Pillars</h3><p>Derive content pillars from the customer's problem, solution, values and offers in your saved plan.</p></article></div>''','business')

@app.route('/launch-plan')
@login_required
def launch_plan():
    return page('90-Day Launch Plan','''<div class="hero paid"><span class="badge gold">BUSINESS PACKAGE</span><h1>90-Day Launch Plan</h1></div><div class="three"><article class="card"><span class="badge">DAYS 1–30</span><h3>Foundation</h3><p class="muted">Offer, audience, pricing, branding and app/profile setup.</p></article><article class="card"><span class="badge">DAYS 31–60</span><h3>Visibility / Outreach</h3><p class="muted">Content, partnerships, outreach and early customer feedback.</p></article><article class="card"><span class="badge">DAYS 61–90</span><h3>Launch / Learn / Refine</h3><p class="muted">Launch campaign, track response and improve the offer.</p></article></div>''','business')

# -----------------------------------------------------------------------------
# Retreats
# -----------------------------------------------------------------------------
@app.route('/retreats')
def retreats():
    if session.get('user_id'):
        conn=db(); own=conn.execute('SELECT * FROM retreats WHERE user_id=? ORDER BY id DESC',(session['user_id'],)).fetchall(); conn.close(); own_html=''.join(f'<article class="card"><span class="badge">{r["status"]}</span><h3>{r["retreat_type"]}</h3><p class="muted">{r["season"]} • {r["preferred_dates"]} • {r["guests"]}</p></article>' for r in own)
    else: own_html=''
    return page('Retreats',f'''<div class="hero"><span class="badge">RETREATS</span><h1>Upcoming Retreats & Design Your Own</h1><p class="muted">Intentional shared experiences connecting members, wellness and participating businesses.</p><a class="btn" href="{url_for('retreat_builder')}">Build My Retreat</a></div><div class="grid"><article class="card"><span class="badge">DESIGN YOUR OWN</span><h2>Build a Private Retreat</h2><p class="muted">Season • dates • group size • budget • lodging preferences • wellness interests.</p><a class="btn" href="{url_for('retreat_builder')}">Start Retreat Builder</a></article><article class="card"><span class="badge gold">PARTICIPATING BUSINESSES</span><h3>Free Hosted Business Apps can participate</h3><p class="muted">Business participation does not require a hosting subscription.</p></article></div>{own_html}''','retreats')

@app.route('/retreat-builder', methods=['GET','POST'])
@login_required
def retreat_builder():
    u=current_user()
    if request.method=='POST':
        keys=['retreat_type','season','preferred_dates','guests','budget','wellness','lodging','businesses','meaning']; vals=[request.form.get(k,'').strip() for k in keys]
        conn=db(); conn.execute('''INSERT INTO retreats(user_id,retreat_type,season,preferred_dates,guests,budget,wellness,lodging,businesses,meaning,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(u['id'],*vals,now())); conn.commit(); conn.close(); notify(u['id'],'Retreat Update','Your Retreat request was saved.'); flash('Retreat request saved to Journal → Retreats.','success'); return redirect(url_for('retreats'))
    return page('Retreat Builder','''<div class="hero"><span class="badge">DESIGN YOUR OWN RETREAT</span><h1>Build Your Retreat</h1><p class="muted">A guided private Retreat request rather than a fake instant booking.</p></div><form class="card" method="post"><label><b>Retreat Type</b></label><select class="input" name="retreat_type"><option>Solo Renewal</option><option>Couples / Dating</option><option>Women's Self-Love</option><option>Men's Renewal</option><option>Family Harmony</option><option>Life Transition</option><option>Custom</option></select><label><b>Season</b></label><select class="input" name="season"><option>Spring Renewal</option><option>Summer Water</option><option>Autumn Reflection</option><option>Winter Stillness</option></select><label><b>Preferred Dates</b></label><input class="input" name="preferred_dates"><label><b>Guests</b></label><input class="input" name="guests"><label><b>Budget</b></label><input class="input" name="budget"><label><b>Wellness Interests</b></label><textarea class="input" name="wellness"></textarea><label><b>Lodging Preferences</b></label><textarea class="input" name="lodging"></textarea><label><b>Desired Businesses / Providers</b></label><textarea class="input" name="businesses"></textarea><label><b>What would make this Retreat meaningful?</b></label><textarea class="input" name="meaning"></textarea><button class="btn">Send Retreat Request</button></form>''','retreats')

# -----------------------------------------------------------------------------
# Membership, settings, more, integrations
# -----------------------------------------------------------------------------
@app.route('/membership')
def membership():
    return page('Membership',f'''<div class="hero"><h1>Membership & Business Packages</h1><p class="muted">Clear separation between belonging, deeper connection tools, free business hosting and one-time professional business development.</p></div><div class="grid"><article class="card"><span class="badge">FREE</span><h2>Community + Hosted Business App</h2><h1>$0</h1><p class="muted">Member profile • Community • Journal • Inbox • Marketplace • Retreats • basic Conscious Coordination identity • one FREE Hosted Business App structure.</p></article><article class="card paid"><span class="badge gold">★ FULL MEMBERSHIP</span><h2>Conscious Coordination</h2><h1>$10.99/mo</h1><p class="muted">Deeper compatibility • shared birth-chart tools when technically supported • expanded profile media • eligible video features.</p><a class="btn" href="{url_for('payment_info',product='conscious-coordination')}">Upgrade</a></article><article class="card paid"><span class="badge gold">BUSINESS DEVELOPMENT</span><h2>Professional Business Development</h2><h1>$79.99</h1><p class="muted">One-time deeper planning package: Business Plan • Marketing Strategy • 90-Day Launch Plan • saved versions.</p><a class="btn" href="{url_for('startup')}">Start</a></article><article class="card paid"><span class="badge gold">VIDEO ADD-ON</span><h2>Add 5 Minutes</h2><h1>$5</h1><p class="muted">Available inside eligible private video connections after provider/payment integration.</p></article></div>''','membership')

@app.route('/more')
@login_required
def more():
    return page('More',f'''<div class="hero"><span class="badge">MEMBER MENU</span><h1>Everything in One Place</h1></div><div class="moregrid"><a class="moreitem" href="{url_for('journal')}">My Journal</a><a class="moreitem" href="{url_for('inbox')}">Journal Inbox</a><a class="moreitem" href="{url_for('notifications')}">Notifications</a><a class="moreitem" href="{url_for('connections')}">Conscious Coordination</a><a class="moreitem" href="{url_for('business_dashboard')}">Business Dashboard</a><a class="moreitem" href="{url_for('retreats')}">Retreats</a><a class="moreitem" href="{url_for('membership')}">Membership</a><a class="moreitem" href="{url_for('settings')}">Settings</a><a class="moreitem" href="{url_for('logout')}">Log Out</a></div>''','more')

@app.route('/settings')
@login_required
def settings():
    return page('Settings',f'''<div class="hero"><span class="badge">ACCOUNT</span><h1>Settings</h1><p class="muted">One account and one password for the entire Seasons Within experience.</p></div><div class="grid"><article class="card"><h3>Email & Password</h3><p class="muted">Password-reset delivery requires the production email integration.</p></article><article class="card"><h3>Profile</h3><a class="out" href="{url_for('profile')}">Edit Profile</a></article><article class="card"><h3>Conscious Coordination</h3><a class="out" href="{url_for('connection_edit')}">Edit / Opt In</a></article><article class="card"><h3>Log Out</h3><a class="out danger" href="{url_for('logout')}">Log Out</a></article></div>''','more')

@app.route('/payment/<product>')
def payment_info(product):
    products={'conscious-coordination':('$10.99/month','Conscious Coordination'),'business-development':('$79.99 one time','Professional Business Development'),'video':('$5','Video Add-on')}
    price,name=products.get(product,('','Payment'))
    return page('Payment Setup',f'''<div class="hero paid"><span class="badge gold">PAYMENT INTEGRATION</span><h1>{name}</h1><h2>{price}</h2><p class="muted">No charge is simulated in this build. Connect Stripe or another approved payment processor and verify successful webhooks before granting paid access.</p></div>''','membership')

@app.route('/health')
def health():
    return {'ok': True, 'app': 'The Seasons Within'}

@app.errorhandler(404)
def not_found(e):
    return page('Not Found','<div class="hero"><h1>Page Not Found</h1><p class="muted">Use the navigation to return to The Seasons Within.</p></div>'),404

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','5000')), debug=os.environ.get('FLASK_DEBUG')=='1')
