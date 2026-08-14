
import os, sqlite3, hashlib, secrets, json, html, re
from pathlib import Path
from functools import wraps
from datetime import datetime, date
from flask import Flask, request, redirect, url_for, session, flash, send_from_directory, Response, send_file

BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get("PERSISTENT_DATA_DIR", BASE/"data")); DATA.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get("DATABASE_PATH", DATA/"the_seasons_within_master_v2.db"))
UPLOADS=Path(os.environ.get("UPLOAD_DIR", DATA/"uploads")); UPLOADS.mkdir(parents=True,exist_ok=True)

app=Flask(__name__); app.secret_key=os.environ.get("SECRET_KEY","change-this-on-render")
GALAXY_EMAIL=os.environ.get("GALAXY_EVE_EMAIL","galaxyeve@theseasonswithin.local").lower()
ADMINS={x.lower() for x in [GALAXY_EMAIL,os.environ.get("ADMIN_EMAIL_1",""),os.environ.get("ADMIN_EMAIL_2","")] if x}

CSS = '\n:root{--plum:#34204f;--purple:#8f63ba;--purple2:#a978c7;--lav:#f2e9f8;--blush:#fff1ef;--line:#eadff1;--muted:#766a80;--gold:#d7bd62;--shadow:0 14px 38px rgba(70,45,95,.09)}\n*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--plum);background:linear-gradient(180deg,#fcf9fd,#fffaf8 58%,#faf6fc);min-height:100vh}\na{text-decoration:none;color:inherit}button,input,textarea,select{font:inherit}button{cursor:pointer}h1,h2,h3{font-family:Georgia,"Times New Roman",serif}h1{font-size:clamp(30px,5vw,48px);line-height:1.05;margin:8px 0 12px}h2{font-size:clamp(22px,3vw,30px);margin:6px 0 12px}\n.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.96);backdrop-filter:blur(18px);border-bottom:1px solid var(--line)}\n.topin{width:min(1240px,94vw);min-height:78px;margin:auto;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:18px}\n.brand{display:flex;align-items:center;gap:11px}.logo{width:50px;height:50px;border-radius:50%;padding:4px;background:#fff}.brand strong{display:block;font:700 19px Georgia}.brand small{display:block;font-size:9px;letter-spacing:1.2px;color:var(--muted);text-transform:uppercase}\n.nav{display:flex;justify-content:center;gap:5px;flex-wrap:wrap}.nav a,.acct a{padding:10px 12px;border-radius:999px;font-weight:800;color:#5e5068;font-size:13px}.nav a.active,.nav a:hover{background:var(--lav);color:#68418c}.acct{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800}\n.page{width:min(1140px,92vw);margin:28px auto 118px}.hero,.card{border:1px solid var(--line);border-radius:24px;background:#fff;box-shadow:var(--shadow)}.hero{padding:28px;background:linear-gradient(135deg,#f0e2fa,#fff1ed)}.card{padding:20px;margin:15px 0}.premium{border:2px solid var(--gold)}\n.badge,.chip{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;background:var(--lav);font-size:10px;font-weight:900}.gold{background:#fff8df;border:1px solid var(--gold);color:#765615}.heart{background:#fff0f4;color:#905068}\n.actions,.chips,.steps{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.btn,.out,button{display:inline-flex;align-items:center;justify-content:center;border-radius:11px;min-height:40px;padding:9px 14px;font-weight:800;border:1px solid var(--purple)}.btn,button{background:linear-gradient(135deg,var(--purple),var(--purple2));color:#fff}.out{background:#fff;color:#68418c;border-color:#cdb7dc}\n.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:15px}.two{display:grid;grid-template-columns:1fr 1fr;gap:15px}.muted{color:var(--muted);line-height:1.55}.small{font-size:12px}\n.input,input,textarea,select{width:100%;padding:12px;border:1px solid #dfd1e8;border-radius:12px;background:#fff;margin:5px 0 12px;color:var(--plum)}textarea{min-height:110px}\n.media{height:225px;border-radius:16px;background:linear-gradient(135deg,#e4d2f0,#f8ded8);display:grid;place-items:center;overflow:hidden}.media img,.media video{width:100%;height:100%;object-fit:cover}.media.logo-box img{object-fit:contain;padding:34px}.avatar{width:54px;height:54px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#c89de1,#efbcc6);color:#fff;font-weight:900;overflow:hidden}.avatar img{width:100%;height:100%;object-fit:cover}.post{display:grid;grid-template-columns:54px 1fr;gap:12px}\n.fact{padding:13px;border:1px solid var(--line);border-radius:14px;background:#fcf9fd;margin:7px 0}.fact small{display:block;color:var(--muted)}.meter{height:10px;background:#eee6f1;border-radius:999px;overflow:hidden}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--purple),#c992c4)}\n.steps span{padding:8px 10px;border:1px solid var(--line);border-radius:999px;background:#fff;font-size:10px;font-weight:900}.sectiontitle{display:flex;align-items:end;justify-content:space-between;gap:10px;margin-top:26px}.appnav{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}.appnav span{padding:8px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;font-size:10px;font-weight:900}\n.flash{width:min(1140px,92vw);margin:12px auto;padding:12px;border:1px solid #d9c6e7;border-radius:12px;background:#f7eefb}.bottom{display:none}\n@media(max-width:820px){body{padding-bottom:84px}.topin{min-height:68px;display:flex;justify-content:center}.nav,.acct{display:none}.page{width:94vw;margin-top:18px}.two{grid-template-columns:1fr}.bottom{position:fixed;left:50%;bottom:9px;transform:translateX(-50%);z-index:50;width:95vw;display:grid;grid-template-columns:repeat(5,1fr);padding:7px;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.97);backdrop-filter:blur(18px);box-shadow:0 15px 45px rgba(70,45,95,.18)}.bottom a{text-align:center;padding:7px 4px;border-radius:13px;color:#75677f;font-size:9px;font-weight:900}.bottom a b{display:block;font-size:18px}.bottom a.active{background:var(--lav);color:#68418c}}\n'
LOGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n<circle cx="50" cy="50" r="47" fill="#f4ebf9"/>\n<path d="M50 6A44 44 0 0 1 94 50H50Z" fill="#d6b8e5"/>\n<path d="M94 50A44 44 0 0 1 50 94V50Z" fill="#efc4cb"/>\n<path d="M50 94A44 44 0 0 1 6 50H50Z" fill="#ead7ad"/>\n<path d="M6 50A44 44 0 0 1 50 6V50Z" fill="#c9b7df"/>\n<circle cx="50" cy="50" r="18" fill="#fff"/>\n</svg>'

