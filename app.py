import os,re,sqlite3,hashlib,secrets,json,textwrap
from datetime import datetime,date
from functools import wraps
from pathlib import Path
from flask import Flask,render_template,request,redirect,url_for,session,flash,send_from_directory,abort,Response,send_file
from werkzeug.utils import secure_filename
from jinja2 import DictLoader

BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get('PERSISTENT_DATA_DIR',BASE/'data')); DATA.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get('DATABASE_PATH',DATA/'the_seasons_within.db'))
UPLOADS=Path(os.environ.get('UPLOAD_DIR',DATA/'uploads')); UPLOADS.mkdir(parents=True,exist_ok=True)
PDFS=Path(os.environ.get('PDF_DIR',DATA/'pdfs')); PDFS.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get('SECRET_KEY','change-me-in-render')
GALAXY_EMAIL=os.environ.get('GALAXY_EVE_EMAIL','galaxyeve@theseasonswithin.local').lower().strip()
ADMIN_EMAILS={x.lower().strip() for x in [GALAXY_EMAIL,os.environ.get('ADMIN_EMAIL_1',''),os.environ.get('ADMIN_EMAIL_2','')] if x.strip()}

def hp(p): return hashlib.sha256(('tsw::'+p).encode()).hexdigest()
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def me():
    if not session.get('uid'): return None
    c=conn(); u=c.execute('select * from users where id=?',(session['uid'],)).fetchone(); c.close(); return u
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not me(): return redirect(url_for('login',next=request.path))
        return f(*a,**k)
    return w
def slugify(x): return re.sub(r'[^a-z0-9]+','-',(x or '').lower()).strip('-') or secrets.token_hex(4)
def media_url(x): return url_for('uploads',filename=x) if x else ''
def save_file(fs,prefix):
    if not fs or not fs.filename:return ''
    ext=Path(secure_filename(fs.filename)).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp','.gif','.mp4','.mov','.m4v','.webm'}:return ''
    n=f'{prefix}-{secrets.token_hex(6)}{ext}'; fs.save(UPLOADS/n); return n
def multi(name): return ' • '.join(request.form.getlist(name))
def split(v): return [x.strip() for x in (v or '').split(' • ') if x.strip()]
def age(v):
    if not v:return None
    try:
        b=datetime.strptime(v,'%Y-%m-%d').date(); t=date.today(); return t.year-b.year-((t.month,t.day)<(b.month,b.day))
    except:return None
def notify(uid,title,body,kind='General'):
    c=conn(); c.execute('insert into notifications(user_id,title,body,kind) values(?,?,?,?)',(uid,title,body,kind)); c.commit(); c.close()
def notify_all(title,body,kind='Community',exclude=None):
    c=conn()
    for r in c.execute('select id from users').fetchall():
        if r['id']!=exclude:c.execute('insert into notifications(user_id,title,body,kind) values(?,?,?,?)',(r['id'],title,body,kind))
    c.commit(); c.close()

def init_db():
    c=conn(); c.executescript('''
    create table if not exists users(id integer primary key autoincrement,name text,email text unique,password_hash text,photo text default '',city text default '',headline text default '',bio text default '',birth_date text default '',birth_time text default '',birth_city text default '',birth_state text default '',birth_country text default '',time_known integer default 0,full_member integer default 0,startup_access integer default 0,is_admin integer default 0,created_at text default current_timestamp);
    create table if not exists posts(id integer primary key autoincrement,user_id integer,body text,photo text default '',post_as text default 'member',created_at text default current_timestamp);
    create table if not exists journals(id integer primary key autoincrement,user_id integer,title text,body text,category text default 'Reflection',visibility text default 'private',created_at text default current_timestamp);
    create table if not exists messages(id integer primary key autoincrement,sender_id integer,recipient_id integer,source text,subject text,body text,created_at text default current_timestamp);
    create table if not exists notifications(id integer primary key autoincrement,user_id integer,title text,body text,kind text,created_at text default current_timestamp);
    create table if not exists connection_profiles(user_id integer primary key,coordination_types text,gender text,seeking text,age_min integer default 18,age_max integer default 99,occupation text,children text,location_pref text,emotional_regulation text,emotional_support text,communication_style text,conflict_style text,repair_style text,accountability text,boundaries text,trust_style text,independence_style text,social_energy text,love_languages text,interests text,values_text text,work_style text,decision_style text,risk_style text,reliability_style text,retreat_pace text,retreat_social text,retreat_interests text,about text);
    create table if not exists connection_media(id integer primary key autoincrement,user_id integer,filename text,media_type text);
    create table if not exists businesses(id integer primary key autoincrement,owner_id integer,slug text unique,business_name text,creator_title text,category text,city text,tagline text,description text,logo text default '',cover_media text default '',cover_type text default '',website text,instagram text,tiktok text,youtube text,booking_url text,modules text,retreat_participation integer default 0,featured_order integer default 999,status text default 'active');
    create table if not exists business_builder(user_id integer primary key,stage text,business_name text,business_types text,founder_story text,strengths text,target_customer text,customer_problem text,solution text,vision text,core_values text,usp text,offers text,pricing text,revenue text,competitors text,operations text,certifications text,startup_requirements text,startup_budget text,funding text,marketing_channels text,app_goals text,goals_90 text,goals_1yr text);
    create table if not exists business_plans(id integer primary key autoincrement,user_id integer,business_name text,version_no integer,sections_json text,marketing_text text,launch_text text,created_at text default current_timestamp);
    create table if not exists retreats(id integer primary key autoincrement,owner_id integer,title text,retreat_type text,season text,preferred_dates text,guests integer,budget text,wellness_interests text,lodging text,desired_businesses text,created_at text default current_timestamp);
    ''')
    for e in ADMIN_EMAILS:
        c.execute('update users set full_member=1,startup_access=1,is_admin=1 where lower(email)=?',(e,))
    c.commit(); c.close()

def business_modules(category,goals):
    out=['Home','About','Contact']; g=set(split(goals)); t=(category or '').lower()
    def add(x):
        if x not in out: out.append(x)
    if any(k in t for k in ['massage','beauty','hair','coach','consult','reiki','yoga','fitness']): add('Services'); add('Booking')
    if 'Classes' in g or any(k in t for k in ['yoga','fitness','teacher','educator']): add('Classes')
    if 'Events' in g or 'creator' in t or 'speaker' in t: add('Events')
    if 'Shop' in g: add('Shop')
    if 'Videos' in g or 'creator' in t: add('Watch')
    if 'Retreats' in g: add('Retreats')
    if 'Media Kit' in g or 'creator' in t: add('Media Kit')
    if 'Affiliate Links' in g: add('Resources')
    return ' • '.join(out)

