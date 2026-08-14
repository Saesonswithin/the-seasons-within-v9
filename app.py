import os,re,json,sqlite3,secrets,hashlib,hmac,time,urllib.parse,urllib.request,smtplib,ssl,textwrap
from pathlib import Path
from datetime import datetime,date,timezone
from functools import wraps
from email.message import EmailMessage
from flask import Flask,render_template,request,redirect,url_for,session,flash,send_from_directory,abort,Response,send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash,check_password_hash
from jinja2 import DictLoader
try: import swisseph as swe
except Exception: swe=None
try: from geopy.geocoders import Nominatim
except Exception: Nominatim=None
try: from timezonefinder import TimezoneFinder
except Exception: TimezoneFinder=None
try: from zoneinfo import ZoneInfo
except Exception: ZoneInfo=None
BASE=Path(__file__).resolve().parent
DATA_DIR=Path(os.environ.get('DATA_DIR',os.environ.get('PERSISTENT_DATA_DIR',str(BASE/'data'))));DATA_DIR.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get('DATABASE_PATH',str(DATA_DIR/'the_seasons_within.db')))
UPLOADS=Path(os.environ.get('UPLOAD_DIR',str(DATA_DIR/'uploads')));UPLOADS.mkdir(parents=True,exist_ok=True)
PDFS=Path(os.environ.get('PDF_DIR',str(DATA_DIR/'pdfs')));PDFS.mkdir(parents=True,exist_ok=True)
app=Flask(__name__);app.secret_key=os.environ.get('SECRET_KEY','replace-this-secret-on-render');app.config.update(MAX_CONTENT_LENGTH=50*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
BASE_URL=os.environ.get('BASE_URL','').rstrip('/');STRIPE_SECRET_KEY=os.environ.get('STRIPE_SECRET_KEY','');STRIPE_WEBHOOK_SECRET=os.environ.get('STRIPE_WEBHOOK_SECRET','')
GALAXY_EVE_EMAIL=os.environ.get('GALAXY_EVE_EMAIL','galaxyeve@theseasonswithin.local').strip().lower()
ADMIN_EMAILS={x.strip().lower() for x in [os.environ.get('ADMIN_EMAIL_1','admin1@theseasonswithin.local'),os.environ.get('ADMIN_EMAIL_2','admin2@theseasonswithin.local')] if x.strip()};SYSTEM_EMAIL='community@theseasonswithin.local'
SIGNS=['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
BUSINESS_TYPES=['Wellness','Yoga/Fitness','Reiki','Massage/Bodywork','Sound Wellness','Beauty/Hair','Food/Cooking','Motivational Speaker','Coach/Consultant','Content Creator','Artist/Creative','Retreat/Event Host','Teacher/Educator','Courses','Products/E-commerce','Membership/Community','Professional Services','Nonprofit','Other']
APP_GOALS=['Sell products','Book appointments','Live classes','Recorded classes','Courses','Memberships','Videos/content','Blog','Community','Speaking','Events','Retreats','Consultations','Portfolio','Affiliate links','Media Kit']
EMOTIONAL_FIELDS=[('When I am upset, I usually...','emotional_response',['Need quiet time before talking','Want to talk fairly soon','Need reassurance before discussing it','Prefer practical problem-solving','It depends on the situation']),('When someone I care about is emotional, I usually...','others_emotions',['Listen first','Ask what they need','Offer solutions','Give them space','Use affection or reassurance']),('During conflict, I prefer...','conflict_style',['Calm direct conversation','Take a break and return later','Resolve it quickly','Write/text first, then talk','A structured / mediated approach']),('Repair after conflict looks like...','repair_style',['Clear apology + changed behavior','Talking it through fully','Affection + reassurance','Quality time together','Practical action to fix the problem']),('My apology style is closest to...','apology_style',['I name what happened and take responsibility','I explain my intention and apologize','I show change through actions','I need time before I can apologize well','I prefer mutual discussion and repair']),('Communication style','communication_style',['Direct but gentle','Very direct','Thoughtful / needs processing time','Emotionally expressive','Calm and practical']),('Boundaries','boundaries',['Strong privacy / personal-space needs','Flexible but clear boundaries','Prefer frequent closeness/contact','Need lots of independence','Still learning what works for me']),('Social energy','social_energy',['Mostly homebody','Small groups','Balanced social / home time','Very social','Adventure / always doing something']),('Family goals','family_goals',['Want children / family','Already have children and open to blending','Do not want children','Adult children / later-life partnership','Open / still deciding'])]
PAY_ITEMS={'full_membership':{'name':'Full Membership — Conscious Coordination','amount':1099,'display':'$10.99/month','mode':'subscription','description':'Full compatibility, shared birth charts, expanded Connections media and eligible video tools.'},'business_app':{'name':'Business Network Hosted App','amount':2999,'display':'$29.99/month','mode':'subscription','description':'Standout hosted business app with classes, media, links and expanded modules.'},'startup_package':{'name':'Startup/Hobby → Business Plan Package','amount':7999,'display':'$79.99','mode':'payment','description':'Editable 10–15 page Business Plan PDF + Marketing Strategy + 90-Day Launch Plan.'},'video_message':{'name':'Paid Video Request / Message','amount':500,'display':'$5','mode':'payment','description':'Sender pays $5; receiving member may answer without paying.'},'video_time':{'name':'Add 5 Minutes of Video Talk Time','amount':500,'display':'$5','mode':'payment','description':'Adds another 5 minutes to this video connection.'}}
def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def ensure_column(c,t,col,definition):
 cols={r['name'] for r in c.execute(f'PRAGMA table_info({t})').fetchall()}
 if col not in cols:c.execute(f'ALTER TABLE {t} ADD COLUMN {col} {definition}')
def init_db():
 c=conn();c.executescript('''
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,email TEXT UNIQUE,password_hash TEXT,city TEXT DEFAULT '',state TEXT DEFAULT '',country TEXT DEFAULT '',bio TEXT DEFAULT '',headline TEXT DEFAULT '',photo TEXT DEFAULT '',birth_date TEXT DEFAULT '',birth_time TEXT DEFAULT '',birth_city TEXT DEFAULT '',birth_state TEXT DEFAULT '',birth_country TEXT DEFAULT '',birth_lat REAL,birth_lon REAL,birth_timezone TEXT DEFAULT '',time_known INTEGER DEFAULT 0,sun TEXT DEFAULT '',moon TEXT DEFAULT '',rising TEXT DEFAULT '',mercury TEXT DEFAULT '',venus TEXT DEFAULT '',mars TEXT DEFAULT '',jupiter TEXT DEFAULT '',saturn TEXT DEFAULT '',full_member INTEGER DEFAULT 0,business_access INTEGER DEFAULT 0,startup_access INTEGER DEFAULT 0,is_admin INTEGER DEFAULT 0,is_system INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS community_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,body TEXT,photo TEXT DEFAULT '',post_as TEXT DEFAULT 'member',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS journals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT DEFAULT '',body TEXT,visibility TEXT DEFAULT 'private',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_id INTEGER,recipient_id INTEGER,message_type TEXT DEFAULT 'member',subject TEXT DEFAULT '',body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,notification_type TEXT,title TEXT,body TEXT,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS reset_tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,token TEXT UNIQUE,expires_at INTEGER,used INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS connection_profiles(user_id INTEGER PRIMARY KEY,connection_type TEXT DEFAULT 'Both',gender TEXT,seeking TEXT,location_pref TEXT,age_min INTEGER DEFAULT 18,age_max INTEGER DEFAULT 99,occupation TEXT,children TEXT,height TEXT,weight TEXT,looking_for TEXT,lifestyle TEXT,activities TEXT,values_text TEXT,emotional_response TEXT,others_emotions TEXT,conflict_style TEXT,repair_style TEXT,apology_style TEXT,love_languages TEXT,communication_style TEXT,boundaries TEXT,social_energy TEXT,family_goals TEXT,about TEXT);
 CREATE TABLE IF NOT EXISTS connection_media(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,filename TEXT,media_type TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS connection_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,body TEXT,media TEXT DEFAULT '',media_type TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS blocks(id INTEGER PRIMARY KEY AUTOINCREMENT,blocker_id INTEGER,blocked_id INTEGER,UNIQUE(blocker_id,blocked_id));
 CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,reporter_id INTEGER,reported_id INTEGER,reason TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER UNIQUE,slug TEXT UNIQUE,business_name TEXT,creator_title TEXT DEFAULT '',tagline TEXT DEFAULT '',description TEXT DEFAULT '',category TEXT DEFAULT '',city TEXT DEFAULT '',state TEXT DEFAULT '',website TEXT DEFAULT '',logo TEXT DEFAULT '',hero_image TEXT DEFAULT '',featured_video TEXT DEFAULT '',instagram TEXT DEFAULT '',tiktok TEXT DEFAULT '',youtube TEXT DEFAULT '',facebook TEXT DEFAULT '',booking_url TEXT DEFAULT '',paid_business INTEGER DEFAULT 0,retreat_participation INTEGER DEFAULT 0,sponsor_community INTEGER DEFAULT 0,approved_connections INTEGER DEFAULT 0,featured_order INTEGER DEFAULT 999,modules TEXT DEFAULT '',status TEXT DEFAULT 'active');
 CREATE TABLE IF NOT EXISTS business_classes(id INTEGER PRIMARY KEY AUTOINCREMENT,business_id INTEGER,title TEXT,description TEXT,class_format TEXT,class_date TEXT,class_time TEXT,price TEXT,meeting_url TEXT,active INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS business_builder(user_id INTEGER PRIMARY KEY,stage TEXT,business_types TEXT,app_goals TEXT,strengths TEXT,target_customer TEXT,offers TEXT,business_name TEXT,marketing_channels TEXT,pricing_ideas TEXT,goals_90 TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS business_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,business_name TEXT,version_no INTEGER DEFAULT 1,sections_json TEXT,marketing_text TEXT,launch_text TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS retreats(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER,title TEXT,season TEXT,retreat_type TEXT,preferred_dates TEXT,guests INTEGER DEFAULT 1,budget TEXT,lodging_preferences TEXT,wellness_interests TEXT,connection_retreat INTEGER DEFAULT 0,status TEXT DEFAULT 'request');
 CREATE TABLE IF NOT EXISTS retreat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,retreat_id INTEGER,sender_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS video_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,requester_id INTEGER,recipient_id INTEGER,status TEXT DEFAULT 'requested',seconds_available INTEGER DEFAULT 300,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,target_id INTEGER,amount_cents INTEGER,status TEXT DEFAULT 'pending',stripe_session_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
 for t,cols in {'users':[('state',"TEXT DEFAULT ''"),('country',"TEXT DEFAULT ''"),('birth_city',"TEXT DEFAULT ''"),('birth_state',"TEXT DEFAULT ''"),('birth_country',"TEXT DEFAULT ''"),('birth_timezone',"TEXT DEFAULT ''"),('full_member','INTEGER DEFAULT 0'),('startup_access','INTEGER DEFAULT 0'),('is_system','INTEGER DEFAULT 0')],'community_posts':[('photo',"TEXT DEFAULT ''"),('post_as',"TEXT DEFAULT 'member'")],'journals':[('title',"TEXT DEFAULT ''"),('visibility',"TEXT DEFAULT 'private'")],'businesses':[('state',"TEXT DEFAULT ''"),('sponsor_community','INTEGER DEFAULT 0'),('approved_connections','INTEGER DEFAULT 0')],'connection_profiles':[('location_pref','TEXT'),('height','TEXT'),('weight','TEXT'),('apology_style','TEXT')]}.items():
  for col,d in cols:
   try:ensure_column(c,t,col,d)
   except Exception:pass
 if not c.execute('SELECT 1 FROM users WHERE lower(email)=?',(SYSTEM_EMAIL,)).fetchone():c.execute('INSERT INTO users(name,email,password_hash,headline,is_admin,is_system,full_member,business_access,startup_access) VALUES(?,?,?,?,1,1,1,1,1)',('The Seasons Within',SYSTEM_EMAIL,generate_password_hash(secrets.token_urlsafe(30)),'Conscious Coordination Community'))
 c.commit();c.close()
def role_email(email):email=(email or '').lower().strip();return email==GALAXY_EVE_EMAIL or email in ADMIN_EMAILS
def sync_privileged_account(uid):
 c=conn();u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
 if u and role_email(u['email']):
  c.execute('UPDATE users SET full_member=1,business_access=1,startup_access=1,is_admin=1 WHERE id=?',(uid,))
  if u['email'].lower()==GALAXY_EVE_EMAIL and not c.execute('SELECT 1 FROM businesses WHERE owner_id=?',(uid,)).fetchone():c.execute('''INSERT INTO businesses(owner_id,slug,business_name,creator_title,tagline,description,category,paid_business,retreat_participation,sponsor_community,approved_connections,featured_order,modules) VALUES(?,?,?,?,?,?,?,1,1,1,1,1,?)''',(uid,'galaxy-eve','Galaxy Eve','Conscious Coordinator • Content Creator','Content • Collaborations • Creator Experiences',"Galaxy Eve's real creator content, collaborations, events and retreats appear here as she adds them.",'Content Creator','Home|About|Watch|Events|Retreats|Media Kit|Collaborate|Social Links|Contact'))
  c.commit()
 c.close()
init_db()
def q1(sql,args=()):c=conn();r=c.execute(sql,args).fetchone();c.close();return r
def qall(sql,args=()):c=conn();r=c.execute(sql,args).fetchall();c.close();return r
def me():
 uid=session.get('uid')
 if not uid:return None
 sync_privileged_account(uid);return q1('SELECT * FROM users WHERE id=?',(uid,))
def login_required(fn):
 @wraps(fn)
 def w(*a,**k):
  if not me():return redirect(url_for('login',next=request.path))
  return fn(*a,**k)
 return w
def admin_required(fn):
 @wraps(fn)
 def w(*a,**k):
  u=me()
  if not u or not u['is_admin']:abort(403)
  return fn(*a,**k)
 return w
def age_from_birth(v):
 if not v:return None
 try:b=datetime.strptime(v,'%Y-%m-%d').date();t=date.today();return t.year-b.year-((t.month,t.day)<(b.month,b.day))
 except:return None
def slugify(x):return re.sub(r'[^a-z0-9]+','-',(x or '').lower()).strip('-') or secrets.token_hex(4)
def parts(v):return {x.strip() for x in (v or '').split('•') if x.strip()}
def multi(name,limit=20):return ' • '.join(request.form.getlist(name)[:limit])
def media_url(p):return url_for('uploads',filename=p) if p else ''
def is_video(f):return Path(f or '').suffix.lower() in {'.mp4','.mov','.m4v','.webm'}
def save_file(fs,prefix,allowed=None):
 if not fs or not fs.filename:return ''
 ext=Path(secure_filename(fs.filename)).suffix.lower();allowed=allowed or {'.jpg','.jpeg','.png','.webp','.gif','.mp4','.mov','.m4v','.webm'}
 if ext not in allowed:return ''
 name=f'{prefix}-{secrets.token_hex(6)}{ext}';fs.save(UPLOADS/name);return name
def notify(uid,kind,title,body):c=conn();c.execute('INSERT INTO notifications(user_id,notification_type,title,body) VALUES(?,?,?,?)',(uid,kind,title,body));c.commit();c.close()
def notify_all_members(kind,title,body,exclude=None):
 c=conn()
 for r in c.execute('SELECT id FROM users WHERE is_system=0').fetchall():
  if r['id']!=exclude:c.execute('INSERT INTO notifications(user_id,notification_type,title,body) VALUES(?,?,?,?)',(r['id'],kind,title,body))
 c.commit();c.close()
def blocked(a,b):return bool(q1('SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)',(a,b,b,a)))
HIGH_RISK=[(r'\b(kill you|hurt you|beat you|shoot you|stab you|rape you)\b','Threatening or violent language is not allowed.'),(r'\b(send nudes?|nude pics?|naked pics?|explicit pics?|show me your body)\b','Sexual/nude solicitation is not allowed.'),(r'\b(underage|minor)\b','Age-inappropriate dating or sexual content is not allowed.')];ABUSE={'bitch','whore','slut','cunt','faggot','retard'}
def moderate_text(text):
 t=(text or '').lower()
 for pat,reason in HIGH_RISK:
  if re.search(pat,t):return False,reason
 if len([w for w in ABUSE if re.search(r'\b'+re.escape(w)+r'\b',t)])>=2:return False,'Targeted abusive language may violate the member rules. Please revise the message.'
 return True,''
def zdeg(d):d=float(d)%360;i=int(d//30);return SIGNS[i],round(d-i*30,2)
def geocode_birth(city,state,country):
 if not Nominatim:return None,None,None
 try:
  loc=Nominatim(user_agent='the-seasons-within').geocode(', '.join(x for x in [city,state,country] if x),timeout=8)
  if not loc:return None,None,None
  tz=None
  if TimezoneFinder:
   try:tz=TimezoneFinder().timezone_at(lat=loc.latitude,lng=loc.longitude)
   except:pass
  return float(loc.latitude),float(loc.longitude),tz
 except:return None,None,None
def calc_chart(uid):
 if not swe:return
 c=conn();u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
 if not u or not u['birth_date']:c.close();return
 lat,lon,tz=u['birth_lat'],u['birth_lon'],u['birth_timezone']
 if (lat is None or lon is None) and u['birth_city']:
  lat,lon,tz=geocode_birth(u['birth_city'],u['birth_state'],u['birth_country']);c.execute('UPDATE users SET birth_lat=?,birth_lon=?,birth_timezone=? WHERE id=?',(lat,lon,tz or '',uid));c.commit()
 try:
  d=datetime.strptime(u['birth_date'],'%Y-%m-%d');hour=12.0
  if u['time_known'] and u['birth_time']:
   hh,mm=map(int,u['birth_time'].split(':')[:2]);local=datetime(d.year,d.month,d.day,hh,mm);offset=0
   if tz and ZoneInfo:
    try:offset=local.replace(tzinfo=ZoneInfo(tz)).utcoffset().total_seconds()/3600
    except:pass
   hour=hh+mm/60-offset
  jd=swe.julday(d.year,d.month,d.day,hour);vals={}
  for k,v in {'sun':swe.SUN,'moon':swe.MOON,'mercury':swe.MERCURY,'venus':swe.VENUS,'mars':swe.MARS,'jupiter':swe.JUPITER,'saturn':swe.SATURN}.items():vals[k]=zdeg(swe.calc_ut(jd,v)[0][0])[0]
  rising=''
  if u['time_known'] and lat is not None and lon is not None:
   try:rising=zdeg(swe.houses(jd,float(lat),float(lon),b'P')[1][0])[0]
   except:pass
  c.execute('UPDATE users SET sun=?,moon=?,rising=?,mercury=?,venus=?,mars=?,jupiter=?,saturn=? WHERE id=?',(vals['sun'],vals['moon'],rising,vals['mercury'],vals['venus'],vals['mars'],vals['jupiter'],vals['saturn'],uid));c.commit()
 except:pass
 c.close()
def sky_now():
 out={'moon_sign':'','moon_phase':'Current lunar phase','moon_degree':None,'moon_symbol':'☾','positions':{}}
 if not swe:return out
 try:
  n=datetime.now(timezone.utc);jd=swe.julday(n.year,n.month,n.day,n.hour+n.minute/60+n.second/3600);deg={}
  for k,v in {'Sun':swe.SUN,'Moon':swe.MOON,'Mercury':swe.MERCURY,'Venus':swe.VENUS,'Mars':swe.MARS,'Jupiter':swe.JUPITER,'Saturn':swe.SATURN}.items():d=swe.calc_ut(jd,v)[0][0];deg[k]=d;sg,dd=zdeg(d);out['positions'][k]={'sign':sg,'degree':dd}
  out['moon_sign']=out['positions']['Moon']['sign'];out['moon_degree']=out['positions']['Moon']['degree'];a=(deg['Moon']-deg['Sun'])%360
  for cut,nm,sym in [(22.5,'New Moon','🌑'),(67.5,'Waxing Crescent','🌒'),(112.5,'First Quarter','🌓'),(157.5,'Waxing Gibbous','🌔'),(202.5,'Full Moon','🌕'),(247.5,'Waning Gibbous','🌖'),(292.5,'Last Quarter','🌗'),(337.5,'Waning Crescent','🌘'),(361,'New Moon','🌑')]:
   if a<cut:out['moon_phase']=nm;out['moon_symbol']=sym;break
 except:pass
 return out
def daily_reflection(sky):
 p={'Aries':'Notice where you need a clean beginning without rushing.','Taurus':'Choose steadiness. Let your body set the pace.','Gemini':'Notice which conversation or idea deserves your attention.','Cancer':'Make room for emotional comfort without carrying everything.','Leo':'Let yourself be seen without needing to perform.','Virgo':'Organize what matters without turning reflection into pressure.','Libra':'Notice where balance requires an honest choice.','Scorpio':'Pay attention to what is ready to be released or understood more deeply.','Sagittarius':'Give curiosity somewhere useful to go today.','Capricorn':'Choose one grounded step instead of carrying the whole future.','Aquarius':'Make room for a different perspective and meaningful community.','Pisces':'Slow down enough to hear what your inner life is saying.'}
 return {'reflection':p.get(sky.get('moon_sign'),'Notice your pace, your needs and what deserves conscious attention.'),'relaxation':'Unclench your jaw, lower your shoulders, and take three slow breaths.','journal':'What deserves your conscious attention today?'}
def signscore(a,b):
 if not a or not b or a not in SIGNS or b not in SIGNS:return 60
 d=min((SIGNS.index(a)-SIGNS.index(b))%12,(SIGNS.index(b)-SIGNS.index(a))%12);return {0:92,2:80,3:72,4:88,6:66}.get(d,62)
def overlap(a,b):
 A,B=parts(a),parts(b)
 if not A or not B:return 60
 return round(55+40*len(A&B)/len(A|B))
def compatibility(a,b,ca,cb):
 same=lambda k,hi=90,lo=70:hi if (ca[k] and cb[k] and ca[k]==cb[k]) else lo
 social={'Social & Emotional Intelligence':round((same('others_emotions',92,72)+same('emotional_response',88,68))/2),'Communication':same('communication_style',92,70),'Handling Conflict':same('conflict_style',88,68),'Repair & Accountability':round((same('repair_style',92,70)+same('apology_style',90,68))/2),'Emotional Rhythm':same('emotional_response',86,67),'Affection & Love Language':overlap(ca['love_languages'],cb['love_languages']),'Lifestyle & Values':round((overlap(ca['values_text'],cb['values_text'])+overlap(ca['lifestyle'],cb['lifestyle']))/2),'Psychology-Oriented Compatibility':round((same('boundaries',88,67)+same('social_energy',84,68)+same('family_goals',88,66))/3)}
 astro={'Communication • Mercury':signscore(a['mercury'],b['mercury']),'Emotional Rhythm • Moon':signscore(a['moon'],b['moon']),'Affection • Venus':signscore(a['venus'],b['venus']),'Attraction / Drive • Mars':signscore(a['mars'],b['mars']),'Identity • Sun':signscore(a['sun'],b['sun']),'Interaction • Rising':signscore(a['rising'],b['rising']) if a['rising'] and b['rising'] else None};sv=round(sum(social.values())/len(social));av=[x for x in astro.values() if x is not None];ast=round(sum(av)/len(av)) if av else 60;overall=round(sv*.68+ast*.32)
 basic={'Communication':social['Communication'],'Emotional Style':round((social['Social & Emotional Intelligence']+social['Emotional Rhythm'])/2),'Lifestyle & Values':social['Lifestyle & Values'],'Astrology Preview':ast};shared=parts(ca['values_text'])&parts(cb['values_text']);strengths=('Shared values: '+', '.join(sorted(shared))) if shared else 'Your profiles show areas of natural coordination worth exploring.';questions=['When something is bothering you, do you usually want to talk right away or have time to think first?','What makes an apology feel sincere to you?','How much alone time do you need in a close relationship?','How do you naturally show someone that you care?'];desc={k:'Compares how both members describe this part of their real-life connection style.' for k in social};desc.update({k:'Astrology is shown as a separate reflective layer, not a diagnosis or guarantee.' for k in astro});return {'overall':overall,'social':social,'astro':astro,'basic':basic,'strengths':strengths,'differences':'Differences in emotional timing, boundaries, affection or social energy can become useful conversation points.','questions':questions,'descriptions':desc}
def recommended_modules(types,goals):
 t=(types+' '+goals).lower();m=['Home','About','Contact']
 def add(*xs):
  for x in xs:
   if x not in m:m.append(x)
 if any(x in t for x in ['appointment','massage','beauty','hair','reiki','consultation']):add('Services','Booking')
 if any(x in t for x in ['class','course','teacher','yoga']):add('Classes')
 if any(x in t for x in ['product','e-commerce','shop']):add('Shop')
 if any(x in t for x in ['content','creator','video']):add('Watch')
 if 'event' in t:add('Events')
 if 'retreat' in t:add('Retreats')
 if any(x in t for x in ['creator','speaker','motivational']):add('Media Kit','Collaborate')
 if 'affiliate' in t:add('Recommendations')
 return m
def build_plan_sections(row):
 name=row['business_name'] or 'Your Business';target=row['target_customer'] or 'your intended customer';offers=row['offers'] or 'the products, services or experiences identified in your questionnaire';strengths=row['strengths'] or 'your skills, experience, certifications and lived knowledge';mods=recommended_modules(row['business_types'] or '',row['app_goals'] or '')
 return {'Executive Summary':f'{name} is being developed to serve {target}. The business will focus on {offers}. This plan organizes the concept into a practical launch path and digital business presence.','Business Concept & Mission':f'{name} will turn the founder\'s current skills, ideas or experience into a clear customer offering. The mission should center on the value delivered to {target}.','Founder Strengths & Qualifications':f'Founder strengths identified in the questionnaire include: {strengths}. Translate these into trust signals such as credentials, portfolio examples, demonstrations, educational content or a clear founder story.','Target Customer':f'Primary target customer: {target}. Build customer profiles around the problem they are trying to solve, what they value, where they spend attention and what builds trust.','Market Need & Positioning':f"{name} should position itself around a specific customer need rather than trying to serve everyone. Focus on the intersection of founder strengths, selected categories ({row['business_types'] or 'to be refined'}) and customer need.",'Products & Services':f'Proposed offers: {offers}. Start with a focused set of offers that are easy to explain, price and deliver. Add new offers after observing demand.','Pricing & Revenue Model':f"Pricing ideas: {row['pricing_ideas'] or 'Pricing is still being developed.'} Revenue may come from services, products, classes, courses, memberships, events, retreats or content where appropriate.",'Brand & Customer Experience':f'The brand should make it easy for a visitor to understand who {name} serves, what it offers, why it matters and what action to take next.','Operations & Technology':'Define booking, payment, fulfillment, customer support and record-keeping procedures. Use the Business Dashboard to manage the profile/app, classes, plan and marketing.','Hosted App Strategy':f"Recommended app modules: {' | '.join(mods)}. These modules are based on the selected business types and app goals and can change as the business grows."}
def marketing_text(row):return f"""TARGET AUDIENCE\n{row['target_customer'] or 'Define the clearest first customer segment.'}\n\nPRIMARY CHANNELS\n{row['marketing_channels'] or 'Social media • referrals • local/community partnerships'}\n\nCONTENT PILLARS\n1. Education — teach something useful connected to the offer.\n2. Founder Story — show why the business exists.\n3. Offers — explain services/products clearly.\n4. Customer Experience — show how someone books, buys or participates.\n5. Collaboration — build relationships with businesses, creators, events and retreat partners.\n\nFOCUS\nBuild awareness first, then invitations, then repeatable follow-up. Track which content, partnerships and offers lead to inquiries or purchases."""
def launch_text(row):return f"""GOAL\n{row['goals_90'] or 'Launch the first clear offer and begin building repeatable customer demand.'}\n\nDAYS 1–30 — FOUNDATION\nFinalize the business name, core customer, first offers, pricing, operational needs, brand direction and app structure.\n\nDAYS 31–60 — VISIBILITY & OUTREACH\nPublish useful content, contact potential partners, build local/community awareness, collect early interest and test messaging.\n\nDAYS 61–90 — LAUNCH & LEARN\nRun a focused launch campaign, invite customers to the clearest offer, gather feedback, track results and refine pricing, messaging and the hosted app."""
def simple_pdf_bytes(title,sections):
 objs=[]
 def add(x):objs.append(x);return len(objs)
 font=add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');pages=[]
 for page_title,body in sections:
  lines=[page_title,'']+textwrap.wrap((body or '').replace('\t',' '),88);lines=lines[:48];y=760;cmd=['BT','/F1 12 Tf']
  for i,line in enumerate(lines):
   safe=line.encode('latin-1','replace').decode('latin-1').replace('\\','\\\\').replace('(','\\(').replace(')','\\)');size=17 if i==0 else 11;cmd.append(f'/F1 {size} Tf 54 {y} Td ({safe}) Tj');step=28 if i==0 else 15;cmd.append(f'0 {-step} Td');y-=step
  cmd.append('ET');stream='\n'.join(cmd).encode('latin-1');content=add(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream');page=add(f'<< /Type /Page /Parent PAGESREF /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>');pages.append(page)
 kids=' '.join(f'{x} 0 R' for x in pages);pages_id=add(f'<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>');catalog=add(f'<< /Type /Catalog /Pages {pages_id} 0 R >>');fixed=[]
 for x in objs:
  fixed.append(x.replace(b'PAGESREF',f'{pages_id} 0 R'.encode()) if isinstance(x,bytes) else x.replace('PAGESREF',f'{pages_id} 0 R').encode('latin-1'))
 out=bytearray(b'%PDF-1.4\n');offs=[0]
 for i,obj in enumerate(fixed,1):offs.append(len(out));out+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
 xref=len(out);out+=f'xref\n0 {len(fixed)+1}\n'.encode()+b'0000000000 65535 f \n'
 for o in offs[1:]:out+=f'{o:010d} 00000 n \n'.encode()
 out+=f'trailer\n<< /Size {len(fixed)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF'.encode();return bytes(out)
def stripe_ready():return bool(STRIPE_SECRET_KEY and BASE_URL)
def stripe_checkout(kind,user_id,target_id=0):
 item=PAY_ITEMS[kind];data={'mode':item['mode'],'success_url':BASE_URL+'/payment/success?session_id={CHECKOUT_SESSION_ID}','cancel_url':BASE_URL+'/membership','line_items[0][price_data][currency]':'usd','line_items[0][price_data][unit_amount]':str(item['amount']),'line_items[0][price_data][product_data][name]':item['name'],'line_items[0][quantity]':'1','metadata[user_id]':str(user_id),'metadata[kind]':kind,'metadata[target_id]':str(target_id)}
 if item['mode']=='subscription':data['line_items[0][price_data][recurring][interval]']='month';data['subscription_data[metadata][user_id]']=str(user_id);data['subscription_data[metadata][kind]']=kind
 req=urllib.request.Request('https://api.stripe.com/v1/checkout/sessions',data=urllib.parse.urlencode(data).encode(),headers={'Authorization':'Bearer '+STRIPE_SECRET_KEY,'Content-Type':'application/x-www-form-urlencoded'})
 with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
def verify_stripe(payload,sig):
 if not STRIPE_WEBHOOK_SECRET:return False
 parts=dict(x.split('=',1) for x in sig.split(',') if '=' in x);ts=parts.get('t');v1=parts.get('v1')
 if not ts or not v1:return False
 expected=hmac.new(STRIPE_WEBHOOK_SECRET.encode(),(ts+'.').encode()+payload,hashlib.sha256).hexdigest();return hmac.compare_digest(expected,v1) and abs(time.time()-int(ts))<600
def activate_purchase(uid,kind,target=0):
 c=conn()
 if kind=='full_membership':c.execute('UPDATE users SET full_member=1 WHERE id=?',(uid,))
 elif kind=='business_app':c.execute('UPDATE users SET business_access=1 WHERE id=?',(uid,));c.execute('UPDATE businesses SET paid_business=1 WHERE owner_id=?',(uid,))
 elif kind=='startup_package':c.execute('UPDATE users SET startup_access=1 WHERE id=?',(uid,))
 elif kind=='video_time':c.execute('UPDATE video_sessions SET seconds_available=seconds_available+300 WHERE id=?',(target,))
 elif kind=='video_message' and target:c.execute('INSERT INTO messages(sender_id,recipient_id,message_type,subject,body) VALUES(?,?,?,?,?)',(uid,target,'video','Paid video request','A paid video request/message was sent. You may answer without paying the sender charge.'));c.execute('INSERT INTO notifications(user_id,notification_type,title,body) VALUES(?,?,?,?)',(target,'video','New paid video request','A member sent you a paid video request. You may answer without paying.'))
 c.commit();c.close()
T={}
T['base.html']=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{% block title %}The Seasons Within{% endblock %}</title><style>:root{--p:#34204f;--u:#8f63ba;--u2:#aa79c7;--l:#f2e9f8;--rose:#fff0f3;--line:#eadff1;--m:#786b82;--gold:#ddc26f;--sh:0 14px 36px rgba(72,42,96,.09)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:linear-gradient(180deg,#fcf9fd,#fffaf8 56%,#faf6fc);color:var(--p);font-family:Arial,Helvetica,sans-serif;min-height:100vh}a{text-decoration:none;color:inherit}img,video{max-width:100%}h1,h2,h3{font-family:Georgia,"Times New Roman",serif}.top{position:sticky;top:0;z-index:50;background:#fffffff4;border-bottom:1px solid var(--line);backdrop-filter:blur(16px)}.topin{width:min(1240px,94vw);min-height:78px;margin:auto;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px}.brand{display:flex;align-items:center;gap:10px}.brand img{width:50px;height:50px;object-fit:contain}.brand strong{display:block;font:700 19px Georgia}.brand small{display:block;font-size:9px;letter-spacing:1.2px;color:var(--m);text-transform:uppercase}.nav{display:flex;justify-content:center;gap:5px;flex-wrap:wrap}.nav a{padding:10px 12px;border-radius:999px;font-size:13px;font-weight:800;color:#65576d}.nav a.on,.nav a:hover{background:var(--l);color:#68428a}.acct{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:800}.wrap{width:min(1140px,92vw);margin:26px auto 110px}.hero,.card{background:#fff;border:1px solid var(--line);border-radius:22px;box-shadow:var(--sh)}.hero{padding:27px;background:linear-gradient(135deg,#f0e3fa,#fff1ed)}.card{padding:20px;margin:15px 0}.paid{border:2px solid var(--gold)!important}.badge,.chip{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;background:var(--l);font-size:10px;font-weight:900;color:#68428a}.badge.gold{background:#fff8df;border:1px solid var(--gold);color:#765615}.badge.heart{background:var(--rose);color:#96526b}.actions,.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.btn,.out,button{display:inline-flex;align-items:center;justify-content:center;min-height:41px;padding:9px 14px;border-radius:11px;font-weight:800;cursor:pointer;font:inherit}.btn,button{background:linear-gradient(135deg,var(--u),var(--u2));color:#fff;border:1px solid var(--u)}.out{background:#fff;color:#68428a;border:1px solid #cdb6dd}.danger{background:#fff;color:#8c364d;border:1px solid #d9aab7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:15px}.two{display:grid;grid-template-columns:1fr 1fr;gap:15px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.muted{color:var(--m);line-height:1.55}.small{font-size:12px}.field{margin:12px 0}.field>label{display:block;font-size:12px;font-weight:900;margin-bottom:6px}input,textarea,select{width:100%;border:1px solid #dfd1e8;border-radius:12px;padding:11px;font:inherit;color:var(--p);background:#fff}textarea{min-height:110px}.choice{display:inline-flex;align-items:center;gap:5px;padding:8px 10px;border:1px solid var(--line);border-radius:999px;background:#fff;font-size:12px;font-weight:700}.choice input{width:auto;margin:0}.media{height:215px;border-radius:16px;background:linear-gradient(135deg,#e5d4f1,#f7ded9);display:grid;place-items:center;overflow:hidden;color:#6e6075;font-weight:800}.media img,.media video{width:100%;height:100%;object-fit:cover}.biz{padding:0;overflow:hidden}.biz .media{border-radius:0}.bizbody{padding:18px}.fallback{width:106px;height:106px;object-fit:contain}.fact{padding:13px;border:1px solid var(--line);border-radius:14px;background:#fcf9fd;margin:7px 0}.fact small{display:block;color:var(--m);margin-bottom:4px}.meter{height:10px;background:#eee6f1;border-radius:999px;overflow:hidden;margin:7px 0}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--u),#c992c4)}.notice{padding:14px;border-left:4px solid var(--u);background:#faf6fc;border-radius:10px;color:#65576d;line-height:1.5}.empty{padding:28px;border:1px dashed #d5c1e0;border-radius:16px;text-align:center;color:var(--m)}.avatar{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#c99de3,#efb8c3);color:#fff;font-weight:900;object-fit:cover;overflow:hidden}.post{display:grid;grid-template-columns:52px 1fr;gap:12px}.postmedia{max-height:450px;width:100%;object-fit:cover;border-radius:15px;margin:12px 0}.moon{display:grid;grid-template-columns:100px 1fr;gap:18px;align-items:center}.moonorb{width:86px;height:86px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,#fff,#d9c4e7 48%,#b795cb);font-size:42px}.toolgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.tool{display:block;padding:17px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--sh)}.flash{width:min(1140px,92vw);margin:12px auto;padding:12px 14px;border:1px solid #dfcbed;background:#f5ecfa;border-radius:12px}.bottom{display:none}.moregroup{margin:25px 0 9px}.moregrid{display:grid;grid-template-columns:repeat(2,1fr);gap:11px}.moreitem{display:block;padding:15px;border:1px solid var(--line);border-radius:15px;background:#fff;font-weight:800;box-shadow:var(--sh)}@media(max-width:850px){body{padding-bottom:82px}.topin{display:flex;justify-content:center;min-height:69px}.nav,.acct{display:none}.wrap{width:94vw;margin-top:18px;margin-bottom:24px}.two,.three{grid-template-columns:1fr}.actions .btn,.actions .out{width:100%}.moon{grid-template-columns:80px 1fr}.moonorb{width:72px;height:72px;font-size:35px}.bottom{position:fixed;left:50%;bottom:9px;transform:translateX(-50%);z-index:60;width:95vw;display:grid;grid-template-columns:repeat(5,1fr);padding:7px;border:1px solid var(--line);border-radius:20px;background:#fffffff7;backdrop-filter:blur(17px);box-shadow:0 15px 45px rgba(70,45,95,.18)}.bottom a{padding:7px 3px;border-radius:13px;text-align:center;font-size:9px;font-weight:900;color:#74677d}.bottom a b{display:block;font-size:18px}.bottom a.on{background:var(--l);color:#68428a}}</style>{% block head %}{% endblock %}</head><body><header class="top"><div class="topin"><a class="brand" href="{{url_for('home')}}"><img src="{{url_for('brand_logo')}}"><span><strong>The Seasons Within</strong><small>Conscious Coordination</small></span></a><nav class="nav"><a href="{{url_for('home')}}">Home</a>{% if me %}<a href="{{url_for('community')}}">Community</a><a href="{{url_for('profile')}}">My Profile</a>{% endif %}<a href="{{url_for('business')}}">Business Network</a><a href="{{url_for('retreats')}}">Retreats</a><a href="{{url_for('membership')}}">Membership</a></nav><div class="acct">{% if me %}<a href="{{url_for('messages')}}">Inbox</a><a href="{{url_for('notifications')}}">Notifications</a>{% if me.is_admin %}<a href="{{url_for('admin')}}">Admin</a>{% endif %}<a href="{{url_for('logout')}}">Log Out</a>{% else %}<a href="{{url_for('login')}}">Log In</a><a class="btn" href="{{url_for('join')}}">Join Free</a>{% endif %}</div></div></header>{% with msgs=get_flashed_messages() %}{% if msgs %}<div class="flash">{{msgs|join(' • ')}}</div>{% endif %}{% endwith %}<main class="wrap">{% block content %}{% endblock %}</main><nav class="bottom"><a href="{{url_for('home')}}"><b>⌂</b>Home</a>{% if me %}<a href="{{url_for('community')}}"><b>☼</b>Community</a><a href="{{url_for('profile')}}"><b>◉</b>Profile</a>{% else %}<a href="{{url_for('join')}}"><b>＋</b>Join</a><a href="{{url_for('login')}}"><b>◉</b>Login</a>{% endif %}<a href="{{url_for('business')}}"><b>◇</b>Business</a><a href="{{url_for('more')}}"><b>•••</b>More</a></nav>{% block scripts %}{% endblock %}</body></html>'''
T['business_card.html']=r'''<article class="card biz {% if b.paid_business %}paid{% endif %}"><div class="media">{% if b.paid_business and b.featured_video %}<video src="{{media_url(b.featured_video)}}" controls muted></video>{% elif b.paid_business and b.hero_image %}<img src="{{media_url(b.hero_image)}}">{% elif b.logo %}<img src="{{media_url(b.logo)}}" style="object-fit:contain;padding:20px">{% else %}<img class="fallback" src="{{url_for('brand_logo')}}">{% endif %}</div><div class="bizbody"><span class="badge {% if b.paid_business %}gold{% endif %}">{{'★ HOSTED APP' if b.paid_business else 'FREE BUSINESS LISTING'}}</span><h3>{{b.business_name}}</h3><p><b>{{b.creator_title or b.category}}</b>{% if b.city %} • {{b.city}}{% endif %}</p><p class="muted small">{{b.tagline or b.description}}</p><a class="{{'btn' if b.paid_business else 'out'}}" href="{{url_for('business_app',slug=b.slug)}}">{{'Open App' if b.paid_business else 'View Business'}}</a></div></article>'''
T['home.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">THE SEASONS WITHIN</span><h1>Discover Wellness Within the Community</h1><p class="muted">Explore every active wellness business, hosted app, retreat experience and tools for community, conscious connection and business building.</p><div class="actions"><a class="btn" href="{{url_for('business')}}">Explore Business Network</a><a class="out" href="{{url_for('retreats')}}">Explore Retreats</a></div></section><form class="card" action="{{url_for('business')}}"><input name="q" placeholder="Search businesses, services, classes, creators or wellness experiences..."></form><h2>All Businesses & Apps</h2><p class="muted">Galaxy Eve first, then paid Hosted Apps, then free listings. Every active business appears on Home.</p><div class="grid">{% for b in businesses %}{% include 'business_card.html' %}{% else %}<div class="empty">Real businesses will appear here as they join.</div>{% endfor %}</div><article class="card moon"><div class="moonorb">{{sky.moon_symbol}}</div><div><span class="badge">MOON TODAY</span><h2>Moon in {{sky.moon_sign or 'the current sky'}}{% if sky.moon_degree is not none %} • {{sky.moon_degree}}°{% endif %}</h2><p class="muted"><b>{{sky.moon_phase}}</b> • reflection, not prediction.</p><div class="chips">{% for p in ['Mercury','Venus','Mars','Jupiter','Saturn'] %}{% if sky.positions.get(p) %}<span class="chip">{{p}} • {{sky.positions[p].sign}}</span>{% endif %}{% endfor %}</div></div></article><h2>Retreats</h2><div class="grid">{% for r in retreat_rows %}<article class="card"><span class="badge">{{r.season}}</span><h3>{{r.title}}</h3><p class="muted">{{r.retreat_type}} • {{r.preferred_dates}}</p><a class="btn" href="{{url_for('retreat_detail',rid=r.id)}}">View Retreat</a></article>{% else %}<article class="card"><h3>Design Your Own Retreat</h3><a class="btn" href="{{url_for('retreat_build')}}">Build My Retreat</a></article>{% endfor %}</div><article class="card paid"><span class="badge gold">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan Package — $79.99</h2><p class="muted">Guided questionnaire, editable 10–15 page Business Plan PDF, Marketing Strategy and 90-Day Launch Plan. Save versions, download, email or share from your phone.</p><a class="btn" href="{{url_for('business_builder')}}">Start My Business Plan</a></article>{% endblock %}'''
T['join.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">ONE ACCOUNT</span><h1>Create Your Free Account</h1><p class="muted">Your profile, messages and saved work stay connected to the same login.</p></section><form class="card" method="post"><div class="field"><label>Name</label><input name="name" required></div><div class="field"><label>Email</label><input type="email" name="email" required></div><div class="field"><label>Password</label><input type="password" name="password" minlength="8" required></div><div class="field"><label>Date of Birth</label><input type="date" name="birth_date" required></div><label class="choice"><input type="checkbox" name="age_confirm" required> I confirm I am 18 or older.</label><br><br><button>Create My Free Account</button></form>{% endblock %}'''
T['forgot_password.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">ACCOUNT RECOVERY</span><h1>Forgot Password?</h1><p class="muted">Enter the email connected to your Seasons Within account.</p></section><form class="card" method="post"><div class="field"><label>Email</label><input type="email" name="email" required></div><button>Send Reset Instructions</button></form>{% endblock %}'''
T['reset_password.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><h1>Create a New Password</h1></section><form class="card" method="post"><div class="field"><label>New Password</label><input type="password" name="password" minlength="8" required></div><button>Save New Password</button></form>{% endblock %}'''
T['login.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><h1>Welcome Back</h1><p class="muted">Log in using the same email and password connected to your account.</p></section><form class="card" method="post"><div class="field"><label>Email</label><input type="email" name="email" required></div><div class="field"><label>Password</label><input type="password" name="password" required></div><label class="choice"><input type="checkbox" name="remember"> Remember Me</label><br><br><button>Log In</button><div class="actions"><a class="out" href="{{url_for('forgot_password')}}">Forgot Password?</a><a class="out" href="{{url_for('join')}}">Create a Free Account</a></div></form>{% endblock %}'''
T['forgot.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Forgot Password</h1><form class="card" method="post"><div class="field"><label>Email</label><input type="email" name="email" required></div><button>Send Reset Link</button></form><p class="muted">If email delivery is configured, a secure reset link will be sent. Otherwise an administrator can help reset the account.</p>{% endblock %}'''
T['reset.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Set a New Password</h1><form class="card" method="post"><div class="field"><label>New Password</label><input type="password" name="password" minlength="8" required></div><button>Update Password</button></form>{% endblock %}'''
T['profile.html']=r'''{% extends 'base.html' %}{% block content %}<article class="card {% if u.full_member %}paid{% endif %}"><div class="two" style="align-items:center"><div><span class="badge {% if u.full_member %}gold{% endif %}">{{'★ FULL MEMBER' if u.full_member else 'FREE MEMBER'}}</span><h1>{{u.name}}</h1><p class="muted">{{u.headline}}{% if u.city %} • {{u.city}}{% endif %}</p><p>{{u.bio}}</p><div class="chips">{% for x in ['sun','moon','rising','mercury','venus','mars','jupiter','saturn'] %}{% if u[x] %}<span class="chip">{{x|title}} {{u[x]}}</span>{% endif %}{% endfor %}</div><div class="actions"><a class="btn" href="{{url_for('profile_edit')}}">Edit My Profile</a></div></div><div>{% if u.photo %}<img class="avatar" style="width:115px;height:115px" src="{{media_url(u.photo)}}">{% else %}<span class="avatar" style="width:115px;height:115px;font-size:30px">{{u.name[:1]}}</span>{% endif %}</div></div></article><div class="toolgrid"><a class="tool" href="{{url_for('community')}}"><b>Community</b><br><small>Daily astrology, wellness and member posts</small></a><a class="tool" href="{{url_for('journal')}}"><b>My Private Journal</b></a><a class="tool" href="{{url_for('messages')}}"><b>My Inbox</b></a><a class="tool" href="{{url_for('notifications')}}"><b>Notifications</b></a>{% if cp %}<a class="tool" href="{{url_for('connections')}}"><b>♡ Conscious Connections</b><br><small>{{cp.connection_type}}</small></a>{% else %}<a class="tool" href="{{url_for('connections_join')}}"><b>♡ Join Conscious Connections</b><br><small>Love & Dating, Friendship, or Both</small></a>{% endif %}<a class="tool" href="{{url_for('business_dashboard')}}"><b>My Business Dashboard</b></a></div>{% endblock %}'''
T['profile_edit.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Edit My Profile</h1><form class="card" method="post" enctype="multipart/form-data"><div class="field"><label>Profile Photo</label><input type="file" name="photo" accept="image/*"></div><div class="two"><div class="field"><label>Name</label><input name="name" value="{{u.name}}"></div><div class="field"><label>City</label><input name="city" value="{{u.city}}"></div></div><div class="two"><div class="field"><label>State / Province</label><input name="state" value="{{u.state}}"></div><div class="field"><label>Country</label><input name="country" value="{{u.country}}"></div></div><div class="field"><label>Headline</label><input name="headline" value="{{u.headline}}"></div><div class="field"><label>About Me</label><textarea name="bio">{{u.bio}}</textarea></div><h2>Birth Information</h2><div class="two"><div class="field"><label>Birth Date</label><input type="date" name="birth_date" value="{{u.birth_date}}"></div><div class="field"><label>Birth Time</label><input type="time" name="birth_time" value="{{u.birth_time}}"></div></div><label class="choice"><input type="checkbox" name="time_known" {% if u.time_known %}checked{% endif %}> Exact birth time known</label><div class="three"><div class="field"><label>Birth City</label><input name="birth_city" value="{{u.birth_city}}"></div><div class="field"><label>Birth State / Province</label><input name="birth_state" value="{{u.birth_state}}"></div><div class="field"><label>Birth Country</label><input name="birth_country" value="{{u.birth_country}}"></div></div><div class="notice">The app handles coordinates/time zone behind the scenes. Rising and houses appear only when accurate birth time/location supports them.</div><br><button>Save Profile</button></form>{% endblock %}'''
T['community.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">MEMBERS ONLY</span><h1>Community</h1><p class="muted">Daily astrology, reflection, wellness and real member posts. There are no public comment threads; replies go privately to Inbox.</p></section><article class="card moon"><div class="moonorb">{{sky.moon_symbol}}</div><div><span class="badge">DAILY SEASONS WITHIN</span><h2>Moon in {{sky.moon_sign or 'the current sky'}}{% if sky.moon_degree is not none %} • {{sky.moon_degree}}°{% endif %}</h2><p><b>{{sky.moon_phase}}</b></p><p class="muted">{{daily.reflection}}</p><div class="chips">{% for p in ['Mercury','Venus','Mars','Jupiter','Saturn'] %}{% if sky.positions.get(p) %}<span class="chip">{{p}} • {{sky.positions[p].sign}}</span>{% endif %}{% endfor %}</div></div></article><div class="grid"><article class="card"><span class="badge">RELAXATION</span><h3>60-Second Reset</h3><p class="muted">{{daily.relaxation}}</p></article><article class="card"><span class="badge">JOURNAL PROMPT</span><h3>{{daily.journal}}</h3><a class="out" href="{{url_for('journal')}}">Open My Journal</a></article></div>{% if me.is_admin %}<form class="card paid" method="post" enctype="multipart/form-data"><span class="badge gold">THE SEASONS WITHIN COMMUNITY POST</span><h3>Post an official Community update</h3><input type="hidden" name="post_as" value="system"><textarea name="body" required></textarea><div class="field"><input type="file" name="photo" accept="image/*"></div><button>Post & Notify Members</button><p class="muted small">Members receive a notification when The Seasons Within posts.</p></form>{% endif %}<form class="card" method="post" enctype="multipart/form-data"><input type="hidden" name="post_as" value="member"><textarea name="body" placeholder="Share with the Community..." required></textarea><div class="field"><label>Add Photo</label><input type="file" name="photo" accept="image/*"></div><button>Post to Community</button></form>{% for p in posts %}<article class="card"><div class="post"><div>{% if p.post_as=='system' %}<img class="avatar" src="{{url_for('brand_logo')}}">{% elif p.user_photo %}<img class="avatar" src="{{media_url(p.user_photo)}}">{% else %}<span class="avatar">{{p.display_name[:1]}}</span>{% endif %}</div><div><span class="badge {% if p.post_as=='system' %}gold{% endif %}">{{'THE SEASONS WITHIN' if p.post_as=='system' else 'MEMBER POST'}}</span><h3>{{p.display_name}}</h3><small class="muted">{{p.created_at}}</small><p style="white-space:pre-wrap">{{p.body}}</p>{% if p.photo %}<img class="postmedia" src="{{media_url(p.photo)}}">{% endif %}{% if p.post_as!='system' and p.user_id!=me.id %}<a class="out" href="{{url_for('compose_message',recipient_id=p.user_id,kind='community')}}">Inbox {{p.display_name}}</a>{% endif %}</div></div></article>{% if loop.index % 4 == 0 and sponsors %}{% set b=sponsors[(loop.index//4-1)%sponsors|length] %}{% include 'business_card.html' %}{% endif %}{% else %}<div class="empty">Community posts will appear here.</div>{% endfor %}{% endblock %}'''
T['journal.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">MY JOURNAL</span><h1>Private by Default</h1><p class="muted">Choose whether each entry stays private or shares a separate copy to Community.</p></section><form class="card" method="post"><div class="field"><label>Title</label><input name="title"></div><div class="field"><label>Reflection</label><textarea name="body" required></textarea></div><div class="field"><label>Visibility</label><select name="visibility"><option value="private">Keep Private</option><option value="community">Share a Copy to Community</option></select></div><button>Save Entry</button></form>{% for e in entries %}<article class="card"><span class="badge">{{'PRIVATE' if e.visibility=='private' else 'SHARED COPY TO COMMUNITY'}}</span><h3>{{e.title or 'Journal Entry'}}</h3><p style="white-space:pre-wrap">{{e.body}}</p><small class="muted">{{e.updated_at}}</small><div class="actions"><a class="out" href="{{url_for('journal_edit',jid=e.id)}}">Edit Entry</a>{% if e.visibility=='private' %}<form method="post" action="{{url_for('journal_share',jid=e.id)}}"><button class="out">Share a Copy to Community</button></form>{% endif %}</div></article>{% else %}<div class="empty">Your journal entries appear here.</div>{% endfor %}{% endblock %}'''
T['journal_edit.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Edit Journal Entry</h1><form class="card" method="post"><div class="field"><label>Title</label><input name="title" value="{{e.title}}"></div><div class="field"><label>Reflection</label><textarea name="body">{{e.body}}</textarea></div><div class="field"><label>Visibility</label><select name="visibility"><option value="private" {% if e.visibility=='private' %}selected{% endif %}>Keep Private</option><option value="community" {% if e.visibility=='community' %}selected{% endif %}>Share a Copy to Community</option></select></div><button>Save Changes</button></form>{% endblock %}'''
T['messages.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">PRIVATE MESSAGES</span><h1>My Inbox</h1><p class="muted">Community, Conscious Connections, Business and Retreat conversations all arrive here privately.</p></section>{% for m in rows %}<article class="card"><span class="badge">{{m.message_type}}</span><h3>{{m.other_name}}</h3><p>{{m.body}}</p><small class="muted">{{m.created_at}}</small><a class="out" href="{{url_for('compose_message',recipient_id=m.other_id,kind=m.message_type)}}">Reply Privately</a></article>{% else %}<div class="empty">Private conversations appear here.</div>{% endfor %}{% endblock %}'''
T['compose.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Private Message to {{person.name}}</h1><form class="card" method="post"><div class="field"><label>Subject</label><input name="subject"></div><div class="field"><label>Message</label><textarea name="body" required></textarea></div><button>Send Private Message</button></form><div class="notice">Threats, harassment, abusive targeting and sexual/nude solicitation may be blocked or reviewed. Profanity alone is not treated as automatic abuse.</div>{% endblock %}'''
T['notifications.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">MEMBER ALERTS</span><h1>Notifications</h1></section>{% for n in rows %}<article class="card"><span class="badge {% if n.notification_type=='seasons' %}gold{% endif %}">{{n.notification_type}}</span><h3>{{n.title}}</h3><p class="muted">{{n.body}}</p><small>{{n.created_at}}</small></article>{% else %}<div class="empty">Notifications appear here.</div>{% endfor %}{% endblock %}'''
T['connections_join.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge heart">♡ OPTIONAL MEMBER AREA</span><h1>Join Conscious Connections</h1><p class="muted">Choose how you want to participate. Members who do not opt in cannot browse this private area.</p></section><form class="card" method="post"><label class="fact"><input style="width:auto" type="radio" name="connection_type" value="Love & Dating" required> <b>♡ Love & Dating</b></label><label class="fact"><input style="width:auto" type="radio" name="connection_type" value="Friendship" required> <b>☼ Friendship</b></label><label class="fact"><input style="width:auto" type="radio" name="connection_type" value="Both" required> <b>♡ + ☼ Both</b></label><br><button>Continue to My Connections Profile</button></form>{% endblock %}'''
T['connections_edit.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge heart">♡ CONSCIOUS CONNECTIONS PROFILE</span><h1>Create / Edit My Connections Profile</h1><p class="muted">Mostly multiple-choice questions shape discovery, social/emotional compatibility and the information shown on your profile.</p></section><form class="card" method="post" enctype="multipart/form-data"><div class="two"><div class="field"><label>Connection Type</label><select name="connection_type">{% for x in ['Love & Dating','Friendship','Both'] %}<option {% if cp and cp.connection_type==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div><div class="field"><label>I am</label><select name="gender">{% for x in ['Woman','Man','Nonbinary','Other / Self-describe','Prefer not to say'] %}<option {% if cp and cp.gender==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div></div><div class="two"><div class="field"><label>Who would you like to meet?</label><select name="seeking">{% for x in ['Men','Women','Both','Everyone','Open / No preference'] %}<option {% if cp and cp.seeking==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div><div class="field"><label>Location Preference</label><select name="location_pref">{% for x in ['Local only','Within driving distance','Same state / region','Open to distance','Open to travel'] %}<option {% if cp and cp.location_pref==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div></div><div class="two"><div class="field"><label>Minimum Age</label><input type="number" min="18" name="age_min" value="{{cp.age_min if cp else 25}}"></div><div class="field"><label>Maximum Age</label><input type="number" min="18" name="age_max" value="{{cp.age_max if cp else 65}}"></div></div>{% macro opts(name,items,current='') %}<div class="chips">{% for x in items %}<label class="choice"><input type="checkbox" name="{{name}}" value="{{x}}" {% if x in (current or '') %}checked{% endif %}>{{x}}</label>{% endfor %}</div>{% endmacro %}<div class="field"><label>What are you looking for?</label>{{opts('looking_for',['Long-term relationship','Dating','Friendship','Wellness companion','Activity partner','Travel companion','Retreat companion','Open to possibilities'],cp.looking_for if cp else '')}}</div><div class="two"><div class="field"><label>Occupation</label><input name="occupation" value="{{cp.occupation if cp else ''}}"></div><div class="field"><label>Children</label><select name="children">{% for x in ['No children','Young children','Teen children','Adult children','Prefer not to say'] %}<option {% if cp and cp.children==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div></div><h2>Social & Emotional Compatibility</h2>{% for label,name,items in emotional_fields %}<div class="field"><label>{{label}}</label><select name="{{name}}">{% for x in items %}<option {% if cp and cp[name]==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div>{% endfor %}<div class="field"><label>Love Languages</label>{{opts('love_languages',['Words of Affirmation','Quality Time','Acts of Service','Physical Touch','Gifts / Thoughtful Gestures'],cp.love_languages if cp else '')}}</div><h2>Lifestyle & Values</h2><div class="field"><label>Lifestyle</label>{{opts('lifestyle',['Wellness & self-care','Active & outdoors','Social & outgoing','Homebody & relaxed','Spiritual / reflective','Family-centered','Career-focused','Creative lifestyle'],cp.lifestyle if cp else '')}}</div><div class="field"><label>Things I Enjoy</label>{{opts('activities',['Travel','Dining & entertainment','Nature & outdoors','Wellness & retreats','Relaxing at home','Arts & culture','Fitness','Live music / events'],cp.activities if cp else '')}}</div><div class="field"><label>What Matters Most</label>{{opts('values_text',['Trust & honesty','Communication','Affection & chemistry','Shared values','Growth & support','Reliability','Family','Freedom & independence'],cp.values_text if cp else '')}}</div><div class="field"><label>About Me</label><textarea name="about">{{cp.about if cp else ''}}</textarea></div><h2>Profile Media</h2><p class="muted">Free: 1 photo. $10.99 Full: up to 7 photos + 2 profile videos.</p><input type="file" name="media_files" multiple accept="image/*,video/*"><br><br><button>Save & Enter Conscious Connections</button></form>{% endblock %}'''
T['connections.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge heart">♡ PARTICIPATING MEMBERS ONLY</span><h1>Conscious Connections</h1><p class="muted">Love, Dating & Friendship through real member profiles, compatibility, private Inbox and shared experiences.</p><a class="btn" href="{{url_for('connections_edit')}}">Edit My Connections Profile</a></section>{% for p in host_posts %}<article class="card"><span class="badge">HOST</span><h3>Galaxy Eve</h3><p>{{p.body}}</p>{% if p.media %}{% if p.media_type=='video' %}<video class="postmedia" src="{{media_url(p.media)}}" controls></video>{% else %}<img class="postmedia" src="{{media_url(p.media)}}">{% endif %}{% endif %}<a class="out" href="{{url_for('compose_message',recipient_id=p.user_id,kind='connections')}}">Inbox Galaxy Eve</a></article>{% endfor %}{% if is_host %}<form class="card paid" method="post" enctype="multipart/form-data"><h3>Post as Conscious Connections Host</h3><textarea name="body" required></textarea><input type="file" name="media" accept="image/*,video/*"><br><br><button>Publish Host Post</button></form>{% endif %}<h2>Discover Members</h2><div class="grid">{% for p in people %}<article class="card {% if p.full_member %}paid{% endif %}"><span class="badge {% if p.full_member %}gold{% endif %}">{{'★ FULL MEMBER' if p.full_member else 'FREE CONNECTION PROFILE'}}</span><h3>{{p.name}}{% if p.age %}, {{p.age}}{% endif %}</h3><p class="muted">{{p.city}} • {{p.connection_type}}</p><div class="chips">{% if p.sun %}<span class="chip">Sun {{p.sun}}</span>{% endif %}{% if p.moon %}<span class="chip">Moon {{p.moon}}</span>{% endif %}{% if p.rising %}<span class="chip">Rising {{p.rising}}</span>{% endif %}</div><h3>{{p.score}}% Conscious Coordination</h3><div class="meter"><i style="width:{{p.score}}%"></i></div><div class="actions"><a class="btn" href="{{url_for('connection_profile',uid=p.id)}}">View Profile</a><a class="out" href="{{url_for('compose_message',recipient_id=p.id,kind='connections')}}">Inbox</a></div></article>{% else %}<div class="empty">Real participating members will appear here.</div>{% endfor %}</div>{% if connection_businesses %}<h2>Approved Connection Experiences</h2><div class="grid">{% for b in connection_businesses %}{% include 'business_card.html' %}{% endfor %}</div>{% endif %}{% endblock %}'''
T['connection_profile.html']=r'''{% extends 'base.html' %}{% block content %}<section class="card {% if person.full_member %}paid{% endif %}"><div class="two"><div>{% if media %}{% set first=media[0] %}{% if first.media_type=='video' %}<video class="media" src="{{media_url(first.filename)}}" controls></video>{% else %}<img class="media" src="{{media_url(first.filename)}}">{% endif %}{% else %}<div class="media">Profile Photo</div>{% endif %}</div><div><span class="badge {% if person.full_member %}gold{% endif %}">{{'★ FULL CONSCIOUS CONNECTIONS PROFILE' if person.full_member else 'FREE CONSCIOUS CONNECTIONS PROFILE'}}</span><h1>{{person.name}}{% if person_age %}, {{person_age}}{% endif %}</h1><p class="muted">{{person.city}} • {{cp.connection_type}}</p><p>{{cp.about}}</p><div class="actions"><a class="btn" href="{{url_for('compose_message',recipient_id=person.id,kind='connections')}}">Inbox {{person.name}}</a>{% if me.full_member %}<a class="out" href="{{url_for('video_request',uid=person.id)}}">Video Connection</a>{% endif %}</div></div></div></section><div class="grid"><article class="card"><h2>About</h2>{% for k,l in [('occupation','Occupation'),('children','Children'),('looking_for','Looking for'),('lifestyle','Lifestyle'),('activities','Enjoys'),('values_text','Values')] %}<div class="fact"><small>{{l}}</small><b>{{cp[k] or '—'}}</b></div>{% endfor %}</article><article class="card"><h2>How {{person.name}} Connects</h2>{% for k,l in [('emotional_response','When upset'),('others_emotions','When someone else is emotional'),('conflict_style','Conflict'),('repair_style','Repair'),('apology_style','Apology style'),('love_languages','Love languages'),('communication_style','Communication'),('boundaries','Boundaries')] %}<div class="fact"><small>{{l}}</small><b>{{cp[k] or '—'}}</b></div>{% endfor %}</article></div><article class="card"><h2>Birth Chart</h2><div class="chips">{% if person.sun %}<span class="chip">Sun {{person.sun}}</span>{% endif %}{% if person.moon %}<span class="chip">Moon {{person.moon}}</span>{% endif %}</div>{% if me.full_member %}<p class="muted">Full members can see participating members' full shared chart and compare both charts.</p><div class="actions"><a class="btn" href="{{url_for('birth_chart_view',uid=person.id)}}">View {{person.name}}'s Birth Chart</a><a class="out" href="{{url_for('compatibility_view',uid=person.id)}}">Compare Our Birth Charts</a></div>{% else %}<a class="btn" href="{{url_for('membership')}}">Upgrade to $10.99</a>{% endif %}</article><article class="card {% if me.full_member %}paid{% endif %}"><h2>{{report.overall}}% {{'Full Compatibility' if me.full_member else 'Basic Compatibility Preview'}}</h2><a class="btn" href="{{url_for('compatibility_view',uid=person.id)}}">Open Compatibility</a></article>{% if me.full_member and media|length>1 %}<article class="card"><h2>Photos & Videos</h2><div class="grid">{% for x in media %}{% if x.media_type=='video' %}<video class="media" src="{{media_url(x.filename)}}" controls></video>{% else %}<img class="media" src="{{media_url(x.filename)}}">{% endif %}{% endfor %}</div></article>{% endif %}<div class="actions"><form method="post" action="{{url_for('block_member',uid=person.id)}}"><button class="danger">Block</button></form><a class="danger out" href="{{url_for('report_member',uid=person.id)}}">Report</a></div>{% endblock %}'''
T['compatibility.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero {% if me.full_member %}paid{% endif %}"><span class="badge {% if me.full_member %}gold{% endif %}">{{'★ $10.99 FULL COMPATIBILITY' if me.full_member else 'FREE COMPATIBILITY PREVIEW'}}</span><h1>Conscious Coordination Report</h1><p class="muted">Social/emotional compatibility comes from members' own answers. Astrology is a separate reflective layer.</p></section><article class="card"><h2>{{report.overall}}% Overall Coordination</h2><div class="meter"><i style="width:{{report.overall}}%"></i></div></article>{% if me.full_member %}<div class="grid">{% for name,score in report.social.items() %}<article class="card"><h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div><p class="muted">{{report.descriptions[name]}}</p></article>{% endfor %}</div><article class="card"><h2>Astrology Layer</h2>{% for name,score in report.astro.items() %}{% if score is not none %}<h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div>{% endif %}{% endfor %}<a class="btn" href="{{url_for('birth_chart_view',uid=person.id)}}">Open Full Birth Chart Compatibility</a></article><article class="card"><h2>Strengths</h2><p>{{report.strengths}}</p><h2>Differences Worth Understanding</h2><p>{{report.differences}}</p>{% for q in report.questions %}<div class="fact">{{q}}</div>{% endfor %}<a class="out" href="{{url_for('connection_ideas',uid=person.id)}}">See Date / Friendship Ideas</a></article>{% else %}<article class="card">{% for name in ['Communication','Emotional Style','Lifestyle & Values','Astrology Preview'] %}<h3>{{name}} — {{report.basic[name]}}%</h3><div class="meter"><i style="width:{{report.basic[name]}}%"></i></div>{% endfor %}<p><b>Strength:</b> {{report.strengths}}</p><p><b>Difference:</b> {{report.differences}}</p><p><b>Conversation Starter:</b> {{report.questions[0]}}</p><a class="btn" href="{{url_for('membership')}}">Unlock Full Compatibility — $10.99</a></article>{% endif %}{% endblock %}'''
T['birth_chart.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">★ FULL MEMBER • BIRTH CHART COMPATIBILITY</span><h1>Chart-to-Chart Conscious Coordination</h1><p class="muted">View the participating member's full shared chart and compare it with yours. Rising and houses appear only when reliable birth data supports them.</p></section><div class="two"><article class="card"><h2>Your Chart</h2><div class="chips">{% for x in planets %}{% if me[x] %}<span class="chip">{{x|title}} {{me[x]}}</span>{% endif %}{% endfor %}</div></article><article class="card"><h2>{{person.name}}'s Shared Chart</h2><div class="chips">{% for x in planets %}{% if person[x] %}<span class="chip">{{x|title}} {{person[x]}}</span>{% endif %}{% endfor %}</div></article></div><article class="card"><h2>Planet-to-Planet Coordination</h2>{% for name,score in report.astro.items() %}{% if score is not none %}<h3>{{name}} — {{score}}%</h3><div class="meter"><i style="width:{{score}}%"></i></div>{% endif %}{% endfor %}</article>{% if me.rising and person.rising %}<article class="card"><h2>House Overlay Layer Available</h2><p class="muted">Both profiles have usable birth-time/location information.</p></article>{% endif %}{% endblock %}'''
T['connection_ideas.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">★ CONNECTION IDEAS</span><h1>Ideas for You + {{person.name}}</h1><p class="muted">Ideas are based on the two profiles, interests, communication preferences and compatibility—not only zodiac signs.</p></section><div class="grid"><article class="card"><span class="badge">DATE IDEA</span><h3>Low-pressure shared experience</h3><p class="muted">Choose a relaxed café, art space, nature walk or wellness experience.</p></article><article class="card"><span class="badge">FRIENDSHIP IDEA</span><h3>Do something you both selected</h3><p class="muted">Use overlapping interests such as nature, wellness, live events, travel or arts.</p></article><article class="card"><span class="badge">CONVERSATION</span><h3>{{report.questions[0]}}</h3></article><article class="card"><span class="badge">RETREAT</span><h3>Build a Connection Retreat</h3><a class="btn" href="{{url_for('retreat_build',connection=1)}}">Build Retreat</a></article></div>{% endblock %}'''
T['video_request.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">★ VIDEO CONNECTION</span><h1>Connect With {{person.name}}</h1><p class="muted">Full members can request an approved 5-minute private video connection. Extra 5-minute blocks are $5. A paid video request/message is $5; the recipient may answer without paying.</p></section><div class="grid"><article class="card"><h2>5-Minute Live Video Request</h2><form method="post"><button>Send Live Video Request</button></form></article><article class="card paid"><h2>$5 Video Request / Message</h2><a class="btn" href="{{url_for('checkout',kind='video_message',target_id=person.id)}}">Send for $5</a></article></div>{% endblock %}'''
T['video.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">★ PRIVATE VIDEO CONNECTION</span><h1>Video Chat With {{person.name}}</h1><p class="muted">Approved access and paid talk time are handled here. Reliable live camera transport still requires WebRTC signaling/TURN service configuration.</p></section><div class="two"><article class="card"><div class="media">Your Camera</div></article><article class="card"><div class="media">{{person.name}}'s Camera</div></article></div><article class="card" style="text-align:center"><h1 id="timer">05:00</h1><a class="btn" href="{{url_for('checkout',kind='video_time',target_id=session_row.id)}}">Add 5 Minutes — $5</a></article>{% endblock %}{% block scripts %}<script>let s={{session_row.seconds_available}};setInterval(()=>{if(s>0)s--;let m=Math.floor(s/60),x=s%60;document.getElementById('timer').textContent=String(m).padStart(2,'0')+':'+String(x).padStart(2,'0')},1000)</script>{% endblock %}'''
T['report.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Report {{person.name}}</h1><form class="card" method="post"><div class="field"><label>Reason</label><select name="reason"><option>Harassment</option><option>Threats</option><option>Sexual / Nude Content</option><option>Fake / Misleading Profile</option><option>Underage Concern</option><option>Other</option></select></div><div class="field"><label>Details</label><textarea name="details"></textarea></div><button>Submit Report</button></form>{% endblock %}'''
T['business.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">BUSINESS NETWORK</span><h1>Discover Wellness Within the Community</h1><p class="muted">Free listings stay clean and simple. $29.99 Hosted Apps stand out and open as mini-apps inside The Seasons Within.</p>{% if me %}<div class="actions"><a class="btn" href="{{url_for('business_setup')}}">My Business Listing / App</a><a class="out" href="{{url_for('business_builder')}}">Startup/Hobby → Business • $79.99</a><a class="out" href="{{url_for('business_dashboard')}}">Business Dashboard</a></div>{% endif %}</section><form class="card" method="get"><input name="q" value="{{q}}" placeholder="Search businesses, services, classes or creators..."></form><div class="grid">{% for b in businesses %}{% include 'business_card.html' %}{% else %}<div class="empty">Real businesses appear here as they join.</div>{% endfor %}</div><article class="card paid"><span class="badge gold">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan + Marketing + 90-Day Launch Plan — $79.99</h2><p class="muted">Create a guided 10–15 page plan, store it in your profile, modify it, save versions, download the PDF, email it or share it from your phone.</p><a class="btn" href="{{url_for('business_builder')}}">Start My Business Package</a></article>{% endblock %}'''
T['business_setup.html']=r'''{% extends 'base.html' %}{% block content %}<h1>My Business Listing / Hosted App</h1><form class="card" method="post" enctype="multipart/form-data"><div class="field"><label>Business Logo</label><input type="file" name="logo" accept="image/*"></div><div class="two"><div class="field"><label>Business Name</label><input name="business_name" value="{{b.business_name if b else ''}}" required></div><div class="field"><label>Category</label><input name="category" value="{{b.category if b else ''}}"></div></div><div class="two"><div class="field"><label>Title / Role</label><input name="creator_title" value="{{b.creator_title if b else ''}}"></div><div class="field"><label>City</label><input name="city" value="{{b.city if b else ''}}"></div></div><div class="field"><label>State</label><input name="state" value="{{b.state if b else ''}}"></div><div class="field"><label>Tagline</label><input name="tagline" value="{{b.tagline if b else ''}}"></div><div class="field"><label>Description</label><textarea name="description">{{b.description if b else ''}}</textarea></div><h2>Social & Business Links</h2><div class="two">{% for x in ['website','instagram','tiktok','youtube','facebook','booking_url'] %}<div class="field"><label>{{x|replace('_',' ')|title}}</label><input name="{{x}}" value="{{b[x] if b else ''}}"></div>{% endfor %}</div>{% if me.business_access or me.is_admin %}<h2>Paid Hosted App Media</h2><div class="two"><div class="field"><label>Cover Photo</label><input type="file" name="hero_image" accept="image/*"></div><div class="field"><label>Featured Video</label><input type="file" name="featured_video" accept="video/*"></div></div><div class="field"><label>App Modules</label><input name="modules" value="{{b.modules if b else ''}}" placeholder="Home|About|Services|Classes|Events|Media Kit|Contact"></div>{% endif %}<div class="chips"><label class="choice"><input type="checkbox" name="retreat_participation" {% if b and b.retreat_participation %}checked{% endif %}> Retreat Provider</label>{% if me.business_access or me.is_admin %}<label class="choice"><input type="checkbox" name="sponsor_community" {% if b and b.sponsor_community %}checked{% endif %}> Community Featured Experience</label><label class="choice"><input type="checkbox" name="approved_connections" {% if b and b.approved_connections %}checked{% endif %}> Approved Conscious Connections Experience</label>{% endif %}</div><br><button>Save Business</button></form>{% endblock %}'''
T['business_app.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero {% if b.paid_business %}paid{% endif %}"><span class="badge {% if b.paid_business %}gold{% endif %}">{{'★ HOSTED BUSINESS APP' if b.paid_business else 'FREE BUSINESS LISTING'}}</span><div class="two" style="align-items:center"><div><h1>{{b.business_name}}</h1><h3>{{b.creator_title}}</h3><p class="muted">{{b.tagline}}</p><div class="chips">{% for label,url in socials %}<a class="chip" href="{{url}}" target="_blank">{{label}}</a>{% endfor %}</div></div><div>{% if b.logo %}<img class="fallback" src="{{media_url(b.logo)}}">{% else %}<img class="fallback" src="{{url_for('brand_logo')}}">{% endif %}</div></div></section><article class="card"><h2>About</h2><p>{{b.description}}</p></article>{% if b.paid_business %}<div class="chips">{% for m in modules %}<span class="chip">{{m}}</span>{% endfor %}</div><h2>Classes & Experiences</h2><div class="grid">{% for x in classes %}<article class="card"><span class="badge">{{x.class_format}}</span><h3>{{x.title}}</h3><p class="muted">{{x.description}}</p><p>{{x.class_date}} {{x.class_time}} • {{x.price}}</p>{% if x.meeting_url %}<a class="btn" href="{{x.meeting_url}}" target="_blank">Join / Register</a>{% endif %}</article>{% else %}<div class="empty">Classes and experiences created by this business appear here.</div>{% endfor %}</div>{% endif %}{% endblock %}'''
T['business_manage.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Manage Hosted App Classes</h1>{% if b and (me.business_access or me.is_admin) %}<form class="card" method="post"><div class="two"><div class="field"><label>Class Title</label><input name="title" required></div><div class="field"><label>Format</label><select name="class_format"><option>Live</option><option>Recorded</option><option>Hybrid</option></select></div></div><div class="field"><label>Description</label><textarea name="description"></textarea></div><div class="three"><div class="field"><label>Date</label><input type="date" name="class_date"></div><div class="field"><label>Time</label><input type="time" name="class_time"></div><div class="field"><label>Price</label><input name="price"></div></div><div class="field"><label>Meeting / Registration Link</label><input name="meeting_url"></div><button>Add Class</button></form>{% else %}<div class="empty">A paid Hosted Business App is required to host classes inside the app.</div>{% endif %}{% endblock %}'''
T['business_builder.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">STARTUP / HOBBY → BUSINESS • $79.99</span><h1>Turn What You Know Into a Business</h1><p class="muted">The questionnaire shapes your Business Plan, app structure, Marketing Strategy and 90-Day Launch Plan.</p></section>{% if not me %}<div class="card"><a class="btn" href="{{url_for('join')}}">Join Free to Continue</a></div>{% else %}<form class="card" method="post">{% macro opts(name,items,current='') %}<div class="chips">{% for x in items %}<label class="choice"><input type="checkbox" name="{{name}}" value="{{x}}" {% if x in (current or '') %}checked{% endif %}>{{x}}</label>{% endfor %}</div>{% endmacro %}<div class="field"><label>Where are you starting?</label><select name="stage">{% for x in ['Already own a business','Starting a new business','Business idea','Hobby to business','Skill/talent to monetize','Certification/license','Content creator','Help me develop an idea'] %}<option {% if row and row.stage==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div><div class="field"><label>Business Types</label>{{opts('business_types',business_types,row.business_types if row else '')}}</div><div class="field"><label>What should your app help you do?</label>{{opts('app_goals',app_goals,row.app_goals if row else '')}}</div><div class="field"><label>What are you good at?</label><textarea name="strengths">{{row.strengths if row else ''}}</textarea></div><div class="field"><label>Who do you want to help?</label><textarea name="target_customer">{{row.target_customer if row else ''}}</textarea></div><div class="field"><label>What will you offer?</label><textarea name="offers">{{row.offers if row else ''}}</textarea></div><div class="field"><label>Business Name</label><input name="business_name" value="{{row.business_name if row else ''}}"></div><div class="field"><label>Marketing Channels</label>{{opts('marketing_channels',['Social media','Google/search','Local community','Events','Referrals','Influencers','Email','Partnerships','Paid advertising'],row.marketing_channels if row else '')}}</div><div class="field"><label>Pricing / Revenue Ideas</label><textarea name="pricing_ideas">{{row.pricing_ideas if row else ''}}</textarea></div><div class="field"><label>Goals for the next 90 days</label><textarea name="goals_90">{{row.goals_90 if row else ''}}</textarea></div><button>Save Questionnaire</button></form>{% if row %}<article class="card paid"><h2>Ready for Your Business Package?</h2><h1>$79.99</h1><p class="muted">10–15 page Business Plan PDF + Marketing Strategy + 90-Day Launch Plan + editable saved copies.</p>{% if me.startup_access or me.is_admin %}<a class="btn" href="{{url_for('generate_business_plan')}}">Generate My Business Plan</a>{% else %}<a class="btn" href="{{url_for('checkout',kind='startup_package')}}">Purchase $79.99 Package</a>{% endif %}</article>{% endif %}{% endif %}{% endblock %}'''
T['business_dashboard.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">BUSINESS DASHBOARD</span><h1>{{b.business_name if b else (builder.business_name if builder else 'My Business')}}</h1><p class="muted">Manage your listing/app, classes, Business Plan, saved plan copies, Marketing Strategy and 90-Day Launch Plan.</p><div class="actions"><a class="btn" href="{{url_for('business_setup')}}">Business Profile / App</a><a class="out" href="{{url_for('business_manage')}}">Manage Classes</a><a class="out" href="{{url_for('business_builder')}}">Startup Business Builder</a></div></section>{% if latest_plan %}<article class="card paid"><span class="badge gold">MY BUSINESS PLAN</span><h2>{{latest_plan.business_name}} • Version {{latest_plan.version_no}}</h2><div class="actions"><a class="btn" href="{{url_for('business_plan_view',plan_id=latest_plan.id)}}">Open Plan</a><a class="out" href="{{url_for('business_plan_edit',plan_id=latest_plan.id)}}">Edit Plan</a><a class="out" href="{{url_for('business_plan_pdf',plan_id=latest_plan.id)}}">Download PDF</a><a class="out" href="{{url_for('business_plan_versions')}}">Saved Copies</a></div></article>{% else %}<article class="card"><h2>No Business Plan Yet</h2><a class="btn" href="{{url_for('business_builder')}}">Create My $79.99 Business Package</a></article>{% endif %}{% endblock %}'''
T['business_plan.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">BUSINESS PLAN • VERSION {{plan.version_no}}</span><h1>{{plan.business_name}}</h1><p class="muted">Stored in your Business Dashboard. Modify it, save versions, download PDF, email it or share from your device.</p><div class="actions"><a class="btn" href="{{url_for('business_plan_edit',plan_id=plan.id)}}">Edit Plan</a><a class="out" href="{{url_for('business_plan_pdf',plan_id=plan.id)}}">Download PDF</a><a class="out" href="{{url_for('business_plan_send',plan_id=plan.id)}}">Email PDF</a><button class="out" onclick="sharePlan()">Share PDF</button><a class="out" href="{{url_for('business_plan_versions')}}">Saved Copies</a></div></section>{% for title,text in sections.items() %}<article class="card"><h2>{{title}}</h2><p style="white-space:pre-wrap">{{text}}</p></article>{% endfor %}<article class="card"><h2>Marketing Strategy</h2><p style="white-space:pre-wrap">{{plan.marketing_text}}</p></article><article class="card"><h2>90-Day Launch Plan</h2><p style="white-space:pre-wrap">{{plan.launch_text}}</p></article>{% endblock %}{% block scripts %}<script>async function sharePlan(){try{let r=await fetch("{{url_for('business_plan_pdf',plan_id=plan.id)}}");let b=await r.blob();let f=new File([b],"business-plan.pdf",{type:"application/pdf"});if(navigator.share&&navigator.canShare&&navigator.canShare({files:[f]})){await navigator.share({title:"{{plan.business_name}} Business Plan",files:[f]});}else{window.location="{{url_for('business_plan_pdf',plan_id=plan.id)}}";}}catch(e){window.location="{{url_for('business_plan_pdf',plan_id=plan.id)}}";}}</script>{% endblock %}'''
T['business_plan_edit.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Edit Business Plan</h1><form class="card" method="post"><p class="muted">Saving creates a new version so earlier copies remain available.</p>{% for title,text in sections.items() %}<div class="field"><label>{{title}}</label><textarea name="section_{{loop.index0}}">{{text}}</textarea><input type="hidden" name="title_{{loop.index0}}" value="{{title}}"></div>{% endfor %}<div class="field"><label>Marketing Strategy</label><textarea name="marketing_text">{{plan.marketing_text}}</textarea></div><div class="field"><label>90-Day Launch Plan</label><textarea name="launch_text">{{plan.launch_text}}</textarea></div><button>Save as New Version</button></form>{% endblock %}'''
T['business_plan_versions.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Saved Business Plan Copies</h1>{% for p in plans %}<article class="card"><span class="badge">VERSION {{p.version_no}}</span><h3>{{p.business_name}}</h3><small class="muted">{{p.created_at}}</small><div class="actions"><a class="btn" href="{{url_for('business_plan_view',plan_id=p.id)}}">Open</a><a class="out" href="{{url_for('business_plan_pdf',plan_id=p.id)}}">Download PDF</a></div></article>{% else %}<div class="empty">Saved versions appear here.</div>{% endfor %}{% endblock %}'''
T['business_plan_send.html']=r'''{% extends 'base.html' %}{% block content %}<h1>Email Business Plan PDF</h1><form class="card" method="post"><div class="field"><label>Email Address</label><input type="email" name="email" required></div><div class="field"><label>Message</label><textarea name="message">Attached is my {{plan.business_name}} Business Plan.</textarea></div><button>Send PDF</button></form><p class="muted">Email sending uses configured SMTP settings. If SMTP is not configured, download the PDF and use your normal email/share tools.</p>{% endblock %}'''
T['retreats.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">RETREATS</span><h1>Upcoming Retreats & Design Your Own</h1><p class="muted">Private wellness experiences with participating paid businesses and providers.</p>{% if me %}<a class="btn" href="{{url_for('retreat_build')}}">Build My Retreat</a>{% endif %}</section><div class="grid">{% for r in retreat_rows %}<article class="card"><span class="badge">{{r.season}}</span><h3>{{r.title}}</h3><p class="muted">{{r.retreat_type}} • {{r.preferred_dates}}</p><a class="btn" href="{{url_for('retreat_detail',rid=r.id)}}">Open Retreat</a></article>{% else %}<div class="empty">Upcoming Retreat experiences will appear here.</div>{% endfor %}</div><h2>Participating Wellness Apps</h2><div class="grid">{% for b in businesses %}{% include 'business_card.html' %}{% else %}<div class="empty">Participating paid businesses appear here.</div>{% endfor %}</div>{% endblock %}'''
T['retreat_build.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">DESIGN YOUR OWN RETREAT</span><h1>Build Your Retreat</h1><p class="muted">A guided private retreat request rather than forcing a direct booking date.</p></section><form class="card" method="post"><div class="field"><label>Retreat Title</label><input name="title" required></div><div class="two"><div class="field"><label>Season / Element</label><select name="season"><option>Spring Renewal</option><option>Summer Water</option><option>Autumn Reflection</option><option>Winter Stillness</option></select></div><div class="field"><label>Retreat Type</label><select name="retreat_type"><option>Solo Renewal</option><option>Couples / Dating</option><option>Friendship</option><option>Women's Self-Love</option><option>Men's Renewal</option><option>Family Harmony</option><option>Life Transition</option><option>Creator / Business</option></select></div></div><div class="three"><div class="field"><label>Preferred Dates</label><input name="preferred_dates"></div><div class="field"><label>Guests</label><input type="number" min="1" name="guests" value="1"></div><div class="field"><label>Budget</label><select name="budget"><option>Under $300</option><option>$300–$500</option><option>$500–$750</option><option>$750+</option><option>Let's discuss</option></select></div></div><div class="field"><label>Lodging / Property Preferences</label><textarea name="lodging_preferences"></textarea></div><div class="field"><label>Wellness Interests / What would make this meaningful?</label><textarea name="wellness_interests"></textarea></div><input type="hidden" name="connection_retreat" value="{{1 if connection else 0}}"><button>Send Retreat Request</button></form>{% endblock %}'''
T['retreat_detail.html']=r'''{% extends 'base.html' %}{% block content %}<section class="card"><span class="badge">{{r.season}}</span><h1>{{r.title}}</h1><p>{{r.retreat_type}} • {{r.guests}} guests</p><p class="muted">{{r.preferred_dates}}</p><h3>Property Preferences</h3><p>{{r.lodging_preferences}}</p><h3>Wellness Interests</h3><p>{{r.wellness_interests}}</p></section>{% if me %}<form class="card" method="post"><h2>Private Retreat Message</h2><textarea name="body" required></textarea><button>Send Message</button></form>{% endif %}{% for m in messages %}<article class="card"><b>{{m.name}}</b><p>{{m.body}}</p><small class="muted">{{m.created_at}}</small></article>{% endfor %}{% endblock %}'''
T['membership.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><h1>Membership & Business Packages</h1><p class="muted">Free to belong. Upgrade when you want deeper connection tools, a Hosted Business App or the Startup Business package.</p></section><div class="grid"><article class="card"><span class="badge">FREE</span><h2>Community</h2><h1>$0</h1><p class="muted">Member profile • Community • Journal • Inbox • Marketplace • Retreats • free Conscious Connections profile.</p></article><article class="card paid"><span class="badge gold">★ FULL MEMBERSHIP</span><h2>Conscious Coordination</h2><h1>$10.99/mo</h1><p class="muted">Full compatibility • participating members' full shared birth charts • chart comparison • up to 7 photos + 2 videos • eligible video tools.</p>{% if me and not me.full_member %}<a class="btn" href="{{url_for('checkout',kind='full_membership')}}">Upgrade</a>{% endif %}</article><article class="card paid"><span class="badge gold">★ BUSINESS NETWORK</span><h2>Hosted Business App</h2><h1>$29.99/mo</h1><p class="muted">Standout hosted app • social links • classes • events • services • media kit • Retreat participation.</p>{% if me and not me.business_access %}<a class="btn" href="{{url_for('checkout',kind='business_app')}}">Upgrade Business</a>{% endif %}</article><article class="card paid"><span class="badge gold">STARTUP / HOBBY → BUSINESS</span><h2>Business Plan Package</h2><h1>$79.99</h1><p class="muted">Editable 10–15 page Business Plan PDF • Marketing Strategy • 90-Day Launch Plan • saved versions • email/share/download.</p>{% if me and not me.startup_access %}<a class="btn" href="{{url_for('checkout',kind='startup_package')}}">Purchase</a>{% else %}<a class="out" href="{{url_for('business_builder')}}">Open Builder</a>{% endif %}</article></div><article class="card"><h2>Video Add-Ons</h2><p><b>Add 5 minutes — $5.</b> <b>Paid video request/message — $5.</b> The receiving Free or Full member can answer without paying the sender fee.</p></article>{% if me and me.is_admin %}<div class="notice"><b>Administrator / Galaxy Eve:</b> Full Membership, Business App and Startup Package access are complimentary for this account.</div>{% endif %}{% endblock %}'''
T['checkout.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">CHECKOUT</span><h1>{{item.name}}</h1><h1>{{item.display}}</h1><p class="muted">{{item.description}}</p>{% if complimentary %}<div class="notice"><b>This account has complimentary full access.</b> No payment is required.</div><a class="btn" href="{{url_for('profile')}}">Continue</a>{% elif stripe_ready %}<form method="post"><button>Continue to Secure Checkout</button></form>{% else %}<div class="notice"><b>Payment processor is not connected yet.</b> Add Stripe environment variables in Render before accepting real charges.</div>{% endif %}</section>{% endblock %}'''
T['payment_success.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><h1>Thank You</h1><p class="muted">Your payment was submitted. Access updates after secure payment confirmation reaches The Seasons Within.</p><a class="btn" href="{{url_for('profile')}}">Return to My Profile</a></section>{% endblock %}'''
T['more.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">MEMBER MENU</span><h1>Everything in One Place</h1><p class="muted">The complete phone menu keeps every page easy to locate without crowding the bottom navigation.</p></section>{% if me %}<div class="moregroup"><span class="badge">MY ACCOUNT</span><h2>Profile & Communication</h2></div><div class="moregrid"><a class="moreitem" href="{{url_for('profile')}}">My Profile</a><a class="moreitem" href="{{url_for('community')}}">Community</a><a class="moreitem" href="{{url_for('messages')}}">Inbox</a><a class="moreitem" href="{{url_for('notifications')}}">Notifications</a><a class="moreitem" href="{{url_for('journal')}}">Private Journal</a><a class="moreitem" href="{{url_for('settings')}}">Settings / Account</a></div><div class="moregroup"><span class="badge heart">♡ OPT-IN</span><h2>Conscious Connections</h2></div><div class="moregrid"><a class="moreitem" href="{{url_for('connections')}}">Discover Members</a><a class="moreitem" href="{{url_for('connections_edit')}}">My Connections Profile</a></div><div class="moregroup"><span class="badge gold">BUSINESS</span><h2>My Business Tools</h2></div><div class="moregrid"><a class="moreitem" href="{{url_for('business')}}">Business Network</a><a class="moreitem" href="{{url_for('business_dashboard')}}">Business Dashboard</a><a class="moreitem" href="{{url_for('business_plan_versions')}}">Saved Plan Copies</a><a class="moreitem" href="{{url_for('business_builder')}}">Startup/Hobby → Business</a></div><div class="moregroup"><span class="badge">RETREATS</span></div><div class="moregrid"><a class="moreitem" href="{{url_for('retreats')}}">Upcoming Retreats</a><a class="moreitem" href="{{url_for('retreat_build')}}">Design Your Own Retreat</a></div><div class="moregroup"><span class="badge">MEMBERSHIP</span></div><div class="moregrid"><a class="moreitem" href="{{url_for('membership')}}">Membership & Upgrades</a>{% if me.is_admin %}<a class="moreitem" href="{{url_for('admin')}}">Admin</a>{% endif %}<a class="moreitem" href="{{url_for('logout')}}">Log Out</a></div>{% else %}<div class="moregrid"><a class="moreitem" href="{{url_for('join')}}">Join Free</a><a class="moreitem" href="{{url_for('login')}}">Log In</a><a class="moreitem" href="{{url_for('business')}}">Business Network</a><a class="moreitem" href="{{url_for('retreats')}}">Retreats</a><a class="moreitem" href="{{url_for('membership')}}">Membership</a></div>{% endif %}{% endblock %}'''
T['settings.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge">ACCOUNT</span><h1>Settings</h1><p class="muted">One account and one password for the full Seasons Within experience.</p></section><div class="toolgrid"><a class="tool" href="{{url_for('profile_edit')}}"><b>Edit Profile</b></a><a class="tool" href="{{url_for('forgot_password')}}"><b>Change / Reset Password</b></a>{% if cp %}<form class="tool" method="post" action="{{url_for('leave_connections')}}"><b>Leave Conscious Connections</b><br><small>Your main account stays active.</small><br><br><button class="danger">Leave Connections</button></form>{% endif %}<a class="tool" href="{{url_for('logout')}}"><b>Log Out</b></a></div>{% endblock %}'''
T['admin.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero paid"><span class="badge gold">ADMIN</span><h1>Platform Administration</h1><p class="muted">Galaxy Eve and the two configured administrator emails receive complimentary full access.</p></section><article class="card"><h2>Administrator Access</h2><p><b>Galaxy Eve:</b> {{galaxy_email}}</p>{% for e in admin_emails %}<p><b>Admin:</b> {{e}}</p>{% endfor %}</article><h2>Members</h2>{% for u in users %}<article class="card"><h3>{{u.name}} • {{u.email}}</h3><p class="muted">Full: {{'Yes' if u.full_member else 'No'}} • Business: {{'Yes' if u.business_access else 'No'}} • Startup: {{'Yes' if u.startup_access else 'No'}} • Admin: {{'Yes' if u.is_admin else 'No'}}</p><form method="post" action="{{url_for('admin_access',uid=u.id)}}"><div class="chips"><label class="choice"><input type="checkbox" name="full_member" {% if u.full_member %}checked{% endif %}> Full Membership</label><label class="choice"><input type="checkbox" name="business_access" {% if u.business_access %}checked{% endif %}> Business App</label><label class="choice"><input type="checkbox" name="startup_access" {% if u.startup_access %}checked{% endif %}> Startup Package</label><label class="choice"><input type="checkbox" name="is_admin" {% if u.is_admin %}checked{% endif %}> Admin</label></div><br><button>Save Access</button></form></article>{% endfor %}{% endblock %}'''
T['moderation_block.html']=r'''{% extends 'base.html' %}{% block content %}<section class="hero"><span class="badge heart">CONTENT NOT SENT</span><h1>Please Revise This Content</h1><p class="muted">{{reason}}</p><a class="out" href="javascript:history.back()">Go Back</a></section>{% endblock %}'''
app.jinja_loader=DictLoader(T);app.jinja_env.globals.update(media_url=media_url,age_from_birth=age_from_birth,is_video=is_video)
@app.context_processor
def inject_context():return {'me':me(),'galaxy_email':GALAXY_EVE_EMAIL}
# Final safe migrations for persistent databases created by earlier builds.
_c=conn()
for _t,_col,_d in [('journals','updated_at','TEXT'),('business_builder','pricing_ideas',"TEXT DEFAULT ''"),('business_builder','goals_90',"TEXT DEFAULT ''")]:
 try:ensure_column(_c,_t,_col,_d)
 except Exception:pass
_c.commit();_c.close()

@app.route('/brand-logo')
def brand_logo():
 for name in ['seasons-within-logo.png','logo.svg','seasons-within-logo.svg']:
  p=BASE/'static'/name
  if p.exists():return send_from_directory(p.parent,p.name)
 svg='''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"><circle cx="150" cy="150" r="140" fill="#f2e9f8"/><path d="M150 18A132 132 0 0 1 282 150H150Z" fill="#d6b9e5"/><path d="M282 150A132 132 0 0 1 150 282V150Z" fill="#efc4cb"/><path d="M150 282A132 132 0 0 1 18 150H150Z" fill="#ead7ad"/><path d="M18 150A132 132 0 0 1 150 18V150Z" fill="#c9b7df"/><circle cx="150" cy="150" r="58" fill="white"/><text x="150" y="158" text-anchor="middle" font-family="Georgia" font-size="28" fill="#68428a">TSW</text></svg>'''
 return Response(svg,mimetype='image/svg+xml')

@app.route('/uploads/<path:filename>')
def uploads(filename):return send_from_directory(UPLOADS,filename)

@app.route('/')
@app.route('/home')
def home():
 businesses=qall("SELECT * FROM businesses WHERE status='active' ORDER BY CASE WHEN lower(business_name)='galaxy eve' THEN 0 ELSE 1 END, paid_business DESC,featured_order,id")
 retreats_rows=qall('SELECT * FROM retreats ORDER BY id DESC LIMIT 6')
 return render_template('home.html',businesses=businesses,retreats=retreats_rows,sky=sky_now())

@app.route('/join',methods=['GET','POST'])
def join():
 if me():return redirect(url_for('profile'))
 if request.method=='POST':
  bd=request.form.get('birth_date','');age=age_from_birth(bd)
  if not request.form.get('age_confirm') or (age is not None and age<18):
   flash('The Seasons Within member account and Conscious Connections are for adults age 18+.');return render_template('join.html')
  try:
   c=conn();cur=c.execute('INSERT INTO users(name,email,password_hash,birth_date) VALUES(?,?,?,?)',(request.form.get('name','').strip(),request.form.get('email','').strip().lower(),generate_password_hash(request.form.get('password','')),bd));uid=cur.lastrowid;c.commit();c.close();sync_privileged_account(uid);session['uid']=uid;calc_chart(uid);return redirect(url_for('profile'))
  except sqlite3.IntegrityError:flash('That email already has an account. Please log in.')
 return render_template('join.html')

@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  u=q1('SELECT * FROM users WHERE lower(email)=?',(request.form.get('email','').strip().lower(),))
  if u and not u['is_system'] and check_password_hash(u['password_hash'],request.form.get('password','')):
   session['uid']=u['id'];session.permanent=bool(request.form.get('remember'));sync_privileged_account(u['id']);return redirect(request.args.get('next') or url_for('profile'))
  flash('Email or password did not match.')
 return render_template('login.html')

@app.route('/logout')
def logout():session.clear();return redirect(url_for('home'))

@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
 if request.method=='POST':
  email=request.form.get('email','').strip().lower();u=q1('SELECT * FROM users WHERE lower(email)=? AND is_system=0',(email,))
  if u:
   token=secrets.token_urlsafe(32);c=conn();c.execute('INSERT INTO reset_tokens(user_id,token,expires_at) VALUES(?,?,?)',(u['id'],token,int(time.time())+3600));c.commit();c.close();link=(BASE_URL or request.url_root.rstrip('/'))+url_for('reset_password',token=token)
   host=os.environ.get('SMTP_HOST');sender=os.environ.get('SMTP_FROM',os.environ.get('SMTP_USER',''))
   if host and sender:
    try:
     msg=EmailMessage();msg['From']=sender;msg['To']=email;msg['Subject']='Reset your Seasons Within password';msg.set_content('Use this link within one hour to reset your password: '+link);port=int(os.environ.get('SMTP_PORT','587'))
     with smtplib.SMTP(host,port,timeout=20) as s:s.starttls(context=ssl.create_default_context());s.login(os.environ.get('SMTP_USER',''),os.environ.get('SMTP_PASSWORD',''));s.send_message(msg)
    except Exception:pass
   elif me() and me()['is_admin']:flash('Reset link: '+link)
  flash('If that email is registered, password-reset instructions have been prepared.')
 return render_template('forgot_password.html')

@app.route('/reset-password/<token>',methods=['GET','POST'])
def reset_password(token):
 row=q1('SELECT * FROM reset_tokens WHERE token=? AND used=0 AND expires_at>?',(token,int(time.time())))
 if not row:abort(404)
 if request.method=='POST':
  c=conn();c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(request.form.get('password','')),row['user_id']));c.execute('UPDATE reset_tokens SET used=1 WHERE id=?',(row['id'],));c.commit();c.close();flash('Password updated. Please log in.');return redirect(url_for('login'))
 return render_template('reset_password.html')

@app.route('/profile')
@login_required
def profile():
 u=me();cp=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],));return render_template('profile.html',u=u,cp=cp)

@app.route('/profile/edit',methods=['GET','POST'])
@login_required
def profile_edit():
 u=me()
 if request.method=='POST':
  photo=save_file(request.files.get('photo'),f"user{u['id']}",{'.jpg','.jpeg','.png','.webp','.gif'}) or u['photo']
  vals=(request.form.get('name','').strip(),request.form.get('city','').strip(),request.form.get('state','').strip(),request.form.get('country','').strip(),request.form.get('headline','').strip(),request.form.get('bio','').strip(),photo,request.form.get('birth_date',''),request.form.get('birth_time',''),request.form.get('birth_city','').strip(),request.form.get('birth_state','').strip(),request.form.get('birth_country','').strip(),1 if request.form.get('time_known') else 0,u['id'])
  c=conn();c.execute("UPDATE users SET name=?,city=?,state=?,country=?,headline=?,bio=?,photo=?,birth_date=?,birth_time=?,birth_city=?,birth_state=?,birth_country=?,time_known=?,birth_lat=NULL,birth_lon=NULL,birth_timezone='' WHERE id=?",vals);c.commit();c.close();calc_chart(u['id']);flash('Profile saved.');return redirect(url_for('profile'))
 return render_template('profile_edit.html',u=u)

@app.route('/community',methods=['GET','POST'])
@login_required
def community():
 u=me()
 if request.method=='POST':
  body=request.form.get('body','').strip();ok,reason=moderate_text(body)
  if not ok:return render_template('moderation_block.html',reason=reason)
  photo=save_file(request.files.get('photo'),f"community{u['id']}",{'.jpg','.jpeg','.png','.webp','.gif'})
  post_as=request.form.get('post_as','member')
  poster=u
  if post_as=='system' and u['is_admin']:
   poster=q1('SELECT * FROM users WHERE lower(email)=?',(SYSTEM_EMAIL,));post_as='system'
  else:post_as='member'
  c=conn();c.execute('INSERT INTO community_posts(user_id,body,photo,post_as) VALUES(?,?,?,?)',(poster['id'],body,photo,post_as));c.commit();c.close()
  if post_as=='system':notify_all_members('seasons','New post from The Seasons Within',body[:180],exclude=u['id'])
  return redirect(url_for('community'))
 posts=qall("""SELECT p.*,CASE WHEN p.post_as='system' THEN 'The Seasons Within' ELSE u.name END display_name,u.photo user_photo FROM community_posts p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC""")
 sponsors=qall("SELECT * FROM businesses WHERE status='active' AND paid_business=1 AND sponsor_community=1 ORDER BY featured_order,id")
 s=sky_now();return render_template('community.html',posts=posts,sponsors=sponsors,sky=s,daily=daily_reflection(s))

@app.route('/journal',methods=['GET','POST'])
@login_required
def journal():
 u=me()
 if request.method=='POST':
  title=request.form.get('title','');body=request.form.get('body','');vis=request.form.get('visibility','private');c=conn();cur=c.execute('INSERT INTO journals(user_id,title,body,visibility,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)',(u['id'],title,body,vis));jid=cur.lastrowid;c.commit();c.close()
  if vis=='community':share_journal_copy(jid,u);return redirect(url_for('journal'))
 entries=qall('SELECT * FROM journals WHERE user_id=? ORDER BY id DESC',(u['id'],));return render_template('journal.html',entries=entries)

def share_journal_copy(jid,u):
 e=q1('SELECT * FROM journals WHERE id=? AND user_id=?',(jid,u['id']))
 if not e:return
 text=((e['title']+'\n\n') if e['title'] else '')+e['body'];c=conn();c.execute("INSERT INTO community_posts(user_id,body,photo,post_as) VALUES(?,?,?,'member')",(u['id'],text,''));c.commit();c.close()

@app.route('/journal/<int:jid>/edit',methods=['GET','POST'])
@login_required
def journal_edit(jid):
 u=me();e=q1('SELECT * FROM journals WHERE id=? AND user_id=?',(jid,u['id']))
 if not e:abort(404)
 if request.method=='POST':
  vis=request.form.get('visibility','private');c=conn();c.execute('UPDATE journals SET title=?,body=?,visibility=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(request.form.get('title',''),request.form.get('body',''),vis,jid,u['id']));c.commit();c.close()
  if vis=='community':share_journal_copy(jid,u)
  return redirect(url_for('journal'))
 return render_template('journal_edit.html',e=e)

@app.post('/journal/<int:jid>/share')
@login_required
def journal_share(jid):
 u=me();c=conn();c.execute("UPDATE journals SET visibility='community',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",(jid,u['id']));c.commit();c.close();share_journal_copy(jid,u);flash('A copy was shared to Community. Your original journal entry remains stored in your Journal.');return redirect(url_for('journal'))

@app.route('/messages')
@login_required
def messages():
 u=me();rows=qall("""SELECT m.*,CASE WHEN m.sender_id=? THEN rr.name ELSE s.name END other_name,CASE WHEN m.sender_id=? THEN rr.id ELSE s.id END other_id FROM messages m JOIN users s ON s.id=m.sender_id JOIN users rr ON rr.id=m.recipient_id WHERE m.sender_id=? OR m.recipient_id=? ORDER BY m.id DESC""",(u['id'],u['id'],u['id'],u['id']));return render_template('messages.html',rows=rows)

@app.route('/message/<int:recipient_id>',methods=['GET','POST'])
@login_required
def compose_message(recipient_id):
 u=me();person=q1('SELECT * FROM users WHERE id=? AND is_system=0',(recipient_id,))
 if not person or blocked(u['id'],recipient_id):abort(404)
 if request.method=='POST':
  body=request.form.get('body','');ok,reason=moderate_text(body)
  if not ok:return render_template('moderation_block.html',reason=reason)
  kind=request.args.get('kind','member');c=conn();c.execute('INSERT INTO messages(sender_id,recipient_id,message_type,subject,body) VALUES(?,?,?,?,?)',(u['id'],recipient_id,kind,request.form.get('subject',''),body));c.commit();c.close();notify(recipient_id,kind,'New private message',f"{u['name']} sent you a private message.");return redirect(url_for('messages'))
 return render_template('compose.html',person=person)

@app.route('/notifications')
@login_required
def notifications():return render_template('notifications.html',rows=qall('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(me()['id'],)))
@app.route('/connections/join',methods=['GET','POST'])
@login_required
def connections_join():
 u=me()
 if age_from_birth(u['birth_date']) is not None and age_from_birth(u['birth_date'])<18:abort(403)
 if request.method=='POST':
  c=conn();c.execute('INSERT OR IGNORE INTO connection_profiles(user_id,connection_type) VALUES(?,?)',(u['id'],request.form.get('connection_type','Both')));c.execute('UPDATE connection_profiles SET connection_type=? WHERE user_id=?',(request.form.get('connection_type','Both'),u['id']));c.commit();c.close();return redirect(url_for('connections_edit'))
 return render_template('connections_join.html')

@app.route('/connections/edit',methods=['GET','POST'])
@login_required
def connections_edit():
 u=me();cp=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],))
 if not cp:return redirect(url_for('connections_join'))
 if request.method=='POST':
  keys=['connection_type','gender','seeking','location_pref','occupation','children','height','weight','emotional_response','others_emotions','conflict_style','repair_style','apology_style','communication_style','boundaries','social_energy','family_goals','about'];data={k:request.form.get(k,'') for k in keys};data.update(age_min=int(request.form.get('age_min') or 18),age_max=int(request.form.get('age_max') or 99),looking_for=multi('looking_for'),love_languages=multi('love_languages'),lifestyle=multi('lifestyle'),activities=multi('activities'),values_text=multi('values_text'))
  ok,reason=moderate_text(data['about'])
  if not ok:return render_template('moderation_block.html',reason=reason)
  c=conn();sets=','.join(f'{k}=?' for k in data);c.execute(f'UPDATE connection_profiles SET {sets} WHERE user_id=?',tuple(data.values())+(u['id'],));rows=c.execute('SELECT media_type,count(*) n FROM connection_media WHERE user_id=? GROUP BY media_type',(u['id'],)).fetchall();counts={r['media_type']:r['n'] for r in rows};max_img=7 if u['full_member'] or u['is_admin'] else 1;max_vid=2 if u['full_member'] or u['is_admin'] else 0
  for fs in request.files.getlist('media_files'):
   ext=Path(secure_filename(fs.filename)).suffix.lower();typ='video' if ext in {'.mp4','.mov','.m4v','.webm'} else 'image'
   if typ=='image' and counts.get('image',0)<max_img:
    f=save_file(fs,f"conn{u['id']}");c.execute('INSERT INTO connection_media(user_id,filename,media_type) VALUES(?,?,?)',(u['id'],f,'image'));counts['image']=counts.get('image',0)+1
   elif typ=='video' and counts.get('video',0)<max_vid:
    f=save_file(fs,f"conn{u['id']}");c.execute('INSERT INTO connection_media(user_id,filename,media_type) VALUES(?,?,?)',(u['id'],f,'video'));counts['video']=counts.get('video',0)+1
  c.commit();c.close();return redirect(url_for('connections'))
 return render_template('connections_edit.html',cp=cp,emotional_fields=EMOTIONAL_FIELDS)

@app.route('/connections',methods=['GET','POST'])
@login_required
def connections():
 u=me();cp=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],))
 if not cp:return redirect(url_for('connections_join'))
 is_host=bool(u['is_admin'] or u['email'].lower()==GALAXY_EVE_EMAIL)
 if request.method=='POST' and is_host:
  body=request.form.get('body','');ok,reason=moderate_text(body)
  if not ok:return render_template('moderation_block.html',reason=reason)
  fs=request.files.get('media');filename=save_file(fs,f"host{u['id']}") if fs else '';typ='video' if is_video(filename) else ('image' if filename else '');c=conn();c.execute('INSERT INTO connection_posts(user_id,body,media,media_type) VALUES(?,?,?,?)',(u['id'],body,filename,typ));c.commit();c.close();return redirect(url_for('connections'))
 host_posts=qall('SELECT p.*,u.name FROM connection_posts p JOIN users u ON u.id=p.user_id WHERE lower(u.email)=? OR u.is_admin=1 ORDER BY p.id DESC',(GALAXY_EVE_EMAIL,))
 raw=qall('SELECT u.*,cp.connection_type FROM users u JOIN connection_profiles cp ON cp.user_id=u.id WHERE u.id<>? AND u.is_system=0 AND NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=?)) ORDER BY u.id DESC',(u['id'],u['id'],u['id']))
 people=[]
 for p in raw:
  othercp=q1('SELECT * FROM connection_profiles WHERE user_id=?',(p['id'],));d=dict(p);d['age']=age_from_birth(p['birth_date']);d['score']=compatibility(u,p,cp,othercp)['overall'];people.append(d)
 businesses=qall("SELECT * FROM businesses WHERE status='active' AND paid_business=1 AND approved_connections=1 ORDER BY featured_order,id")
 return render_template('connections.html',people=people,host_posts=host_posts,is_host=is_host,connection_businesses=businesses)

@app.route('/connections/profile/<int:uid>')
@login_required
def connection_profile(uid):
 u=me();ca=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],));person=q1('SELECT * FROM users WHERE id=? AND is_system=0',(uid,));cb=q1('SELECT * FROM connection_profiles WHERE user_id=?',(uid,))
 if not ca:return redirect(url_for('connections_join'))
 if not person or not cb or blocked(u['id'],uid):abort(404)
 media=qall('SELECT * FROM connection_media WHERE user_id=? ORDER BY id',(uid,));return render_template('connection_profile.html',person=person,cp=cb,media=media,person_age=age_from_birth(person['birth_date']),report=compatibility(u,person,ca,cb))

@app.route('/connections/compatibility/<int:uid>')
@login_required
def compatibility_view(uid):
 u=me();ca=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],));person=q1('SELECT * FROM users WHERE id=? AND is_system=0',(uid,));cb=q1('SELECT * FROM connection_profiles WHERE user_id=?',(uid,))
 if not ca:return redirect(url_for('connections_join'))
 if not person or not cb or blocked(u['id'],uid):abort(404)
 return render_template('compatibility.html',person=person,report=compatibility(u,person,ca,cb))

@app.route('/connections/birth-chart/<int:uid>')
@login_required
def birth_chart_view(uid):
 u=me()
 if not (u['full_member'] or u['is_admin']):return redirect(url_for('membership'))
 person=q1('SELECT * FROM users WHERE id=? AND is_system=0',(uid,));ca=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],));cb=q1('SELECT * FROM connection_profiles WHERE user_id=?',(uid,))
 if not person or not ca or not cb or blocked(u['id'],uid):abort(404)
 return render_template('birth_chart.html',person=person,report=compatibility(u,person,ca,cb),planets=['sun','moon','rising','mercury','venus','mars','jupiter','saturn'])

@app.route('/connections/ideas/<int:uid>')
@login_required
def connection_ideas(uid):
 u=me();person=q1('SELECT * FROM users WHERE id=?',(uid,));ca=q1('SELECT * FROM connection_profiles WHERE user_id=?',(u['id'],));cb=q1('SELECT * FROM connection_profiles WHERE user_id=?',(uid,))
 if not person or not ca or not cb:abort(404)
 return render_template('connection_ideas.html',person=person,report=compatibility(u,person,ca,cb))

@app.route('/connections/video/request/<int:uid>',methods=['GET','POST'])
@login_required
def video_request(uid):
 u=me();person=q1('SELECT * FROM users WHERE id=? AND is_system=0',(uid,))
 if not person:abort(404)
 if not (u['full_member'] or u['is_admin']):return redirect(url_for('membership'))
 if request.method=='POST':
  c=conn();cur=c.execute("INSERT INTO video_sessions(requester_id,recipient_id,status,seconds_available) VALUES(?,?, 'requested',300)",(u['id'],uid));sid=cur.lastrowid;c.commit();c.close();notify(uid,'video','Video connection request',f"{u['name']} requested a private 5-minute video connection.");flash('Video request sent. The recipient must accept before a live call.');return redirect(url_for('video_room',sid=sid))
 return render_template('video_request.html',person=person)

@app.route('/connections/video/<int:sid>')
@login_required
def video_room(sid):
 u=me();row=q1('SELECT * FROM video_sessions WHERE id=?',(sid,))
 if not row or u['id'] not in (row['requester_id'],row['recipient_id']):abort(403)
 other=row['recipient_id'] if u['id']==row['requester_id'] else row['requester_id'];person=q1('SELECT * FROM users WHERE id=?',(other,));return render_template('video.html',person=person,session_row=row)

@app.post('/connections/block/<int:uid>')
@login_required
def block_member(uid):
 u=me();c=conn();c.execute('INSERT OR IGNORE INTO blocks(blocker_id,blocked_id) VALUES(?,?)',(u['id'],uid));c.commit();c.close();flash('Member blocked.');return redirect(url_for('connections'))

@app.route('/connections/report/<int:uid>',methods=['GET','POST'])
@login_required
def report_member(uid):
 person=q1('SELECT * FROM users WHERE id=?',(uid,))
 if not person:abort(404)
 if request.method=='POST':
  c=conn();c.execute('INSERT INTO reports(reporter_id,reported_id,reason,details) VALUES(?,?,?,?)',(me()['id'],uid,request.form.get('reason','Other'),request.form.get('details','')));c.commit();c.close();flash('Report received.');return redirect(url_for('connections'))
 return render_template('report.html',person=person)

@app.route('/business')
def business():
 q=request.args.get('q','').strip();cat=request.args.get('category','').strip();businesses=qall("""SELECT * FROM businesses WHERE status='active' AND (?='' OR business_name LIKE ? OR category LIKE ? OR description LIKE ?) AND (?='' OR category LIKE ?) ORDER BY CASE WHEN lower(business_name)='galaxy eve' THEN 0 ELSE 1 END,paid_business DESC,featured_order,id""",(q,f'%{q}%',f'%{q}%',f'%{q}%',cat,f'%{cat}%'));return render_template('business.html',businesses=businesses,q=q,category=cat)

@app.route('/business/setup',methods=['GET','POST'])
@login_required
def business_setup():
 u=me();b=q1('SELECT * FROM businesses WHERE owner_id=?',(u['id'],))
 if request.method=='POST':
  logo=save_file(request.files.get('logo'),f"biz{u['id']}logo",{'.jpg','.jpeg','.png','.webp','.gif'}) or (b['logo'] if b else '');hero=save_file(request.files.get('hero_image'),f"biz{u['id']}hero",{'.jpg','.jpeg','.png','.webp','.gif'}) or (b['hero_image'] if b else '');video=save_file(request.files.get('featured_video'),f"biz{u['id']}video",{'.mp4','.mov','.m4v','.webm'}) or (b['featured_video'] if b else '')
  fields=['business_name','creator_title','tagline','description','category','city','state','website'];vals=[request.form.get(k,'') for k in fields]+[logo,hero,video]+[request.form.get(k,'') for k in ['instagram','tiktok','youtube','facebook','booking_url','modules']]+[1 if request.form.get('retreat_participation') else 0,1 if request.form.get('sponsor_community') else 0,1 if request.form.get('approved_connections') else 0]
  c=conn()
  if b:c.execute('UPDATE businesses SET business_name=?,creator_title=?,tagline=?,description=?,category=?,city=?,state=?,website=?,logo=?,hero_image=?,featured_video=?,instagram=?,tiktok=?,youtube=?,facebook=?,booking_url=?,modules=?,retreat_participation=?,sponsor_community=?,approved_connections=? WHERE owner_id=?',tuple(vals)+(u['id'],))
  else:c.execute('INSERT INTO businesses(business_name,creator_title,tagline,description,category,city,state,website,logo,hero_image,featured_video,instagram,tiktok,youtube,facebook,booking_url,modules,retreat_participation,sponsor_community,approved_connections,owner_id,slug,paid_business) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',tuple(vals)+(u['id'],slugify(request.form.get('business_name','')),1 if u['business_access'] else 0))
  c.commit();c.close();return redirect(url_for('business'))
 return render_template('business_setup.html',b=b)

@app.route('/app/<slug>')
def business_app(slug):
 b=q1("SELECT * FROM businesses WHERE slug=? AND status='active'",(slug,))
 if not b:abort(404)
 classes=qall('SELECT * FROM business_classes WHERE business_id=? AND active=1 ORDER BY class_date,id',(b['id'],));socials=[('Website',b['website']),('Instagram',b['instagram']),('TikTok',b['tiktok']),('YouTube',b['youtube']),('Facebook',b['facebook']),('Book',b['booking_url'])];return render_template('business_app.html',b=b,classes=classes,socials=[x for x in socials if x[1]],modules=[x for x in (b['modules'] or '').split('|') if x])
@app.route('/business/manage',methods=['GET','POST'])
@login_required
def business_manage():
 u=me();b=q1('SELECT * FROM businesses WHERE owner_id=?',(u['id'],))
 if request.method=='POST' and b and (u['business_access'] or u['is_admin']):
  c=conn();c.execute('INSERT INTO business_classes(business_id,title,description,class_format,class_date,class_time,price,meeting_url) VALUES(?,?,?,?,?,?,?,?)',(b['id'],request.form.get('title',''),request.form.get('description',''),request.form.get('class_format','Live'),request.form.get('class_date',''),request.form.get('class_time',''),request.form.get('price',''),request.form.get('meeting_url','')));c.commit();c.close();return redirect(url_for('business_manage'))
 classes=qall('SELECT * FROM business_classes WHERE business_id=? ORDER BY id DESC',(b['id'],)) if b else []
 return render_template('business_manage.html',b=b,classes=classes)

@app.route('/business/builder',methods=['GET','POST'])
def business_builder():
 u=me()
 if not u:return render_template('business_builder.html',row=None,business_types=BUSINESS_TYPES,app_goals=APP_GOALS)
 row=q1('SELECT * FROM business_builder WHERE user_id=?',(u['id'],))
 if request.method=='POST':
  vals=(request.form.get('stage',''),multi('business_types'),multi('app_goals'),request.form.get('strengths',''),request.form.get('target_customer',''),request.form.get('offers',''),request.form.get('business_name',''),multi('marketing_channels'),request.form.get('pricing_ideas',''),request.form.get('goals_90',''),u['id']);c=conn()
  if row:c.execute('UPDATE business_builder SET stage=?,business_types=?,app_goals=?,strengths=?,target_customer=?,offers=?,business_name=?,marketing_channels=?,pricing_ideas=?,goals_90=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?',vals)
  else:c.execute('INSERT INTO business_builder(stage,business_types,app_goals,strengths,target_customer,offers,business_name,marketing_channels,pricing_ideas,goals_90,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',vals)
  c.commit();c.close();flash('Questionnaire saved.');return redirect(url_for('business_builder'))
 return render_template('business_builder.html',row=row,business_types=BUSINESS_TYPES,app_goals=APP_GOALS)

@app.route('/business/plan/generate')
@login_required
def generate_business_plan():
 u=me()
 if not (u['startup_access'] or u['is_admin']):return redirect(url_for('checkout',kind='startup_package'))
 row=q1('SELECT * FROM business_builder WHERE user_id=?',(u['id'],))
 if not row:flash('Complete the Startup/Hobby → Business questionnaire first.');return redirect(url_for('business_builder'))
 mx=q1('SELECT max(version_no) v FROM business_plans WHERE user_id=?',(u['id'],));ver=(mx['v'] or 0)+1;sections=build_plan_sections(row);c=conn();cur=c.execute('INSERT INTO business_plans(user_id,business_name,version_no,sections_json,marketing_text,launch_text) VALUES(?,?,?,?,?,?)',(u['id'],row['business_name'] or 'My Business',ver,json.dumps(sections),marketing_text(row),launch_text(row)));pid=cur.lastrowid;c.commit();c.close();return redirect(url_for('business_plan_view',plan_id=pid))

@app.route('/business/dashboard')
@login_required
def business_dashboard():
 u=me();return render_template('business_dashboard.html',b=q1('SELECT * FROM businesses WHERE owner_id=?',(u['id'],)),builder=q1('SELECT * FROM business_builder WHERE user_id=?',(u['id'],)),latest_plan=q1('SELECT * FROM business_plans WHERE user_id=? ORDER BY version_no DESC,id DESC LIMIT 1',(u['id'],)))

@app.route('/business/plan/<int:plan_id>')
@login_required
def business_plan_view(plan_id):
 p=q1('SELECT * FROM business_plans WHERE id=? AND user_id=?',(plan_id,me()['id']))
 if not p:abort(404)
 return render_template('business_plan.html',plan=p,sections=json.loads(p['sections_json'] or '{}'))

@app.route('/business/plan/<int:plan_id>/edit',methods=['GET','POST'])
@login_required
def business_plan_edit(plan_id):
 u=me();p=q1('SELECT * FROM business_plans WHERE id=? AND user_id=?',(plan_id,u['id']))
 if not p:abort(404)
 sections=json.loads(p['sections_json'] or '{}')
 if request.method=='POST':
  new={}
  for i in range(len(sections)):new[request.form.get(f'title_{i}','Section')]=request.form.get(f'section_{i}','')
  mx=q1('SELECT max(version_no) v FROM business_plans WHERE user_id=?',(u['id'],));ver=(mx['v'] or 0)+1;c=conn();cur=c.execute('INSERT INTO business_plans(user_id,business_name,version_no,sections_json,marketing_text,launch_text) VALUES(?,?,?,?,?,?)',(u['id'],p['business_name'],ver,json.dumps(new),request.form.get('marketing_text',''),request.form.get('launch_text','')));nid=cur.lastrowid;c.commit();c.close();flash(f'Saved as Version {ver}.');return redirect(url_for('business_plan_view',plan_id=nid))
 return render_template('business_plan_edit.html',plan=p,sections=sections)

@app.route('/business/plan/versions')
@login_required
def business_plan_versions():return render_template('business_plan_versions.html',plans=qall('SELECT * FROM business_plans WHERE user_id=? ORDER BY version_no DESC,id DESC',(me()['id'],)))

@app.route('/business/plan/<int:plan_id>/pdf')
@login_required
def business_plan_pdf(plan_id):
 p=q1('SELECT * FROM business_plans WHERE id=? AND user_id=?',(plan_id,me()['id']))
 if not p:abort(404)
 sections=json.loads(p['sections_json'] or '{}');pages=list(sections.items())+[('Marketing Strategy',p['marketing_text']),('90-Day Launch Plan',p['launch_text'])];pdf=simple_pdf_bytes(p['business_name'],pages[:15]);name=slugify(p['business_name'])+'-business-plan-v'+str(p['version_no'])+'.pdf';path=PDFS/name;path.write_bytes(pdf);return send_file(path,as_attachment=True,download_name=name,mimetype='application/pdf')

@app.route('/business/plan/<int:plan_id>/send',methods=['GET','POST'])
@login_required
def business_plan_send(plan_id):
 p=q1('SELECT * FROM business_plans WHERE id=? AND user_id=?',(plan_id,me()['id']))
 if not p:abort(404)
 if request.method=='POST':
  host=os.environ.get('SMTP_HOST');user=os.environ.get('SMTP_USER');pwd=os.environ.get('SMTP_PASSWORD');sender=os.environ.get('SMTP_FROM',user or '')
  if not host or not sender:flash('Email is not configured yet. Download the PDF and use your normal email/share tools.');return redirect(url_for('business_plan_send',plan_id=plan_id))
  sections=json.loads(p['sections_json'] or '{}');pdf=simple_pdf_bytes(p['business_name'],list(sections.items())+[('Marketing Strategy',p['marketing_text']),('90-Day Launch Plan',p['launch_text'])]);msg=EmailMessage();msg['From']=sender;msg['To']=request.form.get('email','');msg['Subject']=p['business_name']+' Business Plan';msg.set_content(request.form.get('message','Attached is the Business Plan.'));msg.add_attachment(pdf,maintype='application',subtype='pdf',filename=slugify(p['business_name'])+'-business-plan.pdf');port=int(os.environ.get('SMTP_PORT','587'))
  with smtplib.SMTP(host,port,timeout=20) as s:s.starttls(context=ssl.create_default_context());s.login(user,pwd);s.send_message(msg)
  flash('Business Plan PDF emailed.');return redirect(url_for('business_plan_view',plan_id=plan_id))
 return render_template('business_plan_send.html',plan=p)

@app.route('/retreats')
def retreats():
 rows=qall('SELECT * FROM retreats ORDER BY id DESC');businesses=qall("SELECT * FROM businesses WHERE status='active' AND paid_business=1 AND retreat_participation=1 ORDER BY CASE WHEN lower(business_name)='galaxy eve' THEN 0 ELSE 1 END,featured_order,id");return render_template('retreats.html',retreats=rows,businesses=businesses)

@app.route('/retreats/build',methods=['GET','POST'])
@login_required
def retreat_build():
 u=me();connection=request.args.get('connection')=='1'
 if request.method=='POST':
  c=conn();cur=c.execute('INSERT INTO retreats(owner_id,title,season,retreat_type,preferred_dates,guests,budget,lodging_preferences,wellness_interests,connection_retreat) VALUES(?,?,?,?,?,?,?,?,?,?)',(u['id'],request.form.get('title','My Retreat'),request.form.get('season',''),request.form.get('retreat_type',''),request.form.get('preferred_dates',''),int(request.form.get('guests') or 1),request.form.get('budget',''),request.form.get('lodging_preferences',''),request.form.get('wellness_interests',''),1 if request.form.get('connection_retreat') else 0));rid=cur.lastrowid;c.commit();c.close();return redirect(url_for('retreat_detail',rid=rid))
 return render_template('retreat_build.html',connection=connection)

@app.route('/retreats/<int:rid>',methods=['GET','POST'])
def retreat_detail(rid):
 r=q1('SELECT * FROM retreats WHERE id=?',(rid,))
 if not r:abort(404)
 u=me()
 if request.method=='POST' and u:
  body=request.form.get('body','');ok,reason=moderate_text(body)
  if not ok:return render_template('moderation_block.html',reason=reason)
  c=conn();c.execute('INSERT INTO retreat_messages(retreat_id,sender_id,body) VALUES(?,?,?)',(rid,u['id'],body));c.commit();c.close()
 return render_template('retreat_detail.html',r=r,messages=qall('SELECT m.*,u.name FROM retreat_messages m JOIN users u ON u.id=m.sender_id WHERE retreat_id=? ORDER BY m.id',(rid,)))

@app.route('/membership')
def membership():return render_template('membership.html')

@app.route('/more')
def more():return render_template('more.html')

@app.route('/settings')
@login_required
def settings():return render_template('settings.html',cp=q1('SELECT * FROM connection_profiles WHERE user_id=?',(me()['id'],)))

@app.post('/connections/leave')
@login_required
def leave_connections():
 u=me();c=conn();c.execute('DELETE FROM connection_media WHERE user_id=?',(u['id'],));c.execute('DELETE FROM connection_profiles WHERE user_id=?',(u['id'],));c.commit();c.close();flash('You left Conscious Connections. Your main Seasons Within account remains active.');return redirect(url_for('profile'))
@app.route('/checkout/<kind>',methods=['GET','POST'])
@app.route('/checkout/<kind>/<int:target_id>',methods=['GET','POST'])
@login_required
def checkout(kind,target_id=0):
 if kind not in PAY_ITEMS:abort(404)
 u=me();item=PAY_ITEMS[kind];complimentary=bool(u['is_admin'] or role_email(u['email']))
 if complimentary and kind in {'full_membership','business_app','startup_package'}:
  activate_purchase(u['id'],kind,target_id);return render_template('checkout.html',item=item,stripe_ready=False,complimentary=True)
 if request.method=='POST' and stripe_ready():
  c=conn();cur=c.execute('INSERT INTO purchases(user_id,kind,target_id,amount_cents) VALUES(?,?,?,?)',(u['id'],kind,target_id,item['amount']));pid=cur.lastrowid;c.commit();c.close()
  try:
   s=stripe_checkout(kind,u['id'],target_id);c=conn();c.execute('UPDATE purchases SET stripe_session_id=? WHERE id=?',(s.get('id'),pid));c.commit();c.close();return redirect(s['url'])
  except Exception:flash('Secure checkout could not open. Please check the payment configuration.')
 return render_template('checkout.html',item=item,stripe_ready=stripe_ready(),complimentary=False)

@app.route('/payment/success')
def payment_success():return render_template('payment_success.html')

@app.post('/stripe/webhook')
def stripe_webhook():
 payload=request.get_data();sig=request.headers.get('Stripe-Signature','')
 if not verify_stripe(payload,sig):return 'invalid',400
 event=json.loads(payload.decode());typ=event.get('type');obj=event.get('data',{}).get('object',{})
 if typ=='checkout.session.completed':
  md=obj.get('metadata',{});uid=int(md.get('user_id') or 0);kind=md.get('kind');target=int(md.get('target_id') or 0)
  if uid and kind in PAY_ITEMS:
   activate_purchase(uid,kind,target);c=conn();c.execute("UPDATE purchases SET status='paid' WHERE stripe_session_id=?",(obj.get('id'),));c.commit();c.close()
 elif typ=='customer.subscription.deleted':
  md=obj.get('metadata',{});uid=int(md.get('user_id') or 0);kind=md.get('kind');u=q1('SELECT * FROM users WHERE id=?',(uid,)) if uid else None
  if u and not role_email(u['email']) and kind in {'full_membership','business_app'}:
   c=conn()
   if kind=='full_membership':c.execute('UPDATE users SET full_member=0 WHERE id=?',(uid,))
   else:c.execute('UPDATE users SET business_access=0 WHERE id=?',(uid,));c.execute('UPDATE businesses SET paid_business=0 WHERE owner_id=?',(uid,))
   c.commit();c.close()
 return 'ok',200

@app.route('/admin')
@admin_required
def admin():return render_template('admin.html',users=qall('SELECT * FROM users WHERE is_system=0 ORDER BY id DESC'),galaxy_email=GALAXY_EVE_EMAIL,admin_emails=sorted(ADMIN_EMAILS))

@app.post('/admin/access/<int:uid>')
@admin_required
def admin_access(uid):
 target=q1('SELECT * FROM users WHERE id=? AND is_system=0',(uid,))
 if not target:abort(404)
 if role_email(target['email']):
  sync_privileged_account(uid);flash('Configured Galaxy Eve/admin accounts always keep complimentary full access.');return redirect(url_for('admin'))
 c=conn();c.execute('UPDATE users SET full_member=?,business_access=?,startup_access=?,is_admin=? WHERE id=?',(1 if request.form.get('full_member') else 0,1 if request.form.get('business_access') else 0,1 if request.form.get('startup_access') else 0,1 if request.form.get('is_admin') else 0,uid));c.execute('UPDATE businesses SET paid_business=? WHERE owner_id=?',(1 if request.form.get('business_access') else 0,uid));c.commit();c.close();flash('Member access updated.');return redirect(url_for('admin'))

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=False)