def cdb():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def esc(x): return html.escape(str(x or ""))
def hp(p): return hashlib.sha256(("tsw::"+p).encode()).hexdigest()
def slug(x): return re.sub(r"[^a-z0-9]+","-",x.lower()).strip("-") or secrets.token_hex(4)
def me():
    if not session.get("uid"): return None
    c=cdb(); u=c.execute("select * from users where id=?",(session["uid"],)).fetchone(); c.close(); return u
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not me(): return redirect(url_for("login",next=request.path))
        return f(*a,**k)
    return w
def save_file(fs,prefix):
    if not fs or not fs.filename:return ""
    ext=Path(fs.filename).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".gif",".mp4",".mov",".webm",".m4v"}: return ""
    n=f"{prefix}-{secrets.token_hex(5)}{ext}"; fs.save(UPLOADS/n); return n
def notify(uid,title,body,kind="General"):
    c=cdb(); c.execute("insert into notifications(user_id,title,body,kind) values(?,?,?,?)",(uid,title,body,kind)); c.commit(); c.close()
def notify_all(title,body,kind="Community",exclude=None):
    c=cdb()
    for r in c.execute("select id from users").fetchall():
        if r["id"]!=exclude:c.execute("insert into notifications(user_id,title,body,kind) values(?,?,?,?)",(r["id"],title,body,kind))
    c.commit(); c.close()

def init_db():
    c=cdb(); c.executescript("""
    create table if not exists users(id integer primary key autoincrement,name text,email text unique,password_hash text,photo text default '',city text default '',headline text default '',bio text default '',birth_date text default '',birth_time text default '',birth_city text default '',birth_state text default '',birth_country text default '',time_known integer default 0,full_member integer default 0,business_access integer default 0,is_admin integer default 0);
    create table if not exists posts(id integer primary key autoincrement,user_id integer,body text,photo text default '',post_as text default 'member',created_at text default current_timestamp);
    create table if not exists journal(id integer primary key autoincrement,user_id integer,title text,body text,category text,visibility text default 'private',created_at text default current_timestamp);
    create table if not exists messages(id integer primary key autoincrement,sender_id integer,recipient_id integer,source text,subject text,body text,created_at text default current_timestamp);
    create table if not exists notifications(id integer primary key autoincrement,user_id integer,title text,body text,kind text,created_at text default current_timestamp);
    create table if not exists connections(user_id integer primary key,types text,emotional_regulation text,emotional_support text,communication text,conflict text,repair text,accountability text,boundaries text,trust text,love_languages text,lifestyle_values text,business_style text,retreat_style text,about text);
    create table if not exists businesses(id integer primary key autoincrement,owner_id integer,slug text unique,name text,title text,category text,city text,tagline text,description text,logo text default '',cover text default '',website text,instagram text,tiktok text,youtube text,modules text,status text default 'active',featured integer default 0);
    create table if not exists business_dev(user_id integer primary key,stage text,business_name text,strengths text,target_customer text,problem text,solution text,vision text,values_text text,usp text,offers text,pricing text,revenue text,competitors text,operations text,startup text,marketing text,goals90 text,goals1yr text);
    create table if not exists business_plans(id integer primary key autoincrement,user_id integer,business_name text,version integer,sections text,created_at text default current_timestamp);
    create table if not exists retreats(id integer primary key autoincrement,user_id integer,title text,type text,season text,dates text,guests text,budget text,wellness text,lodging text,businesses text,created_at text default current_timestamp);
    """)
    for e in ADMINS:
        c.execute("update users set full_member=1,business_access=1,is_admin=1 where lower(email)=?",(e,))
    c.commit(); c.close()

def logo_img(cls="logo"):
    return f"<img class='{cls}' src='{url_for('brand_logo')}' alt='The Seasons Within logo'>"

