import os,re,sqlite3,hashlib,secrets
from datetime import datetime,date,timezone
from functools import wraps
from pathlib import Path
from flask import Flask,render_template,request,redirect,url_for,session,flash,send_from_directory,abort,Response,send_file
from werkzeug.utils import secure_filename
from jinja2 import DictLoader
from email.message import EmailMessage
try:
    import swisseph as swe
except Exception:
    swe=None
BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get("PERSISTENT_DATA_DIR",BASE/"data")); DATA.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get("DATABASE_PATH",DATA/"the_seasons_within.db"))
UPLOADS=Path(os.environ.get("UPLOAD_DIR",DATA/"uploads")); UPLOADS.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get("SECRET_KEY","change-me-in-render")
GALAXY_EMAIL=os.environ.get("GALAXY_EVE_EMAIL","galaxyeve@theseasonswithin.local").lower().strip()
SIGNS=["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
def hp(p): return hashlib.sha256(("tsw::"+p).encode()).hexdigest()
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def slugify(x): return re.sub(r"[^a-z0-9]+","-",x.lower()).strip("-") or secrets.token_hex(4)
def me():
    if not session.get("uid"): return None
    c=conn(); u=c.execute("select * from users where id=?",(session["uid"],)).fetchone(); c.close(); return u
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not me(): return redirect(url_for("login",next=request.path))
        return f(*a,**k)
    return w
def media_url(p): return url_for("uploads",filename=p) if p else ""
def save_file(fs,prefix):
    if not fs or not fs.filename:return ""
    ext=Path(secure_filename(fs.filename)).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".gif",".mp4",".mov",".m4v"}:return ""
    n=f"{prefix}-{secrets.token_hex(6)}{ext}"; fs.save(UPLOADS/n); return n
def age(v):
    if not v:return None
    try:
        b=datetime.strptime(v,"%Y-%m-%d").date(); t=date.today(); return t.year-b.year-((t.month,t.day)<(b.month,b.day))
    except:return None
