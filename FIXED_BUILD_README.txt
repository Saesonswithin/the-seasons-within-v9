THE SEASONS WITHIN — FIXED ONE-FILE PYTHON BUILD

UPLOAD
Replace the root GitHub app.py with the included app.py.

Render start command:
gunicorn app:app

Required packages:
Flask
gunicorn

Recommended Render environment variables:
SECRET_KEY=<long-random-secret>
PERSISTENT_DATA_DIR=/var/data   (use the mount path of your Render persistent disk)

Optional:
DATABASE_PATH=/var/data/seasons_within.db

Important:
- Existing SQLite data is migrated in place where possible.
- Galaxy Eve is seeded as the authorized featured Hosted Business App from the frozen master contract.
- Hosted Business Apps are FREE; there is no $29.99 hosted-app model.
- Actual live ephemeris, payment processing, live video transport, and production email still require external providers.