def shell(title,body,active=""):
    u=me()
    nav=[("Home","home"),("Community","community"),("My Profile","profile"),("Business Network","business"),("Retreats","retreats"),("Membership","membership")]
    nav_html="".join(f"<a class='{'active' if active==ep else ''}' href='{url_for(ep)}'>{label}</a>" for label,ep in nav if u or ep in {"home","business","retreats","membership"})
    acct=(f"<a href='{url_for('journal')}'>Journal</a><a href='{url_for('notifications')}'>Notifications</a><a href='{url_for('logout')}'>Log Out</a>" if u else f"<a href='{url_for('login')}'>Log In</a><a class='btn' href='{url_for('join')}'>Join Free</a>")
    flashes="".join(f"<div class='flash'>{esc(x)}</div>" for x in __import__("flask").get_flashed_messages())
    bottom=""
    if u:
        bottom=f"""<nav class='bottom'><a href='{url_for("home")}'><b>⌂</b>Home</a><a href='{url_for("community")}'><b>☼</b>Community</a><a href='{url_for("profile")}'><b>◉</b>Profile</a><a href='{url_for("business")}'><b>◇</b>Business</a><a href='{url_for("more")}'><b>•••</b>More</a></nav>"""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)} — The Seasons Within</title><style>{CSS}</style></head><body><header class='top'><div class='topin'><a class='brand' href='{url_for("home")}'>{logo_img()}<div><strong>The Seasons Within</strong><small>Conscious Coordination</small></div></a><nav class='nav'>{nav_html}</nav><div class='acct'>{acct}</div></div></header>{flashes}<main class='page'>{body}</main>{bottom}</body></html>"""

@app.route("/brand-logo.svg")
def brand_logo(): return Response(LOGO,mimetype="image/svg+xml")
@app.route("/uploads/<path:filename>")
def uploads(filename): return send_from_directory(UPLOADS,filename)

@app.route("/")
def home():
    c=cdb(); biz=c.execute("select * from businesses where status='active' order by featured desc,id").fetchall(); c.close()
    cards=""
    for b in biz:
        image=f"<img src='{url_for('uploads',filename=b['cover'])}'>" if b["cover"] else (f"<img src='{url_for('uploads',filename=b['logo'])}' style='object-fit:contain;padding:30px'>" if b["logo"] else logo_img(""))
        cards+=f"<article class='card {'premium' if b['featured'] else ''}'><span class='badge {'gold' if b['featured'] else ''}'>{'FEATURED HOSTED APP' if b['featured'] else 'FREE HOSTED APP'}</span><div class='media logo-box'>{image}</div><h2>{esc(b['name'])}</h2><p><b>{esc(b['title'] or b['category'])}</b></p><p>{esc(b['tagline'])}</p><a class='btn' href='{url_for('business_app',slug=b['slug'])}'>Open App</a></article>"
    if not cards: cards="<div class='card'><p>Businesses will appear here as they join.</p></div>"
    body=f"""<section class='hero'><span class='badge'>THE SEASONS WITHIN</span><h1>Better Relationships With Self, Others, Purpose & Experience</h1><p class='muted'>A wellness community where members can reflect, connect privately, coordinate relationships and collaborations, discover real businesses, build a free Hosted Business App, and design meaningful Retreat experiences.</p><div class='actions'><a class='btn' href='{url_for("business")}'>Explore Businesses & Apps</a><a class='out' href='{url_for("retreats")}'>Explore Retreats</a></div></section><div class='card'><input placeholder='Search businesses, services, classes, creators, retreats or wellness experiences...'><div class='chips'><span class='chip'>Yoga</span><span class='chip'>Reiki</span><span class='chip'>Massage</span><span class='chip'>Creators</span><span class='chip'>Coaching</span><span class='chip'>Retreats</span></div></div><h2>All Active Hosted Business Apps</h2><div class='grid'>{cards}</div><div class='grid'><div class='card'><h2>Moon Today</h2><p class='muted'>Current-sky reflection and a short wellness reset belong here.</p></div><div class='card'><h2>Design Your Own Retreat</h2><a class='btn' href='{url_for("retreat_builder")}'>Build My Retreat</a></div><div class='card premium'><span class='badge gold'>$79.99 BUSINESS DEVELOPMENT</span><h2>Professional Business Plan Package</h2><a class='btn' href='{url_for("business_dev")}'>Start Business Development</a></div></div>"""
    return shell("Home",body,"home")

@app.route("/join",methods=["GET","POST"])
def join():
    if request.method=="POST":
        try:
            email=request.form["email"].strip().lower(); admin=1 if email in ADMINS else 0
            c=cdb(); cur=c.execute("insert into users(name,email,password_hash,birth_date,full_member,business_access,is_admin) values(?,?,?,?,?,?,?)",(request.form["name"],email,hp(request.form["password"]),request.form.get("birth_date",""),admin,admin,admin)); c.commit(); session["uid"]=cur.lastrowid; c.close(); return redirect(url_for("profile"))
        except sqlite3.IntegrityError: flash("That email already has an account. Please log in.")
    return shell("Join Free","""<section class='hero'><h1>Create Your Free Account</h1><p>One permanent account for Community, Journal, Business, Retreats and Conscious Coordination.</p></section><form class='card' method='post'><input name='name' placeholder='Name' required><input name='email' type='email' placeholder='Email' required><input name='password' type='password' placeholder='Password' required><input name='birth_date' type='date'><button>Create Free Account</button></form>""")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=cdb(); u=c.execute("select * from users where lower(email)=?",(request.form["email"].lower().strip(),)).fetchone(); c.close()
        if u and u["password_hash"]==hp(request.form["password"]): session["uid"]=u["id"]; return redirect(url_for("profile"))
        flash("Email or password did not match.")
    return shell("Log In","""<section class='hero'><h1>Log In</h1></section><form class='card' method='post'><input name='email' type='email' placeholder='Email' required><input name='password' type='password' placeholder='Password' required><button>Log In</button></form>""")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("home"))

@app.route("/community",methods=["GET","POST"])
@login_required
def community():
    u=me()
    if request.method=="POST":
        pa=request.form.get("post_as","member")
        if pa=="official" and not u["is_admin"]: return "Forbidden",403
        photo=save_file(request.files.get("photo"),f"post{u['id']}")
        c=cdb(); c.execute("insert into posts(user_id,body,photo,post_as) values(?,?,?,?)",(u["id"],request.form["body"],photo,pa)); c.commit(); c.close()
        if pa=="official": notify_all("The Seasons Within Posted",request.form["body"][:120],"Community",u["id"])
        elif u["email"].lower()==GALAXY_EMAIL: notify_all("Galaxy Eve Posted",request.form["body"][:120],"Community",u["id"])
        return redirect(url_for("community"))
    c=cdb(); rows=c.execute("select p.*,u.name,u.photo profile_photo from posts p join users u on u.id=p.user_id order by p.id desc").fetchall(); c.close()
    posts=""
    for p in rows:
        av=logo_img("") if p["post_as"]=="official" else (f"<img src='{url_for('uploads',filename=p['profile_photo'])}'>" if p["profile_photo"] else esc(p["name"][:1]))
        msg="" if p["post_as"]=="official" or p["user_id"]==u["id"] else f"<a class='out' href='{url_for('compose_message',uid=p['user_id'],source='Community')}'>Message {esc(p['name'])}</a>"
        pic=f"<div class='media'><img src='{url_for('uploads',filename=p['photo'])}'></div>" if p["photo"] else ""
        posts+=f"<article class='card'><div class='post'><div class='avatar'>{av}</div><div><span class='badge'>{'THE SEASONS WITHIN' if p['post_as']=='official' else esc(p['name'])}</span><p>{esc(p['body'])}</p>{pic}{msg}</div></div></article>"
    admin_form=f"<form class='card premium' method='post'><input type='hidden' name='post_as' value='official'><h2>Post as The Seasons Within</h2><textarea name='body' required></textarea><button>Publish Official Post</button></form>" if u["is_admin"] else ""
    body=f"""<section class='hero'><span class='badge'>MEMBERS ONLY</span><h1>Community</h1><p>Daily reflection, wellness, official posts and real member posts. No public comments.</p></section><div class='grid'><div class='card'><h2>Moon Today</h2></div><div class='card'><h2>60-Second Reset</h2></div><div class='card'><h2>Journal Prompt</h2><a class='out' href='{url_for("journal")}'>Open My Journal</a></div></div>{admin_form}<form class='card' method='post' enctype='multipart/form-data'><input type='hidden' name='post_as' value='member'><textarea name='body' placeholder='Share with the community...' required></textarea><input type='file' name='photo'><button>Post to Community</button></form>{posts}"""
    return shell("Community",body,"community")

@app.route("/profile",methods=["GET","POST"])
@login_required
def profile():
    u=me()
    if request.method=="POST":
        photo=save_file(request.files.get("photo"),f"user{u['id']}") or u["photo"]
        c=cdb(); c.execute("update users set name=?,photo=?,city=?,headline=?,bio=?,birth_date=?,birth_time=?,birth_city=?,birth_state=?,birth_country=?,time_known=? where id=?",(request.form["name"],photo,request.form.get("city",""),request.form.get("headline",""),request.form.get("bio",""),request.form.get("birth_date",""),request.form.get("birth_time",""),request.form.get("birth_city",""),request.form.get("birth_state",""),request.form.get("birth_country",""),1 if request.form.get("time_known") else 0,u["id"])); c.commit(); c.close(); flash("Profile saved."); return redirect(url_for("profile"))
    pic=f"<div class='media'><img src='{url_for('uploads',filename=u['photo'])}'></div>" if u["photo"] else f"<div class='media logo-box'>{logo_img('')}</div>"
    body=f"""<section class='hero {'premium' if u['full_member'] else ''}'><span class='badge {'gold' if u['full_member'] else ''}'>{'★ FULL MEMBER • CONSCIOUS COORDINATION' if u['full_member'] else 'FREE MEMBER'}</span><h1>{esc(u['name'])}</h1><p>{esc(u['headline'])} • {esc(u['city'])}</p><p>{esc(u['bio'])}</p></section><div class='two'><div class='card'>{pic}</div><form class='card' method='post' enctype='multipart/form-data'><h2>Edit Profile</h2><input name='name' value='{esc(u['name'])}'><input name='city' value='{esc(u['city'])}' placeholder='City'><input name='headline' value='{esc(u['headline'])}' placeholder='Headline'><textarea name='bio'>{esc(u['bio'])}</textarea><input name='photo' type='file'><h3>Birth Information</h3><input name='birth_date' type='date' value='{esc(u['birth_date'])}'><input name='birth_time' type='time' value='{esc(u['birth_time'])}'><input name='birth_city' value='{esc(u['birth_city'])}' placeholder='Birth City'><input name='birth_state' value='{esc(u['birth_state'])}' placeholder='Birth State / Province'><input name='birth_country' value='{esc(u['birth_country'])}' placeholder='Birth Country'><label><input style='width:auto' type='checkbox' name='time_known' {'checked' if u['time_known'] else ''}> Exact birth time known</label><button>Save Profile</button></form></div>"""
    return shell("My Profile",body,"profile")

@app.route("/journal",methods=["GET","POST"])
@login_required
def journal():
    u=me()
    if request.method=="POST":
        c=cdb(); c.execute("insert into journal(user_id,title,body,category,visibility) values(?,?,?,?,?)",(u["id"],request.form.get("title",""),request.form["body"],request.form.get("category","Reflection"),request.form.get("visibility","private")))
        if request.form.get("visibility")=="community": c.execute("insert into posts(user_id,body) values(?,?)",(u["id"],request.form["body"]))
        c.commit(); c.close(); return redirect(url_for("journal"))
    c=cdb(); rows=c.execute("select * from journal where user_id=? order by id desc",(u["id"],)).fetchall(); c.close()
    items="".join(f"<div class='card'><span class='badge'>{esc(x['category'])}</span><h3>{esc(x['title'])}</h3><p>{esc(x['body'])}</p></div>" for x in rows)
    body=f"""<section class='hero'><span class='badge'>PRIVATE HUB</span><h1>My Journal</h1></section><div class='grid'><a class='btn' href='{url_for("messages")}'>Journal Inbox</a><a class='out' href='{url_for("business_dashboard")}'>Business</a><a class='out' href='{url_for("retreat_builder")}'>Retreats</a><a class='out' href='{url_for("connections")}'>Conscious Coordination</a></div><form class='card' method='post'><input name='title' placeholder='Title'><textarea name='body' required></textarea><select name='category'><option>Reflection</option><option>Business</option><option>Retreats</option><option>Conscious Coordination</option></select><select name='visibility'><option value='private'>Private Journal only</option><option value='community'>Share a Copy to Community</option></select><button>Save to Journal</button></form>{items}"""
    return shell("My Journal",body)

@app.route("/messages")
@login_required
def messages():
    u=me(); c=cdb(); rows=c.execute("""select m.*,case when m.sender_id=? then r.name else s.name end other_name,case when m.sender_id=? then r.id else s.id end other_id from messages m join users s on s.id=m.sender_id join users r on r.id=m.recipient_id where m.sender_id=? or m.recipient_id=? order by m.id desc""",(u["id"],u["id"],u["id"],u["id"])).fetchall(); c.close()
    items="".join(f"<div class='card'><span class='badge'>{esc(x['source'])}</span><h3>{esc(x['subject'])}</h3><p>{esc(x['body'])}</p><a class='out' href='{url_for('compose_message',uid=x['other_id'],source=x['source'])}'>Reply</a></div>" for x in rows) or "<div class='card'>Private messages will appear here.</div>"
    return shell("Journal Inbox",f"<section class='hero'><h1>Journal Inbox</h1></section>{items}")

@app.route("/message/<int:uid>",methods=["GET","POST"])
@login_required
def compose_message(uid):
    u=me(); c=cdb(); p=c.execute("select * from users where id=?",(uid,)).fetchone(); c.close()
    if not p:return "Not found",404
    source=request.args.get("source","Private"); subject=f"{source} Message from {u['name']}"
    if request.method=="POST":
        c=cdb(); c.execute("insert into messages(sender_id,recipient_id,source,subject,body) values(?,?,?,?,?)",(u["id"],uid,source,request.form.get("subject") or subject,request.form["body"])); c.commit(); c.close(); notify(uid,"New Private Message",subject,"Message"); return redirect(url_for("messages"))
    return shell("Private Message",f"<section class='hero'><h1>Message {esc(p['name'])}</h1></section><form class='card' method='post'><input name='subject' value='{esc(subject)}'><textarea name='body' required></textarea><button>Send Private Message</button></form>")

@app.route("/notifications")
@login_required
def notifications():
    c=cdb(); rows=c.execute("select * from notifications where user_id=? order by id desc",(me()["id"],)).fetchall(); c.close()
    items="".join(f"<div class='card'><span class='badge'>{esc(x['kind'])}</span><h3>{esc(x['title'])}</h3><p>{esc(x['body'])}</p></div>" for x in rows) or "<div class='card'>Notifications will appear here.</div>"
    return shell("Notifications",f"<section class='hero'><h1>Notifications</h1></section>{items}")

CONN_FIELDS=["types","emotional_regulation","emotional_support","communication","conflict","repair","accountability","boundaries","trust","love_languages","lifestyle_values","business_style","retreat_style","about"]
@app.route("/connections")
@login_required
def connections():
    u=me(); c=cdb(); cp=c.execute("select * from connections where user_id=?",(u["id"],)).fetchone()
    if not cp: c.close(); return redirect(url_for("connections_setup"))
    others=c.execute("select u.*,x.types from users u join connections x on x.user_id=u.id where u.id<>?",(u["id"],)).fetchall(); c.close()
    cards="".join(f"<div class='card {'premium' if x['full_member'] else ''}'><h3>{esc(x['name'])}</h3><p>{esc(x['types'])}</p><a class='btn' href='{url_for('connection_profile',uid=x['id'])}'>View Profile</a></div>" for x in others) or "<div class='card'>Participating members will appear here.</div>"
    body=f"<section class='hero premium'><span class='badge gold'>$10.99 / MONTH</span><h1>Conscious Coordination</h1><p>Relationships • Friendship • Business Partnerships • Retreat Coordination.</p><a class='btn' href='{url_for('connections_setup')}'>Edit My Coordination Profile</a></section><div class='grid'>{cards}</div>"
    return shell("Conscious Coordination",body)

@app.route("/connections/setup",methods=["GET","POST"])
@login_required
def connections_setup():
    u=me(); c=cdb(); cp=c.execute("select * from connections where user_id=?",(u["id"],)).fetchone(); c.close()
    if request.method=="POST":
        data=[request.form.get(x,"") for x in CONN_FIELDS]
        c=cdb()
        if cp:
            c.execute("update connections set "+",".join(f"{x}=?" for x in CONN_FIELDS)+" where user_id=?",tuple(data)+(u["id"],))
        else:
            c.execute("insert into connections(user_id,"+",".join(CONN_FIELDS)+") values(?,"+",".join("?" for _ in CONN_FIELDS)+")",(u["id"],)+tuple(data))
        c.commit(); c.close(); return redirect(url_for("connections"))
    def val(k): return esc(cp[k]) if cp else ""
    fields="".join(f"<textarea name='{k}' placeholder='{label}'>{val(k)}</textarea>" for k,label in [("emotional_regulation","What helps you regulate when overwhelmed?"),("emotional_support","How do you support someone who is emotional?"),("communication","Communication style"),("conflict","Conflict style"),("repair","Repair style"),("accountability","Accountability"),("boundaries","Boundaries"),("trust","What builds trust?"),("love_languages","Love languages / affection"),("lifestyle_values","Lifestyle & values"),("business_style","Business partnership style"),("retreat_style","Retreat preferences"),("about","About me")])
    body=f"<section class='hero'><h1>Emotional Intelligence & Connection Style</h1></section><form class='card' method='post'><input name='types' value='{val('types')}' placeholder='Love / Dating • Friendship • Business / Collaboration • Retreat Connections'>{fields}<button>Save Profile</button></form>"
    return shell("Coordination Setup",body)

def compat(a,b):
    keys=["communication","emotional_regulation","conflict","repair","boundaries","trust","lifestyle_values"]
    scores={k:(90 if a[k] and b[k] and a[k].strip().lower()==b[k].strip().lower() else 72) for k in keys}
    overall=round(sum(scores.values())/len(scores))
    return overall,scores

@app.route("/connections/profile/<int:uid>")
@login_required
def connection_profile(uid):
    u=me(); c=cdb(); a=c.execute("select * from connections where user_id=?",(u["id"],)).fetchone(); b=c.execute("select * from connections where user_id=?",(uid,)).fetchone(); p=c.execute("select * from users where id=?",(uid,)).fetchone(); c.close()
    if not a or not b or not p:return "Not found",404
    overall,s=compat(a,b)
    body=f"<section class='hero {'premium' if p['full_member'] else ''}'><h1>{esc(p['name'])}</h1><p>{esc(b['types'])}</p><a class='btn' href='{url_for('compose_message',uid=uid,source='Conscious Coordination')}'>Message</a></section><div class='card'><h2>{overall}% Coordination</h2><a class='out' href='{url_for('compatibility_basic',uid=uid)}'>Basic Compatibility</a> <a class='btn' href='{url_for('compatibility_full',uid=uid)}'>Full Compatibility</a></div>"
    return shell("Coordination Profile",body)

@app.route("/connections/compatibility/basic/<int:uid>")
@login_required
def compatibility_basic(uid):
    u=me(); c=cdb(); a=c.execute("select * from connections where user_id=?",(u["id"],)).fetchone(); b=c.execute("select * from connections where user_id=?",(uid,)).fetchone(); c.close()
    if not a or not b:return "Not found",404
    o,s=compat(a,b)
    return shell("Basic Compatibility",f"<section class='hero'><h1>Basic Compatibility Preview</h1></section><div class='grid'><div class='card'><h3>Overall — {o}%</h3></div><div class='card'><h3>Communication — {s['communication']}%</h3></div><div class='card'><h3>Emotional Style — {s['emotional_regulation']}%</h3></div><div class='card'><h3>Lifestyle & Values — {s['lifestyle_values']}%</h3></div><div class='card'><h3>Astrology Preview — 76%</h3></div></div>")

@app.route("/connections/compatibility/full/<int:uid>")
@login_required
def compatibility_full(uid):
    if not me()["full_member"] and not me()["is_admin"]: return redirect(url_for("membership"))
    u=me(); c=cdb(); a=c.execute("select * from connections where user_id=?",(u["id"],)).fetchone(); b=c.execute("select * from connections where user_id=?",(uid,)).fetchone(); c.close()
    if not a or not b:return "Not found",404
    o,s=compat(a,b)
    cards="".join(f"<div class='card'><h3>{label} — {score}%</h3></div>" for label,score in [("Social & Emotional Intelligence",round((s['emotional_regulation']+s['trust'])/2)),("Communication",s["communication"]),("Conflict",s["conflict"]),("Repair & Accountability",s["repair"]),("Emotional Rhythm",s["emotional_regulation"]),("Love Languages / Affection",78),("Lifestyle & Values",s["lifestyle_values"]),("Boundaries",s["boundaries"]),("Psychology-Oriented Compatibility",82),("Astrology",79)])
    return shell("Full Compatibility",f"<section class='hero premium'><span class='badge gold'>FULL PAID REPORT</span><h1>How You Coordinate — {o}%</h1><p>Self-reported behavior, not diagnosis or prediction.</p></section><div class='grid'>{cards}</div><div class='actions'><a class='btn' href='{url_for('birth_chart',uid=uid)}'>Full Birth Chart</a><a class='out' href='{url_for('connection_ideas',uid=uid)}'>Connection Ideas</a><a class='out' href='{url_for('video',uid=uid)}'>Video Area</a></div>")

@app.route("/connections/birth-chart/<int:uid>")
@login_required
def birth_chart(uid):
    return shell("Birth Chart Compatibility","<section class='hero premium'><h1>Full Birth Chart Compatibility</h1><p>Sun • Moon • Rising • Mercury • Venus • Mars • Jupiter • Saturn. Rising/houses are never guessed. Live calculation can be connected after the navigation architecture is approved.</p></section>")
@app.route("/connections/ideas/<int:uid>")
@login_required
def connection_ideas(uid):
    return shell("Connection Ideas","<section class='hero'><h1>Connection / Date / Friendship / Collaboration Ideas</h1></section><div class='grid'><div class='card'><h3>Nature Walk + Tea</h3></div><div class='card'><h3>Museum / Local Experience</h3></div><div class='card'><h3>Wellness Class</h3></div><div class='card'><h3>Business Collaboration</h3></div><div class='card'><h3>Retreat Experience</h3></div></div>")
@app.route("/connections/video/<int:uid>")
@login_required
def video(uid):
    if not me()["full_member"] and not me()["is_admin"]: return redirect(url_for("membership"))
    return shell("Private Video","<section class='hero premium'><span class='badge gold'>PRIVATE VIDEO</span><h1>05:00</h1><p>First eligible connection included. Add 5 Minutes — $5. Paid Video Request / Message — $5. Real camera transport requires WebRTC/TURN infrastructure.</p></section>")

@app.route("/business")
def business():
    c=cdb(); rows=c.execute("select * from businesses where status='active' order by featured desc,id").fetchall(); c.close()
    cards="".join(f"<div class='card {'premium' if x['featured'] else ''}'><h2>{esc(x['name'])}</h2><p>{esc(x['title'] or x['category'])}</p><a class='btn' href='{url_for('business_app',slug=x['slug'])}'>Open App</a></div>" for x in rows) or "<div class='card'>Businesses will appear here as they join.</div>"
    cta = f"<a class='btn' href='{url_for('business_builder')}'>Create My Free Hosted App</a>" if me() else ""
    return shell("Business Network",f"<section class='hero'><span class='badge'>FREE HOSTING</span><h1>Business Network</h1><p>Every business gets the same Hosted App shell for free.</p>{cta}</section><div class='grid'>{cards}</div>","business")

@app.route("/business/builder",methods=["GET","POST"])
@login_required
def business_builder():
    u=me(); c=cdb(); b=c.execute("select * from businesses where owner_id=?",(u["id"],)).fetchone(); c.close()
    if request.method=="POST":
        logo=save_file(request.files.get("logo"),f"biz{u['id']}logo") or (b["logo"] if b else "")
        cover=save_file(request.files.get("cover"),f"biz{u['id']}cover") or (b["cover"] if b else "")
        category=request.form.get("category","Other"); goals=" • ".join(request.form.getlist("modules")); featured=1 if u["email"].lower()==GALAXY_EMAIL else 0
        c=cdb()
        if b:c.execute("update businesses set name=?,title=?,category=?,city=?,tagline=?,description=?,logo=?,cover=?,website=?,instagram=?,tiktok=?,youtube=?,modules=?,featured=? where owner_id=?",(request.form["name"],request.form.get("title",""),category,request.form.get("city",""),request.form.get("tagline",""),request.form.get("description",""),logo,cover,request.form.get("website",""),request.form.get("instagram",""),request.form.get("tiktok",""),request.form.get("youtube",""),goals,featured,u["id"]))
        else:c.execute("insert into businesses(owner_id,slug,name,title,category,city,tagline,description,logo,cover,website,instagram,tiktok,youtube,modules,featured) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],slug(request.form["name"]),request.form["name"],request.form.get("title",""),category,request.form.get("city",""),request.form.get("tagline",""),request.form.get("description",""),logo,cover,request.form.get("website",""),request.form.get("instagram",""),request.form.get("tiktok",""),request.form.get("youtube",""),goals,featured))
        c.commit(); c.close(); return redirect(url_for("business_dashboard"))
    v=lambda k:esc(b[k]) if b else ""
    chips="".join(f"<label class='chip'><input style='width:auto' type='checkbox' name='modules' value='{x}'> {x}</label>" for x in ["Services","Booking","Classes","Courses","Events","Shop","Videos","Retreats","Media Kit","Affiliate Links"])
    form=f"<section class='hero'><h1>Free Hosted App Builder</h1></section><div class='steps'><span>1 Identity</span><span>2 About</span><span>3 Offers</span><span>4 Features</span><span>5 Branding</span><span>6 Links</span><span>7 Preview</span><span>8 Edit</span><span>9 Publish</span></div><form class='card' method='post' enctype='multipart/form-data'><input name='name' value='{v('name')}' placeholder='Business Name' required><input name='title' value='{v('title')}' placeholder='Owner / Creator Title'><select name='category'><option>Content Creator</option><option>Yoga / Fitness</option><option>Reiki / Wellness</option><option>Massage / Bodywork</option><option>Coach / Consultant</option><option>Beauty / Hair</option><option>Food / Cooking</option><option>Speaker / Educator</option><option>Retail / Products</option><option>Other</option></select><input name='city' value='{v('city')}' placeholder='City'><input name='tagline' value='{v('tagline')}' placeholder='Tagline'><textarea name='description'>{v('description')}</textarea><div class='chips'>{chips}</div><input type='file' name='logo'><input type='file' name='cover'><input name='website' value='{v('website')}' placeholder='Website'><input name='instagram' value='{v('instagram')}' placeholder='Instagram'><input name='tiktok' value='{v('tiktok')}' placeholder='TikTok'><input name='youtube' value='{v('youtube')}' placeholder='YouTube'><button>Save / Publish Hosted App</button></form>"
    return shell("Free Hosted App Builder",form)

@app.route("/app/<slug>")
def business_app(slug):
    c=cdb(); b=c.execute("select * from businesses where slug=?",(slug,)).fetchone(); c.close()
    if not b:return "Not found",404
    image=f"<img src='{url_for('uploads',filename=b['cover'])}'>" if b["cover"] else (f"<img src='{url_for('uploads',filename=b['logo'])}' style='object-fit:contain;padding:30px'>" if b["logo"] else logo_img(""))
    mods="".join(f"<span>{esc(x.strip())}</span>" for x in (b["modules"] or "").split("•") if x.strip())
    return shell(b["name"],f"<section class='hero {'premium' if b['featured'] else ''}'><span class='badge {'gold' if b['featured'] else ''}'>HOSTED BUSINESS APP</span><div class='two'><div><h1>{esc(b['name'])}</h1><h3>{esc(b['title'] or b['category'])}</h3><p>{esc(b['tagline'])}</p></div><div class='media logo-box'>{image}</div></div></section><div class='appnav'><span>Home</span><span>About</span>{mods}<span>Contact</span></div><div class='card'><h2>About</h2><p>{esc(b['description'])}</p></div>")

@app.route("/business/dashboard")
@login_required
def business_dashboard():
    c=cdb(); b=c.execute("select * from businesses where owner_id=?",(me()["id"],)).fetchone(); plan=c.execute("select * from business_plans where user_id=? order by version desc limit 1",(me()["id"],)).fetchone(); c.close()
    preview=f"<a class='out' href='{url_for('business_app',slug=b['slug'])}'>Preview Hosted App</a>" if b else ""
    planbtn=f"<a class='out' href='{url_for('business_plan',pid=plan['id'])}'>Business Plan</a>" if plan else f"<a class='out' href='{url_for('business_dev')}'>Start Business Development</a>"
    return shell("Business Dashboard",f"<section class='hero'><h1>Business Dashboard</h1></section><div class='grid'><a class='btn' href='{url_for('business_builder')}'>Edit Hosted App</a>{preview}<button>Services</button><button>Booking</button><button>Classes</button><button>Events</button><button>Media</button><button>Links</button><button>Retreat Participation</button><button>Business Inquiries</button>{planbtn}</div>")

DEV_FIELDS=["stage","business_name","strengths","target_customer","problem","solution","vision","values_text","usp","offers","pricing","revenue","competitors","operations","startup","marketing","goals90","goals1yr"]
@app.route("/business/development",methods=["GET","POST"])
@login_required
def business_dev():
    u=me(); c=cdb(); r=c.execute("select * from business_dev where user_id=?",(u["id"],)).fetchone(); c.close()
    if request.method=="POST":
        data=[request.form.get(x,"") for x in DEV_FIELDS]; c=cdb()
        if r:c.execute("update business_dev set "+",".join(f"{x}=?" for x in DEV_FIELDS)+" where user_id=?",tuple(data)+(u["id"],))
        else:c.execute("insert into business_dev(user_id,"+",".join(DEV_FIELDS)+") values(?,"+",".join("?" for _ in DEV_FIELDS)+")",(u["id"],)+tuple(data))
        c.commit(); c.close(); flash("Business interview saved."); return redirect(url_for("business_dev"))
    def v(k):return esc(r[k]) if r else ""
    fields="".join(f"<textarea name='{k}' placeholder='{label}'>{v(k)}</textarea>" for k,label in [("strengths","What are you good at / qualified to do?"),("target_customer","Who do you want to help?"),("problem","What problem do they have?"),("solution","How will your business help them?"),("vision","What should it become in 3–5 years?"),("values_text","Core values"),("usp","What makes it different?"),("offers","Products / services / classes / events"),("pricing","Pricing"),("revenue","Revenue streams"),("competitors","Competitors / alternatives"),("operations","Operations"),("startup","Startup requirements / budget / funding"),("marketing","Marketing channels"),("goals90","90-day goals"),("goals1yr","One-year goals")])
    gen=f"<a class='btn' href='{url_for('generate_plan')}'>Generate Professional Package</a>" if (u["business_access"] or u["is_admin"]) and r else "<p class='muted'>The $79.99 payment gate will unlock plan generation when payment processing is connected.</p>"
    body=f"<section class='hero premium'><span class='badge gold'>$79.99 ONE TIME</span><h1>Professional Business Development</h1></section><form class='card' method='post'><input name='stage' value='{v('stage')}' placeholder='Business stage'><input name='business_name' value='{v('business_name')}' placeholder='Business name'>{fields}<button>Save Business Interview</button></form><div class='card premium'>{gen}</div>"
    return shell("Business Development",body)

def sections_from(r):
    n=r["business_name"] or "Your Business"; cust=r["target_customer"] or "the target customer"; prob=r["problem"] or "the customer's key problem"; sol=r["solution"] or r["offers"] or "the proposed solution"
    return {"Executive Summary":f"{n} is designed to serve {cust} by addressing {prob} through {sol}.","Business Description":f"{n} is being developed from the '{r['stage'] or 'business development'}' stage.","Founder Story":r["strengths"] or "Founder experience and motivation.","Mission":f"{n} exists to help {cust} address {prob} through {sol}.","Vision":r["vision"] or "Build a trusted, sustainable business over the next 3–5 years.","Core Values":r["values_text"] or "Integrity • Quality • Care • Reliability","USP":r["usp"] or "Clarify the strongest differentiator.","Products & Services":r["offers"] or "Define the initial focused offers.","Target Customer":cust,"Customer Problem":prob,"Business Solution":sol,"Market Overview":"Validate demand through customer conversations, competitor research and local/online market observation.","Competitor Analysis":r["competitors"] or "Identify direct competitors, indirect alternatives and gaps.","Pricing Strategy":r["pricing"] or "Set pricing from cost, value, margin and market range.","Revenue Streams":r["revenue"] or "Services, products, classes, events, memberships, retreats, digital products or partnerships.","Marketing Strategy":r["marketing"] or "Use social media, local/community partnerships, referrals and search according to where the target customer is active.","Social Media Strategy":"Use repeatable pillars: education, founder story, proof/customer experience, offers, collaborations.","Sales Strategy":"Discovery → trust → inquiry → purchase → follow-up.","Operations":r["operations"] or "Define delivery, booking, payment, customer support and scheduling.","Startup Requirements":r["startup"] or "List equipment, software, supplies, branding and professional support.","Startup Budget":r["startup"] or "Separate one-time startup costs from monthly operating costs.","Revenue Projections":"Build conservative, target and high scenarios using customers × average sale × purchase frequency.","90-Day Launch Strategy":r["goals90"] or "Days 1–30 foundation; Days 31–60 visibility; Days 61–90 launch and refine.","One-Year Goals":r["goals1yr"] or "Set measurable customer, revenue, partnership and operating goals."}

@app.route("/business/plan/generate")
@login_required
def generate_plan():
    u=me()
    if not (u["business_access"] or u["is_admin"]):return redirect(url_for("business_dev"))
    c=cdb(); r=c.execute("select * from business_dev where user_id=?",(u["id"],)).fetchone()
    if not r:c.close();return redirect(url_for("business_dev"))
    ver=(c.execute("select max(version) v from business_plans where user_id=?",(u["id"],)).fetchone()["v"] or 0)+1
    cur=c.execute("insert into business_plans(user_id,business_name,version,sections) values(?,?,?,?)",(u["id"],r["business_name"] or "My Business",ver,json.dumps(sections_from(r)))); pid=cur.lastrowid; c.execute("insert into journal(user_id,title,body,category,visibility) values(?,?,?,'Business','private')",(u["id"],f"{r['business_name']} Business Plan",f"Business Plan Version {ver} generated.")); c.commit(); c.close(); notify(u["id"],"Business Plan Ready",f"Version {ver} is ready.","Business"); return redirect(url_for("business_plan",pid=pid))

@app.route("/business/plan/<int:pid>")
@login_required
def business_plan(pid):
    c=cdb(); p=c.execute("select * from business_plans where id=? and user_id=?",(pid,me()["id"])).fetchone(); c.close()
    if not p:return "Not found",404
    sec=json.loads(p["sections"]); cards="".join(f"<div class='card'><h3>{esc(k)}</h3><p>{esc(v)}</p></div>" for k,v in sec.items())
    return shell("Business Plan",f"<section class='hero premium'><h1>{esc(p['business_name'])} Business Plan</h1><p>Version {p['version']} • Stored in Journal → Business</p></section><div class='grid'>{cards}</div>")

@app.route("/retreats")
def retreats():
    c=cdb(); rows=c.execute("select * from retreats order by id desc").fetchall(); c.close()
    cards="".join(f"<div class='card'><h3>{esc(x['title'])}</h3><p>{esc(x['type'])} • {esc(x['season'])} • {esc(x['dates'])}</p></div>" for x in rows) or "<div class='card'>Upcoming Retreats will appear here.</div>"
    cta = f"<a class='btn' href='{url_for('retreat_builder')}'>Design Your Own Retreat</a>" if me() else ""
    return shell("Retreats",f"<section class='hero'><h1>Retreats</h1>{cta}</section><div class='grid'>{cards}</div>","retreats")
@app.route("/retreats/builder",methods=["GET","POST"])
@login_required
def retreat_builder():
    u=me()
    if request.method=="POST":
        c=cdb(); c.execute("insert into retreats(user_id,title,type,season,dates,guests,budget,wellness,lodging,businesses) values(?,?,?,?,?,?,?,?,?,?)",(u["id"],request.form["title"],request.form["type"],request.form["season"],request.form.get("dates",""),request.form.get("guests",""),request.form.get("budget",""),request.form.get("wellness",""),request.form.get("lodging",""),request.form.get("businesses",""))); c.execute("insert into journal(user_id,title,body,category,visibility) values(?,?,?,'Retreats','private')",(u["id"],request.form["title"],"Retreat request saved.")); c.commit(); c.close(); return redirect(url_for("journal"))
    return shell("Retreat Builder","""<section class='hero'><h1>Design Your Own Retreat</h1></section><form class='card' method='post'><input name='title' placeholder='Retreat Title' required><select name='type'><option>Solo Renewal</option><option>Couples / Dating</option><option>Friendship / Group</option><option>Women’s Self-Love</option><option>Men’s Renewal</option><option>Family Harmony</option><option>Life Transition</option></select><select name='season'><option>Spring Renewal</option><option>Summer Water</option><option>Autumn Reflection</option><option>Winter Stillness</option></select><input name='dates' placeholder='Preferred dates'><input name='guests' placeholder='Guests'><input name='budget' placeholder='Budget'><textarea name='wellness' placeholder='Wellness interests'></textarea><textarea name='lodging' placeholder='Lodging preferences'></textarea><textarea name='businesses' placeholder='Desired participating businesses'></textarea><button>Save Retreat Request</button></form>""")

@app.route("/membership")
def membership():
    return shell("Membership","""<section class='hero'><h1>Membership & Packages</h1></section><div class='grid'><div class='card'><span class='badge'>FREE</span><h2>Community + Hosted Business App</h2><h1>$0</h1></div><div class='card premium'><span class='badge gold'>CONSCIOUS COORDINATION</span><h2>Full Membership</h2><h1>$10.99/month</h1></div><div class='card premium'><span class='badge gold'>BUSINESS DEVELOPMENT</span><h2>Professional Business Plan Package</h2><h1>$79.99</h1></div></div><div class='card'><h2>Video Add-Ons</h2><p>Add 5 Minutes — $5 • Paid Video Request / Message — $5</p></div>""","membership")

@app.route("/more")
@login_required
def more():
    return shell("More",f"<section class='hero'><h1>More</h1></section><div class='grid'><a class='btn' href='{url_for('journal')}'>My Journal</a><a class='out' href='{url_for('messages')}'>Journal Inbox</a><a class='out' href='{url_for('notifications')}'>Notifications</a><a class='out' href='{url_for('connections')}'>Conscious Coordination</a><a class='out' href='{url_for('business_dashboard')}'>Business Dashboard</a><a class='out' href='{url_for('retreats')}'>Retreats</a><a class='out' href='{url_for('membership')}'>Membership</a></div>")

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5000")))