def report(ca,cb):
    keys=['emotional_regulation','emotional_support','communication_style','conflict_style','repair_style','accountability','boundaries','trust_style','independence_style','social_energy']
    vals=[90 if ca[k] and cb[k] and ca[k]==cb[k] else 68 for k in keys]
    social=round(sum(vals)/len(vals)); love=85 if set(split(ca['love_languages'])) & set(split(cb['love_languages'])) else 65; values=85 if set(split(ca['values_text'])) & set(split(cb['values_text'])) else 68; overall=round((social*5+love+values)/7)
    return {'overall':overall,'basic':{'Communication':vals[2],'Emotional Style':round((vals[0]+vals[1])/2),'Lifestyle & Values':values,'Astrology Preview':70},'full':{'Social & Emotional Intelligence':social,'Communication':vals[2],'Conflict':vals[3],'Repair & Accountability':round((vals[4]+vals[5])/2),'Emotional Rhythm':vals[0],'Love Languages / Affection':love,'Lifestyle & Values':values,'Boundaries':vals[6],'Psychology-Oriented Compatibility':round((vals[7]+vals[8]+vals[9])/3),'Astrology':70}}

def plan_sections(r):
    name=r['business_name'] or 'Your Business'; customer=r['target_customer'] or 'your intended customer'; problem=r['customer_problem'] or 'the customer problem identified in the interview'; solution=r['solution'] or r['offers'] or 'your proposed solution'
    return {
    'Executive Summary':f'{name} is being developed to serve {customer} by addressing {problem} through {solution}. The plan focuses on a clear offer, sustainable operations, customer acquisition and measured growth.',
    'Business Description':f"{name} is currently at the '{r['stage'] or 'business development'}' stage and operates within {r['business_types'] or 'its selected market category'}.",
    'Founder Story':r['founder_story'] or r['strengths'] or "Add the founder's story, qualifications and motivation.",
    'Mission':f'{name} exists to help {customer} address {problem} by providing {solution}.',
    'Vision':r['vision'] or f'Build {name} into a trusted, sustainable brand with meaningful customer impact over the next 3–5 years.',
    'Core Values':r['core_values'] or 'Integrity • Quality • Care • Reliability • Growth',
    'Unique Selling Proposition':r['usp'] or 'Clarify the strongest difference in specialization, experience, convenience, community, results or customer care.',
    'Products & Services':r['offers'] or 'Define the first focused products, services, classes, events or packages.',
    'Target Customer':customer,'Customer Problem':problem,'Business Solution':solution,
    'Market Overview':'Validate the market through customer conversations, competitor research, local/community demand and online search behavior before making large fixed-cost commitments.',
    'Competitor Analysis':r['competitors'] or 'Identify direct competitors, indirect alternatives, price ranges, strengths and gaps.',
    'Competitive Advantage':r['usp'] or 'Develop a clear reason customers should choose this business instead of an alternative.',
    'Pricing Strategy':r['pricing'] or 'Set pricing from delivery cost, market range, desired margin and customer value; test before expanding.',
    'Revenue Streams':r['revenue'] or 'Possible revenue may include services, products, classes, events, memberships, retreats, digital content, sponsorships or affiliate income.',
    'Marketing Strategy':f"Primary channels: {r['marketing_channels'] or 'social media, referrals and local/community partnerships'}. Use one clear brand message and call to action.",
    'Social Media Strategy':'Use repeatable content pillars: education, founder story, customer experience/proof, offers, and community/collaborations.',
    'Sales Strategy':'Create a simple discovery → trust → inquiry → purchase → follow-up process. Track conversions and response time.',
    'Operations':r['operations'] or 'Define booking, payment, delivery, scheduling, customer support, supplies, record-keeping and cancellation/refund processes.',
    'Technology / Hosted App Strategy':f"Recommended Hosted App modules: {business_modules(r['business_types'],r['app_goals'])}.",
    'Startup Requirements':r['startup_requirements'] or 'List equipment, software, supplies, branding, space, inventory and professional support.',
    'Startup Budget':r['startup_budget'] or 'Separate one-time startup costs from ongoing monthly operating expenses.',
    'Funding Plan':r['funding'] or 'Identify self-funding, grants, loans, investors, donations or other sources if funding is needed.',
    'Revenue Projections':'Build low, target and high scenarios using customers × average sale × purchase frequency rather than relying on one optimistic estimate.',
    '90-Day Launch Strategy':r['goals_90'] or 'Days 1–30 foundation; Days 31–60 visibility/outreach; Days 61–90 launch, measure and refine.',
    'One-Year Goals':r['goals_1yr'] or 'Set measurable one-year goals for customers, revenue, repeat business, partnerships and operating capacity.'}

