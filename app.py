import os, re, json, sqlite3, hashlib, secrets
from datetime import datetime, date, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.utils import secure_filename
from jinja2 import DictLoader
try:
    import swisseph as swe
except Exception:
    swe=None

BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get('PERSISTENT_DATA_DIR', BASE/'data')); DATA.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get('DATABASE_PATH', DATA/'the_seasons_within.db'))
UPLOADS=Path(os.environ.get('UPLOAD_DIR', DATA/'uploads')); UPLOADS.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get('SECRET_KEY','change-me-in-render')
MEMBER_PRICE='10.99'; BUSINESS_PRICE='29.99'
GALAXY_EMAIL=os.environ.get('GALAXY_EVE_EMAIL','galaxyeve@theseasonswithin.local').strip().lower()
ADMIN_EMAILS={x.strip().lower() for x in os.environ.get('ADMIN_EMAILS','').split(',') if x.strip()}
SIGNS=['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def hp(p): return hashlib.sha256(('tsw::'+p).encode()).hexdigest()
def slugify(t): return re.sub(r'[^a-z0-9]+','-',(t or '').lower()).strip('-') or secrets.token_hex(4)
def me():
    uid=session.get('uid')
    if not uid:return None
    c=conn();u=c.execute('select * from users where id=?',(uid,)).fetchone();c.close();return u
def admin(u): return bool(u and (u['is_admin'] or (u['email'] or '').lower() in ADMIN_EMAILS))
def login_required(fn):
    @wraps(fn)
    def w(*a,**k):
        if not me(): return redirect(url_for('login',next=request.path))
        return fn(*a,**k)
    return w
def admin_required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=me()
        if not u:return redirect(url_for('login'))
        if not admin(u):return 'Admin access required',403
        return fn(*a,**k)
    return w

def media_url(p): return url_for('uploads',filename=p) if p else ''
def save_file(f,prefix):
    if not f or not f.filename:return ''
    ext=Path(secure_filename(f.filename)).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp','.gif','.mp4','.mov','.m4v'}: return ''
    name=f'{prefix}-{secrets.token_hex(8)}{ext}'; f.save(UPLOADS/name); return name

def season_now():
    m=date.today().month
    return 'Winter' if m in (12,1,2) else 'Spring' if m in (3,4,5) else 'Summer' if m in (6,7,8) else 'Autumn'
def zdeg(d):
    d=float(d)%360;i=int(d//30);return SIGNS[i],round(d-i*30,2)
def current_sky():
    sky={'moon_sign':'','moon_phase':'','moon_degree':None,'positions':{},'season':season_now()}
    if not swe:return sky
    try:
        n=datetime.now(timezone.utc);jd=swe.julday(n.year,n.month,n.day,n.hour+n.minute/60+n.second/3600)
        ids={'Sun':swe.SUN,'Moon':swe.MOON,'Mercury':swe.MERCURY,'Venus':swe.VENUS,'Mars':swe.MARS,'Jupiter':swe.JUPITER,'Saturn':swe.SATURN,'Uranus':swe.URANUS,'Neptune':swe.NEPTUNE,'Pluto':swe.PLUTO};deg={}
        for name,pid in ids.items():
            x=swe.calc_ut(jd,pid)[0][0];sign,sd=zdeg(x);deg[name]=x;sky['positions'][name]={'sign':sign,'degree':sd}
        sky['moon_sign']=sky['positions']['Moon']['sign'];sky['moon_degree']=sky['positions']['Moon']['degree'];angle=(deg['Moon']-deg['Sun'])%360
        for cut,name in [(22.5,'New Moon'),(67.5,'Waxing Crescent'),(112.5,'First Quarter'),(157.5,'Waxing Gibbous'),(202.5,'Full Moon'),(247.5,'Waning Gibbous'),(292.5,'Last Quarter'),(337.5,'Waning Crescent'),(361,'New Moon')]:
            if angle<cut: sky['moon_phase']=name;break
    except Exception: pass
    return sky

def chart_for(u):
    if not swe or not u['birth_date']: return {}
    try:
        d=datetime.strptime(u['birth_date'],'%Y-%m-%d');hour=12
        if u['time_known'] and u['birth_time']:
            h,m=[int(x) for x in u['birth_time'].split(':')[:2]];hour=h+m/60
        jd=swe.julday(d.year,d.month,d.day,hour);ids={'Sun':swe.SUN,'Moon':swe.MOON,'Mercury':swe.MERCURY,'Venus':swe.VENUS,'Mars':swe.MARS,'Jupiter':swe.JUPITER,'Saturn':swe.SATURN,'Uranus':swe.URANUS,'Neptune':swe.NEPTUNE,'Pluto':swe.PLUTO};o={}
        for name,pid in ids.items():
            x=swe.calc_ut(jd,pid)[0][0];s,sd=zdeg(x);o[name]=(s,sd)
        return o
    except Exception:return {}

def journal_reflection(u):
    s=current_sky(); natal=(u['moon'] or u['sun'] or 'your natal chart') if u else 'your natal chart'
    return {'sky':s,'headline':f'Reflect through {natal} and the current {s["moon_sign"] or "Moon"}.','prompt':'What are you noticing within yourself today, and what deserves your conscious attention?'}
def coord(a,b,mode='friendship'):
    score=50
    for k in ('sun','moon','mercury','venus','mars'):
        if a[k] and b[k]: score += 8 if a[k]==b[k] else 3
    return max(40,min(95,score))

def init_db():
    c=conn();c.executescript('''
    create table if not exists users(id integer primary key autoincrement,name text not null,email text unique not null,password text not null,city text default '',bio text default '',photo text default '',profile_headline text default '',birth_date text default '',birth_time text default '',time_known integer default 0,sun text default '',moon text default '',rising text default '',mercury text default '',venus text default '',mars text default '',jupiter text default '',saturn text default '',uranus text default '',neptune text default '',pluto text default '',is_admin integer default 0,is_creator integer default 0,creator_access integer default 0,business_access integer default 0,membership_access integer default 0,dating_active integer default 0,connection_intentions text default '',created_at text default current_timestamp);
    create table if not exists businesses(id integer primary key autoincrement,owner_id integer unique not null references users(id) on delete cascade,slug text unique not null,business_name text not null,creator_title text default '',tagline text default '',description text default '',category text default '',city text default '',website text default '',contact_email text default '',phone text default '',logo text default '',instagram text default '',tiktok text default '',youtube text default '',booking_url text default '',paid_business integer default 0,media_kit_enabled integer default 0,followers text default '',likes text default '',views text default '',audience_info text default '',content_categories text default '',collaboration_interests text default '',retreat_participation integer default 0,featured_order integer default 999,status text default 'active');
    create table if not exists posts(id integer primary key autoincrement,user_id integer references users(id) on delete cascade,body text not null,created_at text default current_timestamp);
    create table if not exists journals(id integer primary key autoincrement,user_id integer references users(id) on delete cascade,body text not null,sky_json text default '{}',created_at text default current_timestamp);
    create table if not exists messages(id integer primary key autoincrement,sender_id integer references users(id),recipient_id integer references users(id),message_type text default 'people',subject text default '',body text not null,created_at text default current_timestamp);
    create table if not exists notifications(id integer primary key autoincrement,user_id integer references users(id),notification_type text default 'general',title text not null,body text not null,link text default '',created_at text default current_timestamp);
    create table if not exists retreats(id integer primary key autoincrement,owner_id integer references users(id),title text not null,season text default '',retreat_type text default '',area text default '',preferred_dates text default '',guests integer default 1,budget text default '',lodging_preferences text default '',wellness_interests text default '',location_status text default 'Searching',status text default 'planning',created_at text default current_timestamp);
    create table if not exists retreat_partners(id integer primary key autoincrement,retreat_id integer references retreats(id) on delete cascade,business_id integer references businesses(id) on delete cascade,availability_status text default 'requested',unique(retreat_id,business_id));
    create table if not exists retreat_messages(id integer primary key autoincrement,retreat_id integer references retreats(id) on delete cascade,sender_id integer references users(id),body text not null,created_at text default current_timestamp);
    ''')
    # permanently remove known prototype/demo data from older builds
    demos=('avery@example.com','morgan@example.com','nia@example.com','marcus@example.com','jordan@example.com','sage@business.demo','maya@business.demo')
    for e in demos:
        r=c.execute('select id from users where lower(email)=?',(e,)).fetchone()
        if r:c.execute('delete from users where id=?',(r['id'],))
    c.execute("delete from businesses where slug in ('rise-flow-yoga','sacred-soul-reiki','sound-harmony','nature-vibes')")
    # Galaxy Eve - create once, never overwrite editable copy
    g=c.execute('select * from users where lower(email)=?',(GALAXY_EMAIL,)).fetchone()
    if not g:
        cur=c.execute('insert into users(name,email,password,bio,profile_headline,is_creator,creator_access,business_access,membership_access) values(?,?,?,?,?,1,1,1,1)',('Galaxy Eve',GALAXY_EMAIL,hp(os.environ.get('GALAXY_EVE_INITIAL_PASSWORD','ChangeMeGalaxyEve!')),'Wellness creator documenting connection, self-discovery, experiences and Conscious Coordination.','Conscious Coordinator • Content Creator'));gid=cur.lastrowid
    else:
        gid=g['id'];c.execute('update users set is_creator=1,creator_access=1,business_access=1,membership_access=1 where id=?',(gid,))
    b=c.execute('select * from businesses where owner_id=?',(gid,)).fetchone()
    if not b:
        c.execute("insert into businesses(owner_id,slug,business_name,creator_title,tagline,description,category,contact_email,paid_business,media_kit_enabled,retreat_participation,featured_order,status) values(?,?,?,?,?,?,?,?,1,1,1,1,'active')",(gid,'galaxy-eve','Galaxy Eve','Conscious Coordinator • Content Creator','Content • Collaborations • Creator Experiences','Content, collaborations, creator experiences, meetups, retreats and Conscious Coordination.','Creator',GALAXY_EMAIL))
    else:c.execute("update businesses set paid_business=1,media_kit_enabled=1,retreat_participation=1,featured_order=1,status='active' where owner_id=?",(gid,))
    for e in ADMIN_EMAILS:c.execute('update users set is_admin=1 where lower(email)=?',(e,))
    c.commit();c.close()

T={}
T['base.html']='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The Seasons Within</title><style>body{margin:0;background:#fbf8fd;color:#2d1d52;font-family:Arial}a{text-decoration:none;color:inherit}.top{background:white;border-bottom:1px solid #eadff2;padding:14px 4vw;display:flex;justify-content:space-between;gap:20px;align-items:center;position:sticky;top:0;z-index:5}.brand{font-family:Georgia;font-size:22px}.nav{display:flex;gap:12px;flex-wrap:wrap;font-size:14px}.btn{background:#9251d0;color:white!important;padding:10px 14px;border-radius:10px;border:0;font-weight:700}.outline{border:1px solid #9251d0;padding:9px 13px;border-radius:10px;background:white}.wrap{width:min(1120px,92vw);margin:28px auto 70px}.hero{background:linear-gradient(135deg,#f2e6fc,#fff2ed);border:1px solid #eadff2;border-radius:24px;padding:32px;display:flex;justify-content:space-between;gap:20px;align-items:center}.hero h1{font:700 44px/1.05 Georgia;margin:8px 0}.logo{width:120px;height:120px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{background:white;border:1px solid #eadff2;border-radius:18px;padding:20px;box-shadow:0 10px 26px rgba(70,35,100,.05);margin:14px 0}.card h2,.card h3,h1,h2{font-family:Georgia}.chips{display:flex;gap:7px;flex-wrap:wrap}.chips span,.chips a{background:#f0e4f8;padding:7px 9px;border-radius:999px;font-size:12px}input,textarea,select{width:100%;padding:11px;border:1px solid #eadff2;border-radius:10px;margin:5px 0 12px}textarea{min-height:100px}.sectionhead{display:flex;justify-content:space-between;align-items:end}.muted{color:#77678d}.flash{width:min(1120px,92vw);margin:10px auto;background:#f0e4f8;padding:10px;border-radius:10px}.tabs{display:flex;gap:8px;flex-wrap:wrap}.portrait{width:100px;height:100px;object-fit:cover;border-radius:50%}@media(max-width:760px){.top{align-items:flex-start;flex-direction:column}.hero h1{font-size:34px}.hero .logo{width:75px;height:75px}}</style></head><body><header class="top"><a class="brand" href="{{url_for('public_home')}}">◉ The Seasons Within</a><nav class="nav"><a href="{{url_for('community')}}">Community</a><a href="{{url_for('connections')}}">Conscious Connections</a><a href="{{url_for('creators')}}">Creators</a><a href="{{url_for('business')}}">Business Network</a><a href="{{url_for('retreats')}}">Retreats</a>{% if me %}<a href="{{url_for('messages')}}">Messages</a><a href="{{url_for('profile')}}">My Profile</a><a href="{{url_for('membership')}}">Membership</a>{% if is_admin(me) %}<a href="{{url_for('admin_page')}}">Admin</a>{% endif %}<a href="{{url_for('logout')}}">Log Out</a>{% else %}<a href="{{url_for('login')}}">Log In</a><a class="btn" href="{{url_for('join')}}">Join Free</a>{% endif %}</nav></header>{% with m=get_flashed_messages() %}{% if m %}<div class="flash">{{m|join(' • ')}}</div>{% endif %}{% endwith %}<main class="wrap">{% block content %}{% endblock %}</main></body></html>'''
T['public.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>THE SEASONS WITHIN</span><h1>Connect With Intention. Discover Your Seasons Within.</h1><p>Community, Conscious Connections, creators, wellness businesses and retreats in one coordinated platform.</p><p><a class="btn" href="{{url_for('join')}}">Join Free</a> <a class="outline" href="{{url_for('business')}}">Explore Wellness Partners</a></p></div><div class="logo">◉</div></section><div class="grid"><article class="card"><span>MOON TODAY</span><h2>Moon in {{sky.moon_sign or 'the current sky'}}</h2><p><b>{{sky.moon_phase or 'Current lunar phase'}}</b>{% if sky.moon_degree is not none %} • {{sky.moon_degree}}°{% endif %}</p><div class="chips">{% for p in ['Mercury','Venus','Mars','Jupiter','Saturn'] %}{% if sky.positions.get(p) %}<span>{{p}} {{sky.positions[p]['sign']}}</span>{% endif %}{% endfor %}</div></article><article class="card"><span>THE SEASON WE'RE IN</span><h2>{{sky.season}}</h2><p>Journal • Reflect • Share</p></article></div><div class="sectionhead"><h2>Featured Creators</h2><a href="{{url_for('creators')}}">View all →</a></div><div class="grid">{% for c in creators %}<a class="card" href="{{url_for('creator_profile',uid=c.id)}}"><h3>{{c.name}}</h3><p>{{c.creator_title or c.profile_headline}}</p><small>{{c.bio}}</small></a>{% endfor %}</div><div class="sectionhead"><h2>Businesses & Apps</h2><a href="{{url_for('business')}}">View all →</a></div><div class="grid">{% for b in businesses %}<a class="card" href="{{url_for('business_app',slug=b.slug)}}"><h3>{{b.business_name}}</h3><p>{{b.creator_title or b.category}}</p><small>{{b.tagline}}</small><p><b>{{'Hosted App' if b.paid_business else 'Free Listing'}}</b></p></a>{% else %}<div class="card">Businesses are beginning to join.</div>{% endfor %}</div><article class="card"><h2>Build a Retreat Constellation</h2><p>Coordinate dates, wellness partners and a private retreat property selected around your season, group size and budget.</p><a class="btn" href="{{url_for('retreat_build')}}">Build My Retreat Constellation</a></article>{% endblock %}'''
T['home.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>YOUR SEASONS WITHIN</span><h1>Connect With Intention. Discover Your Seasons Within.</h1><p>Your private journal, current sky and Conscious Coordination tools begin here.</p></div><div class="logo">◉</div></section><div class="grid"><article class="card"><span>YOUR JOURNAL ENTRY — TODAY</span><h2>Moon in {{reflection.sky.moon_sign or 'the current sky'}}</h2><p><b>{{reflection.sky.moon_phase or 'Current lunar phase'}}</b>{% if reflection.sky.moon_degree is not none %} • {{reflection.sky.moon_degree}}°{% endif %}</p><p>{{reflection.headline}}</p><a class="btn" href="{{url_for('journal')}}">Open My Journal</a></article><article class="card"><span>SEASONAL REFLECTION</span><h2>{{reflection.sky.season}}</h2><p>{{reflection.prompt}}</p></article></div><h2>How Do You Want to Connect?</h2><div class="grid"><a class="card" href="{{url_for('connections',mode='dating')}}"><h3>♡ Love & Dating</h3></a><a class="card" href="{{url_for('connections',mode='friendship')}}"><h3>♧ Friendship & Community</h3></a><a class="card" href="{{url_for('connections',mode='business')}}"><h3>◇ Business & Collaboration</h3></a><a class="card" href="{{url_for('retreats')}}"><h3>✦ Retreats & Experiences</h3></a></div><h2>Creators</h2><div class="grid">{% for c in creators %}<a class="card" href="{{url_for('creator_profile',uid=c.id)}}"><h3>{{c.name}}</h3><p>{{c.profile_headline}}</p></a>{% endfor %}</div><h2>Wellness Within the Community</h2><div class="grid">{% for b in businesses %}<a class="card" href="{{url_for('business_app',slug=b.slug)}}"><h3>{{b.business_name}}</h3><p>{{b.creator_title or b.category}}</p></a>{% else %}<div class="card">Businesses are beginning to join.</div>{% endfor %}</div><h2>Share Your Journey</h2><form method="post" class="card"><textarea name="body" placeholder="Share a thought or reflection..."></textarea><button class="btn">Share</button></form>{% for p in posts %}<article class="card"><b>{{p.name}}</b><small class="muted"> {{p.created_at}}</small><p>{{p.body}}</p></article>{% endfor %}{% endblock %}'''
T['join.html']='''{% extends 'base.html' %}{% block content %}<h1>Join Free</h1><form method="post" class="card"><label>Name<input name="name"></label><label>Email<input name="email" type="email"></label><label>Password<input name="password" type="password"></label><button class="btn">Create Account</button></form>{% endblock %}'''
T['login.html']='''{% extends 'base.html' %}{% block content %}<h1>Log In</h1><form method="post" class="card"><input name="email" type="email" placeholder="Email"><input name="password" type="password" placeholder="Password"><button class="btn">Log In</button></form>{% endblock %}'''
T['profile.html']='''{% extends 'base.html' %}{% block content %}<h1>{{u.name}}</h1><div class="card">{% if u.photo %}<img class="portrait" src="{{media_url(u.photo)}}">{% endif %}<h3>{{u.profile_headline}}</h3><p>{{u.bio}}</p><div class="chips"><span>Sun {{u.sun or '—'}}</span><span>Moon {{u.moon or '—'}}</span><span>Mercury {{u.mercury or '—'}}</span><span>Venus {{u.venus or '—'}}</span><span>Mars {{u.mars or '—'}}</span></div><a class="btn" href="{{url_for('profile_edit')}}">Edit My Profile</a></div><article class="card"><span>PRIVATE JOURNAL ENTRY</span><h2>{{reflection.headline}}</h2><p>{{reflection.prompt}}</p><a class="btn" href="{{url_for('journal')}}">Open My Journal</a></article>{% endblock %}'''
T['profile_edit.html']='''{% extends 'base.html' %}{% block content %}<h1>Edit My Profile</h1><form method="post" enctype="multipart/form-data" class="card"><label>Photo<input type="file" name="photo"></label><label>Name<input name="name" value="{{u.name}}"></label><label>City<input name="city" value="{{u.city}}"></label><label>Headline<input name="profile_headline" value="{{u.profile_headline}}"></label><label>About<textarea name="bio">{{u.bio}}</textarea></label><label>Birth date<input type="date" name="birth_date" value="{{u.birth_date}}"></label><label>Birth time<input type="time" name="birth_time" value="{{u.birth_time}}"></label><label><input type="checkbox" name="time_known" {% if u.time_known %}checked{% endif %}> Exact birth time known</label><label>Connection intentions<input name="connection_intentions" value="{{u.connection_intentions}}"></label><button class="btn">Save Profile</button></form>{% endblock %}'''
T['journal.html']='''{% extends 'base.html' %}{% block content %}<h1>My Private Journal</h1><article class="card"><h2>Moon in {{reflection.sky.moon_sign or 'the current sky'}}</h2><p>{{reflection.sky.moon_phase or 'Current lunar phase'}}{% if reflection.sky.moon_degree is not none %} • {{reflection.sky.moon_degree}}°{% endif %}</p><p>{{reflection.prompt}}</p><form method="post"><textarea name="body" placeholder="What are you noticing within yourself today?"></textarea><button class="btn">Save Entry</button></form></article>{% for e in entries %}<article class="card"><small>{{e.created_at}}</small><p>{{e.body}}</p></article>{% endfor %}{% endblock %}'''
T['connections.html']='''{% extends 'base.html' %}{% block content %}<h1>Conscious Connections</h1><div class="tabs"><a class="outline" href="?mode=dating">Love & Dating</a><a class="outline" href="?mode=friendship">Friendship</a><a class="outline" href="?mode=business">Business Partners</a></div><div class="grid">{% for p,s in cards %}<article class="card"><h3>{{p.name}}</h3><p>{{p.city}}</p><p>{{p.connection_intentions}}</p><b>{{s}}% Conscious Coordination</b>{% if mode=='dating' and me.membership_access %}<div class="chips"><span>Sun {{p.sun}}</span><span>Moon {{p.moon}}</span><span>Mercury {{p.mercury}}</span><span>Venus {{p.venus}}</span><span>Mars {{p.mars}}</span><span>Jupiter {{p.jupiter}}</span><span>Saturn {{p.saturn}}</span></div><p><b>Date idea:</b> choose an experience supporting both conversation and shared interests.</p>{% endif %}</article>{% else %}<article class="card">Real members will appear here as they join.</article>{% endfor %}</div>{% endblock %}'''
T['creators.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>CREATORS WITHIN THE SEASONS WITHIN</span><h1>Creators</h1><p>Content, collaborations, meetups and retreat experiences.</p></div><div class="logo">◉</div></section><div class="grid">{% for c in creators %}<a class="card" href="{{url_for('creator_profile',uid=c.id)}}"><h2>{{c.name}}</h2><p>{{c.creator_title or c.profile_headline}}</p><small>{{c.tagline or c.bio}}</small></a>{% endfor %}</div>{% endblock %}'''
T['creator_profile.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>CREATOR</span><h1>{{creator.name}}</h1><h3>{{business.creator_title if business else creator.profile_headline}}</h3><p>{{creator.bio}}</p></div><div class="logo">◉</div></section><div class="grid"><article class="card"><h2>Media Kit</h2><p><b>Content:</b> {{business.content_categories if business else ''}}</p><p><b>Audience:</b> {{business.audience_info if business else ''}}</p><p><b>Followers:</b> {{business.followers if business else ''}} • <b>Likes:</b> {{business.likes if business else ''}} • <b>Views:</b> {{business.views if business else ''}}</p></article><article class="card"><h2>Collaborations & Retreats</h2><p>{{business.collaboration_interests if business else ''}}</p><a class="btn" href="{{url_for('retreats')}}">Explore Retreats</a></article></div>{% endblock %}'''
T['business.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>THE SEASONS WITHIN</span><h1>Business Network</h1><p>Wellness. Connection. Community.</p></div><a class="btn" href="{{url_for('business_setup')}}">List Your Business Free</a></section><form><input name="q" placeholder="Search businesses, services or categories..."></form><div class="grid">{% for b in businesses %}<a class="card" href="{{url_for('business_app',slug=b.slug)}}"><h2>{{b.business_name}}</h2><p>{{b.creator_title or b.category}}</p><small>{{b.tagline or b.description}}</small><p><b>{{'Hosted App' if b.paid_business else 'Free Listing'}}</b></p></a>{% else %}<article class="card">Businesses are beginning to join.</article>{% endfor %}</div><article class="card"><b>Free to list. ${{BUSINESS_PRICE}}/month for a hosted Business App.</b></article>{% endblock %}'''
T['business_setup.html']='''{% extends 'base.html' %}{% block content %}<h1>Build My Business Profile</h1><form method="post" enctype="multipart/form-data" class="card"><label>Logo<input type="file" name="logo"></label><label>Business name<input name="business_name" value="{{b.business_name if b else ''}}"></label><label>Creator title<input name="creator_title" value="{{b.creator_title if b else ''}}"></label><label>Tagline<input name="tagline" value="{{b.tagline if b else ''}}"></label><label>Description<textarea name="description">{{b.description if b else ''}}</textarea></label><label>Category<input name="category" value="{{b.category if b else ''}}"></label><label>City<input name="city" value="{{b.city if b else ''}}"></label><label>Website<input name="website" value="{{b.website if b else ''}}"></label><label>Contact email<input name="contact_email" value="{{b.contact_email if b else me.email}}"></label><label>Phone<input name="phone" value="{{b.phone if b else ''}}"></label><label>Instagram<input name="instagram" value="{{b.instagram if b else ''}}"></label><label>TikTok<input name="tiktok" value="{{b.tiktok if b else ''}}"></label><label>YouTube<input name="youtube" value="{{b.youtube if b else ''}}"></label><label>Booking link<input name="booking_url" value="{{b.booking_url if b else ''}}"></label><label>Content categories<input name="content_categories" value="{{b.content_categories if b else ''}}"></label><label>Audience information<textarea name="audience_info">{{b.audience_info if b else ''}}</textarea></label><label>Collaboration interests<textarea name="collaboration_interests">{{b.collaboration_interests if b else ''}}</textarea></label><label><input type="checkbox" name="retreat_participation" {% if b and b.retreat_participation %}checked{% endif %}> Participate in Retreat Constellations</label><button class="btn">Save Business Profile</button></form>{% endblock %}'''
T['business_app.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>BUSINESS APP</span><h1>{{b.business_name}}</h1><h3>{{b.creator_title or b.category}}</h3><p>{{b.description}}</p></div><div class="logo">◉</div></section><div class="grid"><article class="card"><h2>Contact</h2><p>{{b.contact_email}}</p><p>{{b.phone}}</p><p>{{b.website}}</p></article><article class="card"><h2>Retreat Participation</h2><p>{{'Available for Retreat Constellations' if b.retreat_participation else 'Not currently participating'}}</p></article></div>{% endblock %}'''
T['retreats.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>THE SEASONS WITHIN</span><h1>Retreats</h1><p>Private wellness experiences and custom Retreat Constellations.</p><p><a class="btn" href="{{url_for('retreat_build')}}">Build My Retreat Constellation</a> <a class="outline" href="{{url_for('business')}}">Explore Wellness Partners</a></p></div><div class="logo">◉</div></section><h2>Participating Wellness Partners</h2><div class="grid">{% for b in partners %}<a class="card" href="{{url_for('business_app',slug=b.slug)}}"><h3>{{b.business_name}}</h3><p>{{b.creator_title or b.category}}</p></a>{% else %}<article class="card">Partners who opt into retreats will appear here.</article>{% endfor %}</div><h2>Upcoming Retreats</h2><div class="grid">{% for r in retreats %}<a class="card" href="{{url_for('retreat_detail',rid=r.id)}}"><h3>{{r.title}}</h3><p>{{r.season}} • {{r.area}}</p><small>{{r.preferred_dates}}</small></a>{% else %}<article class="card">Custom retreats will appear after they are created.</article>{% endfor %}</div>{% endblock %}'''
T['retreat_build.html']='''{% extends 'base.html' %}{% block content %}<h1>Build My Retreat Constellation</h1><form method="post" class="card"><input name="title" placeholder="Retreat name"><select name="season"><option>Spring</option><option>Summer</option><option>Autumn</option><option>Winter</option></select><input name="retreat_type" placeholder="Solo, Couples, Family, Creator..."><input name="area" placeholder="Destination / area"><input name="preferred_dates" placeholder="Preferred dates"><input name="guests" type="number" min="1" value="1"><input name="budget" placeholder="Accommodation budget"><textarea name="lodging_preferences" placeholder="Private property, bedrooms, nature, accessibility..."></textarea><textarea name="wellness_interests" placeholder="Yoga, Reiki, massage, sound, creator meetup..."></textarea><button class="btn">Create Retreat Constellation</button></form>{% endblock %}'''
T['retreat_detail.html']='''{% extends 'base.html' %}{% block content %}<h1>{{r.title}}</h1><div class="grid"><article class="card"><h2>Retreat Plan</h2><p>{{r.season}} • {{r.area}}</p><p><b>Dates:</b> {{r.preferred_dates}}</p><p><b>Guests:</b> {{r.guests}}</p><p><b>Budget:</b> {{r.budget}}</p></article><article class="card"><h2>Your Retreat Location</h2><p><b>Status:</b> {{r.location_status}}</p><p>The Seasons Within will help locate a private retreat property selected around your destination, season, group size, experience and lodging budget.</p><form method="post"><input type="hidden" name="action" value="location"><button class="btn">Request Retreat Location Search</button></form></article></div><h2>Retreat Constellation</h2><div class="grid">{% for p in partners %}<article class="card"><h3>{{p.business_name}}</h3><p>{{p.creator_title or p.category}}</p><p>Status: {{p.availability_status}}</p></article>{% endfor %}</div><form method="post" class="card"><input type="hidden" name="action" value="partner"><select name="business_id">{% for b in eligible %}<option value="{{b.id}}">{{b.business_name}} — {{b.category}}</option>{% endfor %}</select><button class="btn">Request Partner Availability</button></form><h2>Retreat Coordination</h2><article class="card"><p>Coordinate guest dates, business availability, location and retreat details here.</p><form method="post"><input type="hidden" name="action" value="message"><textarea name="body" placeholder="Message about dates, availability or retreat details..."></textarea><button class="btn">Send Retreat Message</button></form></article>{% for m in msgs %}<article class="card"><b>{{m.sender_name}}</b><small>{{m.created_at}}</small><p>{{m.body}}</p></article>{% endfor %}{% endblock %}'''
T['messages.html']='''{% extends 'base.html' %}{% block content %}<h1>Messages</h1><form method="post" class="card"><select name="recipient_id">{% for p in people %}<option value="{{p.id}}">{{p.name}}</option>{% endfor %}</select><select name="message_type"><option value="people">People</option><option value="dating">Dating</option><option value="business">Business</option><option value="creator">Creator</option><option value="retreat">Retreat</option></select><input name="subject" placeholder="Subject"><textarea name="body" placeholder="Message"></textarea><button class="btn">Send</button></form>{% for m in inbox %}<article class="card"><span>{{m.message_type|upper}}</span><h3>{{m.subject or 'Message'}}</h3><b>{{m.sender_name}}</b><p>{{m.body}}</p></article>{% else %}<article class="card">Your messages will appear here.</article>{% endfor %}{% endblock %}'''
T['membership.html']='''{% extends 'base.html' %}{% block content %}<section class="hero"><div><span>MEMBERSHIP</span><h1>Connect With Intention. Discover Your Seasons Within.</h1></div><div class="logo">◉</div></section><div class="grid"><article class="card"><h2>Free</h2><p>Community • Basic profile • Private journal • Basic natal placements • Free business listing</p></article><article class="card"><h2>The Seasons Within Membership — ${{MEMBER_PRICE}}/month</h2><p>Full natal chart • Expanded Conscious Coordination • dating compatibility • date ideas • advanced notifications</p></article><article class="card"><h2>Business Network — ${{BUSINESS_PRICE}}/month</h2><p>Hosted Business App • creator/business tools • collaboration matching • Business Alignment Reflection • Retreat Constellation participation</p></article></div>{% endblock %}'''
T['admin.html']='''{% extends 'base.html' %}{% block content %}<h1>Admin</h1><div class="grid"><article class="card"><h2>Users</h2>{% for u in users %}<p>{{u.name}} — {{u.email}} {% if u.is_admin %}<b>ADMIN</b>{% endif %}</p>{% endfor %}</article><article class="card"><h2>Businesses</h2>{% for b in businesses %}<p>{{b.business_name}} — {{b.status}}</p>{% endfor %}</article><article class="card"><h2>Retreats</h2>{% for r in retreats %}<p>{{r.title}} — {{r.status}}</p>{% endfor %}</article></div>{% endblock %}'''
app.jinja_loader=DictLoader(T)
app.jinja_env.globals.update(media_url=media_url,is_admin=admin,MEMBER_PRICE=MEMBER_PRICE,BUSINESS_PRICE=BUSINESS_PRICE)
@app.context_processor
def ctx():return {'me':me()}
@app.route('/uploads/<path:filename>')
def uploads(filename): return send_from_directory(UPLOADS,filename)
@app.route('/')
def public_home():
    c=conn();bs=c.execute("select * from businesses where status='active' order by featured_order,id limit 8").fetchall();cs=c.execute("select u.*,b.creator_title,b.tagline from users u left join businesses b on b.owner_id=u.id where u.is_creator=1 order by coalesce(b.featured_order,999),u.id").fetchall();c.close();return render_template('public.html',businesses=bs,creators=cs,sky=current_sky())
@app.route('/join',methods=['GET','POST'])
def join():
    if request.method=='POST':
        n=request.form.get('name','').strip();e=request.form.get('email','').strip().lower();p=request.form.get('password','')
        if not n or not e or len(p)<6:flash('Enter name, email and a password of at least 6 characters.')
        else:
            c=conn()
            try:
                cur=c.execute('insert into users(name,email,password) values(?,?,?)',(n,e,hp(p)));c.commit();session['uid']=cur.lastrowid;c.close();return redirect(url_for('profile_edit'))
            except sqlite3.IntegrityError:c.close();flash('That email already has an account.')
    return render_template('join.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        e=request.form.get('email','').strip().lower();p=request.form.get('password','');c=conn();u=c.execute('select * from users where lower(email)=?',(e,)).fetchone();c.close()
        if u and u['password']==hp(p):session['uid']=u['id'];return redirect(request.args.get('next') or url_for('home'))
        flash('Email or password not recognized.')
    return render_template('login.html')
@app.route('/logout')
def logout():session.clear();return redirect(url_for('public_home'))
@app.route('/home',methods=['GET','POST'])
@login_required
def home():
    u=me();c=conn()
    if request.method=='POST' and request.form.get('body','').strip():c.execute('insert into posts(user_id,body) values(?,?)',(u['id'],request.form['body'].strip()));c.commit()
    posts=c.execute('select p.*,u.name from posts p join users u on u.id=p.user_id order by p.id desc limit 30').fetchall();bs=c.execute("select * from businesses where status='active' order by featured_order,id limit 6").fetchall();cs=c.execute('select * from users where is_creator=1 order by id limit 6').fetchall();c.close();return render_template('home.html',reflection=journal_reflection(u),posts=posts,businesses=bs,creators=cs)
@app.route('/community',methods=['GET','POST'])
@login_required
def community():return home()
@app.route('/profile')
@login_required
def profile():return render_template('profile.html',u=me(),reflection=journal_reflection(me()))
@app.route('/profile/edit',methods=['GET','POST'])
@login_required
def profile_edit():
    u=me()
    if request.method=='POST':
        ph=save_file(request.files.get('photo'),f'user{u["id"]}') or u['photo'];c=conn();c.execute('update users set name=?,city=?,profile_headline=?,bio=?,birth_date=?,birth_time=?,time_known=?,connection_intentions=?,photo=? where id=?',(request.form.get('name',''),request.form.get('city',''),request.form.get('profile_headline',''),request.form.get('bio',''),request.form.get('birth_date',''),request.form.get('birth_time',''),1 if request.form.get('time_known') else 0,request.form.get('connection_intentions',''),ph,u['id']));c.commit();nu=c.execute('select * from users where id=?',(u['id'],)).fetchone();ch=chart_for(nu)
        if ch:
            vals=[ch.get(k,('',0))[0] for k in ('Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto')];c.execute('update users set sun=?,moon=?,mercury=?,venus=?,mars=?,jupiter=?,saturn=?,uranus=?,neptune=?,pluto=? where id=?',(*vals,u['id']));c.commit()
        c.close();flash('Profile saved.');return redirect(url_for('profile'))
    return render_template('profile_edit.html',u=u)
@app.route('/journal',methods=['GET','POST'])
@login_required
def journal():
    u=me();c=conn()
    if request.method=='POST' and request.form.get('body','').strip():c.execute('insert into journals(user_id,body,sky_json) values(?,?,?)',(u['id'],request.form['body'].strip(),json.dumps(current_sky())));c.commit()
    es=c.execute('select * from journals where user_id=? order by id desc',(u['id'],)).fetchall();c.close();return render_template('journal.html',reflection=journal_reflection(u),entries=es)
@app.route('/connections')
@login_required
def connections():
    u=me();mode=request.args.get('mode','friendship');c=conn();ps=c.execute('select * from users where id<>? order by id desc',(u['id'],)).fetchall();c.close();return render_template('connections.html',cards=[(p,coord(u,p,mode)) for p in ps],mode=mode)
@app.route('/creators')
def creators():
    c=conn();rows=c.execute('select u.*,b.creator_title,b.tagline from users u left join businesses b on b.owner_id=u.id where u.is_creator=1 order by coalesce(b.featured_order,999),u.id').fetchall();c.close();return render_template('creators.html',creators=rows)
@app.route('/creator/<int:uid>')
def creator_profile(uid):
    c=conn();u=c.execute('select * from users where id=? and is_creator=1',(uid,)).fetchone();b=c.execute('select * from businesses where owner_id=?',(uid,)).fetchone();c.close();
    if not u:abort(404)
    return render_template('creator_profile.html',creator=u,business=b)
@app.route('/business')
def business():
    q=request.args.get('q','').strip();c=conn();rows=c.execute("select * from businesses where status='active' and (?='' or business_name like ? or category like ? or description like ?) order by featured_order,id",(q,f'%{q}%',f'%{q}%',f'%{q}%')).fetchall();c.close();return render_template('business.html',businesses=rows)
@app.route('/business/setup',methods=['GET','POST'])
@login_required
def business_setup():
    u=me();c=conn();b=c.execute('select * from businesses where owner_id=?',(u['id'],)).fetchone()
    if request.method=='POST':
        name=request.form.get('business_name','').strip()
        if not name:flash('Business name required.');c.close();return render_template('business_setup.html',b=b)
        logo=save_file(request.files.get('logo'),f'biz{u["id"]}') or (b['logo'] if b else '');vals=(name,request.form.get('creator_title',''),request.form.get('tagline',''),request.form.get('description',''),request.form.get('category',''),request.form.get('city',''),request.form.get('website',''),request.form.get('contact_email',''),request.form.get('phone',''),logo,request.form.get('instagram',''),request.form.get('tiktok',''),request.form.get('youtube',''),request.form.get('booking_url',''),request.form.get('content_categories',''),request.form.get('audience_info',''),request.form.get('collaboration_interests',''),1 if request.form.get('retreat_participation') else 0)
        if b:c.execute('update businesses set business_name=?,creator_title=?,tagline=?,description=?,category=?,city=?,website=?,contact_email=?,phone=?,logo=?,instagram=?,tiktok=?,youtube=?,booking_url=?,content_categories=?,audience_info=?,collaboration_interests=?,retreat_participation=? where owner_id=?',(*vals,u['id']))
        else:c.execute("insert into businesses(owner_id,slug,business_name,creator_title,tagline,description,category,city,website,contact_email,phone,logo,instagram,tiktok,youtube,booking_url,content_categories,audience_info,collaboration_interests,retreat_participation,paid_business,status) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active')",(u['id'],slugify(name),*vals,1 if u['business_access'] else 0))
        c.commit();c.close();flash('Business profile saved.');return redirect(url_for('business'))
    c.close();return render_template('business_setup.html',b=b)
@app.route('/app/<slug>')
def business_app(slug):
    c=conn();b=c.execute("select * from businesses where slug=? and status='active'",(slug,)).fetchone();c.close();
    if not b:abort(404)
    return render_template('business_app.html',b=b)
@app.route('/retreats')
def retreats():
    c=conn();rs=c.execute("select * from retreats where status<>'cancelled' order by id desc").fetchall();ps=c.execute("select * from businesses where status='active' and retreat_participation=1 order by featured_order,id").fetchall();c.close();return render_template('retreats.html',retreats=rs,partners=ps)
@app.route('/retreats/build',methods=['GET','POST'])
@login_required
def retreat_build():
    if request.method=='POST':
        u=me();c=conn();cur=c.execute('insert into retreats(owner_id,title,season,retreat_type,area,preferred_dates,guests,budget,lodging_preferences,wellness_interests) values(?,?,?,?,?,?,?,?,?,?)',(u['id'],request.form.get('title','My Retreat'),request.form.get('season',''),request.form.get('retreat_type',''),request.form.get('area',''),request.form.get('preferred_dates',''),int(request.form.get('guests') or 1),request.form.get('budget',''),request.form.get('lodging_preferences',''),request.form.get('wellness_interests','')));c.commit();rid=cur.lastrowid;c.close();return redirect(url_for('retreat_detail',rid=rid))
    return render_template('retreat_build.html')
@app.route('/retreat/<int:rid>',methods=['GET','POST'])
@login_required
def retreat_detail(rid):
    u=me();c=conn();r=c.execute('select * from retreats where id=?',(rid,)).fetchone()
    if not r:c.close();abort(404)
    if request.method=='POST':
        a=request.form.get('action')
        if a=='partner':c.execute('insert or ignore into retreat_partners(retreat_id,business_id) values(?,?)',(rid,int(request.form.get('business_id'))));c.commit()
        elif a=='location':c.execute("update retreats set location_status='Search Requested' where id=?",(rid,));c.commit()
        elif a=='message' and request.form.get('body','').strip():c.execute('insert into retreat_messages(retreat_id,sender_id,body) values(?,?,?)',(rid,u['id'],request.form['body'].strip()));c.commit()
    partners=c.execute('select rp.*,b.* from retreat_partners rp join businesses b on b.id=rp.business_id where rp.retreat_id=?',(rid,)).fetchall();eligible=c.execute("select * from businesses where status='active' and retreat_participation=1 order by featured_order,id").fetchall();msgs=c.execute('select rm.*,u.name sender_name from retreat_messages rm join users u on u.id=rm.sender_id where retreat_id=? order by rm.id',(rid,)).fetchall();c.close();return render_template('retreat_detail.html',r=r,partners=partners,eligible=eligible,msgs=msgs)
@app.route('/messages',methods=['GET','POST'])
@login_required
def messages():
    u=me();c=conn()
    if request.method=='POST' and request.form.get('body','').strip():c.execute('insert into messages(sender_id,recipient_id,message_type,subject,body) values(?,?,?,?,?)',(u['id'],int(request.form.get('recipient_id')),request.form.get('message_type','people'),request.form.get('subject',''),request.form['body'].strip()));c.commit()
    inbox=c.execute('select m.*,u.name sender_name from messages m join users u on u.id=m.sender_id where m.recipient_id=? order by m.id desc',(u['id'],)).fetchall();people=c.execute('select id,name from users where id<>? order by name',(u['id'],)).fetchall();c.close();return render_template('messages.html',inbox=inbox,people=people)
@app.route('/membership')
def membership():return render_template('membership.html')
@app.route('/admin')
@admin_required
def admin_page():
    c=conn();us=c.execute('select * from users order by id desc').fetchall();bs=c.execute('select * from businesses order by featured_order,id').fetchall();rs=c.execute('select * from retreats order by id desc').fetchall();c.close();return render_template('admin.html',users=us,businesses=bs,retreats=rs)
init_db()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5055')))
