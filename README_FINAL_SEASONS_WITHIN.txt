THE SEASONS WITHIN — FINAL ONE-FILE PYTHON BUILD

UPLOAD
Replace the root GitHub app.py with the included app.py.
Render start command: gunicorn app:app

CORE RENDER ENVIRONMENT VARIABLES
SECRET_KEY=<long random secret>
PERSISTENT_DATA_DIR=<your Render persistent disk path>
BASE_URL=https://the-seasons-within-v9.onrender.com

COMPLIMENTARY FULL-ACCESS ACCOUNTS
Set these three email variables in Render BEFORE those people create/log into their accounts:
GALAXY_EVE_EMAIL=<Galaxy Eve's real login email>
ADMIN_EMAIL_1=<first administrator email>
ADMIN_EMAIL_2=<second administrator email>

Any account using one of those configured emails is automatically kept at:
- Full $10.99 membership access: complimentary
- $29.99 Hosted Business App access: complimentary
- $79.99 Startup Business package access: complimentary
- Admin access: enabled

Galaxy Eve's Hosted Business App is automatically created when her configured account exists. She can edit her own profile/app and upload her real photos/videos/content.

OFFICIAL THE SEASONS WITHIN COMMUNITY POSTS
Administrators receive an official Community posting box. Posts made through it display as “The Seasons Within,” use the Seasons Within logo, and create notifications for members.

PAYMENTS
For real Stripe Checkout:
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
Webhook endpoint: /stripe/webhook

BUSINESS PLAN EMAIL
SMTP_HOST
SMTP_PORT=587
SMTP_USER
SMTP_PASSWORD
SMTP_FROM

IMPORTANT EXTERNAL-SERVICE LIMITS
- Reliable live camera-to-camera video still requires WebRTC signaling/TURN infrastructure. The app includes the approved video request, access, timer and $5 add-time/payment structure, but does not fake a live video transport service.
- Automated image nudity detection requires an external image-moderation service. The build includes 18+ gating, text moderation, Block and Report controls, and media limits, but does not falsely claim automated visual nudity scanning is active.
- Birth city geocoding/timezone is automatic when geopy/timezonefinder are installed. The astrology engine degrades safely if optional packages are unavailable.

FINAL BUILD INCLUDES
- Mobile-first app navigation
- Desktop: Home / Community / My Profile / Business Network / Retreats / Membership
- Phone: Home / Community / Profile / Business / More
- All active businesses on Home: Galaxy Eve first, paid Hosted Apps next, free listings after
- Seasons Within logo fallback when a business has no logo
- Persistent account/profile data
- Community with current Moon/planet reflection, relaxation and journal prompt
- Member profile picture/name on Community posts
- Private Inbox button under member posts; no public comments
- Official The Seasons Within posts + member notifications
- Private Journal with Private or Share a Copy to Community
- Conscious Connections opt-in: Love & Dating / Friendship / Both
- Free Connections profile: 1 photo and basic compatibility
- $10.99 Full: up to 7 photos + 2 videos, full compatibility and full shared birth-chart access
- Full social/emotional, communication, conflict, repair, emotional rhythm, love language, lifestyle/values and psychology-oriented compatibility
- Sun/Moon/Rising/Mercury/Venus/Mars/Jupiter/Saturn; Rising only when accurate data supports it
- Date/friendship ideas based on both actual profiles
- 5-minute video feature model + $5 add 5 minutes + $5 paid video request/message
- Business Network free listing + $29.99 Hosted App
- Hosted App classes and social links
- $79.99 Startup/Hobby → Business questionnaire
- Editable 10–15 page Business Plan PDF
- Saved Business Plan versions
- Download / Email / device Share PDF
- Marketing Strategy + 90-Day Launch Plan
- Retreat builder and private retreat messages
- Admin access management