def pdf_bytes(sections):
    objs=[]
    def add(x):
        if isinstance(x,str):x=x.encode('latin-1','replace')
        objs.append(x); return len(objs)
    font=add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'); pages=[]
    for heading,body in sections[:15]:
        lines=[heading,'']+textwrap.wrap((body or '').replace('\t',' '),86); lines=lines[:45]; cmds=['BT','/F1 11 Tf','54 758 Td']
        for i,line in enumerate(lines):
            s=line.encode('latin-1','replace').decode('latin-1').replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            cmds += (['/F1 16 Tf',f'({s}) Tj','0 -28 Td','/F1 11 Tf'] if i==0 else [f'({s}) Tj','0 -15 Td'])
        cmds.append('ET'); stream='\n'.join(cmds).encode('latin-1'); cid=add(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream'); pages.append(add(f'<< /Type /Page /Parent PAGESREF /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {cid} 0 R >>'))
    pid=add(f"<< /Type /Pages /Kids [{' '.join(f'{x} 0 R' for x in pages)}] /Count {len(pages)} >>"); catalog=add(f'<< /Type /Catalog /Pages {pid} 0 R >>'); objs=[x.replace(b'PAGESREF',f'{pid} 0 R'.encode()) for x in objs]; out=bytearray(b'%PDF-1.4\n'); offs=[0]
    for i,o in enumerate(objs,1):offs.append(len(out));out+=f'{i} 0 obj\n'.encode()+o+b'\nendobj\n'
    xref=len(out);out+=f'xref\n0 {len(objs)+1}\n'.encode()+b'0000000000 65535 f \n'
    for o in offs[1:]:out+=f'{o:010d} 00000 n \n'.encode()
    out+=f'trailer\n<< /Size {len(objs)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF'.encode();return bytes(out)

T={}
T['base.html']="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>The Seasons Within</title><style>:root{--p:#34204f;--u:#8f63ba;--l:#f2e9f8;--line:#eadff1;--m:#75677f;--g:#ddc26f}*{box-sizing:border-box}body{margin:0;font-family:Arial;color:var(--p);background:linear-gradient(#fcf9fd,#fffaf8)}a{text-decoration:none;color:inherit}h1,h2,h3{font-family:Georgia}.top{position:sticky;top:0;z-index:9;background:#fffffff2;border-bottom:1px solid var(--line)}.topin{width:min(1200px,94vw);margin:auto;min-height:74px;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:18px}.brand{display:flex;align-items:center;gap:10px}.logo{width:50px;height:50px}.nav{display:flex;justify-content:center;gap:6px}.nav a{padding:9px 10px;border-radius:999px;font-weight:700}.acct{display:flex;gap:8px}.page{width:min(1120px,92vw);margin:26px auto 110px}.hero,.card{border:1px solid var(--line);border-radius:22px;background:white;padding:20px;margin:15px 0}.hero{background:linear-gradient(135deg,#f0e2fa,#fff1ed)}.premium{border:2px solid var(--g)}.badge,.chip{display:inline-block;padding:6px 9px;border-radius:999px;background:var(--l);font-size:10px;font-weight:900}.gold{background:#fff8df;border:1px solid var(--g)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}.btn,button,.out{display:inline-flex;align-items:center;justify-content:center;border-radius:11px;min-height:40px;padding:9px 14px;font-weight:800;border:1px solid var(--u)}.btn,button{background:var(--u);color:white}.out{background:white;color:#68418c}.muted{color:var(--m);line-height:1.5}.chips,.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}input,textarea,select{width:100%;padding:11px;border:1px solid #ddd0e6;border-radius:11px;margin:5px 0 11px}textarea{min-height:105px}.media{height:210px;border-radius:16px;background:linear-gradient(135deg,#e4d2f0,#f8ded8);display:grid;place-items:center;overflow:hidden}.media img,.media video{width:100%;height:100%;object-fit:cover}.post{display:grid;grid-template-columns:54px 1fr;gap:12px}.avatar{width:54px;height:54px;border-radius:50%;background:#b88bd0;color:#fff;display:grid;place-items:center;overflow:hidden}.avatar img{width:100%;height:100%;object-fit:cover}.bottom{display:none}@media(max-width:800px){body{padding-bottom:80px}.topin{display:flex;justify-content:center}.nav,.acct{display:none}.two{grid-template-columns:1fr}.bottom{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;bottom:8px;left:2.5vw;width:95vw;background:#fff;border:1px solid var(--line);border-radius:20px;padding:7px;z-index:10}.bottom a{text-align:center;font-size:10px;font-weight:800;padding:8px 3px}}</style></head><body><header class='top'><div class='topin'><a class='brand' href='{{url_for("home")}}'><svg class='logo' viewBox='0 0 100 100'><circle cx='50' cy='50' r='47' fill='#f4ebf9'/><circle cx='50' cy='50' r='18' fill='white'/></svg><div><b>The Seasons Within</b><small style='display:block'>Conscious Coordination</small></div></a><nav class='nav'><a href='{{url_for("home")}}'>Home</a>{% if me %}<a href='{{url_for("community")}}'>Community</a><a href='{{url_for("profile")}}'>My Profile</a>{% endif %}<a href='{{url_for("business")}}'>Business Network</a><a href='{{url_for("retreats")}}'>Retreats</a><a href='{{url_for("membership")}}'>Membership</a></nav><div class='acct'>{% if me %}<a href='{{url_for("journal")}}'>Journal</a><a href='{{url_for("logout")}}'>Log Out</a>{% else %}<a href='{{url_for("login")}}'>Log In</a><a class='btn' href='{{url_for("join")}}'>Join Free</a>{% endif %}</div></div></header><main class='page'>{% block content %}{% endblock %}</main>{% if me %}<nav class='bottom'><a href='{{url_for("home")}}'>⌂<br>Home</a><a href='{{url_for("community")}}'>☼<br>Community</a><a href='{{url_for("profile")}}'>◉<br>Profile</a><a href='{{url_for("business")}}'>◇<br>Business</a><a href='{{url_for("more")}}'>•••<br>More</a></nav>{% endif %}</body></html>"""
T['business_card.html']="""<article class='card {% if b.featured_order<50 %}premium{% endif %}'><span class='badge {% if b.featured_order<50 %}gold{% endif %}'>{{'FEATURED' if b.featured_order<50 else 'FREE HOSTED APP'}}</span><div class='media'>{% if b.cover_media %}{% if b.cover_type=='video' %}<video src='{{media_url(b.cover_media)}}' controls></video>{% else %}<img src='{{media_url(b.cover_media)}}'>{% endif %}{% elif b.logo %}<img src='{{media_url(b.logo)}}' style='object-fit:contain;padding:20px'>{% else %}<img src='{{url_for("brand_logo")}}' style='object-fit:contain;padding:30px'>{% endif %}</div><h2>{{b.business_name}}</h2><p><b>{{b.creator_title or b.category}}</b></p><p class='muted'>{{b.tagline or b.description}}</p><a class='btn' href='{{url_for("business_app",slug=b.slug)}}'>Open App</a></article>"""
T['home.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Wellness, Business, Connection & Retreats</h1><p class='muted'>Join free, discover the wellness community, create a free Hosted Business App, build better relationships with self and others, and coordinate meaningful Retreat experiences.</p></section><h2>All Active Hosted Business Apps</h2><div class='grid'>{% for b in businesses %}{% include 'business_card.html' %}{% else %}<article class='card'>Businesses will appear here as they join.</article>{% endfor %}</div><div class='grid'><article class='card'><h2>Design Your Own Retreat</h2><a class='btn' href='{{url_for("retreat_build")}}'>Build My Retreat</a></article><article class='card premium'><span class='badge gold'>$79.99 BUSINESS DEVELOPMENT</span><h2>Professional Business Plan Package</h2><a class='btn' href='{{url_for("business_builder")}}'>Start Business Builder</a></article></div>{% endblock %}"""
T['join.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Create Your Free Account</h1></section><form class='card' method='post'><input name='name' placeholder='Name' required><input type='email' name='email' placeholder='Email' required><input type='password' name='password' placeholder='Password' required><input type='date' name='birth_date' required><label><input style='width:auto' type='checkbox' name='age_confirm' required> I confirm I am 18 or older.</label><br><br><button>Create My Free Account</button></form>{% endblock %}"""
T['login.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Welcome Back</h1></section><form class='card' method='post'><input type='email' name='email' placeholder='Email' required><input type='password' name='password' placeholder='Password' required><button>Log In</button></form>{% endblock %}"""
T['profile.html']="""{% extends 'base.html' %}{% block content %}<section class='hero {% if u.full_member %}premium{% endif %}'><span class='badge {% if u.full_member %}gold{% endif %}'>{{'★ FULL MEMBER • CONSCIOUS COORDINATION' if u.full_member else 'FREE MEMBER'}}</span><h1>{{u.name}}</h1><p>{{u.headline}} • {{u.city}}</p><p>{{u.bio}}</p><a class='btn' href='{{url_for("profile_edit")}}'>Edit Profile</a></section><div class='grid'><a class='card' href='{{url_for("community")}}'>Community</a><a class='card' href='{{url_for("journal")}}'>My Journal</a><a class='card' href='{{url_for("messages")}}'>Journal Inbox</a><a class='card' href='{{url_for("notifications")}}'>Notifications</a><a class='card' href='{{url_for("connections")}}'>Conscious Coordination</a><a class='card' href='{{url_for("business_dashboard")}}'>Business Dashboard</a></div>{% endblock %}"""
T['profile_edit.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Edit My Profile</h1></section><form class='card' method='post' enctype='multipart/form-data'><input type='file' name='photo' accept='image/*'><input name='name' value='{{u.name}}' placeholder='Name'><input name='city' value='{{u.city}}' placeholder='City'><input name='headline' value='{{u.headline}}' placeholder='Headline'><textarea name='bio' placeholder='About'>{{u.bio}}</textarea><h2>Birth Information</h2><input type='date' name='birth_date' value='{{u.birth_date}}'><input type='time' name='birth_time' value='{{u.birth_time}}'><label><input style='width:auto' type='checkbox' name='time_known' {% if u.time_known %}checked{% endif %}> Exact birth time known</label><input name='birth_city' value='{{u.birth_city}}' placeholder='Birth City'><input name='birth_state' value='{{u.birth_state}}' placeholder='Birth State / Province'><input name='birth_country' value='{{u.birth_country}}' placeholder='Birth Country'><button>Save Profile</button></form>{% endblock %}"""
T['community.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Community</h1><p>Official posts, member posts and private Message Member conversations. No public comments.</p></section>{% if me.is_admin %}<form class='card premium' method='post'><h2>Post as The Seasons Within</h2><textarea name='body' required></textarea><input type='hidden' name='post_as' value='official'><button>Publish Official Post</button></form>{% endif %}<form class='card' method='post' enctype='multipart/form-data'><textarea name='body' placeholder='Share with the community...' required></textarea><input type='file' name='photo'><input type='hidden' name='post_as' value='member'><button>Post</button></form>{% for p in posts %}<article class='card'><div class='post'><div class='avatar'>{% if p.post_as=='official' %}<img src='{{url_for("brand_logo")}}'>{% elif p.profile_photo %}<img src='{{media_url(p.profile_photo)}}'>{% else %}{{p.name[:1]}}{% endif %}</div><div><b>{{'The Seasons Within' if p.post_as=='official' else p.name}}</b><p>{{p.body}}</p>{% if p.photo %}<div class='media'><img src='{{media_url(p.photo)}}'></div>{% endif %}{% if p.post_as!='official' and p.user_id!=me.id %}<a class='out' href='{{url_for("compose_message",uid=p.user_id,source="Community")}}'>Message {{p.name}}</a>{% endif %}</div></div></article>{% endfor %}{% endblock %}"""
T['journal.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>My Seasons Within Journal</h1><p>Private hub for reflections, messages, business work, Retreat planning and Conscious Coordination notes.</p></section><div class='grid'><a class='card' href='{{url_for("messages")}}'>Journal Inbox</a><a class='card' href='{{url_for("business_dashboard")}}'>Business</a><a class='card' href='{{url_for("retreat_build")}}'>Retreat Builder</a><a class='card' href='{{url_for("connections")}}'>Conscious Coordination</a></div><form class='card' method='post'><input name='title' placeholder='Title'><textarea name='body' required></textarea><select name='category'><option>Reflection</option><option>Business</option><option>Retreats</option><option>Conscious Coordination</option></select><select name='visibility'><option value='private'>Private Journal only</option><option value='community'>Share a Copy to Community</option></select><button>Save to Journal</button></form>{% for e in entries %}<article class='card'><span class='badge'>{{e.category}}</span><h3>{{e.title}}</h3><p>{{e.body}}</p></article>{% endfor %}{% endblock %}"""
T['messages.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Journal Inbox</h1></section>{% for m in rows %}<article class='card'><span class='badge'>{{m.source}}</span><h3>{{m.subject}}</h3><p>{{m.body}}</p><a class='out' href='{{url_for("compose_message",uid=m.other_id,source=m.source)}}'>Reply</a></article>{% else %}<article class='card'>Private messages will appear here.</article>{% endfor %}{% endblock %}"""
T['compose.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Message {{person.name}}</h1></section><form class='card' method='post'><input name='subject' value='{{subject}}'><textarea name='body' required></textarea><button>Send Private Message</button></form>{% endblock %}"""
T['notifications.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Notifications</h1></section>{% for n in rows %}<article class='card'><span class='badge'>{{n.kind}}</span><h3>{{n.title}}</h3><p>{{n.body}}</p></article>{% else %}<article class='card'>Notifications will appear here.</article>{% endfor %}{% endblock %}"""
T['connections.html']="""{% extends 'base.html' %}{% block content %}<section class='hero {% if me.full_member %}premium{% endif %}'><h1>Conscious Coordination</h1><p>Relationships, friendship, business partners and Retreats with emotional-intelligence questions.</p><a class='btn' href='{{url_for("connections_edit")}}'>Create / Edit Profile</a>{% if not me.full_member %}<a class='out' href='{{url_for("membership")}}'>Upgrade — $10.99/month</a>{% endif %}</section><div class='grid'>{% for p in people %}<article class='card'><h3>{{p.name}}</h3><p>{{p.coordination_types}}</p><h3>{{p.score}}% Coordination</h3><a class='btn' href='{{url_for("connection_profile",uid=p.id)}}'>View Profile</a></article>{% else %}<article class='card'>Participating members will appear here.</article>{% endfor %}</div>{% endblock %}"""
T['connections_edit.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Emotional Intelligence & Connection Style</h1></section><form class='card' method='post'><label>Coordination Types</label><div class='chips'>{% for x in ['Love / Dating','Friendship','Business / Collaboration','Retreat / Activity Connections'] %}<label class='chip'><input style='width:auto' type='checkbox' name='coordination_types' value='{{x}}'>{{x}}</label>{% endfor %}</div><input name='gender' value='{{cp.gender if cp else ""}}' placeholder='Gender'><input name='seeking' value='{{cp.seeking if cp else ""}}' placeholder='Who would you like to meet?'>{% for k,label,opts in questions %}<label>{{label}}<select name='{{k}}'>{% for x in opts %}<option>{{x}}</option>{% endfor %}</select></label>{% endfor %}<input name='trust_style' value='{{cp.trust_style if cp else ""}}' placeholder='What builds trust for you?'><textarea name='interests' placeholder='Interests'>{{cp.interests if cp else ''}}</textarea><textarea name='values_text' placeholder='Values'>{{cp.values_text if cp else ''}}</textarea><textarea name='work_style' placeholder='Business / work style'>{{cp.work_style if cp else ''}}</textarea><textarea name='retreat_interests' placeholder='Retreat interests'>{{cp.retreat_interests if cp else ''}}</textarea><textarea name='about' placeholder='About me'>{{cp.about if cp else ''}}</textarea><button>Save & Return</button></form>{% endblock %}"""
T['connection_profile.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>{{person.name}}</h1><p>{{cp.coordination_types}}</p><p>{{cp.about}}</p><a class='btn' href='{{url_for("compose_message",uid=person.id,source="Conscious Coordination")}}'>Message</a></section><article class='card'><h2>{{rep.overall}}% Coordination</h2>{% if me.full_member %}{% for n,s in rep.full.items() %}<p><b>{{n}}</b> — {{s}}%</p>{% endfor %}<a class='out' href='{{url_for("connection_ideas",uid=person.id)}}'>Connection Ideas</a>{% else %}{% for n,s in rep.basic.items() %}<p><b>{{n}}</b> — {{s}}%</p>{% endfor %}<a class='btn' href='{{url_for("membership")}}'>Unlock Full — $10.99</a>{% endif %}</article>{% endblock %}"""
T['ideas.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Connection / Friendship / Collaboration Ideas</h1></section><div class='grid'><article class='card'><h3>Nature Walk + Tea</h3><p>Low-pressure conversation and shared wellness.</p></article><article class='card'><h3>Wellness Class</h3><p>A shared experience based on interests.</p></article><article class='card'><h3>Business Collaboration Conversation</h3><p>Compare work style, reliability and goals first.</p></article><article class='card'><h3>Retreat Idea</h3><p>Match pace and social energy.</p></article></div>{% endblock %}"""
T['business.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Business Network — Free Hosting</h1>{% if me %}<a class='btn' href='{{url_for("business_setup")}}'>Create My Free Hosted App</a><a class='out' href='{{url_for("business_builder")}}'>Business Development — $79.99</a>{% endif %}</section><div class='grid'>{% for b in businesses %}{% include 'business_card.html' %}{% else %}<article class='card'>Businesses will appear here as they join.</article>{% endfor %}</div>{% endblock %}"""
T['business_setup.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Free Hosted App Builder</h1></section><form class='card' method='post' enctype='multipart/form-data'><input name='business_name' value='{{b.business_name if b else ""}}' placeholder='Business Name' required><input name='creator_title' value='{{b.creator_title if b else ""}}' placeholder='Title / Role'><select name='category'>{% for x in business_types %}<option>{{x}}</option>{% endfor %}</select><input name='city' value='{{b.city if b else ""}}' placeholder='City'><input name='tagline' value='{{b.tagline if b else ""}}' placeholder='Tagline'><textarea name='description'>{{b.description if b else ''}}</textarea><div class='chips'>{% for x in app_goals %}<label class='chip'><input style='width:auto' type='checkbox' name='app_goals' value='{{x}}'>{{x}}</label>{% endfor %}</div><input type='file' name='logo'><input type='file' name='cover_media'><input name='website' value='{{b.website if b else ""}}' placeholder='Website'><input name='instagram' value='{{b.instagram if b else ""}}' placeholder='Instagram'><input name='tiktok' value='{{b.tiktok if b else ""}}' placeholder='TikTok'><input name='youtube' value='{{b.youtube if b else ""}}' placeholder='YouTube'><input name='booking_url' value='{{b.booking_url if b else ""}}' placeholder='Booking link'><label><input style='width:auto' type='checkbox' name='retreat_participation'> Participate in Retreats</label><br><br><button>Save Hosted App</button></form>{% endblock %}"""
T['business_app.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>{{b.business_name}}</h1><h3>{{b.creator_title or b.category}}</h3><p>{{b.tagline}}</p><div class='chips'>{% for x in modules %}<span class='chip'>{{x}}</span>{% endfor %}</div></section><article class='card'><h2>About</h2><p>{{b.description}}</p></article>{% if 'Media Kit' in modules %}<article class='card'><h2>Media Kit</h2><p>Creator bio, content categories, collaborations, portfolio and partnership contact.</p></article>{% endif %}{% endblock %}"""
T['business_dashboard.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Business Dashboard</h1></section><div class='grid'><a class='card' href='{{url_for("business_setup")}}'>Edit Hosted App</a>{% if b %}<a class='card' href='{{url_for("business_app",slug=b.slug)}}'>Preview Hosted App</a>{% endif %}<a class='card' href='{{url_for("business_builder")}}'>Professional Business Builder</a><a class='card' href='{{url_for("business_plan_versions")}}'>Business Plans & Versions</a><a class='card' href='{{url_for("journal")}}'>Business Journal</a></div>{% endblock %}"""
T['business_builder.html']="""{% extends 'base.html' %}{% block content %}<section class='hero premium'><span class='badge gold'>$79.99</span><h1>Professional Business Consultant Interview</h1></section>{% if not me %}<a class='btn' href='{{url_for("join")}}'>Join Free to Continue</a>{% else %}<form class='card' method='post'>{% for k,label in biz_questions %}<label>{{label}}{% if k=='stage' %}<select name='stage'>{% for x in stages %}<option>{{x}}</option>{% endfor %}</select>{% else %}<textarea name='{{k}}'>{{row[k] if row else ''}}</textarea>{% endif %}</label>{% endfor %}<label>Marketing Channels</label><div class='chips'>{% for x in marketing %}<label class='chip'><input style='width:auto' type='checkbox' name='marketing_channels' value='{{x}}'>{{x}}</label>{% endfor %}</div><label>Hosted App Goals</label><div class='chips'>{% for x in app_goals %}<label class='chip'><input style='width:auto' type='checkbox' name='app_goals' value='{{x}}'>{{x}}</label>{% endfor %}</div><button>Save Professional Interview</button></form>{% if row %}<article class='card premium'>{% if me.startup_access or me.is_admin %}<a class='btn' href='{{url_for("generate_business_plan")}}'>Generate Professional Business Plan</a>{% else %}<p>Purchase access: $79.99 one time.</p>{% endif %}</article>{% endif %}{% endif %}{% endblock %}"""
T['business_plan.html']="""{% extends 'base.html' %}{% block content %}<section class='hero premium'><h1>{{p.business_name}} Business Plan</h1><p>Version {{p.version_no}} • saved in Journal → Business</p><a class='btn' href='{{url_for("business_plan_pdf",pid=p.id)}}'>Download PDF</a></section>{% for h,b in sections.items() %}<article class='card'><h2>{{h}}</h2><p>{{b}}</p></article>{% endfor %}{% endblock %}"""
T['versions.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Business Plan Versions</h1></section>{% for p in plans %}<article class='card'><h3>{{p.business_name}} — Version {{p.version_no}}</h3><a class='btn' href='{{url_for("business_plan_view",pid=p.id)}}'>Open</a></article>{% else %}<article class='card'>No business plans yet.</article>{% endfor %}{% endblock %}"""
T['retreats.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Retreats</h1><a class='btn' href='{{url_for("retreat_build")}}'>Design Your Own Retreat</a></section>{% for r in rows %}<article class='card'><h3>{{r.title}}</h3><p>{{r.retreat_type}} • {{r.season}} • {{r.preferred_dates}}</p></article>{% else %}<article class='card'>Upcoming Retreats will appear here.</article>{% endfor %}{% endblock %}"""
T['retreat_build.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Design Your Own Retreat</h1></section><form class='card' method='post'><input name='title' placeholder='Retreat Title' required><select name='retreat_type'><option>Solo Renewal</option><option>Couples / Dating</option><option>Friendship / Group</option><option>Women’s Self-Love</option><option>Men’s Renewal</option><option>Family Harmony</option><option>Life Transition</option></select><select name='season'><option>Spring Renewal</option><option>Summer Water</option><option>Autumn Reflection</option><option>Winter Stillness</option></select><input name='preferred_dates' placeholder='Preferred dates'><input type='number' name='guests' value='1'><select name='budget'><option>Under $300</option><option>$300–$500</option><option>$500–$750</option><option>$750+</option><option>Let's discuss</option></select><textarea name='wellness_interests' placeholder='Wellness interests'></textarea><textarea name='lodging' placeholder='Lodging preferences'></textarea><textarea name='desired_businesses' placeholder='Desired businesses/providers'></textarea><button>Save Retreat to Journal</button></form>{% endblock %}"""
T['membership.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>Membership & Packages</h1></section><div class='grid'><article class='card'><span class='badge'>FREE</span><h2>Community + Hosted Business App</h2><h1>$0</h1></article><article class='card premium'><span class='badge gold'>CONSCIOUS COORDINATION</span><h2>Full Membership</h2><h1>$10.99/mo</h1></article><article class='card premium'><span class='badge gold'>BUSINESS DEVELOPMENT</span><h2>Professional Business Plan Package</h2><h1>$79.99</h1></article></div><article class='card'><h2>Video Add-Ons</h2><p>Add 5 Minutes — $5 • Paid Video Request/Message — $5</p></article>{% endblock %}"""
T['more.html']="""{% extends 'base.html' %}{% block content %}<section class='hero'><h1>More</h1></section><div class='grid'><a class='card' href='{{url_for("journal")}}'>My Journal</a><a class='card' href='{{url_for("messages")}}'>Journal Inbox</a><a class='card' href='{{url_for("notifications")}}'>Notifications</a><a class='card' href='{{url_for("connections")}}'>Conscious Coordination</a><a class='card' href='{{url_for("business_dashboard")}}'>Business Dashboard</a><a class='card' href='{{url_for("retreats")}}'>Retreats</a><a class='card' href='{{url_for("membership")}}'>Membership</a></div>{% endblock %}"""
app.jinja_loader=DictLoader(T); app.jinja_env.globals.update(media_url=media_url)
@app.context_processor
def inject():return {'me':me()}
BUSINESS_TYPES=['Content Creator','Yoga / Fitness','Reiki / Wellness','Massage / Bodywork','Coach / Consultant','Beauty / Hair','Food / Cooking','Speaker / Educator','Products / Retail','Other']
APP_GOALS=['Services','Booking','Classes','Events','Shop','Videos','Retreats','Media Kit','Affiliate Links']
MARKETING=['Social Media','Google / Search','Local Community','Events','Referrals','Influencers','Email','Partnerships','Paid Advertising']
QUESTIONS=[('emotional_regulation','When emotionally overwhelmed, what helps you regulate first?',['Quiet time','Reassurance','Conversation','Practical problem-solving','Depends']),('emotional_support','When someone else is emotional, what do you naturally do?',['Listen first','Ask what they need','Offer reassurance','Offer solutions','Give space']),('communication_style','Communication style',['Direct but gentle','Very direct','Needs processing time','Emotionally expressive','Calm and practical']),('conflict_style','Conflict approach',['Calm direct conversation','Pause and return later','Resolve quickly','Write first then talk','Structured discussion']),('repair_style','Repair after conflict',['Clear apology + changed behavior','Talk it through fully','Reassurance','Practical repair','Need time']),('accountability','Accountability style',['Own it directly','Explain intent then apologize','Show change through actions','Need time before repair','Mutual discussion']),('boundaries','Boundaries',['Strong privacy needs','Flexible but clear','Balanced closeness/independence','Frequent closeness','Still learning']),('independence_style','Independence / closeness',['Need lots of independence','Balanced','Prefer frequent closeness','Depends']),('social_energy','Social energy',['Homebody','Small groups','Balanced','Very social','Adventure-oriented'])]
BIZQ=[('stage','Where are you in your business journey?'),('business_name','Business name'),('business_types','Business type(s)'),('founder_story','Founder story / why this matters'),('strengths','What are you good at or qualified to do?'),('target_customer','Who do you want to help?'),('customer_problem','What problem do they have?'),('solution','How will your business help them?'),('vision','What should this business become in 3–5 years?'),('core_values','What values should guide the business?'),('usp','What makes your offer different?'),('offers','Products / services / classes / events'),('pricing','Pricing ideas'),('revenue','How will the business make money?'),('competitors','Competitors / alternatives'),('operations','How will the business operate?'),('certifications','Certifications / licenses / insurance / compliance'),('startup_requirements','Startup requirements'),('startup_budget','Startup budget / costs'),('funding','Funding needs / sources'),('goals_90','90-day goals'),('goals_1yr','One-year goals')]
STAGES=['Established business','Recently started','Business idea','Hobby to business','Skill/talent to monetize','Certification/license','Content creator','Help me develop an idea']
@app.route('/brand-logo')
def brand_logo():return Response("<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><circle cx='100' cy='100' r='94' fill='#f4ebf9'/><circle cx='100' cy='100' r='36' fill='white'/></svg>",mimetype='image/svg+xml')
@app.route('/uploads/<path:filename>')
def uploads(filename):return send_from_directory(UPLOADS,filename)
@app.route('/')
def home():
    c=conn();b=c.execute("select * from businesses where status='active' order by featured_order,id").fetchall();c.close();return render_template('home.html',businesses=b)
@app.route('/join',methods=['GET','POST'])
def join():
    if request.method=='POST':
        if not request.form.get('age_confirm') or (age(request.form.get('birth_date')) is not None and age(request.form.get('birth_date'))<18):flash('The member account is 18+.');return render_template('join.html')
        try:
            email=request.form['email'].lower().strip();admin=1 if email in ADMIN_EMAILS else 0;c=conn();cur=c.execute('insert into users(name,email,password_hash,birth_date,full_member,startup_access,is_admin) values(?,?,?,?,?,?,?)',(request.form['name'],email,hp(request.form['password']),request.form['birth_date'],admin,admin,admin));c.commit();session['uid']=cur.lastrowid;c.close();return redirect(url_for('profile'))
        except sqlite3.IntegrityError:flash('That email already has an account.')
    return render_template('join.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=conn();u=c.execute('select * from users where lower(email)=?',(request.form['email'].lower().strip(),)).fetchone();c.close()
        if u and u['password_hash']==hp(request.form['password']):session['uid']=u['id'];return redirect(url_for('profile'))
        flash('Email or password did not match.')
    return render_template('login.html')
@app.route('/logout')
def logout():session.clear();return redirect(url_for('home'))
@app.route('/profile')
@login_required
def profile():return render_template('profile.html',u=me())
@app.route('/profile/edit',methods=['GET','POST'])
@login_required
def profile_edit():
    u=me()
    if request.method=='POST':
        photo=save_file(request.files.get('photo'),f"u{u['id']}") or u['photo'];c=conn();c.execute('update users set name=?,city=?,headline=?,bio=?,photo=?,birth_date=?,birth_time=?,birth_city=?,birth_state=?,birth_country=?,time_known=? where id=?',(request.form['name'],request.form.get('city',''),request.form.get('headline',''),request.form.get('bio',''),photo,request.form.get('birth_date',''),request.form.get('birth_time',''),request.form.get('birth_city',''),request.form.get('birth_state',''),request.form.get('birth_country',''),1 if request.form.get('time_known') else 0,u['id']));c.commit();c.close();return redirect(url_for('profile'))
    return render_template('profile_edit.html',u=u)
@app.route('/community',methods=['GET','POST'])
@login_required
def community():
    u=me()
    if request.method=='POST':
        pa=request.form.get('post_as','member')
        if pa=='official' and not u['is_admin']:abort(403)
        photo=save_file(request.files.get('photo'),f"p{u['id']}");c=conn();c.execute('insert into posts(user_id,body,photo,post_as) values(?,?,?,?)',(u['id'],request.form['body'],photo,pa));c.commit();c.close()
        if pa=='official':notify_all('The Seasons Within Posted',request.form['body'][:140],'Community',u['id'])
        elif u['email'].lower()==GALAXY_EMAIL:notify_all('Galaxy Eve Posted',request.form['body'][:140],'Community',u['id'])
        return redirect(url_for('community'))
    c=conn();posts=c.execute('select p.*,u.name,u.photo profile_photo from posts p join users u on u.id=p.user_id order by p.id desc').fetchall();c.close();return render_template('community.html',posts=posts)
@app.route('/journal',methods=['GET','POST'])
@login_required
def journal():
    u=me()
    if request.method=='POST':
        c=conn();c.execute('insert into journals(user_id,title,body,category,visibility) values(?,?,?,?,?)',(u['id'],request.form.get('title',''),request.form['body'],request.form.get('category','Reflection'),request.form.get('visibility','private')))
        if request.form.get('visibility')=='community':c.execute('insert into posts(user_id,body) values(?,?)',(u['id'],request.form['body']))
        c.commit();c.close();return redirect(url_for('journal'))
    c=conn();entries=c.execute('select * from journals where user_id=? order by id desc',(u['id'],)).fetchall();c.close();return render_template('journal.html',entries=entries)
@app.route('/messages')
@login_required
def messages():
    u=me();c=conn();rows=c.execute('select m.*,case when m.sender_id=? then r.name else s.name end other_name,case when m.sender_id=? then r.id else s.id end other_id from messages m join users s on s.id=m.sender_id join users r on r.id=m.recipient_id where m.sender_id=? or m.recipient_id=? order by m.id desc',(u['id'],u['id'],u['id'],u['id'])).fetchall();c.close();return render_template('messages.html',rows=rows)
@app.route('/message/<int:uid>',methods=['GET','POST'])
@login_required
def compose_message(uid):
    u=me();c=conn();person=c.execute('select * from users where id=?',(uid,)).fetchone();c.close();source=request.args.get('source','Private');subject=f"{source} Message from {u['name']}"
    if not person:abort(404)
    if request.method=='POST':
        c=conn();c.execute('insert into messages(sender_id,recipient_id,source,subject,body) values(?,?,?,?,?)',(u['id'],uid,source,request.form.get('subject') or subject,request.form['body']));c.commit();c.close();notify(uid,'New Private Message',request.form.get('subject') or subject,'Message');return redirect(url_for('messages'))
    return render_template('compose.html',person=person,subject=subject)
@app.route('/notifications')
@login_required
def notifications():
    c=conn();rows=c.execute('select * from notifications where user_id=? order by id desc',(me()['id'],)).fetchall();c.close();return render_template('notifications.html',rows=rows)
@app.route('/connections')
@login_required
def connections():
    u=me();c=conn();cp=c.execute('select * from connection_profiles where user_id=?',(u['id'],)).fetchone()
    if not cp:c.close();return redirect(url_for('connections_edit'))
    raw=c.execute('select u.*,cp.coordination_types from users u join connection_profiles cp on cp.user_id=u.id where u.id<>?',(u['id'],)).fetchall();c.close();people=[]
    for p in raw:
        c=conn();ocp=c.execute('select * from connection_profiles where user_id=?',(p['id'],)).fetchone();c.close();d=dict(p);d['score']=report(cp,ocp)['overall'];people.append(d)
    return render_template('connections.html',people=people)
@app.route('/connections/edit',methods=['GET','POST'])
@login_required
def connections_edit():
    u=me();c=conn();cp=c.execute('select * from connection_profiles where user_id=?',(u['id'],)).fetchone();c.close()
    if request.method=='POST':
        data={k:request.form.get(k,'') for k,_,_ in QUESTIONS};data.update(coordination_types=multi('coordination_types'),gender=request.form.get('gender',''),seeking=request.form.get('seeking',''),trust_style=request.form.get('trust_style',''),interests=request.form.get('interests',''),values_text=request.form.get('values_text',''),work_style=request.form.get('work_style',''),retreat_interests=request.form.get('retreat_interests',''),about=request.form.get('about',''));c=conn()
        if cp:
            sets=','.join(f'{k}=?' for k in data);c.execute(f'update connection_profiles set {sets} where user_id=?',tuple(data.values())+(u['id'],))
        else:
            cols=','.join(data);qs=','.join('?' for _ in data);c.execute(f'insert into connection_profiles(user_id,{cols}) values(?,{qs})',(u['id'],)+tuple(data.values()))
        c.commit();c.close();return redirect(url_for('connections'))
    return render_template('connections_edit.html',cp=cp,questions=QUESTIONS)
@app.route('/connections/profile/<int:uid>')
@login_required
def connection_profile(uid):
    u=me();c=conn();ca=c.execute('select * from connection_profiles where user_id=?',(u['id'],)).fetchone();person=c.execute('select * from users where id=?',(uid,)).fetchone();cb=c.execute('select * from connection_profiles where user_id=?',(uid,)).fetchone();c.close()
    if not ca or not person or not cb:abort(404)
    return render_template('connection_profile.html',person=person,cp=cb,rep=report(ca,cb))
@app.route('/connections/ideas/<int:uid>')
@login_required
def connection_ideas(uid):return render_template('ideas.html')
@app.route('/business')
def business():
    c=conn();rows=c.execute("select * from businesses where status='active' order by featured_order,id").fetchall();c.close();return render_template('business.html',businesses=rows)
@app.route('/business/setup',methods=['GET','POST'])
@login_required
def business_setup():
    u=me();c=conn();b=c.execute('select * from businesses where owner_id=?',(u['id'],)).fetchone();c.close()
    if request.method=='POST':
        logo=save_file(request.files.get('logo'),f"bl{u['id']}") or (b['logo'] if b else '');cover=save_file(request.files.get('cover_media'),f"bc{u['id']}") or (b['cover_media'] if b else '');ctype='video' if Path(cover).suffix.lower() in {'.mp4','.mov','.webm','.m4v'} else 'image';category=request.form['category'];modules=business_modules(category,multi('app_goals'));featured=1 if u['email'].lower()==GALAXY_EMAIL else 999;c=conn()
        if b:c.execute('update businesses set business_name=?,creator_title=?,category=?,city=?,tagline=?,description=?,logo=?,cover_media=?,cover_type=?,website=?,instagram=?,tiktok=?,youtube=?,booking_url=?,modules=?,retreat_participation=?,featured_order=? where owner_id=?',(request.form['business_name'],request.form.get('creator_title',''),category,request.form.get('city',''),request.form.get('tagline',''),request.form.get('description',''),logo,cover,ctype,request.form.get('website',''),request.form.get('instagram',''),request.form.get('tiktok',''),request.form.get('youtube',''),request.form.get('booking_url',''),modules,1 if request.form.get('retreat_participation') else 0,featured,u['id']))
        else:c.execute('insert into businesses(owner_id,slug,business_name,creator_title,category,city,tagline,description,logo,cover_media,cover_type,website,instagram,tiktok,youtube,booking_url,modules,retreat_participation,featured_order) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(u['id'],slugify(request.form['business_name']),request.form['business_name'],request.form.get('creator_title',''),category,request.form.get('city',''),request.form.get('tagline',''),request.form.get('description',''),logo,cover,ctype,request.form.get('website',''),request.form.get('instagram',''),request.form.get('tiktok',''),request.form.get('youtube',''),request.form.get('booking_url',''),modules,1 if request.form.get('retreat_participation') else 0,featured))
        c.commit();c.close();return redirect(url_for('business'))
    return render_template('business_setup.html',b=b,business_types=BUSINESS_TYPES,app_goals=APP_GOALS)
@app.route('/app/<slug>')
def business_app(slug):
    c=conn();b=c.execute('select * from businesses where slug=?',(slug,)).fetchone();c.close();
    if not b:abort(404)
    return render_template('business_app.html',b=b,modules=split(b['modules']))
@app.route('/business/dashboard')
@login_required
def business_dashboard():
    c=conn();b=c.execute('select * from businesses where owner_id=?',(me()['id'],)).fetchone();c.close();return render_template('business_dashboard.html',b=b)
@app.route('/business/builder',methods=['GET','POST'])
def business_builder():
    if not me():return render_template('business_builder.html',row=None,biz_questions=BIZQ,stages=STAGES,marketing=MARKETING,app_goals=APP_GOALS)
    u=me();c=conn();row=c.execute('select * from business_builder where user_id=?',(u['id'],)).fetchone();c.close()
    if request.method=='POST':
        data={k:request.form.get(k,'') for k,_ in BIZQ};data['marketing_channels']=multi('marketing_channels');data['app_goals']=multi('app_goals');c=conn()
        if row:
            sets=','.join(f'{k}=?' for k in data);c.execute(f'update business_builder set {sets} where user_id=?',tuple(data.values())+(u['id'],))
        else:
            cols=','.join(data);qs=','.join('?' for _ in data);c.execute(f'insert into business_builder(user_id,{cols}) values(?,{qs})',(u['id'],)+tuple(data.values()))
        c.commit();c.close();return redirect(url_for('business_builder'))
    c=conn();row=c.execute('select * from business_builder where user_id=?',(u['id'],)).fetchone();c.close();return render_template('business_builder.html',row=row,biz_questions=BIZQ,stages=STAGES,marketing=MARKETING,app_goals=APP_GOALS)
@app.route('/business/plan/generate')
@login_required
def generate_business_plan():
    u=me()
    if not (u['startup_access'] or u['is_admin']):flash('Connect payment processing to activate the $79.99 package.');return redirect(url_for('business_builder'))
    c=conn();r=c.execute('select * from business_builder where user_id=?',(u['id'],)).fetchone()
    if not r:c.close();return redirect(url_for('business_builder'))
    ver=(c.execute('select max(version_no) v from business_plans where user_id=?',(u['id'],)).fetchone()['v'] or 0)+1;sections=plan_sections(r);cur=c.execute('insert into business_plans(user_id,business_name,version_no,sections_json,marketing_text,launch_text) values(?,?,?,?,?,?)',(u['id'],r['business_name'] or 'My Business',ver,json.dumps(sections),sections['Marketing Strategy'],sections['90-Day Launch Strategy']));pid=cur.lastrowid;c.execute("insert into journals(user_id,title,body,category) values(?,?,?,'Business')",(u['id'],f"{r['business_name']} Business Plan",'Professional Business Plan generated.'));c.commit();c.close();notify(u['id'],'Business Plan Ready',f'Version {ver} is ready.','Business');return redirect(url_for('business_plan_view',pid=pid))
@app.route('/business/plan/<int:pid>')
@login_required
def business_plan_view(pid):
    c=conn();p=c.execute('select * from business_plans where id=? and user_id=?',(pid,me()['id'])).fetchone();c.close();
    if not p:abort(404)
    return render_template('business_plan.html',p=p,sections=json.loads(p['sections_json']))
@app.route('/business/plan/<int:pid>/pdf')
@login_required
def business_plan_pdf(pid):
    c=conn();p=c.execute('select * from business_plans where id=? and user_id=?',(pid,me()['id'])).fetchone();c.close();
    if not p:abort(404)
    path=PDFS/f"{slugify(p['business_name'])}-plan-v{p['version_no']}.pdf";path.write_bytes(pdf_bytes(list(json.loads(p['sections_json']).items())));return send_file(path,as_attachment=True)
@app.route('/business/plan/versions')
@login_required
def business_plan_versions():
    c=conn();plans=c.execute('select * from business_plans where user_id=? order by version_no desc',(me()['id'],)).fetchall();c.close();return render_template('versions.html',plans=plans)
@app.route('/retreats')
def retreats():
    c=conn();rows=c.execute('select * from retreats order by id desc').fetchall();c.close();return render_template('retreats.html',rows=rows)
@app.route('/retreats/build',methods=['GET','POST'])
@login_required
def retreat_build():
    u=me()
    if request.method=='POST':
        c=conn();c.execute('insert into retreats(owner_id,title,retreat_type,season,preferred_dates,guests,budget,wellness_interests,lodging,desired_businesses) values(?,?,?,?,?,?,?,?,?,?)',(u['id'],request.form['title'],request.form['retreat_type'],request.form['season'],request.form.get('preferred_dates',''),int(request.form.get('guests') or 1),request.form.get('budget',''),request.form.get('wellness_interests',''),request.form.get('lodging',''),request.form.get('desired_businesses','')));c.execute("insert into journals(user_id,title,body,category) values(?,?,?,'Retreats')",(u['id'],request.form['title'],'Retreat request saved.'));c.commit();c.close();return redirect(url_for('journal'))
    return render_template('retreat_build.html')
@app.route('/membership')
def membership():return render_template('membership.html')
@app.route('/more')
@login_required
def more():return render_template('more.html')
init_db()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=False)