def multi(name,limit=12): return " • ".join(request.form.getlist(name)[:limit])
def parts(v): return {x.strip() for x in (v or "").split("•") if x.strip()}
def init_db():
    c=conn(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,email TEXT UNIQUE,password_hash TEXT,city TEXT DEFAULT '',bio TEXT DEFAULT '',photo TEXT DEFAULT '',headline TEXT DEFAULT '',birth_date TEXT DEFAULT '',birth_time TEXT DEFAULT '',birth_lat REAL,birth_lon REAL,birth_utc_offset REAL DEFAULT 0,time_known INTEGER DEFAULT 0,sun TEXT DEFAULT '',moon TEXT DEFAULT '',rising TEXT DEFAULT '',mercury TEXT DEFAULT '',venus TEXT DEFAULT '',mars TEXT DEFAULT '',jupiter TEXT DEFAULT '',saturn TEXT DEFAULT '',membership_access INTEGER DEFAULT 0,business_access INTEGER DEFAULT 0,is_admin INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS community_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS journals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_id INTEGER,recipient_id INTEGER,message_type TEXT DEFAULT 'people',subject TEXT DEFAULT '',body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,notification_type TEXT,title TEXT,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS connection_profiles(user_id INTEGER PRIMARY KEY,connection_type TEXT DEFAULT 'Both',gender TEXT,seeking TEXT,age_min INTEGER DEFAULT 18,age_max INTEGER DEFAULT 99,occupation TEXT,children TEXT,looking_for TEXT,lifestyle TEXT,activities TEXT,values_text TEXT,emotional_response TEXT,others_emotions TEXT,conflict_style TEXT,repair_style TEXT,love_languages TEXT,communication_style TEXT,boundaries TEXT,social_energy TEXT,family_goals TEXT,about TEXT);
    CREATE TABLE IF NOT EXISTS connection_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER UNIQUE,slug TEXT UNIQUE,business_name TEXT,creator_title TEXT DEFAULT '',tagline TEXT DEFAULT '',description TEXT DEFAULT '',category TEXT DEFAULT '',city TEXT DEFAULT '',website TEXT DEFAULT '',logo TEXT DEFAULT '',hero_image TEXT DEFAULT '',featured_video TEXT DEFAULT '',instagram TEXT DEFAULT '',tiktok TEXT DEFAULT '',youtube TEXT DEFAULT '',facebook TEXT DEFAULT '',booking_url TEXT DEFAULT '',paid_business INTEGER DEFAULT 0,retreat_participation INTEGER DEFAULT 0,featured_order INTEGER DEFAULT 999,modules TEXT DEFAULT '',status TEXT DEFAULT 'active');
    CREATE TABLE IF NOT EXISTS business_classes(id INTEGER PRIMARY KEY AUTOINCREMENT,business_id INTEGER,title TEXT,description TEXT,class_format TEXT,class_date TEXT,class_time TEXT,price TEXT,meeting_url TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS business_builder(user_id INTEGER PRIMARY KEY,stage TEXT,business_types TEXT,app_goals TEXT,strengths TEXT,target_customer TEXT,offers TEXT,business_name TEXT,marketing_channels TEXT,plan_text TEXT,marketing_plan TEXT,launch_plan TEXT,recommended_modules TEXT);
    CREATE TABLE IF NOT EXISTS retreats(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER,title TEXT,season TEXT,retreat_type TEXT,preferred_dates TEXT,guests INTEGER DEFAULT 1,budget TEXT,lodging_preferences TEXT,wellness_interests TEXT,connection_retreat INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS retreat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,retreat_id INTEGER,sender_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    g=c.execute("select * from users where lower(email)=?",(GALAXY_EMAIL,)).fetchone()
    if not g:
        cur=c.execute("insert into users(name,email,password_hash,headline,membership_access,business_access) values(?,?,?,?,1,1)",("Galaxy Eve",GALAXY_EMAIL,hp(os.environ.get("GALAXY_EVE_INITIAL_PASSWORD","ChangeMeGalaxyEve!")),"Conscious Coordinator • Content Creator")); gid=cur.lastrowid
    else:
        gid=g["id"]; c.execute("update users set membership_access=1,business_access=1 where id=?",(gid,))
    if not c.execute("select 1 from businesses where owner_id=?",(gid,)).fetchone():
        c.execute("insert into businesses(owner_id,slug,business_name,creator_title,tagline,description,category,paid_business,retreat_participation,featured_order,modules) values(?,?,?,?,?,?,?,1,1,1,?)",(gid,"galaxy-eve","Galaxy Eve","Conscious Coordinator • Content Creator","Content • Collaborations • Creator Experiences","Creator content, collaborations, meetups, retreats and Conscious Coordination.","Content Creator","Home|About|Watch|Events|Retreats|Media Kit|Collaborate|Recommendations|Contact"))
    c.commit(); c.close()
def zdeg(d):
    d=float(d)%360;i=int(d//30);return SIGNS[i],round(d-i*30,2)
def sky():
    s={"moon_sign":"","moon_phase":"","moon_degree":None,"moon_symbol":"☾","positions":{}}
    if not swe:return s
    try:
        n=datetime.now(timezone.utc);jd=swe.julday(n.year,n.month,n.day,n.hour+n.minute/60)
        bodies={"Sun":swe.SUN,"Moon":swe.MOON,"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN};deg={}
        for k,v in bodies.items():
            p=swe.calc_ut(jd,v)[0][0];deg[k]=p;sg,dd=zdeg(p);s["positions"][k]={"sign":sg,"degree":dd}
        s["moon_sign"]=s["positions"]["Moon"]["sign"];s["moon_degree"]=s["positions"]["Moon"]["degree"];a=(deg["Moon"]-deg["Sun"])%360
        for cut,nm,sym in [(22.5,"New Moon","🌑"),(67.5,"Waxing Crescent","🌒"),(112.5,"First Quarter","🌓"),(157.5,"Waxing Gibbous","🌔"),(202.5,"Full Moon","🌕"),(247.5,"Waning Gibbous","🌖"),(292.5,"Last Quarter","🌗"),(337.5,"Waning Crescent","🌘"),(361,"New Moon","🌑")]:
            if a<cut:s["moon_phase"]=nm;s["moon_symbol"]=sym;break
    except:pass
    return s
def calc_chart(uid):
    if not swe:return
    c=conn();u=c.execute("select * from users where id=?",(uid,)).fetchone()
    if not u or not u["birth_date"]:c.close();return
    try:
        d=datetime.strptime(u["birth_date"],"%Y-%m-%d");h=12.0
        if u["time_known"] and u["birth_time"]:
            hh,mm=map(int,u["birth_time"].split(":")[:2]);h=hh+mm/60-float(u["birth_utc_offset"] or 0)
        jd=swe.julday(d.year,d.month,d.day,h);vals={}
        for k,v in {"sun":swe.SUN,"moon":swe.MOON,"mercury":swe.MERCURY,"venus":swe.VENUS,"mars":swe.MARS,"jupiter":swe.JUPITER,"saturn":swe.SATURN}.items():vals[k]=zdeg(swe.calc_ut(jd,v)[0][0])[0]
        rising=""
        if u["time_known"] and u["birth_lat"] is not None and u["birth_lon"] is not None:rising=zdeg(swe.houses(jd,float(u["birth_lat"]),float(u["birth_lon"]),b'P')[1][0])[0]
        c.execute("update users set sun=?,moon=?,rising=?,mercury=?,venus=?,mars=?,jupiter=?,saturn=? where id=?",(vals["sun"],vals["moon"],rising,vals["mercury"],vals["venus"],vals["mars"],vals["jupiter"],vals["saturn"],uid));c.commit()
    except:pass
    c.close()
def signscore(a,b):
    if not a or not b or a not in SIGNS or b not in SIGNS:return 60
    d=min((SIGNS.index(a)-SIGNS.index(b))%12,(SIGNS.index(b)-SIGNS.index(a))%12)
    return {0:92,2:80,4:88,6:68}.get(d,62)
def overlap(a,b):
    A,B=parts(a),parts(b)
    if not A or not B:return 60
    return round(55+40*len(A&B)/len(A|B))
def report(a,b,ca,cb):
    social={"Emotional Regulation":90 if ca["emotional_response"]==cb["emotional_response"] else 70,"Conflict & Repair":round(((90 if ca["conflict_style"]==cb["conflict_style"] else 68)+(90 if ca["repair_style"]==cb["repair_style"] else 68))/2),"Communication Style":90 if ca["communication_style"]==cb["communication_style"] else 70,"Love Languages":overlap(ca["love_languages"],cb["love_languages"]),"Values & Lifestyle":round((overlap(ca["values_text"],cb["values_text"])+overlap(ca["lifestyle"],cb["lifestyle"]))/2),"Boundaries":90 if ca["boundaries"]==cb["boundaries"] else 68}
    astro={"Emotional Rhythm • Moon":signscore(a["moon"],b["moon"]),"Communication • Mercury":signscore(a["mercury"],b["mercury"]),"Affection • Venus":signscore(a["venus"],b["venus"]),"Attraction / Drive • Mars":signscore(a["mars"],b["mars"]),"Identity • Sun":signscore(a["sun"],b["sun"]),"Interaction • Rising":signscore(a["rising"],b["rising"]) if a["rising"] and b["rising"] else None}
    sa=round(sum(social.values())/len(social));av=[x for x in astro.values() if x is not None];aa=round(sum(av)/len(av)) if av else 60
    desc={x:"Compares how both members describe this part of their real-life relationship style." for x in social};desc.update({x:"Uses astrology as a reflective coordination layer, not a clinical assessment or guarantee." for x in astro})
    return {"social":social,"astro":astro,"overall":round(sa*.65+aa*.35),"desc":desc}
def modules(types,goals):
    t=(types+" "+goals).lower();m=["Home","About","Contact"]
    def add(*xs):
        for x in xs:
            if x not in m:m.append(x)
    if any(x in t for x in ["appointment","massage","beauty","hair","reiki"]):add("Services","Book")
    if any(x in t for x in ["class","course","teacher","yoga"]):add("Classes")
    if any(x in t for x in ["product","e-commerce"]):add("Shop")
    if any(x in t for x in ["content","creator","video"]):add("Watch")
    if "event" in t:add("Events")
    if "retreat" in t:add("Retreats")
    if any(x in t for x in ["creator","speaker"]):add("Media Kit","Collaborate")
    if "affiliate" in t:add("Recommendations")
    return m
def bizpackage(row):
    name=row["business_name"] or "Your Business";target=row["target_customer"] or "your ideal customer";offers=row["offers"] or "selected services/products";mods=modules(row["business_types"] or "",row["app_goals"] or "")
    plan=f"BUSINESS PLAN — {name}\\n\\nExecutive Summary\\n{name} will serve {target} through {offers}.\\n\\nFounder Strengths\\n{row['strengths'] or 'Define founder strengths, experience and certifications.'}\\n\\nTarget Customer\\n{target}\\n\\nProducts & Services\\n{offers}\\n\\nApp Strategy\\n{' | '.join(mods)}\\n\\nOperations\\nUse one dashboard to manage the business profile, classes, links and retreat participation."
    marketing=f"MARKETING STRATEGY — {name}\\n\\nTarget audience: {target}\\n\\nPrimary channels: {row['marketing_channels'] or 'Social media • referrals • partnerships'}\\n\\nContent pillars: education, founder story, offers, customer experience and collaborations."
    launch=f"90-DAY LAUNCH PLAN — {name}\\n\\nDays 1–30: finalize brand, offers, pricing and app.\\nDays 31–60: publish content, outreach and partnerships.\\nDays 61–90: focused launch campaign, collect feedback and refine."
    return plan,marketing,launch,"|".join(mods)


# ---- Consolidated app upgrades ----
BASE_URL=os.environ.get("BASE_URL","").rstrip("/")
STRIPE_SECRET_KEY=os.environ.get("STRIPE_SECRET_KEY","")
STRIPE_WEBHOOK_SECRET=os.environ.get("STRIPE_WEBHOOK_SECRET","")
PDFS=Path(os.environ.get("PDF_DIR",DATA/"pdfs")); PDFS.mkdir(parents=True,exist_ok=True)

BUSINESS_TYPES=['Wellness','Yoga/Fitness','Reiki','Massage/Bodywork','Sound Wellness','Beauty/Hair','Food/Cooking','Motivational Speaker','Coach/Consultant','Content Creator','Artist/Creative','Retreat/Event Host','Teacher/Educator','Courses','Products/E-commerce','Membership/Community','Professional Services','Nonprofit','Other']
APP_GOALS=['Sell products','Book appointments','Live classes','Recorded classes','Courses','Memberships','Videos/content','Blog','Community','Speaking','Events','Retreats','Consultations','Portfolio','Affiliate links','Media Kit']
EMOTIONAL_FIELDS=[
("When I am upset, I usually...","emotional_response",['Need quiet time before talking','Want to talk fairly soon','Need reassurance before discussing it','Prefer practical problem-solving','It depends on the situation']),
("When someone I care about is emotional, I usually...","others_emotions",['Listen first','Ask what they need','Offer solutions','Give them space','Use affection or reassurance']),
("During conflict, I prefer...","conflict_style",['Calm direct conversation','Take a break and return later','Resolve it quickly','Write/text first, then talk','A structured / mediated approach']),
("Repair after conflict looks like...","repair_style",['Clear apology + changed behavior','Talking it through fully','Affection + reassurance','Quality time together','Practical action to fix the problem']),
("My apology style is closest to...","apology_style",['I name what happened and take responsibility','I explain my intention and apologize','I show change through actions','I need time before I can apologize well','I prefer mutual discussion and repair']),
("Communication style","communication_style",['Direct but gentle','Very direct','Thoughtful / needs processing time','Emotionally expressive','Calm and practical']),
("Boundaries","boundaries",['Strong privacy / personal-space needs','Flexible but clear boundaries','Prefer frequent closeness/contact','Need lots of independence','Still learning what works for me']),
("Social energy","social_energy",['Mostly homebody','Small groups','Balanced social / home time','Very social','Adventure / always doing something']),
("Family goals","family_goals",['Want children / family','Already have children and open to blending','Do not want children','Adult children / later-life partnership','Open / still deciding'])
]
PAY_ITEMS={
"full_membership":{"name":"Full Membership — Conscious Coordination","amount":1099,"display":"$10.99/month","description":"Full compatibility, shared birth charts, expanded media and connection tools.","mode":"subscription"},
"business_app":{"name":"Business Network Hosted App","amount":2999,"display":"$29.99/month","description":"Standout hosted business app with expanded features.","mode":"subscription"},
"startup_package":{"name":"Startup/Hobby → Business Plan Package","amount":7999,"display":"$79.99","description":"10–15 page Business Plan PDF + Marketing Strategy + 90-Day Launch Plan.","mode":"payment"},
"video_message":{"name":"Paid Video Request / Message","amount":500,"display":"$5","description":"Sender pays $5; recipient may answer without paying.","mode":"payment"},
"video_time":{"name":"Add 5 Minutes of Video Talk Time","amount":500,"display":"$5","description":"Adds 5 minutes to the selected video connection.","mode":"payment"}
}

def user_paths(u): return [x for x in (u["paths"] or "").split("|") if x] if u else []
def age_from_birth(v):
    if not v:return None
    try:
        b=datetime.strptime(v,"%Y-%m-%d").date();t=date.today();return t.year-b.year-((t.month,t.day)<(b.month,b.day))
    except:return None

def ensure_column(c,table,col,definition):
    cols={r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")

def migrate_db():
    c=conn()
    for col,definition in [("paths","TEXT DEFAULT 'Community'"),("chart_visibility","TEXT DEFAULT 'full'"),("startup_access","INTEGER DEFAULT 0")]: ensure_column(c,"users",col,definition)
    for col,definition in [("sponsor_community","INTEGER DEFAULT 0"),("approved_connections","INTEGER DEFAULT 0")]: ensure_column(c,"businesses",col,definition)
    for col,definition in [("location_pref","TEXT"),("height","TEXT"),("weight","TEXT"),("apology_style","TEXT"),("video_opt_in","INTEGER DEFAULT 1")]: ensure_column(c,"connection_profiles",col,definition)
    ensure_column(c,"community_posts","photo","TEXT DEFAULT ''")
    ensure_column(c,"journals","title","TEXT DEFAULT ''")
    ensure_column(c,"connection_posts","media","TEXT DEFAULT ''")
    ensure_column(c,"connection_posts","media_type","TEXT DEFAULT ''")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS connection_media(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,filename TEXT,media_type TEXT,sort_order INTEGER DEFAULT 999,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS business_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,business_name TEXT,version_no INTEGER DEFAULT 1,sections_json TEXT,marketing_text TEXT,launch_text TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS video_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,requester_id INTEGER,recipient_id INTEGER,status TEXT DEFAULT 'requested',seconds_available INTEGER DEFAULT 300,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,target_id INTEGER,amount_cents INTEGER,status TEXT DEFAULT 'pending',stripe_session_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    # Add fields to the existing builder without deleting earlier data.
    for col,definition in [("pricing_ideas","TEXT DEFAULT ''"),("goals_90","TEXT DEFAULT ''")]: ensure_column(c,"business_builder",col,definition)
    # Galaxy Eve remains the host/admin and paid hosted app.
    g=c.execute("select * from users where lower(email)=?",(GALAXY_EMAIL,)).fetchone()
    if g:
        c.execute("update users set membership_access=1,business_access=1,startup_access=1,is_admin=1 where id=?",(g["id"],))
        c.execute("update businesses set paid_business=1,retreat_participation=1,sponsor_community=1,approved_connections=1,featured_order=1 where owner_id=?",(g["id"],))
    c.commit();c.close()

def notify(uid,kind,title,body):
    c=conn();c.execute("insert into notifications(user_id,notification_type,title,body) values(?,?,?,?)",(uid,kind,title,body));c.commit();c.close()

HIGH_RISK_PATTERNS=[
(r"\b(kill you|hurt you|beat you|shoot you|stab you|rape you)\b","Threatening or violent language is not allowed."),
(r"\b(send nudes?|nude pics?|naked pics?|explicit pics?|show me your body)\b","Sexual/nude solicitation is not allowed."),
(r"\b(underage|minor)\b","Age-inappropriate sexual or dating content is not allowed.")
]
ABUSE_WORDS={"bitch","whore","slut","cunt","faggot","retard"}
def moderate_text(text):
    t=(text or "").lower()
    for pat,reason in HIGH_RISK_PATTERNS:
        if re.search(pat,t):return False,reason
    hits=[w for w in ABUSE_WORDS if re.search(r"\b"+re.escape(w)+r"\b",t)]
    if len(hits)>=2:return False,"Targeted abusive language may violate the member rules. Please revise the message."
    return True,""

def full_report(a,b,ca,cb):
    base=report(a,b,ca,cb)
    same=lambda k,hi=90,lo=70: hi if (ca[k] and cb[k] and ca[k]==cb[k]) else lo
    social={
      "Social & Emotional Intelligence":round((same("others_emotions",92,72)+same("emotional_response",88,68))/2),
      "Communication":same("communication_style",92,70),
      "Handling Conflict":same("conflict_style",88,68),
      "Repair & Accountability":round((same("repair_style",92,70)+same("apology_style",90,68))/2),
      "Emotional Rhythm":same("emotional_response",86,67),
      "Affection & Love Language":overlap(ca["love_languages"],cb["love_languages"]),
      "Lifestyle & Values":round((overlap(ca["values_text"],cb["values_text"])+overlap(ca["lifestyle"],cb["lifestyle"]))/2),
      "Psychology-Oriented Compatibility":round((same("boundaries",88,67)+same("social_energy",84,68)+same("family_goals",88,66))/3)
    }
    astro={"Communication • Mercury":signscore(a["mercury"],b["mercury"]),"Emotional Rhythm • Moon":signscore(a["moon"],b["moon"]),"Affection • Venus":signscore(a["venus"],b["venus"]),"Attraction / Drive • Mars":signscore(a["mars"],b["mars"]),"Identity • Sun":signscore(a["sun"],b["sun"]),"Interaction • Rising":signscore(a["rising"],b["rising"]) if a["rising"] and b["rising"] else None}
    sv=round(sum(social.values())/len(social));av=[x for x in astro.values() if x is not None];ast=round(sum(av)/len(av)) if av else 60;overall=round(sv*.68+ast*.32)
    descriptions={k:"Compares how both members describe this part of their real-life connection style." for k in social}
    descriptions.update({k:"Astrology is used as a reflective coordination layer, not a diagnosis or guarantee." for k in astro})
    basic={"Communication":social["Communication"],"Emotional Style":round((social["Social & Emotional Intelligence"]+social["Emotional Rhythm"])/2),"Lifestyle & Values":social["Lifestyle & Values"],"Astrology Preview":ast}
    shared=parts(ca["values_text"])&parts(cb["values_text"])
    strengths=("Shared values: "+", ".join(sorted(shared))) if shared else "Your profiles show areas of natural coordination worth exploring."
    differences="Differences in emotional timing, boundaries, affection or social energy can become useful conversation points."
    questions=["When something is bothering you, do you usually want to talk right away or have time to think first?","What makes an apology feel sincere to you?","How much alone time do you need in a close relationship?","How do you naturally show someone that you care?"]
    return {"overall":overall,"social":social,"astro":astro,"basic":basic,"descriptions":descriptions,"strengths":strengths,"differences":differences,"questions":questions}

def can_view_chart(viewer,person):
    if not viewer or not viewer["membership_access"]:return False
    mode=person["chart_visibility"] or "full"
    if mode=="private":return False
    if mode=="full":return True
    c=conn();r=c.execute("select 1 from messages where (sender_id=? and recipient_id=?) or (sender_id=? and recipient_id=?) limit 1",(viewer["id"],person["id"],person["id"],viewer["id"])).fetchone();c.close();return bool(r)

def build_plan_sections(row):
    name=row["business_name"] or "Your Business";target=row["target_customer"] or "your intended customer";offers=row["offers"] or "the products, services or experiences identified in your questionnaire";strengths=row["strengths"] or "your skills, experience, certifications and lived knowledge";mods=modules(row["business_types"] or "",row["app_goals"] or "")
    return {
    "Executive Summary":f"{name} is being developed to serve {target}. The business will focus on {offers}. This plan organizes the concept into a practical launch path and digital business presence.",
    "Business Concept & Mission":f"{name} will turn the founder's current skills, ideas or experience into a clear customer offering. The mission should center on the value delivered to {target}.",
    "Founder Strengths & Qualifications":f"Founder strengths identified in the questionnaire include: {strengths}. Translate these into trust signals such as credentials, portfolio examples, demonstrations, educational content or a clear founder story.",
    "Target Customer":f"Primary target customer: {target}. Build customer profiles around the problem they are trying to solve, what they value and what would make them trust a new business.",
    "Market Need & Positioning":f"{name} should position itself around a specific customer need rather than trying to serve everyone. Focus on the intersection of founder strengths, selected categories ({row['business_types'] or 'to be refined'}) and customer need.",
    "Products & Services":f"Proposed offers: {offers}. Start with a focused set of offers that are easy to explain, price and deliver.",
    "Pricing & Revenue Model":f"Pricing ideas: {row['pricing_ideas'] or 'Pricing is still being developed.'} Revenue can come from services, products, classes, memberships, events, retreats or content where appropriate.",
    "Brand & Customer Experience":f"The brand should make it easy for a visitor to understand who {name} serves, what it offers, why it matters and what action to take next.",
    "Operations & Technology":"Define booking, payment, fulfillment, customer support and record-keeping procedures. Use the Business Dashboard as a central place to manage the app, plan and classes.",
    "Hosted App Strategy":f"Recommended app modules: {' | '.join(mods)}. These modules are based on the business type and app goals selected in the questionnaire."
    }

def marketing_text(row):
    return f"""TARGET AUDIENCE
{row['target_customer'] or 'Define the clearest first customer segment.'}

PRIMARY CHANNELS
{row['marketing_channels'] or 'Social media • referrals • local/community partnerships'}

CONTENT PILLARS
1. Education
2. Founder story
3. Offers
4. Customer experience
5. Collaborations and partnerships

FOCUS
Build awareness first, then invitations, then repeatable follow-up. Track which content, partnerships and offers lead to inquiries or purchases."""
def launch_text(row):
    return f"""GOAL
{row['goals_90'] or 'Launch the first clear offer and begin building repeatable customer demand.'}

DAYS 1–30 — FOUNDATION
Finalize the brand, customer, first offers, pricing, operating needs and app structure.

DAYS 31–60 — VISIBILITY & OUTREACH
Publish useful content, contact partners, build community awareness and test messaging.

DAYS 61–90 — LAUNCH & LEARN
Run a focused launch campaign, invite customers to the clearest offer, gather feedback and refine pricing, messaging and the hosted app."""

def simple_pdf_bytes(title,sections):
    objs=[]
    def add(x):objs.append(x);return len(objs)
    font=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");pages=[]
    for page_title,body in sections:
        lines=[page_title,""]+textwrap.wrap((body or "").replace("\t"," "),88)
        lines=lines[:48];y=760;cmd=["BT","/F1 12 Tf"]
        for i,line in enumerate(lines):
            safe=line.encode("latin-1","replace").decode("latin-1").replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
            size=17 if i==0 else 11;cmd.append(f"/F1 {size} Tf 54 {y} Td ({safe}) Tj");step=28 if i==0 else 15;cmd.append(f"0 {-step} Td");y-=step
        cmd.append("ET");stream="\n".join(cmd).encode("latin-1");content=add(f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream");page=add(f"<< /Type /Page /Parent PAGESREF /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>");pages.append(page)
    kids=" ".join(f"{x} 0 R" for x in pages);pages_id=add(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>");catalog=add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    fixed=[]
    for x in objs:
        if isinstance(x,bytes):fixed.append(x.replace(b"PAGESREF",f"{pages_id} 0 R".encode()))
        else:fixed.append(x.replace("PAGESREF",f"{pages_id} 0 R").encode())
    out=bytearray(b"%PDF-1.4\n");offs=[0]
    for i,obj in enumerate(fixed,1):offs.append(len(out));out+=f"{i} 0 obj\n".encode()+obj+b"\nendobj\n"
    xref=len(out);out+=f"xref\n0 {len(fixed)+1}\n".encode()+b"0000000000 65535 f \n"
    for o in offs[1:]:out+=f"{o:010d} 00000 n \n".encode()
    out+=f"trailer\n<< /Size {len(fixed)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF".encode();return bytes(out)

def stripe_ready(): return bool(STRIPE_SECRET_KEY and BASE_URL)
def stripe_checkout(kind,user_id,target_id=0):
    item=PAY_ITEMS[kind];data={"mode":item["mode"],"success_url":BASE_URL+"/payment/success?session_id={CHECKOUT_SESSION_ID}","cancel_url":BASE_URL+"/membership","line_items[0][price_data][currency]":"usd","line_items[0][price_data][unit_amount]":str(item["amount"]),"line_items[0][price_data][product_data][name]":item["name"],"line_items[0][quantity]":"1","metadata[user_id]":str(user_id),"metadata[kind]":kind,"metadata[target_id]":str(target_id)}
    if item["mode"]=="subscription":data["line_items[0][price_data][recurring][interval]"]="month";data["subscription_data[metadata][user_id]"]=str(user_id);data["subscription_data[metadata][kind]"]=kind
    req=urllib.request.Request("https://api.stripe.com/v1/checkout/sessions",data=urllib.parse.urlencode(data).encode(),headers={"Authorization":"Bearer "+STRIPE_SECRET_KEY,"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
def verify_stripe(payload,sig):
    if not STRIPE_WEBHOOK_SECRET:return False
    parts=dict(x.split("=",1) for x in sig.split(",") if "=" in x);ts=parts.get("t");v1=parts.get("v1")
    if not ts or not v1:return False
    expected=hmac.new(STRIPE_WEBHOOK_SECRET.encode(),(ts+".").encode()+payload,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,v1) and abs(time.time()-int(ts))<600
def activate_purchase(uid,kind,target=0):
    c=conn()
    if kind=="full_membership":c.execute("update users set membership_access=1 where id=?",(uid,))
    elif kind=="business_app":c.execute("update users set business_access=1 where id=?",(uid,));c.execute("update businesses set paid_business=1 where owner_id=?",(uid,))
    elif kind=="startup_package":c.execute("update users set startup_access=1 where id=?",(uid,))
    elif kind=="video_time":c.execute("update video_sessions set seconds_available=seconds_available+300 where id=?",(target,))
    elif kind=="video_message" and target:
        c.execute("insert into messages(sender_id,recipient_id,message_type,subject,body) values(?,?,?,?,?)",(uid,target,"video","Paid video request","A paid video request/message was sent. You may answer without paying the sender charge."))
        c.execute("insert into notifications(user_id,notification_type,title,body) values(?,?,?,?)",(target,"video","New paid video request","A member sent you a paid video request. You may answer without paying."))
    c.commit();c.close()

T={'base.html': '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The Seasons Within</title>\n<style>\n:root{--p:#34204f;--u:#8f63ba;--u2:#a979c8;--l:#f2e9f8;--b:#fff1ef;--line:#eadff1;--m:#786b82;--sh:0 14px 36px rgba(72,42,96,.08)}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#fcf9fd,#fffaf8 55%,#faf6fc);color:var(--p);font-family:Arial,sans-serif}a{text-decoration:none;color:inherit}h1,h2,h3{font-family:Georgia,serif}.top{position:sticky;top:0;z-index:30;background:#fffffff2;border-bottom:1px solid var(--line)}.topin{width:min(1220px,94vw);min-height:80px;margin:auto;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px}.brand{display:flex;align-items:center;gap:10px}.mark{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;color:#fff;background:conic-gradient(#efc6ce 0 25%,#cfb3de 25% 50%,#eedcb4 50% 75%,#d4c1e7 75% 100%);border:7px solid #faf1fa}.brand strong{display:block;font:700 20px Georgia}.brand small{display:block;font-size:9px;letter-spacing:1.2px;text-transform:uppercase;color:var(--m)}.nav{display:flex;justify-content:center;gap:6px;flex-wrap:wrap}.nav a{padding:10px 12px;border-radius:999px;font-size:13px;font-weight:800}.nav a:hover,.nav a.on{background:var(--l)}.acct{display:flex;align-items:center;gap:8px}.wrap{width:min(1140px,92vw);margin:30px auto 90px}.hero,.card{border:1px solid var(--line);border-radius:22px;box-shadow:var(--sh)}.hero{padding:30px;background:linear-gradient(135deg,#f1e3fb,#fff0ec)}.card{padding:20px;background:#fff;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:15px}.two{display:grid;grid-template-columns:1fr 1fr;gap:15px}.btn,.out,button{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:10px 15px;border-radius:11px;font-weight:800}.btn,button{border:1px solid var(--u);background:linear-gradient(135deg,var(--u),var(--u2));color:#fff}.out{border:1px solid #cdb6dd;background:#fff;color:#68428a}.actions,.chips{display:flex;gap:8px;flex-wrap:wrap}.chip,.badge{display:inline-block;background:var(--l);padding:7px 9px;border-radius:999px;font-size:11px;font-weight:800}.paid{border:2px solid #d5bc76}.muted{color:var(--m)}input,textarea,select{width:100%;padding:11px;border:1px solid var(--line);border-radius:10px;margin:5px 0 12px}textarea{min-height:100px}.portrait{width:105px;height:105px;border-radius:50%;object-fit:cover}.tool{display:block;border:1px solid var(--line);border-radius:15px;padding:16px;background:#fff}.biz{padding:0;overflow:hidden}.media{height:190px;display:grid;place-items:center;background:linear-gradient(135deg,#e9d8f5,#fff0ed)}.media img,.media video{width:100%;height:100%;object-fit:cover}.body{padding:17px}.moon{display:grid;grid-template-columns:110px 1fr;gap:18px;align-items:center}.moonpic{width:100px;height:100px;border-radius:50%;display:grid;place-items:center;font-size:62px;background:radial-gradient(circle at 35% 30%,#fff,#ece6f0 58%,#c8bdd0 100%)}.meter{height:10px;background:#eee6f1;border-radius:999px;overflow:hidden}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--u),#c992c4)}.empty{padding:28px;text-align:center;border:1px dashed #d9c8e5;border-radius:16px}.flash{width:min(1140px,92vw);margin:12px auto;background:#f0e4f8;padding:11px;border-radius:10px}.mobile{display:none}@media(max-width:760px){body{padding-bottom:70px}.topin{display:flex;justify-content:center}.nav,.acct{display:none}.wrap{width:94vw}.two{grid-template-columns:1fr}.hero h1{font-size:34px}.moon{grid-template-columns:80px 1fr}.moonpic{width:75px;height:75px;font-size:46px}.mobile{position:fixed;left:50%;bottom:8px;transform:translateX(-50%);display:flex;justify-content:space-around;width:95vw;padding:8px;background:#fff;border:1px solid var(--line);border-radius:18px;z-index:40}.mobile a{font-size:10px;font-weight:800}}\n.fact{padding:13px;border:1px solid var(--line);border-radius:14px;background:#fcf9fd;margin:7px 0}.fact small{display:block;color:var(--m);margin-bottom:4px}.notice{padding:14px;border-left:4px solid var(--u);background:#faf6fc;border-radius:10px;color:#65576d;line-height:1.5}.paid{border:2px solid #d5bc76!important}</style></head><body>\n<header class="top"><div class="topin"><a class="brand" href="{{url_for(\'home\')}}"><span class="mark">✦</span><span><strong>The Seasons Within</strong><small>Conscious Coordination</small></span></a><nav class="nav"><a href="{{url_for(\'home\')}}">Home</a>{% if me %}<a href="{{url_for(\'profile\')}}">My Profile</a>{% endif %}<a href="{{url_for(\'business\')}}">Business Network</a><a href="{{url_for(\'retreats\')}}">Retreats</a><a href="{{url_for(\'membership\')}}">Membership</a></nav><div class="acct">{% if me %}<b>{{me.name}}</b><a href="{{url_for(\'logout\')}}">Log Out</a>{% else %}<a href="{{url_for(\'login\')}}">Log In</a><a class="btn" href="{{url_for(\'join\')}}">Join Free</a>{% endif %}</div></div></header>\n{% with x=get_flashed_messages() %}{% if x %}<div class="flash">{{x|join(\' • \')}}</div>{% endif %}{% endwith %}<main class="wrap">{% block content %}{% endblock %}</main><nav class="mobile"><a href="{{url_for(\'home\')}}">Home</a>{% if me %}<a href="{{url_for(\'profile\')}}">Profile</a>{% endif %}<a href="{{url_for(\'business\')}}">Business</a><a href="{{url_for(\'retreats\')}}">Retreats</a><a href="{{url_for(\'membership\')}}">Membership</a></nav>{% block scripts %}{% endblock %}</body></html>', 'business_card.html': '<article class="card biz {% if b.paid_business %}paid{% endif %}"><div class="media">{% if b.paid_business and b.featured_video %}<video src="{{media_url(b.featured_video)}}" controls muted></video>{% elif b.paid_business and b.hero_image %}<img src="{{media_url(b.hero_image)}}">{% elif b.logo %}<img src="{{media_url(b.logo)}}" style="object-fit:contain;padding:20px">{% else %}<img src="{{url_for(\'brand_logo\')}}" style="width:105px;height:105px;object-fit:contain;padding:8px">{% endif %}</div><div class="body"><span class="badge">{{\'★ Hosted App\' if b.paid_business else \'Free Listing\'}}</span><h3>{{b.business_name}}</h3><p><b>{{b.creator_title or b.category}}</b>{% if b.city %} • {{b.city}}{% endif %}</p><small>{{b.tagline or b.description}}</small><div class="actions" style="margin-top:12px"><a class="btn" href="{{url_for(\'business_app\',slug=b.slug)}}">{{\'Open App\' if b.paid_business else \'View Business\'}}</a></div></div></article>', 'home.html': '{% extends \'base.html\' %}{% block content %}\n<section class="hero"><span class="badge">THE SEASONS WITHIN</span><h1>Discover Wellness Within the Community</h1><p>Explore real wellness businesses, standout hosted apps, classes, creators and retreat experiences. Community and Conscious Connections are private member areas.</p><div class="actions"><a class="btn" href="{{url_for(\'business\')}}">Explore Businesses & Apps</a><a class="out" href="{{url_for(\'retreats\')}}">Explore Retreats</a>{% if not me %}<a class="out" href="{{url_for(\'join\')}}">Join Free</a>{% endif %}</div></section>\n<h2>Featured Businesses & Apps</h2><div class="grid">{% for b in businesses %}{% include \'business_card.html\' %}{% else %}<div class="empty">Real businesses appear here as they join.</div>{% endfor %}</div>\n<article class="card moon"><div class="moonpic">{{sky.moon_symbol}}</div><div><span class="badge">MOON TODAY</span><h2>Moon in {{sky.moon_sign or \'the current sky\'}}{% if sky.moon_degree is not none %} • {{sky.moon_degree}}°{% endif %}</h2><p><b>{{sky.moon_phase or \'Current lunar phase\'}}</b></p><div class="chips">{% for p in [\'Mercury\',\'Venus\',\'Mars\',\'Jupiter\',\'Saturn\'] %}{% if sky.positions.get(p) %}<span class="chip">{{p}} {{sky.positions[p][\'sign\']}}</span>{% endif %}{% endfor %}</div></div></article>\n<h2>Retreats</h2><div class="grid">{% for r in retreats %}<article class="card"><span class="badge">{{r.season}}</span><h3>{{r.title}}</h3><p>{{r.retreat_type}}</p><a class="btn" href="{{url_for(\'retreat_detail\',rid=r.id)}}">View Retreat</a></article>{% else %}<article class="card"><h3>Design Your Own Retreat</h3><a class="btn" href="{{url_for(\'retreat_build\')}}">Build My Retreat</a></article>{% endfor %}</div>\n<article class="card paid"><span class="badge">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan Package — $79.99</h2><p>Guided questionnaire, editable 10–15 page Business Plan PDF, Marketing Strategy and 90-Day Launch Plan. Save versions in your profile, download, email or share the PDF.</p><a class="btn" href="{{url_for(\'business_builder\')}}">Start My Business Plan</a></article>{% endblock %}', 'join.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">ONE ACCOUNT • MULTIPLE PATHS</span><h1>Create Your Free Account</h1><p>Your account, profile, messages and saved work stay attached to the same login.</p></section>\n<form class="card" method="post"><label>Name<input name="name" required></label><label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" minlength="6" required></label><label>Date of Birth<input name="birth_date" type="date" required></label><h2>How would you like to connect?</h2><div class="chips"><label class="chip"><input type="checkbox" name="paths" value="Community" checked> Community</label><label class="chip"><input type="checkbox" name="paths" value="Connections"> Conscious Connections — Love, Dating & Friendship</label><label class="chip"><input type="checkbox" name="paths" value="Business"> Business</label><label class="chip"><input type="checkbox" name="paths" value="Retreats"> Retreats</label></div><p><label><input style="width:auto" type="checkbox" name="age_confirm" required> I confirm I am 18 or older.</label></p><button>Create Account</button></form>{% endblock %}', 'login.html': '{% extends \'base.html\' %}{% block content %}<h1>Log In</h1><form class="card" method="post"><label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label><button>Log In</button></form>{% endblock %}', 'profile.html': '{% extends \'base.html\' %}{% block content %}<article class="card {% if u.membership_access %}paid{% endif %}">{% if u.photo %}<img class="portrait" src="{{media_url(u.photo)}}">{% endif %}<span class="badge">{{\'★ FULL MEMBER • $10.99/MONTH\' if u.membership_access else \'FREE MEMBER\'}}</span><h1>{{u.name}}</h1><p>{{u.headline}} • {{u.city}}</p><p>{{u.bio}}</p><div class="chips">{% for p in user_paths(u) %}<span class="chip">{{\'♡ Conscious Connections\' if p==\'Connections\' else p}}</span>{% endfor %}</div><div class="chips"><span class="chip">Sun {{u.sun or \'—\'}}</span><span class="chip">Moon {{u.moon or \'—\'}}</span><span class="chip">Rising {{u.rising or \'—\'}}</span></div><a class="btn" href="{{url_for(\'profile_edit\')}}">Edit My Profile</a></article>\n<div class="grid"><a class="tool" href="{{url_for(\'community\')}}"><b>Community</b><br><small>Member posts; replies go privately to Inbox.</small></a><a class="tool" href="{{url_for(\'journal\')}}"><b>My Private Journal</b></a><a class="tool" href="{{url_for(\'messages\')}}"><b>My Inbox</b></a><a class="tool" href="{{url_for(\'notifications\')}}"><b>Notifications</b></a>{% if cp or \'Connections\' in user_paths(u) %}<a class="tool" href="{{url_for(\'connections\')}}"><b>♡ Conscious Connections</b><br><small>{{cp.connection_type if cp else \'Create your optional Connections profile\'}}</small></a>{% else %}<a class="tool" href="{{url_for(\'connections_join\')}}"><b>♡ Join Conscious Connections</b><br><small>Love & Dating, Friendship, or Both.</small></a>{% endif %}<a class="tool" href="{{url_for(\'business_dashboard\')}}"><b>My Business Dashboard</b><br><small>Business profile/app, Business Plan, marketing and saved copies.</small></a></div>{% endblock %}', 'profile_edit.html': '{% extends \'base.html\' %}{% block content %}<h1>Edit My Profile</h1><form class="card" method="post" enctype="multipart/form-data"><label>Photo<input type="file" name="photo" accept="image/*"></label><label>Name<input name="name" value="{{u.name}}"></label><label>City<input name="city" value="{{u.city}}"></label><label>Headline<input name="headline" value="{{u.headline}}"></label><label>About<textarea name="bio">{{u.bio}}</textarea></label><h2>My Areas</h2><div class="chips">{% for p in [\'Community\',\'Connections\',\'Business\',\'Retreats\'] %}<label class="chip"><input type="checkbox" name="paths" value="{{p}}" {% if p in user_paths(u) %}checked{% endif %}>{{\'Conscious Connections\' if p==\'Connections\' else p}}</label>{% endfor %}</div><h2>Birth Information</h2><label>Birth Date<input type="date" name="birth_date" value="{{u.birth_date}}"></label><label>Birth Time<input type="time" name="birth_time" value="{{u.birth_time}}"></label><label><input style="width:auto" type="checkbox" name="time_known" {% if u.time_known %}checked{% endif %}> Exact birth time known</label><div class="two"><label>Latitude<input name="birth_lat" value="{{u.birth_lat if u.birth_lat is not none else \'\'}}"></label><label>Longitude<input name="birth_lon" value="{{u.birth_lon if u.birth_lon is not none else \'\'}}"></label></div><label>UTC Offset at Birth<input name="birth_utc_offset" value="{{u.birth_utc_offset or 0}}"></label><label>Full Birth Chart Visibility<select name="chart_visibility"><option value="full" {% if u.chart_visibility==\'full\' %}selected{% endif %}>Full Members Only</option><option value="connected" {% if u.chart_visibility==\'connected\' %}selected{% endif %}>Members I Have Connected With</option><option value="private" {% if u.chart_visibility==\'private\' %}selected{% endif %}>Keep Full Chart Private</option></select></label><p class="muted">Rising signs and houses are shown only when accurate birth time/location supports them.</p><button>Save Profile</button></form>{% endblock %}', 'community.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">MEMBERS ONLY</span><h1>Community</h1><p>Members may post text and photos. There are no public comment threads; replies go to private Inbox.</p></section><form class="card" method="post" enctype="multipart/form-data"><textarea name="body" placeholder="Share with the community..." required></textarea><label>Add Photo<input type="file" name="photo" accept="image/*"></label><button>Post to Community</button></form>{% for p in posts %}<article class="card"><h3>{{p.name}}</h3><p>{{p.body}}</p>{% if p.photo %}<img src="{{media_url(p.photo)}}" style="max-height:420px;border-radius:15px">{% endif %}{% if p.user_id!=me.id %}<a class="out" href="{{url_for(\'compose_message\',recipient_id=p.user_id,kind=\'community\')}}">Inbox {{p.name}}</a>{% endif %}</article>{% if loop.index % 4 == 0 and sponsors %}{% set b=sponsors[(loop.index//4-1)%sponsors|length] %}{% include \'business_card.html\' %}{% endif %}{% else %}<div class="empty">Community posts will appear here.</div>{% endfor %}{% endblock %}', 'journal.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">🔒 PRIVATE</span><h1>My Private Journal</h1><p>Entries stay private unless you intentionally share a separate copy to Community.</p></section><form class="card" method="post"><label>Title<input name="title"></label><textarea name="body" placeholder="What are you noticing within yourself today?" required></textarea><button>Save Privately</button></form>{% for e in entries %}<article class="card"><small>{{e.created_at}}</small><h3>{{e.title or \'Journal Entry\'}}</h3><p style="white-space:pre-wrap">{{e.body}}</p><form method="post" action="{{url_for(\'journal_share\',jid=e.id)}}"><button class="out">Share a Copy to Community</button></form></article>{% endfor %}{% endblock %}', 'connections_join.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">♡ OPTIONAL MEMBER AREA</span><h1>Join Conscious Connections</h1><p>Choose Love & Dating, Friendship, or Both. You are not shown in the Connections directory until you intentionally create this profile.</p></section><form class="card" method="post"><h2>How would you like to connect?</h2><label><input type="radio" name="connection_type" value="Love & Dating" required> ♡ Love & Dating</label><br><br><label><input type="radio" name="connection_type" value="Friendship" required> ☼ Friendship</label><br><br><label><input type="radio" name="connection_type" value="Both" required> ♡ + ☼ Both</label><br><br><button>Continue to My Connections Profile</button></form>{% endblock %}', 'connections.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">♡ PARTICIPATING MEMBERS ONLY</span><h1>Conscious Connections</h1><p>Love, Dating & Friendship through real member profiles, compatibility, private Inbox and shared experiences.</p><a class="btn" href="{{url_for(\'connections_edit\')}}">Edit My Connections Profile</a></section>\n{% for p in host_posts %}<article class="card"><span class="badge">HOST</span><h3>Galaxy Eve</h3><p>{{p.body}}</p>{% if p.media %}{% if p.media_type==\'video\' %}<video src="{{media_url(p.media)}}" controls style="max-height:420px;border-radius:15px"></video>{% else %}<img src="{{media_url(p.media)}}" style="max-height:420px;border-radius:15px">{% endif %}{% endif %}<a class="out" href="{{url_for(\'compose_message\',recipient_id=p.user_id,kind=\'connections\')}}">Inbox Galaxy Eve</a></article>{% endfor %}\n{% if is_host %}<form class="card" method="post" enctype="multipart/form-data"><h3>Post as Conscious Connections Host</h3><textarea name="body"></textarea><input type="file" name="media" accept="image/*,video/*"><button>Publish Host Post</button></form>{% endif %}\n<h2>Conscious Connections Members</h2><div class="grid">{% for p in people %}<article class="card {% if p.membership_access %}paid{% endif %}"><span class="badge">{{\'★ FULL MEMBER\' if p.membership_access else \'FREE CONNECTION PROFILE\'}}</span><h3>{{p.name}}{% if p.age %}, {{p.age}}{% endif %}</h3><p>{{p.city}} • {{p.connection_type}}</p><div class="chips">{% if p.sun %}<span class="chip">Sun {{p.sun}}</span>{% endif %}{% if p.moon %}<span class="chip">Moon {{p.moon}}</span>{% endif %}{% if p.rising %}<span class="chip">Rising {{p.rising}}</span>{% endif %}</div><h3>{{p.score}}% Conscious Coordination</h3><div class="meter"><i style="width:{{p.score}}%"></i></div><div class="actions"><a class="btn" href="{{url_for(\'connection_profile\',uid=p.id)}}">View Profile</a><a class="out" href="{{url_for(\'compose_message\',recipient_id=p.id,kind=\'connections\')}}">Inbox</a></div></article>{% else %}<div class="empty">Real participating members will appear here.</div>{% endfor %}</div>\n{% if connection_businesses %}<h2>Approved Connection Experiences</h2><div class="grid">{% for b in connection_businesses %}{% include \'business_card.html\' %}{% endfor %}</div>{% endif %}{% endblock %}', 'connection_profile.html': '{% extends \'base.html\' %}{% block content %}<section class="card {% if person.membership_access %}paid{% endif %}"><div class="two"><div>{% if media %}{% set first=media[0] %}{% if first.media_type==\'video\' %}<video class="media" src="{{media_url(first.filename)}}" controls></video>{% else %}<img class="media" src="{{media_url(first.filename)}}">{% endif %}{% else %}<div class="media">Profile Photo</div>{% endif %}</div><div><span class="badge">{{\'★ FULL CONSCIOUS CONNECTIONS PROFILE\' if person.membership_access else \'FREE CONSCIOUS CONNECTIONS PROFILE\'}}</span><h1>{{person.name}}{% if person_age %}, {{person_age}}{% endif %}</h1><p>{{person.city}} • {{cp.connection_type}}</p><p>{{cp.about}}</p><div class="actions"><a class="btn" href="{{url_for(\'compose_message\',recipient_id=person.id,kind=\'connections\')}}">Inbox {{person.name}}</a>{% if me.membership_access %}<a class="out" href="{{url_for(\'video_request\',uid=person.id)}}">Video Connection</a>{% endif %}</div></div></div></section>\n<div class="grid"><article class="card"><h2>About</h2>{% for k,l in [(\'occupation\',\'Occupation\'),(\'children\',\'Children\'),(\'looking_for\',\'Looking for\'),(\'lifestyle\',\'Lifestyle\'),(\'activities\',\'Enjoys\'),(\'values_text\',\'Values\')] %}<div class="fact"><small>{{l}}</small><b>{{cp[k] or \'—\'}}</b></div>{% endfor %}</article><article class="card"><h2>How {{person.name}} Connects</h2>{% for k,l in [(\'emotional_response\',\'When upset\'),(\'others_emotions\',\'When someone else is emotional\'),(\'conflict_style\',\'Conflict\'),(\'repair_style\',\'Repair\'),(\'apology_style\',\'Apology style\'),(\'love_languages\',\'Love languages\'),(\'communication_style\',\'Communication\'),(\'boundaries\',\'Boundaries\')] %}<div class="fact"><small>{{l}}</small><b>{{cp[k] or \'—\'}}</b></div>{% endfor %}</article></div>\n<article class="card"><h2>Birth Chart Access</h2><div class="chips">{% if person.sun %}<span class="chip">Sun {{person.sun}}</span>{% endif %}{% if person.moon %}<span class="chip">Moon {{person.moon}}</span>{% endif %}</div>{% if me.membership_access and can_view_chart %}<a class="btn" href="{{url_for(\'birth_chart_view\',uid=person.id)}}">View {{person.name}}\'s Birth Chart</a> <a class="out" href="{{url_for(\'compatibility_view\',uid=person.id)}}">Compare Our Birth Charts</a>{% elif me.membership_access %}<p class="muted">This member keeps their full chart private under their current setting.</p>{% else %}<p class="muted">Full Members can view participating members\' shared full birth charts and compare charts when privacy settings allow.</p><a class="btn" href="{{url_for(\'membership\')}}">Upgrade to $10.99</a>{% endif %}</article>\n{% if me.membership_access %}<article class="card paid"><h2>{{report.overall}}% Full Compatibility</h2><a class="btn" href="{{url_for(\'compatibility_view\',uid=person.id)}}">Open Full Compatibility Report</a></article>{% else %}<article class="card"><h2>{{report.overall}}% Basic Compatibility Preview</h2><a class="out" href="{{url_for(\'compatibility_view\',uid=person.id)}}">View Preview</a></article>{% endif %}\n{% if me.membership_access and media|length>1 %}<article class="card"><h2>Photos & Videos</h2><div class="grid">{% for x in media %}{% if x.media_type==\'video\' %}<video class="media" src="{{media_url(x.filename)}}" controls></video>{% else %}<img class="media" src="{{media_url(x.filename)}}">{% endif %}{% endfor %}</div></article>{% endif %}{% endblock %}', 'business.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">BUSINESS NETWORK</span><h1>Discover Wellness Within the Community</h1><p>Free businesses receive basic listings. $29.99 Hosted Apps stand out with expanded media, classes, services, booking, social links and Retreat participation.</p>{% if me %}<div class="actions"><a class="btn" href="{{url_for(\'business_setup\')}}">My Business Listing / App</a><a class="out" href="{{url_for(\'business_builder\')}}">Startup/Hobby → Business • $79.99</a><a class="out" href="{{url_for(\'business_dashboard\')}}">Business Dashboard</a></div>{% endif %}</section><form class="card"><input name="q" value="{{q}}" placeholder="Search businesses, services, classes or creators..."></form><div class="grid">{% for b in businesses %}{% include \'business_card.html\' %}{% else %}<div class="empty">Real businesses appear here.</div>{% endfor %}</div><article class="card paid"><span class="badge">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan + Marketing + 90-Day Launch Plan — $79.99</h2><p>Create a guided 10–15 page plan, store it in your profile, modify it, save versions, download the PDF, email it or share it from your device.</p><a class="btn" href="{{url_for(\'business_builder\')}}">Start My Business Package</a></article>{% endblock %}', 'business_setup.html': '{% extends \'base.html\' %}{% block content %}<h1>My Business Listing / Hosted App</h1><form class="card" method="post" enctype="multipart/form-data"><label>Logo<input type="file" name="logo" accept="image/*"></label><label>Business Name<input name="business_name" value="{{b.business_name if b else \'\'}}" required></label><label>Title / Role<input name="creator_title" value="{{b.creator_title if b else \'\'}}"></label><label>Tagline<input name="tagline" value="{{b.tagline if b else \'\'}}"></label><label>Description<textarea name="description">{{b.description if b else \'\'}}</textarea></label><div class="two"><label>Category<input name="category" value="{{b.category if b else \'\'}}"></label><label>City<input name="city" value="{{b.city if b else \'\'}}"></label></div><h2>Links</h2><div class="two">{% for x in [\'website\',\'instagram\',\'tiktok\',\'youtube\',\'facebook\',\'booking_url\'] %}<label>{{x|replace(\'_\',\' \')|title}}<input name="{{x}}" value="{{b[x] if b else \'\'}}"></label>{% endfor %}</div>{% if me.business_access or me.is_admin %}<h2>Paid Hosted App Media</h2><label>Cover Photo<input type="file" name="hero_image" accept="image/*"></label><label>Featured Video<input type="file" name="featured_video" accept="video/*"></label><label>App Modules<input name="modules" value="{{b.modules if b else \'\'}}" placeholder="Home|About|Services|Classes|Events|Media Kit|Contact"></label>{% endif %}<div class="chips"><label class="chip"><input type="checkbox" name="retreat_participation" {% if b and b.retreat_participation %}checked{% endif %}> Retreat Provider</label>{% if me.business_access or me.is_admin %}<label class="chip"><input type="checkbox" name="sponsor_community" {% if b and b.sponsor_community %}checked{% endif %}> Community Featured Experience</label><label class="chip"><input type="checkbox" name="approved_connections" {% if b and b.approved_connections %}checked{% endif %}> Approved Conscious Connections Experience</label>{% endif %}</div><br><button>Save Business</button></form>{% endblock %}', 'business_app.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">{{\'★ Hosted App\' if b.paid_business else \'Free Listing\'}}</span><h1>{{b.business_name}}</h1><h3>{{b.creator_title}}</h3><p>{{b.tagline}}</p><div class="actions">{% for label,url in socials %}<a class="out" href="{{url}}" target="_blank">{{label}}</a>{% endfor %}</div></section><article class="card"><h2>About</h2><p>{{b.description}}</p></article>{% if b.paid_business %}<div class="chips">{% for m in modules %}<span class="chip">{{m}}</span>{% endfor %}</div><h2>Classes</h2><div class="grid">{% for x in classes %}<article class="card"><span class="badge">{{x.class_format}}</span><h3>{{x.title}}</h3><p>{{x.description}}</p><p>{{x.class_date}} {{x.class_time}} • {{x.price}}</p>{% if x.meeting_url %}<a class="btn" href="{{x.meeting_url}}" target="_blank">Join / Register</a>{% endif %}</article>{% else %}<div class="empty">Classes created by this business appear here.</div>{% endfor %}</div>{% endif %}{% endblock %}', 'business_builder.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">STARTUP / HOBBY → BUSINESS • $79.99</span><h1>Turn What You Know Into a Business</h1><p>The questionnaire shapes your Business Plan, app structure, Marketing Strategy and 90-Day Launch Plan.</p></section>{% if not me %}<div class="card"><a class="btn" href="{{url_for(\'join\')}}">Join Free to Continue</a></div>{% else %}<form class="card" method="post">{% macro opts(name,items,current=\'\') %}<div class="chips">{% for x in items %}<label class="chip"><input style="width:auto;margin:0 4px 0 0" type="checkbox" name="{{name}}" value="{{x}}" {% if x in (current or \'\') %}checked{% endif %}>{{x}}</label>{% endfor %}</div>{% endmacro %}<label>Where are you starting?<select name="stage">{% for x in [\'Already own a business\',\'Starting a new business\',\'Business idea\',\'Hobby to business\',\'Skill/talent to monetize\',\'Certification/license\',\'Content creator\',\'Help me develop an idea\'] %}<option {% if row and row.stage==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Business types</label>{{opts(\'business_types\',business_types,row.business_types if row else \'\')}}<label>App goals</label>{{opts(\'app_goals\',app_goals,row.app_goals if row else \'\')}}<label>What are you good at?<textarea name="strengths">{{row.strengths if row else \'\'}}</textarea></label><label>Who do you want to help?<textarea name="target_customer">{{row.target_customer if row else \'\'}}</textarea></label><label>What will you offer?<textarea name="offers">{{row.offers if row else \'\'}}</textarea></label><label>Business Name<input name="business_name" value="{{row.business_name if row else \'\'}}"></label><label>Marketing channels</label>{{opts(\'marketing_channels\',[\'Social media\',\'Google/search\',\'Local community\',\'Events\',\'Referrals\',\'Influencers\',\'Email\',\'Partnerships\',\'Paid advertising\'],row.marketing_channels if row else \'\')}}<label>Pricing / revenue ideas<textarea name="pricing_ideas">{{row.pricing_ideas if row else \'\'}}</textarea></label><label>Goals for the next 90 days<textarea name="goals_90">{{row.goals_90 if row else \'\'}}</textarea></label><button>Save Questionnaire</button></form>{% if row %}<article class="card paid"><h2>Ready for Your Business Package?</h2><h1>$79.99</h1><p>10–15 page Business Plan PDF + Marketing Strategy + 90-Day Launch Plan + editable saved copies.</p>{% if me.startup_access or me.is_admin %}<a class="btn" href="{{url_for(\'generate_business_plan\')}}">Generate My Business Plan</a>{% else %}<a class="btn" href="{{url_for(\'checkout\',kind=\'startup_package\')}}">Purchase $79.99 Package</a>{% endif %}</article>{% endif %}{% endif %}{% endblock %}', 'business_dashboard.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">BUSINESS DASHBOARD</span><h1>{{b.business_name if b else (builder.business_name if builder else \'My Business\')}}</h1><p>Manage your listing/app, classes, Business Plan, saved plan copies, Marketing Strategy and 90-Day Launch Plan.</p><div class="actions"><a class="btn" href="{{url_for(\'business_setup\')}}">Business Profile / App</a><a class="out" href="{{url_for(\'business_manage\')}}">Manage Classes</a><a class="out" href="{{url_for(\'business_builder\')}}">Startup Business Builder</a></div></section>{% if latest_plan %}<article class="card paid"><span class="badge">MY BUSINESS PLAN</span><h2>{{latest_plan.business_name}} • Version {{latest_plan.version_no}}</h2><div class="actions"><a class="btn" href="{{url_for(\'business_plan_view\',plan_id=latest_plan.id)}}">Open Plan</a><a class="out" href="{{url_for(\'business_plan_edit\',plan_id=latest_plan.id)}}">Edit Plan</a><a class="out" href="{{url_for(\'business_plan_pdf\',plan_id=latest_plan.id)}}">Download PDF</a><a class="out" href="{{url_for(\'business_plan_versions\')}}">Saved Copies</a></div></article>{% else %}<article class="card"><h2>No Business Plan Yet</h2><a class="btn" href="{{url_for(\'business_builder\')}}">Create My $79.99 Business Package</a></article>{% endif %}{% endblock %}', 'business_manage.html': '{% extends \'base.html\' %}{% block content %}<h1>Manage Hosted App</h1>{% if b %}<form class="card" method="post"><h2>Create a Class</h2><label>Title<input name="title" required></label><label>Description<textarea name="description"></textarea></label><div class="two"><label>Format<select name="class_format"><option>Live</option><option>Recorded</option><option>Hybrid</option></select></label><label>Price<input name="price"></label></div><div class="two"><label>Date<input type="date" name="class_date"></label><label>Time<input type="time" name="class_time"></label></div><label>Meeting / Registration Link<input name="meeting_url"></label><button>Add Class</button></form>{% else %}<div class="empty">Create your business first.</div>{% endif %}{% endblock %}', 'retreats.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">RETREATS</span><h1>Build a Retreat Constellation</h1><p>Coordinate dates, participating wellness businesses and a private retreat property based on season, group size and budget.</p><a class="btn" href="{{url_for(\'retreat_build\')}}">Build My Retreat</a></section><div class="grid">{% for r in retreats %}<article class="card"><span class="badge">{{r.season}}</span><h3>{{r.title}}</h3><p>{{r.retreat_type}}</p><a class="btn" href="{{url_for(\'retreat_detail\',rid=r.id)}}">Open Retreat</a></article>{% endfor %}</div><h2>Participating Wellness Apps</h2><div class="grid">{% for b in businesses %}{% include \'business_card.html\' %}{% endfor %}</div>{% endblock %}', 'retreat_build.html': '{% extends \'base.html\' %}{% block content %}<h1>Build My Retreat</h1><form class="card" method="post"><label>Title<input name="title" required></label><label>Season<select name="season"><option>Spring</option><option>Summer</option><option>Autumn</option><option>Winter</option></select></label><label>Type<select name="retreat_type"><option>Solo Renewal</option><option>Couples / Dating</option><option>Friendship</option><option>Family</option><option>Creator / Business</option></select></label><label>Dates<input name="preferred_dates"></label><label>Guests<input type="number" name="guests" value="1"></label><label>Budget<input name="budget"></label><label>Private retreat property preferences<textarea name="lodging_preferences"></textarea></label><label>Wellness interests<textarea name="wellness_interests"></textarea></label><input type="hidden" name="connection_retreat" value="{{1 if connection else 0}}"><button>Create Retreat Plan</button></form>{% endblock %}', 'retreat_detail.html': '{% extends \'base.html\' %}{% block content %}<article class="card"><span class="badge">{{r.season}}</span><h1>{{r.title}}</h1><p>{{r.retreat_type}} • {{r.guests}} guests</p><p>{{r.preferred_dates}}</p><p>{{r.lodging_preferences}}</p><p>{{r.wellness_interests}}</p></article>{% if me %}<form class="card" method="post"><h2>Contact About Retreat Dates</h2><textarea name="body"></textarea><button>Send Message</button></form>{% endif %}{% for m in messages %}<article class="card"><b>{{m.name}}</b><p>{{m.body}}</p></article>{% endfor %}{% endblock %}', 'membership.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><h1>Membership & Business Packages</h1><p>Free to belong. Upgrade when you want deeper connection tools, a Hosted Business App or the Startup Business package.</p></section><div class="grid"><article class="card"><span class="badge">FREE</span><h2>Community</h2><h1>$0</h1><p>Basic profile, Community, private Journal, marketplace, Retreats and free Conscious Connections profile.</p></article><article class="card paid"><span class="badge">★ FULL MEMBERSHIP</span><h2>Conscious Coordination</h2><h1>$10.99/mo</h1><p>Full compatibility, shared birth-chart access where permitted, chart comparison, up to 7 photos + 2 profile videos, compatible-member alerts and eligible video tools.</p>{% if me and not me.membership_access %}<a class="btn" href="{{url_for(\'checkout\',kind=\'full_membership\')}}">Upgrade</a>{% endif %}</article><article class="card paid"><span class="badge">★ BUSINESS NETWORK</span><h2>Hosted Business App</h2><h1>$29.99/mo</h1><p>Standout hosted app, social links, classes, videos, events, media kit and Retreat participation.</p>{% if me and not me.business_access %}<a class="btn" href="{{url_for(\'checkout\',kind=\'business_app\')}}">Upgrade</a>{% endif %}</article><article class="card paid"><span class="badge">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan Package</h2><h1>$79.99</h1><p>10–15 page Business Plan PDF + Marketing Strategy + 90-Day Launch Plan + editable saved copies, download, email and share.</p>{% if me and not me.startup_access %}<a class="btn" href="{{url_for(\'checkout\',kind=\'startup_package\')}}">Purchase</a>{% else %}<a class="out" href="{{url_for(\'business_builder\')}}">Open Builder</a>{% endif %}</article></div><article class="card"><h2>Video Add-Ons</h2><p><b>Add 5 minutes — $5.</b> <b>Paid video request/message — $5.</b> The receiving Free or Full member can answer without paying the sender charge.</p></article>{% endblock %}', 'messages.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">PRIVATE MEMBER MESSAGES</span><h1>My Inbox</h1></section>{% for m in rows %}<article class="card"><span class="badge">{{m.message_type}}</span><h3>{{m.other_name}}</h3><p>{{m.body}}</p><a class="out" href="{{url_for(\'compose_message\',recipient_id=m.other_id,kind=m.message_type)}}">Reply Privately</a></article>{% else %}<div class="empty">Private conversations appear here.</div>{% endfor %}{% endblock %}', 'compose.html': '{% extends \'base.html\' %}{% block content %}<h1>Message {{person.name}}</h1><form class="card" method="post"><label>Subject<input name="subject"></label><label>Message<textarea name="body" required></textarea></label><button>Send Private Message</button></form>{% endblock %}', 'notifications.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">MEMBER ALERTS</span><h1>Notifications</h1></section>{% for n in rows %}<article class="card"><span class="badge">{{n.notification_type}}</span><h3>{{n.title}}</h3><p>{{n.body}}</p><small>{{n.created_at}}</small></article>{% else %}<div class="empty">Notifications appear here.</div>{% endfor %}{% endblock %}', 'video.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">★ PRIVATE VIDEO CONNECTION</span><h1>Video Chat With {{person.name}}</h1><p>This is the paid Conscious Connections video area. The access/timer model is built here; reliable camera-to-camera calling still requires WebRTC/TURN configuration.</p></section><div class="two"><article class="card"><h3>You</h3><div class="empty">Your Camera</div></article><article class="card"><h3>{{person.name}}</h3><div class="empty">Their Camera</div></article></div><article class="card" style="text-align:center"><h2 id="timer">05:00</h2><p>Included 5 minutes + any purchased extra time.</p><a class="btn" href="{{url_for(\'checkout\',kind=\'video_time\',target_id=session_row.id)}}">Add 5 Minutes — $5</a></article>{% endblock %}', 'connections_edit.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">♡ CONSCIOUS CONNECTIONS PROFILE</span><h1>Create / Edit My Connections Profile</h1><p>Mostly multiple-choice questions shape discovery, compatibility and the information shown on your profile.</p></section><form class="card" method="post" enctype="multipart/form-data">\n<label>Connection Type<select name="connection_type">{% for x in [\'Love & Dating\',\'Friendship\',\'Both\'] %}<option {% if cp and cp.connection_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>\n<div class="two"><label>I am<select name="gender">{% for x in [\'Woman\',\'Man\',\'Nonbinary\',\'Other / Self-describe\',\'Prefer not to say\'] %}<option {% if cp and cp.gender==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Who would you like to meet?<select name="seeking">{% for x in [\'Men\',\'Women\',\'Both\',\'Everyone\',\'Open / No preference\'] %}<option {% if cp and cp.seeking==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label></div>\n<label>Location Preference<select name="location_pref">{% for x in [\'Local only\',\'Within driving distance\',\'Same state / region\',\'Open to distance\',\'Open to travel\'] %}<option {% if cp and cp.location_pref==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>\n<div class="two"><label>Minimum Age<input type="number" min="18" name="age_min" value="{{cp.age_min if cp else 25}}"></label><label>Maximum Age<input type="number" min="18" name="age_max" value="{{cp.age_max if cp else 65}}"></label></div>\n{% macro opts(name,items,current=\'\') %}<div class="chips">{% for x in items %}<label class="chip"><input style="width:auto;margin:0 4px 0 0" type="checkbox" name="{{name}}" value="{{x}}" {% if x in (current or \'\') %}checked{% endif %}>{{x}}</label>{% endfor %}</div>{% endmacro %}\n<label>What are you looking for?</label>{{opts(\'looking_for\',[\'Long-term relationship\',\'Dating\',\'Friendship\',\'Wellness companion\',\'Activity partner\',\'Travel companion\',\'Retreat companion\',\'Open to possibilities\'],cp.looking_for if cp else \'\')}}\n<div class="two"><label>Occupation / What do you do?<input name="occupation" value="{{cp.occupation if cp else \'\'}}"></label><label>Children<select name="children">{% for x in [\'No children\',\'Young children\',\'Teen children\',\'Adult children\',\'Prefer not to say\'] %}<option {% if cp and cp.children==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label></div>\n<div class="two"><label>Height<select name="height">{% for x in [\'Prefer not to say\',\'Under 5ft 2in\',\'5ft 2in–5ft 5in\',\'5ft 6in–5ft 9in\',\'5ft 10in–6ft 1in\',\'6ft 2in+\'] %}<option {% if cp and cp.height==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label><label>Weight<select name="weight">{% for x in [\'Prefer not to say\',\'Under 130\',\'130–160\',\'161–190\',\'191–220\',\'221+\'] %}<option {% if cp and cp.weight==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label></div>\n<h2>Social & Emotional Compatibility</h2>\n{% for label,name,items in emotional_fields %}<label>{{label}}<select name="{{name}}">{% for x in items %}<option {% if cp and cp[name]==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></label>{% endfor %}\n<label>Love Languages</label>{{opts(\'love_languages\',[\'Words of Affirmation\',\'Quality Time\',\'Acts of Service\',\'Physical Touch\',\'Gifts / Thoughtful Gestures\'],cp.love_languages if cp else \'\')}}\n<h2>Lifestyle & Values</h2><label>Lifestyle</label>{{opts(\'lifestyle\',[\'Wellness & self-care\',\'Active & outdoors\',\'Social & outgoing\',\'Homebody & relaxed\',\'Spiritual / reflective\',\'Family-centered\',\'Career-focused\',\'Creative lifestyle\'],cp.lifestyle if cp else \'\')}}\n<label>Things I Enjoy</label>{{opts(\'activities\',[\'Travel\',\'Dining & entertainment\',\'Nature & outdoors\',\'Wellness & retreats\',\'Relaxing at home\',\'Arts & culture\',\'Fitness\',\'Live music / events\'],cp.activities if cp else \'\')}}\n<label>What Matters Most</label>{{opts(\'values_text\',[\'Trust & honesty\',\'Communication\',\'Affection & chemistry\',\'Shared values\',\'Growth & support\',\'Reliability\',\'Family\',\'Freedom & independence\'],cp.values_text if cp else \'\')}}\n<label>About Me<textarea name="about">{{cp.about if cp else \'\'}}</textarea></label>\n<h2>Profile Media</h2><p class="muted">Free: 1 photo. Full $10.99 Membership: up to 7 photos + 2 profile videos.</p><input type="file" name="media_files" multiple accept="image/*,video/*"><br><br><button>Save & Enter Conscious Connections</button></form>{% endblock %}', 'compatibility.html': '{% extends \'base.html\' %}{% block content %}<section class="hero {% if me.membership_access %}paid{% endif %}"><span class="badge">{{\'★ $10.99 FULL COMPATIBILITY\' if me.membership_access else \'FREE COMPATIBILITY PREVIEW\'}}</span><h1>Conscious Coordination Report</h1><p>Social/emotional compatibility comes from members\' own answers. Astrology is shown as a separate reflective layer.</p></section><article class="card"><h2>{{report.overall}}% Overall Coordination</h2><div class="meter"><i style="width:{{report.overall}}%"></i></div><p class="muted">Guidance—not proof of psychological health, destiny or relationship success.</p></article>\n{% if me.membership_access %}<div class="grid">{% for name,score in report.social.items() %}<article class="card"><h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div><p class="muted">{{report.descriptions[name]}}</p></article>{% endfor %}</div><article class="card"><h2>Astrology Layer</h2>{% for name,score in report.astro.items() %}{% if score is not none %}<h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div><p class="muted">{{report.descriptions[name]}}</p>{% endif %}{% endfor %}{% if can_view_chart %}<a class="btn" href="{{url_for(\'birth_chart_view\',uid=person.id)}}">Open Full Birth Chart Compatibility</a>{% endif %}</article><article class="card"><h2>Strengths</h2><p>{{report.strengths}}</p><h2>Differences Worth Understanding</h2><p>{{report.differences}}</p><h2>Conversation Ideas</h2>{% for q in report.questions %}<div class="fact">{{q}}</div>{% endfor %}</article>{% else %}<article class="card"><h2>Basic Compatibility</h2>{% for name in [\'Communication\',\'Emotional Style\',\'Lifestyle & Values\',\'Astrology Preview\'] %}<h3>{{name}} — {{report.basic[name]}}%</h3><div class="meter"><i style="width:{{report.basic[name]}}%"></i></div>{% endfor %}<h3>One Strength</h3><p>{{report.strengths}}</p><h3>One Difference</h3><p>{{report.differences}}</p><h3>Conversation Starter</h3><p>{{report.questions[0]}}</p><a class="btn" href="{{url_for(\'membership\')}}">Unlock Full Compatibility — $10.99</a></article>{% endif %}{% endblock %}', 'birth_chart.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">★ FULL MEMBER • BIRTH CHART COMPATIBILITY</span><h1>Chart-to-Chart Conscious Coordination</h1><p>View the other member\'s shared chart and compare it with yours. Rising and houses appear only when accurate birth data supports them.</p></section><div class="two"><article class="card"><h2>Your Chart</h2><div class="chips">{% for x in planets %}{% if me[x] %}<span class="chip">{{x|title}} {{me[x]}}</span>{% endif %}{% endfor %}</div></article><article class="card"><h2>{{person.name}}\'s Shared Chart</h2><div class="chips">{% for x in planets %}{% if person[x] %}<span class="chip">{{x|title}} {{person[x]}}</span>{% endif %}{% endfor %}</div></article></div><article class="card"><h2>Planet-to-Planet Coordination</h2>{% for name,score in report.astro.items() %}{% if score is not none %}<h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div><p class="muted">{{report.descriptions[name]}}</p>{% endif %}{% endfor %}</article>{% if me.rising and person.rising %}<article class="card"><h2>House Overlay Layer Available</h2><p class="muted">Both profiles have usable birth-time/location information, so house overlays can be calculated.</p></article>{% endif %}{% endblock %}', 'video_request.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">★ VIDEO CONNECTION</span><h1>Connect With {{person.name}}</h1><p>Full members receive an included first 5-minute video connection when the other member accepts. Extra 5-minute blocks are $5. A paid video request/message is $5; the recipient can answer without paying.</p></section><div class="grid"><article class="card"><h2>5-Minute Live Video Request</h2><form method="post"><input type="hidden" name="action" value="live"><button>Send Live Video Request</button></form></article><article class="card paid"><h2>$5 Video Message / Request</h2><a class="btn" href="{{url_for(\'checkout\',kind=\'video_message\',target_id=person.id)}}">Send for $5</a></article></div>{% endblock %}', 'business_plan.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">BUSINESS PLAN • VERSION {{plan.version_no}}</span><h1>{{plan.business_name}}</h1><p>Stored in your Business Dashboard. Modify it, save versions, download PDF, email it or share it from your device.</p><div class="actions"><a class="btn" href="{{url_for(\'business_plan_edit\',plan_id=plan.id)}}">Edit Plan</a><a class="out" href="{{url_for(\'business_plan_pdf\',plan_id=plan.id)}}">Download PDF</a><a class="out" href="{{url_for(\'business_plan_send\',plan_id=plan.id)}}">Email PDF</a><button class="out" onclick="sharePlan()">Share PDF</button><a class="out" href="{{url_for(\'business_plan_versions\')}}">Saved Copies</a></div></section>{% for title,text in sections.items() %}<article class="card"><h2>{{title}}</h2><p style="white-space:pre-wrap;line-height:1.65">{{text}}</p></article>{% endfor %}<article class="card"><h2>Marketing Strategy</h2><p style="white-space:pre-wrap">{{plan.marketing_text}}</p></article><article class="card"><h2>90-Day Launch Plan</h2><p style="white-space:pre-wrap">{{plan.launch_text}}</p></article>{% endblock %}{% block scripts %}<script>async function sharePlan(){try{let r=await fetch("{{url_for(\'business_plan_pdf\',plan_id=plan.id)}}");let b=await r.blob();let f=new File([b],"business-plan.pdf",{type:"application/pdf"});if(navigator.share&&navigator.canShare&&navigator.canShare({files:[f]})){await navigator.share({title:"{{plan.business_name}} Business Plan",files:[f]});}else{window.location="{{url_for(\'business_plan_pdf\',plan_id=plan.id)}}";}}catch(e){window.location="{{url_for(\'business_plan_pdf\',plan_id=plan.id)}}";}}</script>{% endblock %}', 'business_plan_edit.html': '{% extends \'base.html\' %}{% block content %}<h1>Edit Business Plan</h1><form class="card" method="post"><p class="muted">Saving creates a new version so your earlier copy remains available.</p>{% for title,text in sections.items() %}<label>{{title}}<textarea name="section_{{loop.index0}}">{{text}}</textarea><input type="hidden" name="title_{{loop.index0}}" value="{{title}}"></label>{% endfor %}<label>Marketing Strategy<textarea name="marketing_text">{{plan.marketing_text}}</textarea></label><label>90-Day Launch Plan<textarea name="launch_text">{{plan.launch_text}}</textarea></label><button>Save as New Version</button></form>{% endblock %}', 'business_plan_versions.html': '{% extends \'base.html\' %}{% block content %}<h1>Saved Business Plan Copies</h1>{% for p in plans %}<article class="card"><span class="badge">VERSION {{p.version_no}}</span><h3>{{p.business_name}}</h3><small>{{p.created_at}}</small><div class="actions"><a class="btn" href="{{url_for(\'business_plan_view\',plan_id=p.id)}}">Open</a><a class="out" href="{{url_for(\'business_plan_pdf\',plan_id=p.id)}}">Download PDF</a></div></article>{% else %}<div class="empty">Saved versions appear here.</div>{% endfor %}{% endblock %}', 'business_plan_send.html': '{% extends \'base.html\' %}{% block content %}<h1>Email Business Plan PDF</h1><form class="card" method="post"><label>Email Address<input type="email" name="email" required></label><label>Message<textarea name="message">Attached is my {{plan.business_name}} Business Plan.</textarea></label><button>Send PDF</button></form><p class="muted">Email sending uses configured SMTP settings. If SMTP is not configured, download the PDF and use your normal email/share tools.</p>{% endblock %}', 'checkout.html': '{% extends \'base.html\' %}{% block content %}<section class="hero paid"><span class="badge">CHECKOUT</span><h1>{{item.name}}</h1><h1>{{item.display}}</h1><p>{{item.description}}</p>{% if stripe_ready %}<form method="post"><button>Continue to Secure Checkout</button></form>{% else %}<div class="notice"><b>Payment processor is not connected yet.</b> Real charges require Stripe environment variables in Render. Admin accounts can preview paid areas without charging.</div>{% endif %}</section>{% endblock %}', 'payment_success.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><h1>Thank You</h1><p>Your payment was submitted. Access updates after secure payment confirmation reaches The Seasons Within.</p><a class="btn" href="{{url_for(\'profile\')}}">Return to My Profile</a></section>{% endblock %}', 'moderation_block.html': '{% extends \'base.html\' %}{% block content %}<section class="hero"><span class="badge">MESSAGE NOT SENT</span><h1>Please revise this content</h1><p>{{reason}}</p><a class="out" href="javascript:history.back()">Go Back</a></section>{% endblock %}'}

app.jinja_loader=DictLoader(T)
app.jinja_env.globals.update(media_url=media_url,user_paths=user_paths,age_from_birth=age_from_birth)
@app.context_processor
def inject():return {"me":me()}

@app.route("/brand-logo")
def brand_logo():
    for name in ["seasons-within-logo.png","logo.svg","seasons-within-logo.svg"]:
        p=BASE/"static"/name
        if p.exists():return send_from_directory(p.parent,p.name)
    svg="""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"><circle cx="150" cy="150" r="140" fill="#f2e9f8"/><path d="M150 18A132 132 0 0 1 282 150H150Z" fill="#d6b9e5"/><path d="M282 150A132 132 0 0 1 150 282V150Z" fill="#f0c9cc"/><path d="M150 282A132 132 0 0 1 18 150H150Z" fill="#ead8aa"/><path d="M18 150A132 132 0 0 1 150 18V150Z" fill="#cab6df"/><circle cx="150" cy="150" r="58" fill="white"/><text x="150" y="158" text-anchor="middle" font-family="Georgia" font-size="28" fill="#68428a">TSW</text></svg>"""
    return Response(svg,mimetype="image/svg+xml")
@app.route("/uploads/<path:filename>")
def uploads(filename):return send_from_directory(UPLOADS,filename)

@app.route("/")
@app.route("/home")
def home():
    c=conn();businesses=c.execute("select * from businesses where status='active' order by paid_business desc,featured_order,id limit 8").fetchall();retreats=c.execute("select * from retreats order by id desc limit 4").fetchall();c.close()
    return render_template("home.html",businesses=businesses,retreats=retreats,sky=sky())

@app.route("/join",methods=["GET","POST"])
def join():
    if request.method=="POST":
        bd=request.form.get("birth_date","")
        if not request.form.get("age_confirm") or (age_from_birth(bd) is not None and age_from_birth(bd)<18):
            flash("The member account and Conscious Connections are for adults age 18+.");return render_template("join.html")
        paths="|".join(request.form.getlist("paths") or ["Community"])
        try:
            c=conn();cur=c.execute("insert into users(name,email,password_hash,birth_date,paths) values(?,?,?,?,?)",(request.form["name"].strip(),request.form["email"].strip().lower(),hp(request.form["password"]),bd,paths));c.commit();uid=cur.lastrowid;c.close();session["uid"]=uid;calc_chart(uid);return redirect(url_for("profile"))
        except sqlite3.IntegrityError:flash("That email already has an account. Please log in.")
    return render_template("join.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=conn();u=c.execute("select * from users where lower(email)=?",(request.form["email"].strip().lower(),)).fetchone();c.close()
        if u and u["password_hash"]==hp(request.form["password"]):session["uid"]=u["id"];return redirect(request.args.get("next") or url_for("profile"))
        flash("Email or password did not match.")
    return render_template("login.html")
@app.route("/logout")
def logout():session.clear();return redirect(url_for("home"))

@app.route("/profile")
@login_required
def profile():
    u=me();c=conn();cp=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();c.close();return render_template("profile.html",u=u,cp=cp)
@app.route("/profile/edit",methods=["GET","POST"])
@login_required
def profile_edit():
    u=me()
    if request.method=="POST":
        def num(x):
            try:return float(request.form.get(x,""))
            except:return None
        photo=save_file(request.files.get("photo"),f"user{u['id']}") or u["photo"];paths="|".join(request.form.getlist("paths") or ["Community"])
        c=conn();c.execute("update users set name=?,city=?,headline=?,bio=?,photo=?,paths=?,birth_date=?,birth_time=?,birth_lat=?,birth_lon=?,birth_utc_offset=?,time_known=?,chart_visibility=? where id=?",(request.form.get("name","").strip(),request.form.get("city",""),request.form.get("headline",""),request.form.get("bio",""),photo,paths,request.form.get("birth_date",""),request.form.get("birth_time",""),num("birth_lat"),num("birth_lon"),num("birth_utc_offset") or 0,1 if request.form.get("time_known") else 0,request.form.get("chart_visibility","full"),u["id"]));c.commit();c.close();calc_chart(u["id"]);return redirect(url_for("profile"))
    return render_template("profile_edit.html",u=u)

@app.route("/community",methods=["GET","POST"])
@login_required
def community():
    u=me();c=conn()
    if request.method=="POST":
        ok,reason=moderate_text(request.form.get("body",""))
        if not ok:c.close();return render_template("moderation_block.html",reason=reason)
        photo=save_file(request.files.get("photo"),f"community{u['id']}") if request.files.get("photo") else ""
        c.execute("insert into community_posts(user_id,body,photo) values(?,?,?)",(u["id"],request.form["body"].strip(),photo));c.commit()
    posts=c.execute("select p.*,u.name from community_posts p join users u on u.id=p.user_id order by p.id desc").fetchall();sponsors=c.execute("select * from businesses where paid_business=1 and sponsor_community=1 and status='active' order by featured_order,id").fetchall();c.close();return render_template("community.html",posts=posts,sponsors=sponsors)

@app.route("/journal",methods=["GET","POST"])
@login_required
def journal():
    u=me();c=conn()
    if request.method=="POST":c.execute("insert into journals(user_id,title,body) values(?,?,?)",(u["id"],request.form.get("title",""),request.form["body"]));c.commit()
    entries=c.execute("select * from journals where user_id=? order by id desc",(u["id"],)).fetchall();c.close();return render_template("journal.html",entries=entries)
@app.post("/journal/<int:jid>/share")
@login_required
def journal_share(jid):
    u=me();c=conn();e=c.execute("select * from journals where id=? and user_id=?",(jid,u["id"])).fetchone()
    if e:c.execute("insert into community_posts(user_id,body,photo) values(?,?,?)",(u["id"],((e["title"]+"\n\n") if e["title"] else "")+e["body"],""));c.commit();flash("A separate copy was shared to Community. Your journal entry remains private.")
    c.close();return redirect(url_for("journal"))

@app.route("/messages")
@login_required
def messages():
    u=me();c=conn();rows=c.execute("""select m.*,case when m.sender_id=? then rr.name else s.name end other_name,case when m.sender_id=? then rr.id else s.id end other_id from messages m join users s on s.id=m.sender_id join users rr on rr.id=m.recipient_id where m.sender_id=? or m.recipient_id=? order by m.id desc""",(u["id"],u["id"],u["id"],u["id"])).fetchall();c.close();return render_template("messages.html",rows=rows)
@app.route("/message/<int:recipient_id>",methods=["GET","POST"])
@login_required
def compose_message(recipient_id):
    u=me();c=conn();person=c.execute("select * from users where id=?",(recipient_id,)).fetchone();c.close()
    if not person:abort(404)
    if request.method=="POST":
        ok,reason=moderate_text(request.form.get("body",""))
        if not ok:return render_template("moderation_block.html",reason=reason)
        kind=request.args.get("kind","people");c=conn();c.execute("insert into messages(sender_id,recipient_id,message_type,subject,body) values(?,?,?,?,?)",(u["id"],recipient_id,kind,request.form.get("subject",""),request.form["body"]));c.commit();c.close();notify(recipient_id,kind,"New private message",f"{u['name']} sent you a private message.");return redirect(url_for("messages"))
    return render_template("compose.html",person=person)
@app.route("/notifications")
@login_required
def notifications():
    c=conn();rows=c.execute("select * from notifications where user_id=? order by id desc",(me()["id"],)).fetchall();c.close();return render_template("notifications.html",rows=rows)

@app.route("/connections/join",methods=["GET","POST"])
@login_required
def connections_join():
    u=me()
    if request.method=="POST":
        paths=user_paths(u)
        if "Connections" not in paths:paths.append("Connections")
        c=conn();c.execute("update users set paths=? where id=?",("|".join(paths),u["id"]));c.execute("insert or ignore into connection_profiles(user_id,connection_type) values(?,?)",(u["id"],request.form["connection_type"]));c.execute("update connection_profiles set connection_type=? where user_id=?",(request.form["connection_type"],u["id"]));c.commit();c.close();return redirect(url_for("connections_edit"))
    return render_template("connections_join.html")

@app.route("/connections/edit",methods=["GET","POST"])
@login_required
def connections_edit():
    u=me();c=conn();cp=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();c.close()
    if not cp:return redirect(url_for("connections_join"))
    if request.method=="POST":
        data={k:request.form.get(k,"") for k in ["connection_type","gender","seeking","location_pref","occupation","children","height","weight","emotional_response","others_emotions","conflict_style","repair_style","apology_style","communication_style","boundaries","social_energy","family_goals","about"]}
        data.update(age_min=int(request.form.get("age_min") or 18),age_max=int(request.form.get("age_max") or 99),looking_for=multi("looking_for"),love_languages=multi("love_languages"),lifestyle=multi("lifestyle"),activities=multi("activities"),values_text=multi("values_text"))
        ok,reason=moderate_text(data["about"])
        if not ok:return render_template("moderation_block.html",reason=reason)
        c=conn();sets=",".join(f"{k}=?" for k in data);c.execute(f"update connection_profiles set {sets} where user_id=?",tuple(data.values())+(u["id"],))
        rows=c.execute("select media_type,count(*) n from connection_media where user_id=? group by media_type",(u["id"],)).fetchall();counts={r["media_type"]:r["n"] for r in rows};max_img=7 if u["membership_access"] or u["is_admin"] else 1;max_vid=2 if u["membership_access"] or u["is_admin"] else 0
        for fs in request.files.getlist("media_files"):
            ext=Path(secure_filename(fs.filename)).suffix.lower();typ="video" if ext in {".mp4",".mov",".m4v",".webm"} else "image"
            if typ=="image" and counts.get("image",0)<max_img:
                f=save_file(fs,f"conn{u['id']}");c.execute("insert into connection_media(user_id,filename,media_type) values(?,?,?)",(u["id"],f,"image"));counts["image"]=counts.get("image",0)+1
            elif typ=="video" and counts.get("video",0)<max_vid:
                f=save_file(fs,f"conn{u['id']}");c.execute("insert into connection_media(user_id,filename,media_type) values(?,?,?)",(u["id"],f,"video"));counts["video"]=counts.get("video",0)+1
        c.commit();c.close();return redirect(url_for("connections"))
    return render_template("connections_edit.html",cp=cp,emotional_fields=EMOTIONAL_FIELDS)

@app.route("/connections",methods=["GET","POST"])
@login_required
def connections():
    u=me();c=conn();cp=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();c.close()
    if not cp:return redirect(url_for("connections_join"))
    is_host=bool(u["is_admin"] or u["email"].lower()==GALAXY_EMAIL)
    if request.method=="POST" and is_host:
        ok,reason=moderate_text(request.form.get("body",""))
        if not ok:return render_template("moderation_block.html",reason=reason)
        fs=request.files.get("media");filename=save_file(fs,f"host{u['id']}") if fs else "";ext=Path(filename).suffix.lower();typ="video" if ext in {".mp4",".mov",".m4v",".webm"} else ("image" if filename else "")
        c=conn();c.execute("insert into connection_posts(user_id,body,media,media_type) values(?,?,?,?)",(u["id"],request.form.get("body",""),filename,typ));c.commit();c.close()
    c=conn();host_posts=c.execute("select p.*,u.name from connection_posts p join users u on u.id=p.user_id where lower(u.email)=? or u.is_admin=1 order by p.id desc",(GALAXY_EMAIL,)).fetchall();raw=c.execute("select u.*,cp.connection_type from users u join connection_profiles cp on cp.user_id=u.id where u.id<>? and lower(u.email)<>? order by u.id desc",(u["id"],GALAXY_EMAIL)).fetchall();connection_businesses=c.execute("select * from businesses where paid_business=1 and approved_connections=1 and status='active' order by featured_order,id").fetchall();c.close()
    people=[]
    for p in raw:
        c=conn();othercp=c.execute("select * from connection_profiles where user_id=?",(p["id"],)).fetchone();c.close();d=dict(p);d["age"]=age_from_birth(p["birth_date"]);d["score"]=full_report(u,p,cp,othercp)["overall"];people.append(d)
    return render_template("connections.html",people=people,host_posts=host_posts,is_host=is_host,connection_businesses=connection_businesses)


@app.route("/connections/profile/<int:uid>")
@login_required
def connection_profile(uid):
    u=me();c=conn();ca=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();person=c.execute("select * from users where id=?",(uid,)).fetchone();cb=c.execute("select * from connection_profiles where user_id=?",(uid,)).fetchone();media=c.execute("select * from connection_media where user_id=? order by sort_order,id",(uid,)).fetchall();c.close()
    if not ca:return redirect(url_for("connections_join"))
    if not person or not cb:abort(404)
    return render_template("connection_profile.html",person=person,cp=cb,media=media,person_age=age_from_birth(person["birth_date"]),report=full_report(u,person,ca,cb),can_view_chart=can_view_chart(u,person))

@app.route("/connections/compatibility/<int:uid>")
@login_required
def compatibility_view(uid):
    u=me();c=conn();ca=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();person=c.execute("select * from users where id=?",(uid,)).fetchone();cb=c.execute("select * from connection_profiles where user_id=?",(uid,)).fetchone();c.close()
    if not ca:return redirect(url_for("connections_join"))
    if not person or not cb:abort(404)
    return render_template("compatibility.html",person=person,report=full_report(u,person,ca,cb),can_view_chart=can_view_chart(u,person))

@app.route("/connections/birth-chart/<int:uid>")
@login_required
def birth_chart_view(uid):
    u=me();c=conn();person=c.execute("select * from users where id=?",(uid,)).fetchone();ca=c.execute("select * from connection_profiles where user_id=?",(u["id"],)).fetchone();cb=c.execute("select * from connection_profiles where user_id=?",(uid,)).fetchone();c.close()
    if not person or not ca or not cb:abort(404)
    if not can_view_chart(u,person):abort(403)
    return render_template("birth_chart.html",person=person,report=full_report(u,person,ca,cb),planets=["sun","moon","rising","mercury","venus","mars","jupiter","saturn"])

@app.route("/connections/video/request/<int:uid>",methods=["GET","POST"])
@login_required
def video_request(uid):
    u=me();c=conn();person=c.execute("select * from users where id=?",(uid,)).fetchone();c.close()
    if not person:abort(404)
    if not (u["membership_access"] or u["is_admin"]):return redirect(url_for("membership"))
    if request.method=="POST":
        c=conn();cur=c.execute("insert into video_sessions(requester_id,recipient_id,status,seconds_available) values(?,?,?,300)",(u["id"],uid,"requested"));sid=cur.lastrowid;c.commit();c.close();notify(uid,"video","Video connection request",f"{u['name']} requested a private 5-minute video connection.");flash("Video request sent. The recipient must accept before live calling.");return redirect(url_for("video_room",sid=sid))
    return render_template("video_request.html",person=person)

@app.route("/video/<int:sid>")
@login_required
def video_room(sid):
    u=me();c=conn();row=c.execute("select * from video_sessions where id=?",(sid,)).fetchone();c.close()
    if not row or u["id"] not in (row["requester_id"],row["recipient_id"]):abort(403)
    other=row["recipient_id"] if u["id"]==row["requester_id"] else row["requester_id"];c=conn();person=c.execute("select * from users where id=?",(other,)).fetchone();c.close()
    return render_template("video.html",person=person,session_row=row)

@app.route("/business")
def business():
    q=request.args.get("q","").strip();c=conn();businesses=c.execute("select * from businesses where status='active' and (?='' or business_name like ? or category like ? or description like ?) order by paid_business desc,featured_order,id",(q,f"%{q}%",f"%{q}%",f"%{q}%")).fetchall();c.close();return render_template("business.html",businesses=businesses,q=q)

@app.route("/business/setup",methods=["GET","POST"])
@login_required
def business_setup():
    u=me();c=conn();b=c.execute("select * from businesses where owner_id=?",(u["id"],)).fetchone();c.close()
    if request.method=="POST":
        logo=save_file(request.files.get("logo"),f"biz{u['id']}logo") or (b["logo"] if b else "");hero=save_file(request.files.get("hero_image"),f"biz{u['id']}hero") or (b["hero_image"] if b else "");video=save_file(request.files.get("featured_video"),f"biz{u['id']}video") or (b["featured_video"] if b else "")
        vals=[request.form.get(k,"") for k in ["business_name","creator_title","tagline","description","category","city","website"]]+[logo,hero,video]+[request.form.get(k,"") for k in ["instagram","tiktok","youtube","facebook","booking_url","modules"]]+[1 if request.form.get("retreat_participation") else 0,1 if request.form.get("sponsor_community") else 0,1 if request.form.get("approved_connections") else 0]
        c=conn()
        if b:c.execute("update businesses set business_name=?,creator_title=?,tagline=?,description=?,category=?,city=?,website=?,logo=?,hero_image=?,featured_video=?,instagram=?,tiktok=?,youtube=?,facebook=?,booking_url=?,modules=?,retreat_participation=?,sponsor_community=?,approved_connections=? where owner_id=?",tuple(vals)+(u["id"],))
        else:c.execute("insert into businesses(business_name,creator_title,tagline,description,category,city,website,logo,hero_image,featured_video,instagram,tiktok,youtube,facebook,booking_url,modules,retreat_participation,sponsor_community,approved_connections,owner_id,slug,paid_business) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(vals)+(u["id"],slugify(request.form["business_name"]),1 if u["business_access"] else 0))
        c.commit();c.close();return redirect(url_for("business"))
    return render_template("business_setup.html",b=b)

@app.route("/app/<slug>")
def business_app(slug):
    c=conn();b=c.execute("select * from businesses where slug=? and status='active'",(slug,)).fetchone()
    if not b:c.close();abort(404)
    classes=c.execute("select * from business_classes where business_id=? and active=1 order by class_date,id",(b["id"],)).fetchall();c.close()
    socials=[("Website",b["website"]),("Instagram",b["instagram"]),("TikTok",b["tiktok"]),("YouTube",b["youtube"]),("Facebook",b["facebook"]),("Book",b["booking_url"])]
    return render_template("business_app.html",b=b,classes=classes,socials=[x for x in socials if x[1]],modules=[x for x in (b["modules"] or "").split("|") if x])

@app.route("/business/builder",methods=["GET","POST"])
def business_builder():
    if not me():return render_template("business_builder.html",row=None,business_types=BUSINESS_TYPES,app_goals=APP_GOALS)
    u=me();c=conn();row=c.execute("select * from business_builder where user_id=?",(u["id"],)).fetchone();c.close()
    if request.method=="POST":
        vals=(request.form.get("stage",""),multi("business_types"),multi("app_goals"),request.form.get("strengths",""),request.form.get("target_customer",""),request.form.get("offers",""),request.form.get("business_name",""),multi("marketing_channels"),request.form.get("pricing_ideas",""),request.form.get("goals_90",""),u["id"])
        c=conn()
        if row:c.execute("update business_builder set stage=?,business_types=?,app_goals=?,strengths=?,target_customer=?,offers=?,business_name=?,marketing_channels=?,pricing_ideas=?,goals_90=? where user_id=?",vals)
        else:c.execute("insert into business_builder(stage,business_types,app_goals,strengths,target_customer,offers,business_name,marketing_channels,pricing_ideas,goals_90,user_id) values(?,?,?,?,?,?,?,?,?,?,?)",vals)
        c.commit();c.close();flash("Questionnaire saved.");return redirect(url_for("business_builder"))
    c=conn();row=c.execute("select * from business_builder where user_id=?",(u["id"],)).fetchone();c.close();return render_template("business_builder.html",row=row,business_types=BUSINESS_TYPES,app_goals=APP_GOALS)

@app.route("/business/plan/generate")
@login_required
def generate_business_plan():
    u=me()
    if not (u["startup_access"] or u["is_admin"]):return redirect(url_for("checkout",kind="startup_package"))
    c=conn();row=c.execute("select * from business_builder where user_id=?",(u["id"],)).fetchone();c.close()
    if not row:flash("Complete the Startup/Hobby → Business questionnaire first.");return redirect(url_for("business_builder"))
    c=conn();mx=c.execute("select max(version_no) v from business_plans where user_id=?",(u["id"],)).fetchone();ver=(mx["v"] or 0)+1;sections=build_plan_sections(row);cur=c.execute("insert into business_plans(user_id,business_name,version_no,sections_json,marketing_text,launch_text) values(?,?,?,?,?,?)",(u["id"],row["business_name"] or "My Business",ver,json.dumps(sections),marketing_text(row),launch_text(row)));pid=cur.lastrowid;c.commit();c.close();return redirect(url_for("business_plan_view",plan_id=pid))

@app.route("/business/dashboard")
@login_required
def business_dashboard():
    u=me();c=conn();b=c.execute("select * from businesses where owner_id=?",(u["id"],)).fetchone();builder=c.execute("select * from business_builder where user_id=?",(u["id"],)).fetchone();latest=c.execute("select * from business_plans where user_id=? order by version_no desc,id desc limit 1",(u["id"],)).fetchone();c.close();return render_template("business_dashboard.html",b=b,builder=builder,latest_plan=latest)

@app.route("/business/plan/<int:plan_id>")
@login_required
def business_plan_view(plan_id):
    c=conn();p=c.execute("select * from business_plans where id=? and user_id=?",(plan_id,me()["id"])).fetchone();c.close()
    if not p:abort(404)
    return render_template("business_plan.html",plan=p,sections=json.loads(p["sections_json"] or "{}"))

@app.route("/business/plan/<int:plan_id>/edit",methods=["GET","POST"])
@login_required
def business_plan_edit(plan_id):
    u=me();c=conn();p=c.execute("select * from business_plans where id=? and user_id=?",(plan_id,u["id"])).fetchone();c.close()
    if not p:abort(404)
    sections=json.loads(p["sections_json"] or "{}")
    if request.method=="POST":
        new={}
        for i in range(len(sections)):new[request.form.get(f"title_{i}","Section")]=request.form.get(f"section_{i}","")
        c=conn();mx=c.execute("select max(version_no) v from business_plans where user_id=?",(u["id"],)).fetchone();ver=(mx["v"] or 0)+1;cur=c.execute("insert into business_plans(user_id,business_name,version_no,sections_json,marketing_text,launch_text) values(?,?,?,?,?,?)",(u["id"],p["business_name"],ver,json.dumps(new),request.form.get("marketing_text",""),request.form.get("launch_text","")));nid=cur.lastrowid;c.commit();c.close();flash(f"Saved as Version {ver}.");return redirect(url_for("business_plan_view",plan_id=nid))
    return render_template("business_plan_edit.html",plan=p,sections=sections)

@app.route("/business/plan/versions")
@login_required
def business_plan_versions():
    c=conn();plans=c.execute("select * from business_plans where user_id=? order by version_no desc,id desc",(me()["id"],)).fetchall();c.close();return render_template("business_plan_versions.html",plans=plans)

@app.route("/business/plan/<int:plan_id>/pdf")
@login_required
def business_plan_pdf(plan_id):
    c=conn();p=c.execute("select * from business_plans where id=? and user_id=?",(plan_id,me()["id"])).fetchone();c.close()
    if not p:abort(404)
    sections=json.loads(p["sections_json"] or "{}");pages=list(sections.items())+[("Marketing Strategy",p["marketing_text"]),("90-Day Launch Plan",p["launch_text"])]
    pdf=simple_pdf_bytes(p["business_name"],pages[:15]);name=slugify(p["business_name"])+"-business-plan-v"+str(p["version_no"])+".pdf";path=PDFS/name;path.write_bytes(pdf);return send_file(path,as_attachment=True,download_name=name,mimetype="application/pdf")

@app.route("/business/plan/<int:plan_id>/send",methods=["GET","POST"])
@login_required
def business_plan_send(plan_id):
    c=conn();p=c.execute("select * from business_plans where id=? and user_id=?",(plan_id,me()["id"])).fetchone();c.close()
    if not p:abort(404)
    if request.method=="POST":
        host=os.environ.get("SMTP_HOST");user=os.environ.get("SMTP_USER");pwd=os.environ.get("SMTP_PASSWORD");sender=os.environ.get("SMTP_FROM",user or "")
        if not host or not sender:flash("Email is not configured yet. Download the PDF and use your normal email/share tools.");return redirect(url_for("business_plan_send",plan_id=plan_id))
        sections=json.loads(p["sections_json"] or "{}");pdf=simple_pdf_bytes(p["business_name"],list(sections.items())+[("Marketing Strategy",p["marketing_text"]),("90-Day Launch Plan",p["launch_text"])])
        msg=EmailMessage();msg["From"]=sender;msg["To"]=request.form["email"];msg["Subject"]=p["business_name"]+" Business Plan";msg.set_content(request.form.get("message","Attached is the Business Plan."));msg.add_attachment(pdf,maintype="application",subtype="pdf",filename=slugify(p["business_name"])+"-business-plan.pdf")
        port=int(os.environ.get("SMTP_PORT","587"))
        with smtplib.SMTP(host,port,timeout=20) as s:s.starttls(context=ssl.create_default_context());s.login(user,pwd);s.send_message(msg)
        flash("Business Plan PDF emailed.");return redirect(url_for("business_plan_view",plan_id=plan_id))
    return render_template("business_plan_send.html",plan=p)

@app.route("/business/manage",methods=["GET","POST"])
@login_required
def business_manage():
    u=me();c=conn();b=c.execute("select * from businesses where owner_id=?",(u["id"],)).fetchone()
    if request.method=="POST" and b and (u["business_access"] or u["is_admin"]):
        c.execute("insert into business_classes(business_id,title,description,class_format,class_date,class_time,price,meeting_url) values(?,?,?,?,?,?,?,?)",(b["id"],request.form["title"],request.form.get("description",""),request.form.get("class_format","Live"),request.form.get("class_date",""),request.form.get("class_time",""),request.form.get("price",""),request.form.get("meeting_url","")));c.commit()
    c.close();return render_template("business_manage.html",b=b)

@app.route("/retreats")
def retreats():
    c=conn();rows=c.execute("select * from retreats order by id desc").fetchall();businesses=c.execute("select * from businesses where paid_business=1 and retreat_participation=1 and status='active' order by featured_order,id").fetchall();c.close();return render_template("retreats.html",retreats=rows,businesses=businesses)
@app.route("/retreats/build",methods=["GET","POST"])
@login_required
def retreat_build():
    u=me();connection=request.args.get("connection")=="1"
    if request.method=="POST":
        c=conn();cur=c.execute("insert into retreats(owner_id,title,season,retreat_type,preferred_dates,guests,budget,lodging_preferences,wellness_interests,connection_retreat) values(?,?,?,?,?,?,?,?,?,?)",(u["id"],request.form["title"],request.form["season"],request.form["retreat_type"],request.form.get("preferred_dates",""),int(request.form.get("guests") or 1),request.form.get("budget",""),request.form.get("lodging_preferences",""),request.form.get("wellness_interests",""),int(request.form.get("connection_retreat") or 0)));rid=cur.lastrowid;c.commit();c.close();return redirect(url_for("retreat_detail",rid=rid))
    return render_template("retreat_build.html",connection=connection)
@app.route("/retreats/<int:rid>",methods=["GET","POST"])
def retreat_detail(rid):
    c=conn();r=c.execute("select * from retreats where id=?",(rid,)).fetchone();c.close()
    if not r:abort(404)
    u=me()
    if request.method=="POST" and u:
        ok,reason=moderate_text(request.form.get("body",""))
        if not ok:return render_template("moderation_block.html",reason=reason)
        c=conn();c.execute("insert into retreat_messages(retreat_id,sender_id,body) values(?,?,?)",(rid,u["id"],request.form["body"]));c.commit();c.close()
    c=conn();msgs=c.execute("select m.*,u.name from retreat_messages m join users u on u.id=m.sender_id where retreat_id=? order by m.id",(rid,)).fetchall();c.close();return render_template("retreat_detail.html",r=r,messages=msgs)

@app.route("/membership")
def membership():return render_template("membership.html")
@app.route("/checkout/<kind>",methods=["GET","POST"])
@app.route("/checkout/<kind>/<int:target_id>",methods=["GET","POST"])
@login_required
def checkout(kind,target_id=0):
    if kind not in PAY_ITEMS:abort(404)
    item=PAY_ITEMS[kind]
    if request.method=="POST" and stripe_ready():
        u=me();c=conn();cur=c.execute("insert into purchases(user_id,kind,target_id,amount_cents) values(?,?,?,?)",(u["id"],kind,target_id,item["amount"]));pid=cur.lastrowid;c.commit();c.close()
        try:
            s=stripe_checkout(kind,u["id"],target_id);c=conn();c.execute("update purchases set stripe_session_id=? where id=?",(s.get("id"),pid));c.commit();c.close();return redirect(s["url"])
        except Exception:flash("Secure checkout could not open. Please check the payment configuration.")
    return render_template("checkout.html",item=item,stripe_ready=stripe_ready())
@app.route("/payment/success")
def payment_success():return render_template("payment_success.html")
@app.post("/stripe/webhook")
def stripe_webhook():
    payload=request.get_data();sig=request.headers.get("Stripe-Signature","")
    if not verify_stripe(payload,sig):return "invalid",400
    event=json.loads(payload.decode());typ=event.get("type");obj=event.get("data",{}).get("object",{})
    if typ=="checkout.session.completed":
        md=obj.get("metadata",{});uid=int(md.get("user_id") or 0);kind=md.get("kind");target=int(md.get("target_id") or 0)
        if uid and kind in PAY_ITEMS:
            activate_purchase(uid,kind,target);c=conn();c.execute("update purchases set status='paid' where stripe_session_id=?",(obj.get("id"),));c.commit();c.close()
    elif typ=="customer.subscription.deleted":
        md=obj.get("metadata",{});uid=int(md.get("user_id") or 0);kind=md.get("kind")
        if uid and kind in {"full_membership","business_app"}:
            c=conn()
            if kind=="full_membership":c.execute("update users set membership_access=0 where id=?",(uid,))
            else:c.execute("update users set business_access=0 where id=?",(uid,));c.execute("update businesses set paid_business=0 where owner_id=?",(uid,))
            c.commit();c.close()
    return "ok",200

init_db()
migrate_db()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5000")),debug=False)
