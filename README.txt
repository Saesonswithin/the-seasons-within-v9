THE SEASONS WITHIN — FINAL ONE-FILE PYTHON BUILD

Rename the Python file to app.py, then replace the existing app.py in the ROOT of the GitHub repository.

Render start command:
gunicorn app:app

Recommended Render environment variables:
SECRET_KEY
PERSISTENT_DATA_DIR
BASE_URL

For real Stripe payments:
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
Webhook endpoint: /stripe/webhook

For emailing Business Plan PDFs:
SMTP_HOST
SMTP_PORT=587
SMTP_USER
SMTP_PASSWORD
SMTP_FROM

Included:
- Public marketplace Home
- Persistent accounts
- Community with photo posts + private Inbox replies
- Private Journal
- Notifications
- Opt-in Conscious Connections
- Free + $10.99 Full member profiles
- Social/emotional compatibility
- Shared full birth-chart access + chart comparison with privacy controls
- Full profile media up to 7 photos + 2 videos
- Galaxy Eve host posting area
- 18+ gate and text moderation
- 5-minute video connection model + $5 additional 5 minutes + $5 paid video request/message
- Business Network with free listings and $29.99 Hosted Apps
- $79.99 Startup/Hobby-to-Business package
- Editable 10–15 page Business Plan PDF generation
- Saved Business Plan versions
- PDF download, email and device sharing
- Marketing Strategy + 90-Day Launch Plan
- Retreat builder

External services still required for actual live camera-to-camera video transport, automatic image nudity detection, and real payments unless Stripe is configured.
