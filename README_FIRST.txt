THE SEASONS WITHIN — COMPLETE COORDINATED BUILD

This build intentionally contains NO mock/demo people or businesses.
Galaxy Eve is created once and featured first as a Creator + Hosted Business App.
Free member and free business profiles save to the database.
Two or more admins are configured through ADMIN_EMAILS.
The current Moon and planetary positions use pyswisseph.
Retreat Constellation includes partner availability, guest/business date coordination,
and a private retreat-location search workflow. The guest-facing interface does not name
an outside accommodation marketplace.

RENDER ENVIRONMENT VARIABLES:
SECRET_KEY = a long random secret
ADMIN_EMAILS = admin1@example.com,admin2@example.com
GALAXY_EVE_EMAIL = Galaxy Eve login email
GALAXY_EVE_INITIAL_PASSWORD = temporary first password

IMPORTANT PERSISTENCE:
Set PERSISTENT_DATA_DIR to a mounted persistent-disk path before real users join.
Otherwise a cloud deployment can replace local database/upload files.

UPLOAD TO GITHUB ROOT:
app.py
requirements.txt
.python-version
README_FIRST.txt

This is a self-contained build: page templates are embedded in app.py, so old template
mockups cannot reappear from templates/. Existing templates/ may remain in GitHub but are
not used by this app.py.
