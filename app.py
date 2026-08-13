import os
import re
import json
import sqlite3
import hashlib
import secrets

from datetime import datetime, date, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    abort,
)

from werkzeug.utils import secure_filename
from jinja2 import DictLoader


try:
    import swisseph as swe
except Exception:
    swe = None


# ============================================================
# THE SEASONS WITHIN
# ============================================================

BASE = Path(__file__).resolve().parent

DATA = Path(
    os.environ.get(
        "PERSISTENT_DATA_DIR",
        BASE / "data"
    )
)

DATA.mkdir(
    parents=True,
    exist_ok=True
)

DB = Path(
    os.environ.get(
        "DATABASE_PATH",
        DATA / "the_seasons_within.db"
    )
)

UPLOADS = Path(
    os.environ.get(
        "UPLOAD_DIR",
        DATA / "uploads"
    )
)

UPLOADS.mkdir(
    parents=True,
    exist_ok=True
)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-me-in-render"
)


MEMBER_PRICE = "10.99"
BUSINESS_PRICE = "29.99"


GALAXY_EMAIL = os.environ.get(
    "GALAXY_EVE_EMAIL",
    "galaxyeve@theseasonswithin.local"
).strip().lower()


ADMIN_EMAILS = {
    x.strip().lower()
    for x in os.environ.get(
        "ADMIN_EMAILS",
        ""
    ).split(",")
    if x.strip()
}


SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]


DEMO_EMAILS = (
    "avery@example.com",
    "morgan@example.com",
    "nia@example.com",
    "marcus@example.com",
    "jordan@example.com",
    "sage@business.demo",
    "maya@business.demo",
)


DEMO_SLUGS = (
    "rise-flow-yoga",
    "sacred-soul-reiki",
    "sound-harmony",
    "nature-vibes",
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def conn():

    connection = sqlite3.connect(DB)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys=ON"
    )

    return connection


def table_columns(
    connection,
    table
):

    return {
        row[1]
        for row
        in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def ensure_column(
    connection,
    table,
    name,
    definition
):

    if name not in table_columns(
        connection,
        table
    ):

        connection.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {name} {definition}
            """
        )


# ============================================================
# ACCOUNT HELPERS
# ============================================================

def hp(password):

    return hashlib.sha256(
        (
            "tsw::"
            + password
        ).encode()
    ).hexdigest()


def slugify(text):

    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            (
                text
                or ""
            ).lower()
        )
        .strip("-")
        or secrets.token_hex(4)
    )


def me():

    user_id = session.get(
        "uid"
    )

    if not user_id:

        return None


    connection = conn()


    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE id=?
        """,
        (
            user_id,
        )
    ).fetchone()


    connection.close()


    return user


def admin(user):

    return bool(

        user

        and (

            user[
                "is_admin"
            ]

            or

            (
                user[
                    "email"
                ]
                or ""
            ).lower()

            in ADMIN_EMAILS
        )
    )


def login_required(function):

    @wraps(function)
    def wrapped(
        *args,
        **kwargs
    ):

        if not me():

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )


        return function(
            *args,
            **kwargs
        )


    return wrapped


def admin_required(function):

    @wraps(function)
    def wrapped(
        *args,
        **kwargs
    ):

        user = me()


        if not user:

            return redirect(
                url_for(
                    "login"
                )
            )


        if not admin(
            user
        ):

            return (
                "Admin access required",
                403
            )


        return function(
            *args,
            **kwargs
        )


    return wrapped


# ============================================================
# MEDIA
# ============================================================

def media_url(path):

    if not path:

        return ""


    return url_for(
        "uploads",
        filename=path
    )


def save_file(
    file_storage,
    prefix
):

    if (
        not file_storage
        or not file_storage.filename
    ):

        return ""


    extension = Path(
        secure_filename(
            file_storage.filename
        )
    ).suffix.lower()


    allowed = {

        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".mp4",
        ".mov",
        ".m4v",
    }


    if extension not in allowed:

        return ""


    filename = (

        f"{prefix}-"

        f"{secrets.token_hex(8)}"

        f"{extension}"
    )


    file_storage.save(
        UPLOADS / filename
    )


    return filename


def is_video(path):

    if not path:

        return False


    return (

        Path(path)
        .suffix
        .lower()

        in {
            ".mp4",
            ".mov",
            ".m4v",
        }
    )


def age_from_birth_date(value):

    if not value:

        return None


    try:

        born = datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

        today = date.today()

        return (
            today.year
            - born.year
            - (
                (today.month, today.day)
                < (born.month, born.day)
            )
        )

    except Exception:

        return None


# ============================================================
# CURRENT SKY
# ============================================================

def season_now():

    month = date.today().month


    if month in (
        12,
        1,
        2,
    ):

        return "Winter"


    if month in (
        3,
        4,
        5,
    ):

        return "Spring"


    if month in (
        6,
        7,
        8,
    ):

        return "Summer"


    return "Autumn"


def zdeg(degree):

    degree = (
        float(degree)
        % 360
    )


    index = int(
        degree // 30
    )


    return (

        SIGNS[
            index
        ],

        round(
            degree
            - index * 30,
            2
        ),
    )


def moon_symbol(
    phase
):

    return {

        "New Moon":
            "🌑",

        "Waxing Crescent":
            "🌒",

        "First Quarter":
            "🌓",

        "Waxing Gibbous":
            "🌔",

        "Full Moon":
            "🌕",

        "Waning Gibbous":
            "🌖",

        "Last Quarter":
            "🌗",

        "Waning Crescent":
            "🌘",

    }.get(
        phase,
        "☾"
    )


def current_sky():

    sky = {

        "moon_sign":
            "",

        "moon_phase":
            "",

        "moon_degree":
            None,

        "moon_symbol":
            "☾",

        "positions":
            {},

        "season":
            season_now(),
    }


    if not swe:

        return sky


    try:

        now = datetime.now(
            timezone.utc
        )


        julian_day = swe.julday(

            now.year,

            now.month,

            now.day,

            (
                now.hour

                + now.minute / 60

                + now.second / 3600
            ),
        )


        bodies = {

            "Sun":
                swe.SUN,

            "Moon":
                swe.MOON,

            "Mercury":
                swe.MERCURY,

            "Venus":
                swe.VENUS,

            "Mars":
                swe.MARS,

            "Jupiter":
                swe.JUPITER,

            "Saturn":
                swe.SATURN,

            "Uranus":
                swe.URANUS,

            "Neptune":
                swe.NEPTUNE,

            "Pluto":
                swe.PLUTO,
        }


        degrees = {}


        for (
            body_name,
            body_id
        ) in bodies.items():


            position = swe.calc_ut(
                julian_day,
                body_id
            )[0][0]


            sign, degree = zdeg(
                position
            )


            degrees[
                body_name
            ] = position


            sky[
                "positions"
            ][
                body_name
            ] = {

                "sign":
                    sign,

                "degree":
                    degree,
            }


        sky[
            "moon_sign"
        ] = sky[
            "positions"
        ][
            "Moon"
        ][
            "sign"
        ]


        sky[
            "moon_degree"
        ] = sky[
            "positions"
        ][
            "Moon"
        ][
            "degree"
        ]


        angle = (

            degrees[
                "Moon"
            ]

            -

            degrees[
                "Sun"
            ]

        ) % 360


        phases = [

            (
                22.5,
                "New Moon"
            ),

            (
                67.5,
                "Waxing Crescent"
            ),

            (
                112.5,
                "First Quarter"
            ),

            (
                157.5,
                "Waxing Gibbous"
            ),

            (
                202.5,
                "Full Moon"
            ),

            (
                247.5,
                "Waning Gibbous"
            ),

            (
                292.5,
                "Last Quarter"
            ),

            (
                337.5,
                "Waning Crescent"
            ),

            (
                361,
                "New Moon"
            ),
        ]


        for (
            cutoff,
            phase_name
        ) in phases:


            if angle < cutoff:

                sky[
                    "moon_phase"
                ] = phase_name

                break


        sky[
            "moon_symbol"
        ] = moon_symbol(
            sky[
                "moon_phase"
            ]
        )


    except Exception:

        pass


    return sky


# ============================================================
# NATAL CHART
# ============================================================

def chart_for(user):

    if (
        not swe
        or not user
        or not user[
            "birth_date"
        ]
    ):

        return {}


    try:

        birth_date = datetime.strptime(
            user[
                "birth_date"
            ],
            "%Y-%m-%d"
        )


        hour = 12.0


        if (
            user[
                "time_known"
            ]
            and user[
                "birth_time"
            ]
        ):

            hours, minutes = [

                int(value)

                for value

                in user[
                    "birth_time"
                ].split(":")[:2]
            ]


            hour = (
                hours
                + minutes / 60
            )


        julian_day = swe.julday(

            birth_date.year,

            birth_date.month,

            birth_date.day,

            hour,
        )


        bodies = {

            "Sun":
                swe.SUN,

            "Moon":
                swe.MOON,

            "Mercury":
                swe.MERCURY,

            "Venus":
                swe.VENUS,

            "Mars":
                swe.MARS,

            "Jupiter":
                swe.JUPITER,

            "Saturn":
                swe.SATURN,

            "Uranus":
                swe.URANUS,

            "Neptune":
                swe.NEPTUNE,

            "Pluto":
                swe.PLUTO,
        }


        result = {}


        for (
            name,
            body_id
        ) in bodies.items():


            position = swe.calc_ut(
                julian_day,
                body_id
            )[0][0]


            sign, degree = zdeg(
                position
            )


            result[
                name
            ] = {

                "sign":
                    sign,

                "degree":
                    degree,

                "absolute":
                    round(
                        position,
                        4
                    ),
            }


        return result


    except Exception:

        return {}


# ============================================================
# PRIVATE JOURNAL
# ============================================================

def journal_reflection(
    user
):

    sky = current_sky()


    natal_reference = (

        user[
            "moon"
        ]

        or

        user[
            "sun"
        ]

        or

        "your natal chart"

    ) if user else "your natal chart"


    return {

        "sky":
            sky,

        "headline":

            (
                f"Reflect through "
                f"{natal_reference} "
                f"and the current "
                f"{sky['moon_sign'] or 'Moon'}."
            ),

        "prompt":

            (
                "What are you noticing within yourself today, "
                "and what deserves your conscious attention?"
            ),
    }


# ============================================================
# CONSCIOUS COORDINATION
# ============================================================

def coord(
    person_a,
    person_b,
    mode="friendship"
):

    score = 50


    weights = {

        "dating": {

            "sun": 4,
            "moon": 10,
            "mercury": 6,
            "venus": 10,
            "mars": 8,
        },


        "friendship": {

            "sun": 7,
            "moon": 8,
            "mercury": 7,
            "venus": 4,
            "mars": 4,
        },


        "business": {

            "sun": 6,
            "moon": 3,
            "mercury": 10,
            "venus": 3,
            "mars": 7,
        },
    }


    selected = weights.get(
        mode,
        weights[
            "friendship"
        ]
    )


    for (
        placement,
        weight
    ) in selected.items():


        if (
            person_a[
                placement
            ]
            and
            person_b[
                placement
            ]
        ):


            if (
                person_a[
                    placement
                ]
                ==
                person_b[
                    placement
                ]
            ):

                score += weight


            else:

                difference = abs(

                    SIGNS.index(
                        person_a[
                            placement
                        ]
                    )

                    -

                    SIGNS.index(
                        person_b[
                            placement
                        ]
                    )
                )


                if difference in (
                    2,
                    4,
                    8,
                    10,
                ):

                    score += max(
                        2,
                        weight // 2
                    )


    return max(
        40,
        min(
            95,
            score
        )
    )


def date_idea(
    person_a,
    person_b,
    mode="dating"
):

    if mode == "friendship":

        return (
            "Try a wellness class, café conversation, "
            "nature walk, creator meetup or shared community experience."
        )


    combination = {

        person_a[
            "venus"
        ],

        person_b[
            "venus"
        ],

        person_a[
            "moon"
        ],

        person_b[
            "moon"
        ],
    }


    if (
        "Pisces"
        in combination
        or
        "Cancer"
        in combination
    ):

        return (
            "Consider a waterfront walk, relaxing wellness experience, "
            "sound session or intimate conversation setting."
        )


    if (
        "Leo"
        in combination
        or
        "Aries"
        in combination
    ):

        return (
            "Consider live music, a creative class, "
            "movement experience or energetic local event."
        )


    if (
        "Libra"
        in combination
        or
        "Taurus"
        in combination
    ):

        return (
            "Consider an art experience, beautiful dinner setting, "
            "massage or spa experience, or garden outing."
        )


    if (
        "Gemini"
        in combination
        or
        "Aquarius"
        in combination
    ):

        return (
            "Consider a bookstore, coffee conversation, "
            "unique workshop, community event or creative experience."
        )


    return (
        "Choose an experience that supports conversation, "
        "shared interests and the way both of you naturally connect."
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    connection = conn()


    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            city TEXT DEFAULT '',

            bio TEXT DEFAULT '',

            photo TEXT DEFAULT '',

            profile_headline TEXT DEFAULT '',

            birth_date TEXT DEFAULT '',

            birth_time TEXT DEFAULT '',

            time_known INTEGER DEFAULT 0,

            sun TEXT DEFAULT '',

            moon TEXT DEFAULT '',

            rising TEXT DEFAULT '',

            mercury TEXT DEFAULT '',

            venus TEXT DEFAULT '',

            mars TEXT DEFAULT '',

            jupiter TEXT DEFAULT '',

            saturn TEXT DEFAULT '',

            uranus TEXT DEFAULT '',

            neptune TEXT DEFAULT '',

            pluto TEXT DEFAULT '',

            is_admin INTEGER DEFAULT 0,

            is_creator INTEGER DEFAULT 0,

            creator_access INTEGER DEFAULT 0,

            business_access INTEGER DEFAULT 0,

            membership_access INTEGER DEFAULT 0,

            dating_active INTEGER DEFAULT 0,

            connection_intentions TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS businesses(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_id INTEGER UNIQUE NOT NULL
            REFERENCES users(id)
            ON DELETE CASCADE,

            slug TEXT UNIQUE NOT NULL,

            business_name TEXT NOT NULL,

            creator_title TEXT DEFAULT '',

            tagline TEXT DEFAULT '',

            description TEXT DEFAULT '',

            category TEXT DEFAULT '',

            city TEXT DEFAULT '',

            website TEXT DEFAULT '',

            contact_email TEXT DEFAULT '',

            phone TEXT DEFAULT '',

            logo TEXT DEFAULT '',

            instagram TEXT DEFAULT '',

            tiktok TEXT DEFAULT '',

            youtube TEXT DEFAULT '',

            booking_url TEXT DEFAULT '',

            paid_business INTEGER DEFAULT 0,

            media_kit_enabled INTEGER DEFAULT 0,

            followers TEXT DEFAULT '',

            likes TEXT DEFAULT '',

            views TEXT DEFAULT '',

            audience_info TEXT DEFAULT '',

            content_categories TEXT DEFAULT '',

            collaboration_interests TEXT DEFAULT '',

            retreat_participation INTEGER DEFAULT 0,

            featured_order INTEGER DEFAULT 999,

            status TEXT DEFAULT 'active'
        );


        CREATE TABLE IF NOT EXISTS posts(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS connection_posts(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            media_path TEXT DEFAULT '',

            media_type TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS journals(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            sky_json TEXT DEFAULT '{}',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS messages(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            recipient_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            message_type TEXT DEFAULT 'people',

            subject TEXT DEFAULT '',

            body TEXT NOT NULL,

            read_at TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS notifications(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            notification_type TEXT DEFAULT 'general',

            title TEXT NOT NULL,

            body TEXT NOT NULL,

            link TEXT DEFAULT '',

            read_at TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS retreats(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            title TEXT NOT NULL,

            season TEXT DEFAULT '',

            retreat_type TEXT DEFAULT '',

            area TEXT DEFAULT '',

            preferred_dates TEXT DEFAULT '',

            guests INTEGER DEFAULT 1,

            budget TEXT DEFAULT '',

            lodging_preferences TEXT DEFAULT '',

            wellness_interests TEXT DEFAULT '',

            location_status TEXT DEFAULT 'Searching',

            connection_retreat INTEGER DEFAULT 0,

            status TEXT DEFAULT 'planning',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS retreat_partners(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            retreat_id INTEGER
            REFERENCES retreats(id)
            ON DELETE CASCADE,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            availability_status TEXT DEFAULT 'requested',

            UNIQUE(
                retreat_id,
                business_id
            )
        );


        CREATE TABLE IF NOT EXISTS retreat_messages(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            retreat_id INTEGER
            REFERENCES retreats(id)
            ON DELETE CASCADE,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS business_content(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            content_type TEXT DEFAULT 'post',

            caption TEXT DEFAULT '',

            media_path TEXT DEFAULT '',

            media_type TEXT DEFAULT '',

            active INTEGER DEFAULT 1,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS business_items(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            item_type TEXT DEFAULT 'service',

            title TEXT NOT NULL,

            description TEXT DEFAULT '',

            price TEXT DEFAULT '',

            action_url TEXT DEFAULT '',

            active INTEGER DEFAULT 1,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS collaboration_requests(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE SET NULL,

            request_type TEXT DEFAULT 'Collaboration',

            message TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


    # --------------------------------------------------------
    # SAFE MIGRATIONS
    # --------------------------------------------------------

    user_migrations = {

        "community_enabled":
            "INTEGER DEFAULT 1",

        "conscious_connections_enabled":
            "INTEGER DEFAULT 0",

        "connection_type":
            "TEXT DEFAULT ''",

        "business_interest":
            "INTEGER DEFAULT 0",

        "last_moon_sign":
            "TEXT DEFAULT ''",

        "cc_gender":
            "TEXT DEFAULT ''",

        "cc_seeking":
            "TEXT DEFAULT ''",

        "cc_looking_for":
            "TEXT DEFAULT ''",

        "cc_children":
            "TEXT DEFAULT ''",

        "cc_lifestyle":
            "TEXT DEFAULT ''",

        "cc_activities":
            "TEXT DEFAULT ''",

        "cc_values":
            "TEXT DEFAULT ''",

        "cc_style":
            "TEXT DEFAULT ''",

        "cc_first_connection":
            "TEXT DEFAULT ''",

        "cc_retreat_interest":
            "TEXT DEFAULT ''",

        "cc_occupation":
            "TEXT DEFAULT ''",

        "cc_height":
            "TEXT DEFAULT ''",

        "cc_weight":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in user_migrations.items():

        ensure_column(
            connection,
            "users",
            column_name,
            definition
        )


    business_migrations = {

        "hero_image":
            "TEXT DEFAULT ''",

        "featured_video":
            "TEXT DEFAULT ''",

        "previous_collaborations":
            "TEXT DEFAULT ''",

        "engagement_rate":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in business_migrations.items():

        ensure_column(
            connection,
            "businesses",
            column_name,
            definition
        )


    post_migrations = {

        "media_path":
            "TEXT DEFAULT ''",

        "media_type":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in post_migrations.items():

        ensure_column(
            connection,
            "posts",
            column_name,
            definition
        )


    ensure_column(
        connection,
        "retreats",
        "connection_retreat",
        "INTEGER DEFAULT 0"
    )


    # --------------------------------------------------------
    # REMOVE OLD MOCK MEMBERS / BUSINESSES
    # --------------------------------------------------------

    for email in DEMO_EMAILS:

        row = connection.execute(
            """
            SELECT id
            FROM users
            WHERE lower(email)=?
            """,
            (
                email,
            )
        ).fetchone()


        if row:

            connection.execute(
                """
                DELETE FROM users
                WHERE id=?
                """,
                (
                    row[
                        "id"
                    ],
                )
            )


    placeholders = ",".join(
        "?"
        for _
        in DEMO_SLUGS
    )


    connection.execute(
        f"""
        DELETE FROM businesses
        WHERE slug IN ({placeholders})
        """,
        DEMO_SLUGS
    )


    # --------------------------------------------------------
    # GALAXY EVE
    # --------------------------------------------------------

    galaxy_user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE lower(email)=?
        """,
        (
            GALAXY_EMAIL,
        )
    ).fetchone()


    if not galaxy_user:

        cursor = connection.execute(
            """
            INSERT INTO users(

                name,

                email,

                password,

                bio,

                profile_headline,

                is_creator,

                creator_access,

                business_access,

                membership_access,

                community_enabled,

                conscious_connections_enabled,

                connection_type,

                business_interest
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,

                1,
                1,
                1,
                1,
                1,
                1,

                'Both',

                1
            )
            """,
            (

                "Galaxy Eve",

                GALAXY_EMAIL,

                hp(
                    os.environ.get(
                        "GALAXY_EVE_INITIAL_PASSWORD",
                        "ChangeMeGalaxyEve!"
                    )
                ),

                (
                    "Wellness creator documenting connection, "
                    "self-discovery, experiences and Conscious Coordination."
                ),

                (
                    "Conscious Coordinator • "
                    "Content Creator"
                ),
            )
        )


        galaxy_id = (
            cursor.lastrowid
        )


    else:

        galaxy_id = galaxy_user[
            "id"
        ]


        connection.execute(
            """
            UPDATE users

            SET

                is_creator=1,

                creator_access=1,

                business_access=1,

                membership_access=1,

                community_enabled=1,

                conscious_connections_enabled=1,

                connection_type=
                    CASE
                    WHEN connection_type=''
                    THEN 'Both'
                    ELSE connection_type
                    END,

                business_interest=1

            WHERE id=?
            """,
            (
                galaxy_id,
            )
        )


    galaxy_business = connection.execute(
        """
        SELECT *
        FROM businesses
        WHERE owner_id=?
        """,
        (
            galaxy_id,
        )
    ).fetchone()


    if not galaxy_business:

        connection.execute(
            """
            INSERT INTO businesses(

                owner_id,

                slug,

                business_name,

                creator_title,

                tagline,

                description,

                category,

                contact_email,

                paid_business,

                media_kit_enabled,

                retreat_participation,

                featured_order,

                status
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,

                1,
                1,
                1,
                1,

                'active'
            )
            """,
            (

                galaxy_id,

                "galaxy-eve",

                "Galaxy Eve",

                (
                    "Conscious Coordinator • "
                    "Content Creator"
                ),

                (
                    "Content • Collaborations • "
                    "Creator Experiences"
                ),

                (
                    "Content, collaborations, creator experiences, "
                    "meetups, retreats and Conscious Coordination."
                ),

                "Creator",

                GALAXY_EMAIL,
            )
        )


    else:

        connection.execute(
            """
            UPDATE businesses

            SET

                paid_business=1,

                media_kit_enabled=1,

                retreat_participation=1,

                featured_order=1,

                status='active'

            WHERE owner_id=?
            """,
            (
                galaxy_id,
            )
        )


    for email in ADMIN_EMAILS:

        connection.execute(
            """
            UPDATE users

            SET is_admin=1

            WHERE lower(email)=?
            """,
            (
                email,
            )
        )


    connection.commit()

    connection.close()


# ============================================================
# TEMPLATES
# ============================================================

T = {}


# ============================================================
# GLOBAL APP SHELL
# ============================================================

T["base.html"] = r'''
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
The Seasons Within
</title>

<style>

:root {

    --plum:#34204f;

    --purple:#8f63ba;

    --purple2:#a979c8;

    --lav:#f1e7f8;

    --blush:#fff1ef;

    --line:#eadff1;

    --muted:#786a85;

    --shadow:
        0 14px 36px
        rgba(72,42,96,.08);
}


* {
    box-sizing:border-box;
}


body {

    margin:0;

    background:
        linear-gradient(
            180deg,
            #fcf9fd,
            #fffaf8 55%,
            #faf6fc
        );

    color:
        var(--plum);

    font-family:
        Arial,
        Helvetica,
        sans-serif;
}


a {

    text-decoration:none;

    color:inherit;
}


img {

    max-width:100%;
}


.top {

    position:sticky;

    top:0;

    z-index:50;

    background:
        rgba(
            255,
            255,
            255,
            .96
        );

    backdrop-filter:
        blur(16px);

    border-bottom:
        1px solid
        var(--line);
}


.topin {

    width:
        min(
            1220px,
            94vw
        );

    min-height:
        82px;

    margin:auto;

    display:grid;

    grid-template-columns:
        auto 1fr auto;

    align-items:center;

    gap:24px;
}


.brand {

    display:flex;

    align-items:center;

    gap:10px;
}


.brand img {

    width:52px;

    height:52px;

    object-fit:contain;
}


.brandcopy {

    display:flex;

    flex-direction:column;
}


.brandcopy strong {

    font:
        700 20px
        Georgia;
}


.brandcopy small {

    font-size:10px;

    text-transform:uppercase;

    letter-spacing:1.2px;

    color:var(--muted);

    margin-top:4px;
}


.nav {

    display:flex;

    justify-content:center;

    gap:6px;

    flex-wrap:wrap;
}


.nav a {

    padding:
        10px 12px;

    border-radius:
        999px;

    font-size:14px;

    font-weight:700;

    color:#62546d;
}


.nav a:hover,

.nav a.active {

    background:
        var(--lav);

    color:#68428a;
}


.account {

    display:flex;

    align-items:center;

    gap:10px;
}


.acct {

    display:flex;

    align-items:center;

    gap:7px;

    padding:
        5px 9px;

    border:
        1px solid
        var(--line);

    border-radius:
        999px;

    background:white;
}


.acct img,

.initial {

    width:30px;

    height:30px;

    border-radius:50%;

    object-fit:cover;
}


.initial {

    display:grid;

    place-items:center;

    background:
        linear-gradient(
            135deg,
            var(--purple),
            #c58dbe
        );

    color:white;
}


.wrap {

    width:
        min(
            1140px,
            92vw
        );

    margin:
        30px auto
        90px;
}


.hero {

    background:
        linear-gradient(
            135deg,
            #f1e3fb,
            #fff0ec
        );

    border:
        1px solid
        var(--line);

    border-radius:
        26px;

    padding:32px;

    box-shadow:
        var(--shadow);

    display:flex;

    align-items:center;

    justify-content:
        space-between;

    gap:24px;
}


.hero h1 {

    font:
        700 44px/1.03
        Georgia;

    margin:
        8px 0 12px;
}


.hero-logo {

    width:140px;

    height:140px;

    object-fit:contain;
}


.card {

    background:white;

    border:
        1px solid
        var(--line);

    border-radius:
        20px;

    padding:20px;

    box-shadow:
        var(--shadow);

    margin:
        14px 0;
}


.grid {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                230px,
                1fr
            )
        );

    gap:16px;
}


.two {

    display:grid;

    grid-template-columns:
        1fr 1fr;

    gap:16px;
}


.sectionhead {

    display:flex;

    justify-content:
        space-between;

    align-items:end;

    gap:18px;
}


.kicker,

.sectionhead span {

    font-size:11px;

    letter-spacing:
        1.3px;

    font-weight:800;

    color:#8b6a9a;
}


h1,

h2,

h3 {

    font-family:
        Georgia,
        serif;
}


h2 {

    font-size:30px;
}


.btn,

.outline,

button {

    display:inline-flex;

    align-items:center;

    justify-content:center;

    min-height:42px;

    padding:
        10px 16px;

    border-radius:
        11px;

    font-weight:700;
}


.btn,

button {

    border:
        1px solid
        var(--purple);

    background:
        linear-gradient(
            135deg,
            var(--purple),
            var(--purple2)
        );

    color:white;
}


.outline {

    border:
        1px solid
        #cdb6dd;

    background:white;

    color:#68428a;
}


.actions {

    display:flex;

    gap:10px;

    flex-wrap:wrap;
}


input,

textarea,

select {

    width:100%;

    padding:11px;

    border:
        1px solid
        var(--line);

    border-radius:10px;

    background:#fff;

    margin:
        5px 0 12px;
}


textarea {

    min-height:105px;
}


.chips {

    display:flex;

    gap:7px;

    flex-wrap:wrap;
}


.chips span,

.chips a {

    background:
        var(--lav);

    padding:
        7px 9px;

    border-radius:
        999px;

    font-size:12px;
}


.muted {

    color:
        var(--muted);
}


.flash {

    width:
        min(
            1140px,
            92vw
        );

    margin:
        12px auto;

    background:
        #f0e4f8;

    padding:11px;

    border-radius:10px;
}


.portrait {

    width:110px;

    height:110px;

    object-fit:cover;

    border-radius:50%;
}


.empty {

    text-align:center;

    border:
        1px dashed
        #d9c8e5;

    border-radius:18px;

    padding:28px;

    color:
        var(--muted);
}


.moon-card {

    display:grid;

    grid-template-columns:
        130px 1fr;

    gap:20px;

    align-items:center;
}


.moon-picture {

    width:120px;

    height:120px;

    border-radius:50%;

    display:grid;

    place-items:center;

    background:
        radial-gradient(
            circle at 35% 30%,
            #fff,
            #ece6f0 58%,
            #c8bdd0 100%
        );

    font-size:78px;

    box-shadow:

        inset
        -12px
        -14px
        24px
        rgba(
            76,
            57,
            87,
            .18
        ),

        0 12px
        28px
        rgba(
            89,
            60,
            112,
            .12
        );
}


.business-store-card {

    padding:0;

    overflow:hidden;
}


.store-media {

    height:210px;

    background:
        linear-gradient(
            135deg,
            #e9d8f5,
            #fff0ed
        );

    display:grid;

    place-items:center;

    overflow:hidden;
}


.store-media img,

.store-media video {

    width:100%;

    height:100%;

    object-fit:cover;
}


.store-logo-fallback {

    width:110px !important;

    height:110px !important;

    object-fit:contain !important;
}


.store-body {

    padding:18px;
}


.store-links {

    display:flex;

    flex-wrap:wrap;

    gap:8px;

    margin-top:14px;
}


.badge {

    display:inline-block;

    padding:
        6px 8px;

    border-radius:
        999px;

    background:
        var(--lav);

    font-size:11px;

    font-weight:800;

    color:#68428a;
}


.posthead {

    display:flex;

    justify-content:
        space-between;

    gap:10px;

    align-items:center;
}


.postperson {

    display:flex;

    align-items:center;

    gap:9px;
}


.postperson img,

.avatar {

    width:42px;

    height:42px;

    border-radius:50%;

    object-fit:cover;
}


.post-image {

    width:100%;

    max-height:480px;

    object-fit:cover;

    border-radius:15px;

    margin-top:12px;
}


.content-media {

    width:100%;

    max-height:420px;

    object-fit:cover;

    border-radius:14px;
}


.content-video {

    width:100%;

    max-height:420px;

    border-radius:14px;

    background:#000;
}


.profile-tools {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                180px,
                1fr
            )
        );

    gap:12px;
}


.tool {

    border:
        1px solid
        var(--line);

    border-radius:16px;

    padding:16px;

    background:white;
}


.media-kit-grid {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                150px,
                1fr
            )
        );

    gap:10px;
}


.stat {

    background:
        var(--lav);

    border-radius:14px;

    padding:14px;
}


.mobilebar {

    display:none;
}


@media(
    max-width:850px
) {

    .topin {

        grid-template-columns:
            auto 1fr;
    }


    .account {

        display:none;
    }


    .nav {

        justify-content:
            flex-end;
    }


    .two {

        grid-template-columns:
            1fr;
    }
}


@media(
    max-width:700px
) {

    body {

        padding-bottom:78px;
    }


    .topin {

        display:flex;

        justify-content:center;

        min-height:70px;
    }


    .brand img {

        width:45px;

        height:45px;
    }


    .brandcopy strong {

        font-size:18px;
    }


    .nav,

    .account {

        display:none;
    }


    .wrap {

        width:
            min(
                94vw,
                700px
            );

        margin-top:20px;
    }


    .hero {

        padding:22px;

        align-items:
            flex-start;
    }


    .hero h1 {

        font-size:35px;
    }


    .hero-logo {

        width:82px;

        height:82px;
    }


    .moon-card {

        grid-template-columns:
            90px 1fr;
    }


    .moon-picture {

        width:84px;

        height:84px;

        font-size:52px;
    }


    .mobilebar {

        position:fixed;

        left:50%;

        bottom:10px;

        transform:
            translateX(-50%);

        z-index:60;

        width:
            min(
                95vw,
                620px
            );

        display:flex;

        justify-content:
            space-around;

        gap:4px;

        padding:7px;

        background:
            rgba(
                255,
                255,
                255,
                .96
            );

        border:
            1px solid
            var(--line);

        border-radius:20px;

        box-shadow:
            0 14px 36px
            rgba(
                72,
                42,
                96,
                .18
            );
    }


    .mobilebar a {

        display:flex;

        flex-direction:
            column;

        align-items:center;

        gap:3px;

        padding:7px;

        border-radius:12px;

        font-size:9px;

        font-weight:800;

        color:
            var(--muted);
    }


    .mobilebar a.active {

        background:
            var(--lav);

        color:#68428a;
    }


    .mobilebar b {

        font-size:17px;
    }
}

</style>

</head>


<body>


<header class="top">


<div class="topin">


<a
    class="brand"
    href="{{url_for('public_home')}}"
>


<img

    src="{{url_for('static',filename='seasons-within-logo.png')}}"

    alt="The Seasons Within"
>


<span class="brandcopy">


<strong>
The Seasons Within
</strong>


<small>
Conscious Coordination
</small>


</span>


</a>


<nav class="nav">


<a
    href="{{url_for('public_home')}}"
    class="{% if request.endpoint in ['public_home','home'] %}active{% endif %}"
>

Home

</a>


{% if me %}


<a
    href="{{url_for('profile')}}"
    class="{% if request.endpoint in ['profile','profile_edit','journal','community','messages','notifications','connections','connection_profile'] %}active{% endif %}"
>

My Profile

</a>


{% endif %}


<a
    href="{{url_for('business')}}"
    class="{% if request.endpoint in ['business','business_setup','business_app','business_manage'] %}active{% endif %}"
>

Business Network

</a>


<a
    href="{{url_for('retreats')}}"
    class="{% if request.endpoint in ['retreats','retreat_build','retreat_detail'] %}active{% endif %}"
>

Retreats

</a>


<a
    href="{{url_for('membership')}}"
    class="{% if request.endpoint=='membership' %}active{% endif %}"
>

Membership

</a>


</nav>


<div class="account">


{% if me %}


<a
    class="acct"
    href="{{url_for('profile')}}"
>


{% if me.photo %}


<img
    src="{{media_url(me.photo)}}"
    alt=""
>


{% else %}


<span class="initial">
{{me.name[:1]}}
</span>


{% endif %}


<span>
{{me.name}}
</span>


</a>


<a href="{{url_for('logout')}}">

Log Out

</a>


{% else %}


<a href="{{url_for('login')}}">

Log In

</a>


<a
    class="btn"
    href="{{url_for('join')}}"
>

Join Free

</a>


{% endif %}


</div>


</div>


</header>


{% with messages=get_flashed_messages() %}


{% if messages %}


<div class="flash">

{{messages|join(' • ')}}

</div>


{% endif %}


{% endwith %}


<main class="wrap">

{% block content %}

{% endblock %}

</main>


<nav class="mobilebar">


<a
    href="{{url_for('public_home')}}"
>

<b>⌂</b>

Home

</a>


{% if me %}


<a
    href="{{url_for('profile')}}"
>

<b>◉</b>

Profile

</a>


{% endif %}


<a
    href="{{url_for('business')}}"
>

<b>◇</b>

Business

</a>


<a
    href="{{url_for('retreats')}}"
>

<b>✦</b>

Retreats

</a>


<a
    href="{{url_for('membership')}}"
>

<b>♡</b>

Membership

</a>


</nav>


</body>

</html>
'''


# ============================================================
# SHARED BUSINESS CARD
# ============================================================

T["business_card.html"] = r'''

<article class="card business-store-card">


<div class="store-media">


{% if b.paid_business and b.featured_video %}


<video
    src="{{media_url(b.featured_video)}}"
    muted
    playsinline
    controls
>
</video>


{% elif b.paid_business and b.hero_image %}


<img
    src="{{media_url(b.hero_image)}}"
    alt="{{b.business_name}}"
>


{% elif b.logo %}


<img
    class="store-logo-fallback"
    src="{{media_url(b.logo)}}"
    alt="{{b.business_name}}"
>


{% else %}


<img
    class="store-logo-fallback"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


</div>


<div class="store-body">


<span class="badge">

{{'Hosted App' if b.paid_business else 'Free Listing'}}

</span>


<h3>
{{b.business_name}}
</h3>


<p>

<b>

{{b.creator_title or b.category}}

</b>


{% if b.city %}

•
{{b.city}}

{% endif %}

</p>


<small>

{{b.tagline or b.description}}

</small>


<div class="store-links">


<a
    class="btn"
    href="{{url_for('business_app',slug=b.slug)}}"
>

{{'Open App' if b.paid_business else 'View Business'}}

</a>


{% if b.website %}


<a
    class="outline"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Business Link

</a>


{% endif %}


</div>


</div>


</article>
'''


# ============================================================
# HOME = MARKETPLACE
# ============================================================

T["public.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>

Connect With Intention.
Discover Your Seasons Within.

</h1>


<p>

The marketplace for wellness businesses,
hosted apps,
retreats
and conscious community.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('business')}}"
>

Explore Businesses & Apps

</a>


{% if me %}


<a
    class="outline"
    href="{{url_for('community')}}"
>

Enter Member Community

</a>


{% else %}


<a
    class="outline"
    href="{{url_for('join')}}"
>

Join Free

</a>


{% endif %}


</div>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<section class="card moon-card">


<div class="moon-picture">

{{sky.moon_symbol}}

</div>


<div>


<span class="kicker">
MOON TODAY
</span>


<h2>

Moon in

{{sky.moon_sign or 'the current sky'}}

</h2>


<p>


<b>

{{sky.moon_phase or 'Current lunar phase'}}

</b>


{% if sky.moon_degree is not none %}


•
{{sky.moon_degree}}°


{% endif %}


</p>


<div class="chips">


{% for p in ['Mercury','Venus','Mars','Jupiter','Saturn'] %}


{% if sky.positions.get(p) %}


<span>


<b>
{{p}}
</b>


{{sky.positions[p]['sign']}}


</span>


{% endif %}


{% endfor %}


</div>


<small class="muted">

Current sky information is reflective context,
not prediction.

</small>


</div>


</section>


<section>


<div class="sectionhead">


<div>


<span>
BUSINESS NETWORK
</span>


<h2>

Businesses & Apps Within
The Seasons Within

</h2>


</div>


<a href="{{url_for('business')}}">

View All →

</a>


</div>


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Real businesses will appear here
as they create profiles.

</div>


{% endfor %}


</div>


</section>


<section class="card">


<span class="kicker">
RETREAT CONSTELLATION
</span>


<h2>
Build a Wellness Retreat
</h2>


<p>

Choose your season,
dates,
group size,
budget
and participating wellness partners.

The Seasons Within can help coordinate
partner availability
and locate a private retreat property
that fits the experience.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('retreat_build')}}"
>

Build My Retreat Constellation

</a>


<a
    class="outline"
    href="{{url_for('retreats')}}"
>

Explore Retreats

</a>


</div>


</section>


{% endblock %}
'''


# ============================================================
# JOIN / ONBOARDING
# ============================================================

T["join.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Join The Seasons Within
</h1>


<form
    method="post"
    class="card"
>


<label>

Name

<input
    name="name"
    required
>

</label>


<label>

Email

<input
    name="email"
    type="email"
    required
>

</label>


<label>

Password

<input
    name="password"
    type="password"
    minlength="6"
    required
>

</label>


<h2>

How would you like to connect
within The Seasons Within?

</h2>


<label>

<input
    type="checkbox"
    name="community_enabled"
    value="1"
    checked
>

<b>
Community
</b>

—
wellness,
reflection,
conversations
and shared experiences

</label>


<br><br>


<label>

<input
    type="checkbox"
    name="conscious_connections_enabled"
    value="1"
>

<b>

Conscious Connections —
Love, Dating & Friendship

</b>

</label>


<br><br>


<label>

<input
    type="checkbox"
    name="business_interest"
    value="1"
>

<b>
Business
</b>

—
create a business profile
or connect professionally

</label>


<br><br>


<button class="btn">

Create Free Account

</button>


</form>


{% endblock %}
'''


T["onboarding.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Set Up Your Profile
</h1>


<form
    method="post"
    class="card"
>


{% if u.conscious_connections_enabled %}


<h2>
Conscious Connections
</h2>


<p>

What connections are you open to?

</p>


<select name="connection_type">


<option value="Love & Dating">

Love & Dating

</option>


<option value="Friendship">

Friendship

</option>


<option value="Both">

Both

</option>


</select>


<p>

Your normal Seasons Within profile
remains your main profile.

This choice activates your private
Love / Dating / Friendship community profile.

</p>


{% endif %}


{% if u.business_interest %}


<h2>
Business
</h2>


<p>

You can create your free business listing
after your member profile is saved.

</p>


{% endif %}


<button class="btn">

Continue to My Profile

</button>


</form>


{% endblock %}
'''


# ============================================================
# GENERAL COMMUNITY
# ============================================================

T["community.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
MEMBER COMMUNITY
</span>


<h1>
Community
</h1>


<p>

Post,
reflect
and connect privately
with other members.

</p>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<section class="two">


<article class="card">


<span class="kicker">
THE SEASON WE'RE IN
</span>


<h2>
{{reflection.sky.season}}
</h2>


<p>

<b>
Journal • Reflect
</b>

</p>


<p>

Let the current season
and Moon invite reflection
on your pace,
relationships
and what deserves conscious attention.

</p>


<a
    class="outline"
    href="{{url_for('journal')}}"
>

Open My Private Journal

</a>


</article>


<article class="card">


<span class="kicker">
MOON TODAY
</span>


<h2>

{{reflection.sky.moon_symbol}}

Moon in

{{reflection.sky.moon_sign or 'the current sky'}}

</h2>


<p>

{{reflection.sky.moon_phase or 'Current lunar phase'}}


{% if reflection.sky.moon_degree is not none %}

•
{{reflection.sky.moon_degree}}°

{% endif %}

</p>


</article>


</section>


<h2>
Share With Community
</h2>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<textarea
    name="body"
    placeholder="Share a thought, reflection, question or part of your journey..."
>
</textarea>


<label>

Add Photo
(optional)

<input
    type="file"
    name="photo"
    accept="image/*"
>

</label>


<button class="btn">

Post to Community

</button>


</form>


{% for p in posts %}


<article class="card">


<div class="posthead">


<div class="postperson">


{% if p.photo %}


<img
    src="{{media_url(p.photo)}}"
    alt=""
>


{% else %}


<span class="initial avatar">

{{p.name[:1]}}

</span>


{% endif %}


<div>


<b>
{{p.name}}
</b>


<small class="muted">

{{p.created_at}}

</small>


</div>


</div>


{% if p.user_id != me.id %}


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=p.user_id,kind='people')}}"
>

Message Member

</a>


{% endif %}


</div>


<p>

{{p.body}}

</p>


{% if p.media_path %}


<img
    class="post-image"
    src="{{media_url(p.media_path)}}"
    alt=""
>


{% endif %}


</article>


{% else %}


<div class="empty">

Member posts will appear here
as the community grows.

</div>


{% endfor %}


<section>


<div class="sectionhead">


<div>


<span>
WELLNESS WITHIN THE COMMUNITY
</span>


<h2>
Businesses & Apps
</h2>


</div>


<a href="{{url_for('business')}}">

View All →

</a>


</div>


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% endfor %}


</div>


</section>


{% endblock %}
'''


# ============================================================
# PROFILE
# ============================================================

T["profile.html"] = r'''

{% extends 'base.html' %}

{% block content %}

<section class="card">

<span class="kicker">MY PROFILE</span>

{% if u.photo %}
<img class="portrait" src="{{media_url(u.photo)}}" alt="">
{% endif %}

<h1>{{u.name}}</h1>
<h3>{{u.profile_headline}}</h3>
<p>{{u.city}}</p>
<p>{{u.bio}}</p>

{% if u.conscious_connections_enabled %}
<div style="margin:10px 0 14px;">
<span class="badge">♡ Conscious Connections</span>
<small class="muted" style="display:block;margin-top:5px;">{{u.connection_type or 'Love & Dating • Friendship'}}</small>
</div>
{% endif %}

<div class="chips">
<span>Sun {{u.sun or '—'}}</span>
<span>Moon {{u.moon or '—'}}</span>
<span>Rising {{u.rising or '—'}}</span>
{% if u.membership_access %}
<span>Mercury {{u.mercury or '—'}}</span>
<span>Venus {{u.venus or '—'}}</span>
<span>Mars {{u.mars or '—'}}</span>
<span>Jupiter {{u.jupiter or '—'}}</span>
<span>Saturn {{u.saturn or '—'}}</span>
<span>Uranus {{u.uranus or '—'}}</span>
<span>Neptune {{u.neptune or '—'}}</span>
<span>Pluto {{u.pluto or '—'}}</span>
{% endif %}
</div>

<a class="btn" href="{{url_for('profile_edit')}}">Edit My Profile</a>

</section>

<section class="card">
<span class="kicker">PRIVATE JOURNAL ENTRY — TODAY</span>
<h2>{{reflection.sky.moon_symbol}} {{reflection.headline}}</h2>
<p>{{reflection.prompt}}</p>
<a class="btn" href="{{url_for('journal')}}">Open My Journal</a>
</section>

<section class="profile-tools">

{% if u.community_enabled %}
<a class="tool" href="{{url_for('community')}}">
<b>Community</b><br>
<small>Post and see member reflections.</small>
</a>
{% endif %}

<a class="tool" href="{{url_for('messages')}}">
<b>My Inbox</b><br>
<small>Your private conversations.</small>
</a>

<a class="tool" href="{{url_for('notifications')}}">
<b>My Notifications</b><br>
<small>Private astrology, connection and business updates.</small>
</a>

<a class="tool" href="{{url_for('connections') if u.conscious_connections_enabled else url_for('enable_connections')}}">
<b>♡ Conscious Connections</b><br>
<small>{% if u.conscious_connections_enabled %}{{u.connection_type or 'Love & Dating • Friendship'}}{% else %}Love • Dating • Friendship{% endif %}</small>
</a>

<a class="tool" href="{{url_for('business_setup')}}">
<b>My Business Listing / App</b><br>
<small>Create or manage your business presence.</small>
</a>

{% if u.business_access %}
<a class="tool" href="{{url_for('business_manage')}}">
<b>Manage Hosted App</b><br>
<small>Upload videos, content, services, meetups and more.</small>
</a>
{% endif %}

</section>

{% endblock %}
'''


T["profile_edit.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Edit My Profile
</h1>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<label>

Profile Picture

<input
    type="file"
    name="photo"
>

</label>


<label>

Name

<input
    name="name"
    value="{{u.name}}"
>

</label>


<label>

City

<input
    name="city"
    value="{{u.city}}"
>

</label>


<label>

Headline

<input
    name="profile_headline"
    value="{{u.profile_headline}}"
>

</label>


<label>

About

<textarea
    name="bio"
>
{{u.bio}}
</textarea>

</label>


<label>

Birth Date

<input
    type="date"
    name="birth_date"
    value="{{u.birth_date}}"
>

</label>


<label>

Birth Time

<input
    type="time"
    name="birth_time"
    value="{{u.birth_time}}"
>

</label>


<label>

<input
    type="checkbox"
    name="time_known"
    {% if u.time_known %}checked{% endif %}
>

Exact birth time known

</label>





<button class="btn">

Save Profile

</button>


</form>


{% endblock %}
'''


# ============================================================
# JOURNAL
# ============================================================

T["journal.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Private Journal
</h1>


<article class="card">


<span class="kicker">
TODAY'S REFLECTION
</span>


<h2>

{{reflection.sky.moon_symbol}}

Moon in

{{reflection.sky.moon_sign or 'the current sky'}}

</h2>


<p>

{{reflection.sky.moon_phase or 'Current lunar phase'}}


{% if reflection.sky.moon_degree is not none %}

•
{{reflection.sky.moon_degree}}°

{% endif %}

</p>


<p>
{{reflection.prompt}}
</p>


<form method="post">


<textarea
    name="body"
    placeholder="What are you noticing within yourself today?"
>
</textarea>


<button class="btn">

Save Journal Entry

</button>


</form>


</article>


{% for e in entries %}


<article class="card">


<small>
{{e.created_at}}
</small>


<p>
{{e.body}}
</p>


</article>


{% endfor %}


{% endblock %}
'''


# ============================================================
# CONSCIOUS CONNECTIONS
# ============================================================

T["connections_join.html"] = r'''

{% extends 'base.html' %}
{% block content %}

<section class="hero">
<div>
<span class="kicker">♡ CONSCIOUS CONNECTIONS</span>
<h1>Create My Connection Profile</h1>
<p>Love • Dating • Friendship</p>
</div>
<img class="hero-logo" src="{{url_for('static',filename='seasons-within-logo.png')}}" alt="">
</section>

<form method="post" class="card">

<h2>Connection Basics</h2>

<label>What type of connection are you looking for?
<select name="connection_type" required>
<option value="Love & Dating" {% if u.connection_type=='Love & Dating' %}selected{% endif %}>Love & Dating</option>
<option value="Friendship" {% if u.connection_type=='Friendship' %}selected{% endif %}>Friendship</option>
<option value="Both" {% if u.connection_type=='Both' %}selected{% endif %}>Both</option>
</select>
</label>

<label>I am a...
<select name="cc_gender" required>
<option value="">Choose one</option>
{% for x in ['Woman','Man','Nonbinary','Other','Prefer not to say'] %}
<option value="{{x}}" {% if u.cc_gender==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<label>Who would you like to connect with?
<select name="cc_seeking" required>
<option value="">Choose one</option>
{% for x in ['Men','Women','Both','Everyone','Open / No preference'] %}
<option value="{{x}}" {% if u.cc_seeking==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<label>What are you looking for right now? <small class="muted">Choose up to 3.</small></label>
<div class="chips" style="margin-bottom:14px;">
{% for x in ['Long-term relationship','Dating & getting to know someone','Friendship','Activity / travel companion','Open to possibilities'] %}
<label style="width:auto;margin:0;"><input type="checkbox" name="cc_looking_for" value="{{x}}" style="width:auto;margin-right:5px;" {% if x in (u.cc_looking_for or '') %}checked{% endif %}>{{x}}</label>
{% endfor %}
</div>

<label>Do you have children?
<select name="cc_children">
<option value="">Choose one</option>
{% for x in ['No','Yes — young children','Yes — teens','Yes — adult children','Prefer not to say'] %}
<option value="{{x}}" {% if u.cc_children==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<div class="two">
<label>What do you do for a living?
<input name="cc_occupation" maxlength="80" value="{{u.cc_occupation or ''}}" placeholder="Example: Teacher, business owner, artist">
</label>
<label>Height <small class="muted">Optional</small>
<input name="cc_height" maxlength="20" value="{{u.cc_height or ''}}" placeholder="Example: 5 ft 6 in">
</label>
</div>

<label>Weight <small class="muted">Optional</small>
<input name="cc_weight" maxlength="20" value="{{u.cc_weight or ''}}" placeholder="Example: 145 lb">
</label>

<h2>Connection Style</h2>

<label>What best describes your lifestyle? <small class="muted">Choose up to 3.</small></label>
<div class="chips" style="margin-bottom:14px;">
{% for x in ['Wellness & self-care','Active & outdoors','Social & outgoing','Homebody & relaxed','Spiritual / reflective'] %}
<label style="width:auto;margin:0;"><input type="checkbox" name="cc_lifestyle" value="{{x}}" style="width:auto;margin-right:5px;" {% if x in (u.cc_lifestyle or '') %}checked{% endif %}>{{x}}</label>
{% endfor %}
</div>

<label>What do you enjoy doing together? <small class="muted">Choose up to 3.</small></label>
<div class="chips" style="margin-bottom:14px;">
{% for x in ['Travel & new experiences','Dining & entertainment','Nature & outdoors','Wellness & retreats','Relaxing at home'] %}
<label style="width:auto;margin:0;"><input type="checkbox" name="cc_activities" value="{{x}}" style="width:auto;margin-right:5px;" {% if x in (u.cc_activities or '') %}checked{% endif %}>{{x}}</label>
{% endfor %}
</div>

<label>What matters most in a connection? <small class="muted">Choose up to 3.</small></label>
<div class="chips" style="margin-bottom:14px;">
{% for x in ['Trust & honesty','Communication','Affection & chemistry','Shared values','Growth & support'] %}
<label style="width:auto;margin:0;"><input type="checkbox" name="cc_values" value="{{x}}" style="width:auto;margin-right:5px;" {% if x in (u.cc_values or '') %}checked{% endif %}>{{x}}</label>
{% endfor %}
</div>

<label>What is your connection style?
<select name="cc_style">
<option value="">Choose one</option>
{% for x in ['Romantic & affectionate','Fun & adventurous','Deep & thoughtful','Peaceful & easygoing','A little of everything'] %}
<option value="{{x}}" {% if u.cc_style==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<label>What would you enjoy for a first connection?
<select name="cc_first_connection">
<option value="">Choose one</option>
{% for x in ['Dinner or coffee','Walk / nature date','Wellness experience','Activity or event','Suggest by compatibility'] %}
<option value="{{x}}" {% if u.cc_first_connection==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<label>Interested in a Conscious Connection retreat?
<select name="cc_retreat_interest">
<option value="">Choose one</option>
{% for x in ['Romantic / date retreat','Friendship retreat','Either one','Maybe','Not right now'] %}
<option value="{{x}}" {% if u.cc_retreat_interest==x %}selected{% endif %}>{{x}}</option>
{% endfor %}
</select>
</label>

<button class="btn">Save My Conscious Connections Profile</button>

</form>

{% endblock %}
'''


T["connections.html"] = r'''

{% extends 'base.html' %}
{% block content %}

<section class="hero">
<div>
<span class="kicker">LOVE • DATING • FRIENDSHIP</span>
<h1>♡ Conscious Connections</h1>
<p>Connection through shared interests, private conversation and Conscious Coordination.</p>
<div class="actions"><a class="outline" href="{{url_for('enable_connections')}}">Edit My Connection Profile</a></div>
</div>
<img class="hero-logo" src="{{url_for('static',filename='seasons-within-logo.png')}}" alt="">
</section>

{% if galaxy %}
<article class="card">
<div class="posthead">
<div class="postperson">
{% if galaxy.photo %}<img src="{{media_url(galaxy.photo)}}" alt="Galaxy Eve">{% else %}<img src="{{url_for('static',filename='seasons-within-logo.png')}}" alt="Galaxy Eve">{% endif %}
<div><span class="kicker">HOST</span><h3 style="margin:3px 0;">Galaxy Eve</h3><small class="muted">Conscious Coordinator • Content Creator</small></div>
</div>
{% if galaxy.id != me.id %}<a class="outline" href="{{url_for('compose_message',recipient_id=galaxy.id,kind='dating')}}">Inbox Galaxy Eve</a>{% endif %}
</div>
</article>
{% endif %}

{% if host_can_post %}
<form method="post" enctype="multipart/form-data" class="card">
<h3>Share With Conscious Connections</h3>
<textarea name="body" placeholder="Write something..."></textarea>
<label>Add Photo or Video<input type="file" name="media" accept="image/*,video/*"></label>
<button class="btn">Post</button>
</form>
{% endif %}

{% for p in posts %}
<article class="card">
<div class="posthead">
<div class="postperson">
{% if p.photo %}<img src="{{media_url(p.photo)}}" alt="">{% else %}<img src="{{url_for('static',filename='seasons-within-logo.png')}}" alt="">{% endif %}
<div><b>{{p.name}}</b><br><small class="muted">{{p.created_at}}</small></div>
</div>
{% if p.user_id != me.id %}<a class="outline" href="{{url_for('compose_message',recipient_id=p.user_id,kind='dating')}}">Inbox Galaxy Eve</a>{% endif %}
</div>
{% if p.body %}<p>{{p.body}}</p>{% endif %}
{% if p.media_path %}
{% if p.media_type=='video' %}<video class="content-video" src="{{media_url(p.media_path)}}" controls playsinline></video>{% else %}<img class="post-image" src="{{media_url(p.media_path)}}" alt="">{% endif %}
{% endif %}
{% if p.user_id != me.id %}<div class="actions" style="margin-top:12px;"><a class="outline" href="{{url_for('compose_message',recipient_id=p.user_id,kind='dating')}}">♡ Respond Privately</a></div>{% endif %}
</article>
{% endfor %}

<section>
<div class="sectionhead"><div><span>CONNECTION EXPERIENCES</span><h2>Dates, Friendships & Retreat Experiences</h2></div></div>
<div class="grid">
{% for b in businesses %}{% include 'business_card.html' %}{% else %}<div class="empty">Participating wellness experiences will appear here.</div>{% endfor %}
</div>
</section>

<section style="margin-top:34px;">
<div class="sectionhead">
<div><span>CONSCIOUS CONNECTIONS MEMBERS</span><h2>Discover Members</h2></div>
<div class="chips"><a href="?mode=dating">Love & Dating</a><a href="?mode=friendship">Friendship</a><a href="?mode=all">Both</a></div>
</div>
<div class="grid">
{% for p,score in cards %}
<article class="card">
{% if p.photo %}<img class="portrait" src="{{media_url(p.photo)}}" alt="{{p.name}}">{% else %}<span class="initial" style="width:72px;height:72px;font-size:24px;">{{p.name[:1]}}</span>{% endif %}
<p><span class="badge">♡ Conscious Connections</span></p>
<h3>{{p.name}}{% set person_age=age_from_birth_date(p.birth_date) %}{% if person_age %}, {{person_age}}{% endif %}</h3>
<p class="muted">{{p.city or 'Community'}}</p>
<p><b>{{p.connection_type or 'Love & Dating • Friendship'}}</b></p>
{% if p.cc_occupation %}<p>{{p.cc_occupation}}</p>{% endif %}
<div class="chips">{% if p.sun %}<span>Sun {{p.sun}}</span>{% endif %}{% if p.moon %}<span>Moon {{p.moon}}</span>{% endif %}{% if p.rising %}<span>Rising {{p.rising}}</span>{% endif %}</div>
<p><b>{{score}}% Conscious Coordination</b></p>
<div class="actions"><a class="btn" href="{{url_for('connection_profile',uid=p.id,mode=mode)}}">View Profile</a><a class="outline" href="{{url_for('compose_message',recipient_id=p.id,kind='dating' if mode!='friendship' else 'people')}}">Inbox</a></div>
</article>
{% else %}<div class="empty">Real Conscious Connections member profiles will appear here as members create them.</div>{% endfor %}
</div>
</section>

{% endblock %}
'''


T["connection_profile.html"] = r'''

{% extends 'base.html' %}
{% block content %}

<div class="actions" style="margin-bottom:14px;"><a class="outline" href="{{url_for('connections',mode=mode)}}">← Back to Conscious Connections</a></div>

<section class="card">
{% if person.photo %}<img class="portrait" src="{{media_url(person.photo)}}" alt="{{person.name}}">{% endif %}
<p><span class="badge">♡ Conscious Connections</span></p>
<h1>{{person.name}}{% set person_age=age_from_birth_date(person.birth_date) %}{% if person_age %}, {{person_age}}{% endif %}</h1>
<p class="muted">{{person.city}}</p>
<h3>{{person.connection_type or 'Love & Dating • Friendship'}}</h3>
{% if person.cc_gender or person.cc_seeking %}<p>{% if person.cc_gender %}{{person.cc_gender}}{% endif %}{% if person.cc_gender and person.cc_seeking %} • {% endif %}{% if person.cc_seeking %}Interested in {{person.cc_seeking}}{% endif %}</p>{% endif %}
<div class="actions"><a class="btn" href="{{url_for('compose_message',recipient_id=person.id,kind='dating' if mode=='dating' else 'people')}}">Inbox {{person.name}}</a><a class="outline" href="{{url_for('retreat_build',connection=1)}}">Build a {{'Date' if mode=='dating' else 'Friendship'}} Retreat</a></div>
</section>

<section class="two">
<article class="card">
<span class="kicker">ABOUT</span>
{% if person.cc_occupation %}<p><b>What I do</b><br>{{person.cc_occupation}}</p>{% endif %}
{% if person.cc_height %}<p><b>Height</b><br>{{person.cc_height}}</p>{% endif %}
{% if person.cc_weight %}<p><b>Weight</b><br>{{person.cc_weight}}</p>{% endif %}
{% if person.cc_children %}<p><b>Children</b><br>{{person.cc_children}}</p>{% endif %}
{% if person.bio %}<p><b>About me</b><br>{{person.bio}}</p>{% endif %}
</article>
<article class="card">
<span class="kicker">WHAT I'M LOOKING FOR</span>
{% if person.cc_looking_for %}<p><b>Looking for</b><br>{{person.cc_looking_for}}</p>{% endif %}
{% if person.cc_values %}<p><b>What matters most</b><br>{{person.cc_values}}</p>{% endif %}
{% if person.cc_style %}<p><b>Connection style</b><br>{{person.cc_style}}</p>{% endif %}
{% if person.cc_first_connection %}<p><b>Ideal first connection</b><br>{{person.cc_first_connection}}</p>{% endif %}
</article>
</section>

<section class="two">
<article class="card">
<span class="kicker">LIFESTYLE & EXPERIENCES</span>
{% if person.cc_lifestyle %}<p><b>Lifestyle</b><br>{{person.cc_lifestyle}}</p>{% endif %}
{% if person.cc_activities %}<p><b>Things I enjoy</b><br>{{person.cc_activities}}</p>{% endif %}
{% if person.cc_retreat_interest %}<p><b>Connection retreats</b><br>{{person.cc_retreat_interest}}</p>{% endif %}
</article>
<article class="card">
<span class="kicker">CONSCIOUS COORDINATION</span>
<h2>{{score}}%</h2>
<p>{{'Dating compatibility' if mode=='dating' else 'Friendship compatibility'}}</p>
<div class="chips">
<span>Sun {{person.sun or '—'}}</span><span>Moon {{person.moon or '—'}}</span><span>Rising {{person.rising or '—'}}</span>
{% if me.membership_access %}<span>Mercury {{person.mercury or '—'}}</span><span>Venus {{person.venus or '—'}}</span><span>Mars {{person.mars or '—'}}</span><span>Jupiter {{person.jupiter or '—'}}</span><span>Saturn {{person.saturn or '—'}}</span><span>Uranus {{person.uranus or '—'}}</span><span>Neptune {{person.neptune or '—'}}</span><span>Pluto {{person.pluto or '—'}}</span>{% endif %}
</div>
</article>
</section>

<article class="card">
<span class="kicker">SUGGESTED CONNECTION</span>
<h2>{{'Date Idea' if mode=='dating' else 'Friendship Idea'}}</h2>
<p>{{idea}}</p>
<div class="actions"><a class="btn" href="{{url_for('compose_message',recipient_id=person.id,kind='dating' if mode=='dating' else 'people')}}">Inbox {{person.name}}</a><a class="outline" href="{{url_for('retreat_build',connection=1)}}">Build a {{'Date' if mode=='dating' else 'Friendship'}} Retreat</a></div>
</article>

{% endblock %}
'''


# ============================================================
# BUSINESS NETWORK
# ============================================================

T["business.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>
Business Network
</h1>


<p>

Browse creators,
practitioners,
services,
classes,
retreats
and hosted business apps.

</p>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<form class="card">


<input
    name="q"
    value="{{q}}"
    placeholder="Search businesses, creators, services or categories..."
>


</form>


{% if me %}


<div class="actions">


<a
    class="btn"
    href="{{url_for('business_setup')}}"
>

Create / Manage My Business Listing

</a>


</div>


{% endif %}


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Real businesses will appear here
as they create profiles.

</div>


{% endfor %}


</div>


<article class="card">


<b>
Free business listing:
</b>

picture/logo,
bio,
category,
contact
and business link.


<br><br>


<b>

Business Network —
${{BUSINESS_PRICE}}/month:

</b>

hosted Business App,
media,
content,
services,
events,
collaborations
and Retreat Constellation tools.


</article>


{% endblock %}
'''


T["business_setup.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Business Profile / App
</h1>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<label>

Business Logo

<input
    type="file"
    name="logo"
>

</label>


{% if b and b.logo %}


<img
    style="
        width:100px;
        height:100px;
        object-fit:cover;
        border-radius:16px
    "
    src="{{media_url(b.logo)}}"
    alt=""
>


{% endif %}


<label>

Business Name

<input
    name="business_name"
    value="{{b.business_name if b else ''}}"
    required
>

</label>


<label>

Creator / Professional Title

<input
    name="creator_title"
    value="{{b.creator_title if b else ''}}"
>

</label>


<label>

Tagline

<input
    name="tagline"
    value="{{b.tagline if b else ''}}"
>

</label>


<label>

Description / Bio

<textarea
    name="description"
>
{{b.description if b else ''}}
</textarea>

</label>


<label>

Category

<input
    name="category"
    value="{{b.category if b else ''}}"
>

</label>


<label>

City

<input
    name="city"
    value="{{b.city if b else ''}}"
>

</label>


<label>

Business / Website Link

<input
    name="website"
    value="{{b.website if b else ''}}"
>

</label>


<label>

Contact Email

<input
    name="contact_email"
    value="{{b.contact_email if b else me.email}}"
>

</label>


<label>

Phone

<input
    name="phone"
    value="{{b.phone if b else ''}}"
>

</label>


{% if me.business_access %}


<hr>


<h2>
Hosted App Media
</h2>


<label>

App Cover Image

<input
    type="file"
    name="hero_image"
>

</label>


<label>

Featured App Video

<input
    type="file"
    name="featured_video"
>

</label>


<label>

Instagram

<input
    name="instagram"
    value="{{b.instagram if b else ''}}"
>

</label>


<label>

TikTok

<input
    name="tiktok"
    value="{{b.tiktok if b else ''}}"
>

</label>


<label>

YouTube

<input
    name="youtube"
    value="{{b.youtube if b else ''}}"
>

</label>


<label>

Booking Link

<input
    name="booking_url"
    value="{{b.booking_url if b else ''}}"
>

</label>


<label>

Content Categories

<input
    name="content_categories"
    value="{{b.content_categories if b else ''}}"
>

</label>


<label>

Audience Information

<textarea
    name="audience_info"
>
{{b.audience_info if b else ''}}
</textarea>

</label>


<label>

Previous Collaborations

<textarea
    name="previous_collaborations"
>
{{b.previous_collaborations if b else ''}}
</textarea>

</label>


<label>

Collaboration Interests

<textarea
    name="collaboration_interests"
>
{{b.collaboration_interests if b else ''}}
</textarea>

</label>


<div class="two">


<label>

Followers

<input
    name="followers"
    value="{{b.followers if b else ''}}"
>

</label>


<label>

Likes

<input
    name="likes"
    value="{{b.likes if b else ''}}"
>

</label>


<label>

Views

<input
    name="views"
    value="{{b.views if b else ''}}"
>

</label>


<label>

Engagement Rate

<input
    name="engagement_rate"
    value="{{b.engagement_rate if b else ''}}"
>

</label>


</div>


<label>


<input
    type="checkbox"
    name="retreat_participation"
    {% if b and b.retreat_participation %}checked{% endif %}
>


Participate in Retreat Constellations


</label>


{% endif %}


<button class="btn">

Save Business Profile

</button>


</form>


{% if b and me.business_access %}


<a
    class="btn"
    href="{{url_for('business_manage')}}"
>

Manage App Content,
Services & Events

</a>


{% endif %}


{% endblock %}
'''


T["business_manage.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Manage
{{b.business_name}}
Hosted App

</h1>


<div class="two">


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<input
    type="hidden"
    name="section"
    value="content"
>


<h2>
Add Content
</h2>


<select name="content_type">


<option value="post">
Update
</option>


<option value="photo">
Photo
</option>


<option value="video">
Video
</option>


<option value="media">
Featured Media
</option>


</select>


<textarea
    name="caption"
    placeholder="Caption or update..."
>
</textarea>


<input
    type="file"
    name="media"
>


<button class="btn">

Publish Content

</button>


</form>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="section"
    value="item"
>


<h2>
Add App Offering
</h2>


<select name="item_type">


<option value="service">
Service
</option>


<option value="class">
Class
</option>


<option value="event">
Event / Meetup
</option>


<option value="retreat">
Retreat
</option>


<option value="membership">
Membership
</option>


<option value="product">
Product
</option>


</select>


<input
    name="title"
    placeholder="Title"
>


<textarea
    name="description"
    placeholder="Description"
>
</textarea>


<input
    name="price"
    placeholder="Price"
>


<input
    name="action_url"
    placeholder="Booking / purchase link"
>


<button class="btn">

Add to App

</button>


</form>


</div>


<h2>
Published Content
</h2>


<div class="grid">


{% for x in content %}


<article class="card">


{% if x.media_path %}


{% if x.media_type=='video' %}


<video
    class="content-video"
    src="{{media_url(x.media_path)}}"
    controls
>
</video>


{% else %}


<img
    class="content-media"
    src="{{media_url(x.media_path)}}"
    alt=""
>


{% endif %}


{% endif %}


<p>
{{x.caption}}
</p>


</article>


{% else %}


<div class="empty">

Your app content
will appear here.

</div>


{% endfor %}


</div>


<h2>

Services,
Events
& Retreats

</h2>


<div class="grid">


{% for x in items %}


<article class="card">


<span class="badge">

{{x.item_type}}

</span>


<h3>
{{x.title}}
</h3>


<p>
{{x.description}}
</p>


<b>
{{x.price}}
</b>


</article>


{% else %}


<div class="empty">

Your app offerings
will appear here.

</div>


{% endfor %}


</div>


{% endblock %}
'''


T["business_app.html"] = r'''

{% extends 'base.html' %}

{% block content %}


{% if not b.paid_business %}


<section class="card">


{% if b.logo %}


<img
    style="
        width:120px;
        height:120px;
        object-fit:cover;
        border-radius:20px
    "
    src="{{media_url(b.logo)}}"
    alt=""
>


{% else %}


<img
    style="
        width:120px;
        height:120px;
        object-fit:contain
    "
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


<span class="badge">

Free Business Listing

</span>


<h1>
{{b.business_name}}
</h1>


<h3>
{{b.creator_title or b.category}}
</h3>


<p>
{{b.description}}
</p>


{% if b.city %}


<p>
{{b.city}}
</p>


{% endif %}


<div class="actions">


{% if b.website %}


<a
    class="btn"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Business Link

</a>


{% endif %}


{% if me and me.id!=owner.id %}


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Contact Business

</a>


{% endif %}


</div>


</section>


{% else %}


<section class="hero">


<div>


<span class="kicker">
HOSTED APP
</span>


<h1>
{{b.business_name}}
</h1>


<h3>
{{b.creator_title or b.category}}
</h3>


<p>
{{b.tagline}}
</p>


<div class="actions">


{% if me and me.id!=owner.id %}


<a
    class="btn"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Message / Contact

</a>


{% endif %}


{% if b.booking_url %}


<a
    class="outline"
    href="{{b.booking_url}}"
    target="_blank"
    rel="noopener"
>

Book / Apply

</a>


{% endif %}


{% if me and me.id==owner.id %}


<a
    class="outline"
    href="{{url_for('business_setup')}}"
>

Edit App

</a>


<a
    class="outline"
    href="{{url_for('business_manage')}}"
>

Manage Content

</a>


{% endif %}


</div>


</div>


{% if b.featured_video %}


<video
    style="
        width:min(430px,45%);
        border-radius:18px;
        background:#000
    "
    src="{{media_url(b.featured_video)}}"
    controls
    playsinline
>
</video>


{% elif b.hero_image %}


<img
    style="
        width:min(430px,45%);
        max-height:300px;
        object-fit:cover;
        border-radius:18px
    "
    src="{{media_url(b.hero_image)}}"
    alt=""
>


{% elif b.logo %}


<img
    class="hero-logo"
    src="{{media_url(b.logo)}}"
    alt=""
>


{% else %}


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


</section>


<div class="grid">


<article class="card">


<h2>
About
</h2>


<p>
{{b.description}}
</p>


{% if b.city %}


<p>

<b>
Location:
</b>

{{b.city}}

</p>


{% endif %}


{% if b.website %}


<a
    class="outline"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Website

</a>


{% endif %}


</article>


{% if b.media_kit_enabled %}


<article class="card">


<h2>
Media Kit
</h2>


<p>

<b>
Content:
</b>

{{b.content_categories}}

</p>


<p>

<b>
Audience:
</b>

{{b.audience_info}}

</p>


<div class="media-kit-grid">


<div class="stat">

<b>
{{b.followers or '—'}}
</b>

<br>

<small>
Followers
</small>

</div>


<div class="stat">

<b>
{{b.likes or '—'}}
</b>

<br>

<small>
Likes
</small>

</div>


<div class="stat">

<b>
{{b.views or '—'}}
</b>

<br>

<small>
Views
</small>

</div>


<div class="stat">

<b>
{{b.engagement_rate or '—'}}
</b>

<br>

<small>
Engagement
</small>

</div>


</div>


<p>

<b>
Previous Collaborations:
</b>

{{b.previous_collaborations}}

</p>


<p>

<b>
Collaboration Interests:
</b>

{{b.collaboration_interests}}

</p>


</article>


{% endif %}


</div>


<h2>
Content
</h2>


<div class="grid">


{% for x in content %}


<article class="card">


{% if x.media_path %}


{% if x.media_type=='video' %}


<video
    class="content-video"
    src="{{media_url(x.media_path)}}"
    controls
>
</video>


{% else %}


<img
    class="content-media"
    src="{{media_url(x.media_path)}}"
    alt=""
>


{% endif %}


{% endif %}


<p>
{{x.caption}}
</p>


</article>


{% else %}


<div class="empty">

New content
will appear here.

</div>


{% endfor %}


</div>


<h2>

Services
•
Events
•
Retreats
•
Meetups

</h2>


<div class="grid">


{% for x in items %}


<article class="card">


<span class="badge">

{{x.item_type}}

</span>


<h3>
{{x.title}}
</h3>


<p>
{{x.description}}
</p>


<b>
{{x.price}}
</b>


{% if x.action_url %}


<p>


<a
    class="outline"
    href="{{x.action_url}}"
    target="_blank"
    rel="noopener"
>

Open Link

</a>


</p>


{% endif %}


</article>


{% else %}


<div class="empty">

Offerings
and experiences
will appear here.

</div>


{% endfor %}


</div>


<section class="card">


<h2>

Connect With
{{b.business_name}}

</h2>


<div class="actions">


{% if me and me.id!=owner.id %}


<a
    class="btn"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Message / Contact

</a>


<a
    class="outline"
    href="{{url_for('collaborate',slug=b.slug)}}"
>

Collaborate

</a>


{% endif %}


{% if b.retreat_participation %}


<a
    class="outline"
    href="{{url_for('retreats')}}"
>

Retreats & Meetups

</a>


{% endif %}


{% if b.instagram %}


<a
    class="outline"
    href="{{b.instagram}}"
    target="_blank"
    rel="noopener"
>

Instagram

</a>


{% endif %}


{% if b.tiktok %}


<a
    class="outline"
    href="{{b.tiktok}}"
    target="_blank"
    rel="noopener"
>

TikTok

</a>


{% endif %}


{% if b.youtube %}


<a
    class="outline"
    href="{{b.youtube}}"
    target="_blank"
    rel="noopener"
>

YouTube

</a>


{% endif %}


</div>


</section>


{% endif %}


{% endblock %}
'''


# ============================================================
# COLLABORATION
# ============================================================

T["collaborate.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Collaborate With
{{b.business_name}}

</h1>


<form
    method="post"
    class="card"
>


<select name="request_type">


<option>
Creator Collaboration
</option>


<option>
Brand Collaboration
</option>


<option>
Business Visit / Feature
</option>


<option>
Retreat Collaboration
</option>


<option>
Event Appearance
</option>


<option>
Interview / Podcast
</option>


<option>
Content Collaboration
</option>


<option>
Other
</option>


</select>


<textarea
    name="message"
    placeholder="Tell {{b.business_name}} about the collaboration..."
>
</textarea>


<button class="btn">

Send Collaboration Request

</button>


</form>


{% endblock %}
'''


# ============================================================
# INBOX
# ============================================================

T["messages.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Inbox
</h1>


<div class="chips">


<span>
People
</span>


<span>
Dating
</span>


<span>
Business
</span>


<span>
Retreats
</span>


</div>


{% for m in inbox %}


<article class="card">


<span class="badge">

{{m.message_type|upper}}

</span>


<h3>

{{m.subject or 'Message'}}

</h3>


<b>
{{m.sender_name}}
</b>


<small>

{{m.created_at}}

</small>


<p>
{{m.body}}
</p>


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=m.sender_id,kind=m.message_type)}}"
>

Reply

</a>


</article>


{% else %}


<div class="empty">

Your private messages
will appear here.

</div>


{% endfor %}


{% endblock %}
'''


T["compose_message.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Message
{{recipient.name}}

</h1>


<form
    method="post"
    class="card"
>


<span class="badge">

{{kind|upper}}

</span>


<input
    name="subject"
    placeholder="Subject"
    value="{{subject}}"
>


<textarea
    name="body"
    placeholder="Write your private message..."
>
</textarea>


<button class="btn">

Send Message

</button>


</form>


{% endblock %}
'''


# ============================================================
# NOTIFICATIONS
# ============================================================

T["notifications.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Notifications
</h1>


{% for n in notifications %}


<article class="card">


<span class="badge">

{{n.notification_type}}

</span>


<h3>
{{n.title}}
</h3>


<p>
{{n.body}}
</p>


{% if n.link %}


<a
    class="outline"
    href="{{n.link}}"
>

Open

</a>


{% endif %}


</article>


{% else %}


<div class="empty">

Your private astrology,
connection,
business
and retreat notifications
will appear here.

</div>


{% endfor %}


{% endblock %}
'''


# ============================================================
# RETREATS
# ============================================================

T["retreats.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>
Retreats
</h1>


<p>

Private wellness experiences
and custom Retreat Constellations.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('retreat_build')}}"
>

Build My Retreat Constellation

</a>


<a
    class="outline"
    href="{{url_for('business')}}"
>

Explore Wellness Partners

</a>


</div>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<h2>

Participating Wellness Partners

</h2>


<div class="grid">


{% for b in partners %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Participating businesses
will appear here.

</div>


{% endfor %}


</div>


<h2>
Upcoming Retreats
</h2>


<div class="grid">


{% for r in retreats %}


<a
    class="card"
    href="{{url_for('retreat_detail',rid=r.id)}}"
>


<h3>
{{r.title}}
</h3>


<p>

{{r.season}}
•
{{r.area}}

</p>


<small>
{{r.preferred_dates}}
</small>


{% if r.connection_retreat %}


<p>

<span class="badge">

Conscious Connections Retreat

</span>

</p>


{% endif %}


</a>


{% else %}


<div class="empty">

Custom retreats
will appear
after they are created.

</div>


{% endfor %}


</div>


{% endblock %}
'''


T["retreat_build.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

{{'Build a Date / Friendship Retreat' if connection else 'Build My Retreat Constellation'}}

</h1>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="connection_retreat"
    value="{{1 if connection else 0}}"
>


<input
    name="title"
    placeholder="Retreat name"
    required
>


<select name="season">


<option>
Spring
</option>


<option>
Summer
</option>


<option>
Autumn
</option>


<option>
Winter
</option>


</select>


<input
    name="retreat_type"
    value="{{'Date / Friendship Retreat' if connection else ''}}"
    placeholder="Solo, Couples, Family, Creator..."
>


<input
    name="area"
    placeholder="Destination / preferred area"
>


<input
    name="preferred_dates"
    placeholder="Preferred dates"
>


<input
    name="guests"
    type="number"
    min="1"
    value="{{2 if connection else 1}}"
>


<input
    name="budget"
    placeholder="Accommodation budget"
>


<textarea
    name="lodging_preferences"
    placeholder="Private property, bedrooms, water, nature, accessibility, luxury preferences..."
>
</textarea>


<textarea
    name="wellness_interests"
    placeholder="Yoga, Reiki, massage, sound, creator meetup, meditation..."
>
</textarea>


<button class="btn">

Create Retreat Constellation

</button>


</form>


{% endblock %}
'''


T["retreat_detail.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
{{r.title}}
</h1>


<div class="two">


<article class="card">


<span class="kicker">
RETREAT PLAN
</span>


<p>

<b>
Season:
</b>

{{r.season}}

</p>


<p>

<b>
Area:
</b>

{{r.area}}

</p>


<p>

<b>
Dates:
</b>

{{r.preferred_dates}}

</p>


<p>

<b>
Guests:
</b>

{{r.guests}}

</p>


<p>

<b>
Budget:
</b>

{{r.budget}}

</p>


</article>


<article class="card">


<span class="kicker">
YOUR RETREAT LOCATION
</span>


<h2>
{{r.location_status}}
</h2>


<p>

The Seasons Within will help locate
a private retreat property
selected around your destination,
season,
group size,
experience
and lodging budget.

</p>


<form method="post">


<input
    type="hidden"
    name="action"
    value="location"
>


<button class="btn">

Request Retreat Location Search

</button>


</form>


</article>


</div>


<h2>
Retreat Constellation
</h2>


<div class="grid">


{% for p in partners %}


<article class="card">


<h3>
{{p.business_name}}
</h3>


<p>
{{p.creator_title or p.category}}
</p>


<p>

Status:
{{p.availability_status}}

</p>


<a
    class="outline"
    href="{{url_for('business_app',slug=p.slug)}}"
>

Open Business App

</a>


</article>


{% endfor %}


</div>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="action"
    value="partner"
>


<h3>

Add a Participating
Wellness Partner

</h3>


<select name="business_id">


{% for b in eligible %}


<option value="{{b.id}}">

{{b.business_name}}
—
{{b.category}}

</option>


{% endfor %}


</select>


<button class="btn">

Request Partner Availability

</button>


</form>


<h2>
Retreat Coordination
</h2>


<article class="card">


<p>

Use this private thread
to coordinate retreat dates,
business availability,
location
and retreat details.

</p>


<form method="post">


<input
    type="hidden"
    name="action"
    value="message"
>


<textarea
    name="body"
    placeholder="Message about dates, availability, location or retreat details..."
>
</textarea>


<button class="btn">

Send Retreat Message

</button>


</form>


</article>


{% for m in msgs %}


<article class="card">


<b>
{{m.sender_name}}
</b>


<small>
{{m.created_at}}
</small>


<p>
{{m.body}}
</p>


</article>


{% endfor %}


{% endblock %}
'''


# ============================================================
# MEMBERSHIP
# ============================================================

T["membership.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
MEMBERSHIP
</span>


<h1>

Connect With Intention.
Discover Your Seasons Within.

</h1>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<div class="grid">


<article class="card">


<h2>
Free
</h2>


<p>

Member Community

•
Basic profile

•
private journal

•
basic natal placements

•
free business listing

</p>


</article>


<article class="card">


<h2>

The Seasons Within Membership

—
${{MEMBER_PRICE}}/month

</h2>


<p>

Expanded natal chart

•
Conscious Coordination

•
dating compatibility

•
date ideas

•
private astrology
and connection notifications

</p>


</article>


<article class="card">


<h2>

Business Network

—
${{BUSINESS_PRICE}}/month

</h2>


<p>

Hosted Business App

•
photos/videos/content

•
media kit

•
services/classes/events

•
collaboration tools

•
Business Alignment Reflection

•
Retreat Constellation participation

</p>


</article>


</div>


{% endblock %}
'''


# ============================================================
# PRIVATE ADMIN
# ============================================================

T["admin.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Private Admin
</h1>


<div class="grid">


<article class="card">


<h2>
Users
</h2>


{% for u in users %}


<p>

{{u.name}}
—
{{u.email}}

{% if u.is_admin %}

<b>
ADMIN
</b>

{% endif %}

</p>


{% endfor %}


</article>


<article class="card">


<h2>
Businesses
</h2>


{% for b in businesses %}


<p>

{{b.business_name}}
—
{{b.status}}

</p>


{% endfor %}


</article>


<article class="card">


<h2>
Retreats
</h2>


{% for r in retreats %}


<p>

{{r.title}}
—
{{r.status}}

</p>


{% endfor %}


</article>


</div>


{% endblock %}
'''


# ============================================================
# JINJA
# ============================================================

app.jinja_loader = DictLoader(
    T
)


app.jinja_env.globals.update(

    media_url=
        media_url,

    is_admin=
        admin,

    is_video=
        is_video,

    age_from_birth_date=
        age_from_birth_date,

    MEMBER_PRICE=
        MEMBER_PRICE,

    BUSINESS_PRICE=
        BUSINESS_PRICE,
)


@app.context_processor
def context():

    return {
        "me":
            me()
    }


# ============================================================
# UPLOADS
# ============================================================

@app.route(
    "/uploads/<path:filename>"
)
def uploads(filename):

    return send_from_directory(
        UPLOADS,
        filename
    )


# ============================================================
# PUBLIC HOME
# ============================================================

@app.route("/")
def public_home():

    connection = conn()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE status='active'

        ORDER BY
            featured_order ASC,
            id ASC

        LIMIT 10
        """
    ).fetchall()


    connection.close()


    return render_template(

        "public.html",

        businesses=
            businesses,

        sky=
            current_sky(),
    )


@app.route("/home")
def home():

    return redirect(
        url_for(
            "public_home"
        )
    )


# ============================================================
# JOIN
# ============================================================

@app.route(
    "/join",
    methods=[
        "GET",
        "POST"
    ]
)
def join():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        if (
            not name
            or "@" not in email
            or len(password) < 6
        ):

            flash(
                "Enter your name, a valid email "
                "and a password of at least 6 characters."
            )


        else:

            connection = conn()


            try:

                cursor = connection.execute(
                    """
                    INSERT INTO users(

                        name,

                        email,

                        password,

                        community_enabled,

                        conscious_connections_enabled,

                        business_interest
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        name,

                        email,

                        hp(
                            password
                        ),

                        (
                            1
                            if request.form.get(
                                "community_enabled"
                            )
                            else 0
                        ),

                        (
                            1
                            if request.form.get(
                                "conscious_connections_enabled"
                            )
                            else 0
                        ),

                        (
                            1
                            if request.form.get(
                                "business_interest"
                            )
                            else 0
                        ),
                    )
                )


                connection.commit()


                session[
                    "uid"
                ] = cursor.lastrowid


                connection.close()


                return redirect(
                    url_for(
                        "onboarding"
                    )
                )


            except sqlite3.IntegrityError:

                connection.close()


                flash(
                    "That email already has an account."
                )


    return render_template(
        "join.html"
    )


# ============================================================
# ONBOARDING
# ============================================================

@app.route(
    "/onboarding",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def onboarding():

    user = me()


    if request.method == "POST":

        connection = conn()


        if user[
            "conscious_connections_enabled"
        ]:

            connection.execute(
                """
                UPDATE users

                SET connection_type=?

                WHERE id=?
                """,
                (

                    request.form.get(
                        "connection_type",
                        "Both"
                    ),

                    user[
                        "id"
                    ],
                )
            )


        connection.commit()

        connection.close()


        return redirect(
            url_for(
                "profile_edit"
            )
        )


    return render_template(
        "onboarding.html",
        u=user
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        connection = conn()


        user = connection.execute(
            """
            SELECT *

            FROM users

            WHERE lower(email)=?
            """,
            (
                email,
            )
        ).fetchone()


        connection.close()


        if (
            user
            and
            user[
                "password"
            ] == hp(
                password
            )
        ):

            session[
                "uid"
            ] = user[
                "id"
            ]


            return redirect(

                request.args.get(
                    "next"
                )

                or

                url_for(
                    "public_home"
                )
            )


        flash(
            "Email or password not recognized."
        )


    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    session.clear()


    return redirect(
        url_for(
            "public_home"
        )
    )


# ============================================================
# COMMUNITY
# ============================================================

@app.route(
    "/community",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def community():

    user = me()


    if not user[
        "community_enabled"
    ]:

        return redirect(
            url_for(
                "profile"
            )
        )


    connection = conn()


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        media = save_file(

            request.files.get(
                "photo"
            ),

            f"community{user['id']}"
        )


        if (
            media
            and is_video(
                media
            )
        ):

            media = ""


        if (
            body
            or media
        ):

            connection.execute(
                """
                INSERT INTO posts(

                    user_id,

                    body,

                    media_path,

                    media_type
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    body,

                    media,

                    (
                        "image"
                        if media
                        else ""
                    ),
                )
            )


            connection.commit()


    posts = connection.execute(
        """
        SELECT

            p.*,

            u.name,

            u.photo

        FROM posts p

        JOIN users u
        ON u.id=p.user_id

        ORDER BY
            p.id DESC

        LIMIT 50
        """
    ).fetchall()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE status='active'

        ORDER BY
            featured_order,
            id

        LIMIT 6
        """
    ).fetchall()


    connection.close()


    return render_template(

        "community.html",

        posts=
            posts,

        businesses=
            businesses,

        reflection=
            journal_reflection(
                user
            ),
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    user = me()


    return render_template(

        "profile.html",

        u=
            user,

        reflection=
            journal_reflection(
                user
            ),
    )


@app.route(
    "/profile/edit",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def profile_edit():

    user = me()


    if request.method == "POST":

        photo = (

            save_file(

                request.files.get(
                    "photo"
                ),

                f"user{user['id']}"
            )

            or

            user[
                "photo"
            ]
        )


        connection = conn()


        connection.execute(
            """
            UPDATE users

            SET

                name=?,

                city=?,

                profile_headline=?,

                bio=?,

                birth_date=?,

                birth_time=?,

                time_known=?,

                connection_type=?,

                photo=?

            WHERE id=?
            """,
            (

                request.form.get(
                    "name",
                    ""
                ).strip(),

                request.form.get(
                    "city",
                    ""
                ).strip(),

                request.form.get(
                    "profile_headline",
                    ""
                ).strip(),

                request.form.get(
                    "bio",
                    ""
                ).strip(),

                request.form.get(
                    "birth_date",
                    ""
                ).strip(),

                request.form.get(
                    "birth_time",
                    ""
                ).strip(),

                (
                    1
                    if request.form.get(
                        "time_known"
                    )
                    else 0
                ),

                request.form.get(
                    "connection_type",
                    user[
                        "connection_type"
                    ]
                ),

                photo,

                user[
                    "id"
                ],
            )
        )


        connection.commit()


        updated = connection.execute(
            """
            SELECT *
            FROM users
            WHERE id=?
            """,
            (
                user[
                    "id"
                ],
            )
        ).fetchone()


        chart = chart_for(
            updated
        )


        if chart:

            placements = [

                chart.get(
                    placement,
                    {}
                ).get(
                    "sign",
                    ""
                )

                for placement

                in (
                    "Sun",
                    "Moon",
                    "Mercury",
                    "Venus",
                    "Mars",
                    "Jupiter",
                    "Saturn",
                    "Uranus",
                    "Neptune",
                    "Pluto",
                )
            ]


            connection.execute(
                """
                UPDATE users

                SET

                    sun=?,

                    moon=?,

                    mercury=?,

                    venus=?,

                    mars=?,

                    jupiter=?,

                    saturn=?,

                    uranus=?,

                    neptune=?,

                    pluto=?

                WHERE id=?
                """,
                (
                    *placements,

                    user[
                        "id"
                    ],
                )
            )


            connection.commit()


        connection.close()


        flash(
            "Profile saved."
        )


        return redirect(
            url_for(
                "profile"
            )
        )


    return render_template(
        "profile_edit.html",
        u=user
    )


# ============================================================
# JOURNAL
# ============================================================

@app.route(
    "/journal",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def journal():

    user = me()

    connection = conn()


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        if body:

            connection.execute(
                """
                INSERT INTO journals(

                    user_id,

                    body,

                    sky_json
                )

                VALUES(

                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    body,

                    json.dumps(
                        current_sky()
                    ),
                )
            )


            connection.commit()


    entries = connection.execute(
        """
        SELECT *

        FROM journals

        WHERE user_id=?

        ORDER BY
            id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "journal.html",

        reflection=
            journal_reflection(
                user
            ),

        entries=
            entries,
    )


# ============================================================
# ENABLE CONSCIOUS CONNECTIONS
# ============================================================

@app.route(
    "/connections/join",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def enable_connections():

    user = me()

    if request.method == "POST":

        def picked(name):
            return " • ".join(
                request.form.getlist(name)[:3]
            )

        connection = conn()

        connection.execute(
            """
            UPDATE users
            SET
                conscious_connections_enabled=1,
                connection_type=?,
                cc_gender=?,
                cc_seeking=?,
                cc_looking_for=?,
                cc_children=?,
                cc_lifestyle=?,
                cc_activities=?,
                cc_values=?,
                cc_style=?,
                cc_first_connection=?,
                cc_retreat_interest=?,
                cc_occupation=?,
                cc_height=?,
                cc_weight=?
            WHERE id=?
            """,
            (
                request.form.get("connection_type", "Both"),
                request.form.get("cc_gender", "").strip(),
                request.form.get("cc_seeking", "").strip(),
                picked("cc_looking_for"),
                request.form.get("cc_children", "").strip(),
                picked("cc_lifestyle"),
                picked("cc_activities"),
                picked("cc_values"),
                request.form.get("cc_style", "").strip(),
                request.form.get("cc_first_connection", "").strip(),
                request.form.get("cc_retreat_interest", "").strip(),
                request.form.get("cc_occupation", "").strip()[:80],
                request.form.get("cc_height", "").strip()[:20],
                request.form.get("cc_weight", "").strip()[:20],
                user["id"],
            )
        )

        connection.commit()
        connection.close()

        flash("Conscious Connections profile saved.")

        return redirect(url_for("connections"))

    return render_template(
        "connections_join.html",
        u=user
    )


# ============================================================
# CONSCIOUS CONNECTIONS COMMUNITY
# ============================================================

@app.route(
    "/connections",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def connections():

    user = me()

    if not user["conscious_connections_enabled"]:
        return redirect(url_for("enable_connections"))

    mode = request.args.get("mode", "all")
    connection = conn()

    galaxy = connection.execute(
        """
        SELECT *
        FROM users
        WHERE lower(email)=?
        """,
        (GALAXY_EMAIL,)
    ).fetchone()

    host_can_post = bool(
        (user["email"] or "").lower() == GALAXY_EMAIL
    )

    if request.method == "POST":

        if not host_can_post:
            connection.close()
            return redirect(url_for("connections"))

        body = request.form.get("body", "").strip()
        media = save_file(
            request.files.get("media"),
            f"connections{user['id']}"
        )
        media_type = (
            "video" if is_video(media)
            else ("image" if media else "")
        )

        if body or media:
            connection.execute(
                """
                INSERT INTO connection_posts(
                    user_id, body, media_path, media_type
                )
                VALUES(?, ?, ?, ?)
                """,
                (user["id"], body, media, media_type)
            )
            connection.commit()

        connection.close()
        return redirect(url_for("connections", mode=mode))

    posts = connection.execute(
        """
        SELECT p.*, u.name, u.photo
        FROM connection_posts p
        JOIN users u ON u.id=p.user_id
        WHERE lower(u.email)=?
        ORDER BY p.id DESC
        LIMIT 50
        """,
        (GALAXY_EMAIL,)
    ).fetchall()

    people = connection.execute(
        """
        SELECT *
        FROM users
        WHERE id<>?
          AND conscious_connections_enabled=1
          AND lower(email)<>?
        ORDER BY id DESC
        """,
        (user["id"], GALAXY_EMAIL)
    ).fetchall()

    filtered = []
    for person in people:
        connection_type = person["connection_type"] or "Both"
        if mode == "dating":
            if connection_type in ("Love & Dating", "Both"):
                filtered.append(person)
        elif mode == "friendship":
            if connection_type in ("Friendship", "Both"):
                filtered.append(person)
        else:
            filtered.append(person)

    score_mode = "friendship" if mode == "friendship" else "dating"
    cards = [
        (person, coord(user, person, score_mode))
        for person in filtered
    ]

    businesses = connection.execute(
        """
        SELECT *
        FROM businesses
        WHERE status='active'
          AND retreat_participation=1
        ORDER BY featured_order, id
        LIMIT 8
        """
    ).fetchall()

    connection.close()

    return render_template(
        "connections.html",
        posts=posts,
        cards=cards,
        businesses=businesses,
        mode=mode,
        galaxy=galaxy,
        host_can_post=host_can_post,
    )


# ============================================================
# CONNECTION PROFILE / COMPATIBILITY
# ============================================================

@app.route(
    "/connections/profile/<int:uid>"
)
@login_required
def connection_profile(uid):

    user = me()


    if not user[
        "conscious_connections_enabled"
    ]:

        return redirect(
            url_for(
                "enable_connections"
            )
        )


    connection = conn()


    person = connection.execute(
        """
        SELECT *

        FROM users

        WHERE

            id=?

            AND conscious_connections_enabled=1
        """,
        (
            uid,
        )
    ).fetchone()


    connection.close()


    if not person:

        abort(
            404
        )


    mode = request.args.get(
        "mode",
        "dating"
    )


    if mode not in (
        "dating",
        "friendship",
    ):

        mode = "dating"


    return render_template(

        "connection_profile.html",

        person=
            person,

        mode=
            mode,

        score=
            coord(
                user,
                person,
                mode
            ),

        idea=
            date_idea(
                user,
                person,
                mode
            ),
    )


# ============================================================
# CREATORS ARE PART OF BUSINESS NETWORK
# ============================================================

@app.route("/creators")
def creators():

    return redirect(
        url_for(
            "business"
        )
    )


# ============================================================
# BUSINESS DIRECTORY
# ============================================================

@app.route("/business")
def business():

    query = request.args.get(
        "q",
        ""
    ).strip()


    connection = conn()


    rows = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND (

                ?=''

                OR business_name LIKE ?

                OR category LIKE ?

                OR description LIKE ?

                OR creator_title LIKE ?
            )

        ORDER BY

            featured_order,

            id
        """,
        (

            query,

            f"%{query}%",

            f"%{query}%",

            f"%{query}%",

            f"%{query}%",
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business.html",

        businesses=
            rows,

        q=
            query,
    )


# ============================================================
# BUSINESS SETUP
# ============================================================

@app.route(
    "/business/setup",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def business_setup():

    user = me()

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE owner_id=?
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchone()


    if request.method == "POST":

        business_name = request.form.get(
            "business_name",
            ""
        ).strip()


        if not business_name:

            flash(
                "Business name required."
            )


            connection.close()


            return render_template(
                "business_setup.html",
                b=business_record
            )


        logo = (

            save_file(

                request.files.get(
                    "logo"
                ),

                f"biz{user['id']}-logo"
            )

            or

            (
                business_record[
                    "logo"
                ]

                if business_record

                else ""
            )
        )


        hero_image = (

            business_record[
                "hero_image"
            ]

            if business_record

            else ""
        )


        featured_video = (

            business_record[
                "featured_video"
            ]

            if business_record

            else ""
        )


        if user[
            "business_access"
        ]:

            hero_image = (

                save_file(

                    request.files.get(
                        "hero_image"
                    ),

                    f"biz{user['id']}-hero"
                )

                or hero_image
            )


            featured_video = (

                save_file(

                    request.files.get(
                        "featured_video"
                    ),

                    f"biz{user['id']}-video"
                )

                or featured_video
            )


        values = {

            "business_name":
                business_name,

            "creator_title":
                request.form.get(
                    "creator_title",
                    ""
                ).strip(),

            "tagline":
                request.form.get(
                    "tagline",
                    ""
                ).strip(),

            "description":
                request.form.get(
                    "description",
                    ""
                ).strip(),

            "category":
                request.form.get(
                    "category",
                    ""
                ).strip(),

            "city":
                request.form.get(
                    "city",
                    ""
                ).strip(),

            "website":
                request.form.get(
                    "website",
                    ""
                ).strip(),

            "contact_email":
                request.form.get(
                    "contact_email",
                    ""
                ).strip(),

            "phone":
                request.form.get(
                    "phone",
                    ""
                ).strip(),

            "logo":
                logo,

            "hero_image":
                hero_image,

            "featured_video":
                featured_video,

            "instagram":

                request.form.get(
                    "instagram",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "instagram"
                    ]

                    if business_record

                    else ""
                ),

            "tiktok":

                request.form.get(
                    "tiktok",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "tiktok"
                    ]

                    if business_record

                    else ""
                ),

            "youtube":

                request.form.get(
                    "youtube",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "youtube"
                    ]

                    if business_record

                    else ""
                ),

            "booking_url":

                request.form.get(
                    "booking_url",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "booking_url"
                    ]

                    if business_record

                    else ""
                ),

            "content_categories":

                request.form.get(
                    "content_categories",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "content_categories"
                    ]

                    if business_record

                    else ""
                ),

            "audience_info":

                request.form.get(
                    "audience_info",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "audience_info"
                    ]

                    if business_record

                    else ""
                ),

            "previous_collaborations":

                request.form.get(
                    "previous_collaborations",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "previous_collaborations"
                    ]

                    if business_record

                    else ""
                ),

            "collaboration_interests":

                request.form.get(
                    "collaboration_interests",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "collaboration_interests"
                    ]

                    if business_record

                    else ""
                ),

            "followers":

                request.form.get(
                    "followers",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "followers"
                    ]

                    if business_record

                    else ""
                ),

            "likes":

                request.form.get(
                    "likes",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "likes"
                    ]

                    if business_record

                    else ""
                ),

            "views":

                request.form.get(
                    "views",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "views"
                    ]

                    if business_record

                    else ""
                ),

            "engagement_rate":

                request.form.get(
                    "engagement_rate",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "engagement_rate"
                    ]

                    if business_record

                    else ""
                ),

            "retreat_participation":

                1

                if (

                    user[
                        "business_access"
                    ]

                    and

                    request.form.get(
                        "retreat_participation"
                    )
                )

                else (

                    business_record[
                        "retreat_participation"
                    ]

                    if (
                        business_record
                        and
                        not user[
                            "business_access"
                        ]
                    )

                    else 0
                ),
        }


        if business_record:

            connection.execute(
                """
                UPDATE businesses

                SET

                    business_name=:business_name,

                    creator_title=:creator_title,

                    tagline=:tagline,

                    description=:description,

                    category=:category,

                    city=:city,

                    website=:website,

                    contact_email=:contact_email,

                    phone=:phone,

                    logo=:logo,

                    hero_image=:hero_image,

                    featured_video=:featured_video,

                    instagram=:instagram,

                    tiktok=:tiktok,

                    youtube=:youtube,

                    booking_url=:booking_url,

                    content_categories=:content_categories,

                    audience_info=:audience_info,

                    previous_collaborations=:previous_collaborations,

                    collaboration_interests=:collaboration_interests,

                    followers=:followers,

                    likes=:likes,

                    views=:views,

                    engagement_rate=:engagement_rate,

                    retreat_participation=:retreat_participation,

                    status='active'

                WHERE owner_id=:owner_id
                """,
                {

                    **values,

                    "owner_id":
                        user[
                            "id"
                        ],
                }
            )


        else:

            connection.execute(
                """
                INSERT INTO businesses(

                    owner_id,

                    slug,

                    business_name,

                    creator_title,

                    tagline,

                    description,

                    category,

                    city,

                    website,

                    contact_email,

                    phone,

                    logo,

                    hero_image,

                    featured_video,

                    instagram,

                    tiktok,

                    youtube,

                    booking_url,

                    content_categories,

                    audience_info,

                    previous_collaborations,

                    collaboration_interests,

                    followers,

                    likes,

                    views,

                    engagement_rate,

                    retreat_participation,

                    paid_business,

                    media_kit_enabled,

                    status
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,

                    'active'
                )
                """,
                (

                    user[
                        "id"
                    ],

                    slugify(
                        business_name
                    ),

                    values[
                        "business_name"
                    ],

                    values[
                        "creator_title"
                    ],

                    values[
                        "tagline"
                    ],

                    values[
                        "description"
                    ],

                    values[
                        "category"
                    ],

                    values[
                        "city"
                    ],

                    values[
                        "website"
                    ],

                    values[
                        "contact_email"
                    ],

                    values[
                        "phone"
                    ],

                    values[
                        "logo"
                    ],

                    values[
                        "hero_image"
                    ],

                    values[
                        "featured_video"
                    ],

                    values[
                        "instagram"
                    ],

                    values[
                        "tiktok"
                    ],

                    values[
                        "youtube"
                    ],

                    values[
                        "booking_url"
                    ],

                    values[
                        "content_categories"
                    ],

                    values[
                        "audience_info"
                    ],

                    values[
                        "previous_collaborations"
                    ],

                    values[
                        "collaboration_interests"
                    ],

                    values[
                        "followers"
                    ],

                    values[
                        "likes"
                    ],

                    values[
                        "views"
                    ],

                    values[
                        "engagement_rate"
                    ],

                    values[
                        "retreat_participation"
                    ],

                    (
                        1
                        if user[
                            "business_access"
                        ]
                        else 0
                    ),

                    (
                        1
                        if user[
                            "creator_access"
                        ]
                        else 0
                    ),
                )
            )


        connection.commit()

        connection.close()


        flash(
            "Business profile saved."
        )


        return redirect(
            url_for(
                "business"
            )
        )


    connection.close()


    return render_template(
        "business_setup.html",
        b=business_record
    )


# ============================================================
# BUSINESS APP MANAGER
# ============================================================

@app.route(
    "/business/manage",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def business_manage():

    user = me()


    if not user[
        "business_access"
    ]:

        return (
            "Hosted Business App access required.",
            403
        )


    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE owner_id=?
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchone()


    if not business_record:

        connection.close()


        return redirect(
            url_for(
                "business_setup"
            )
        )


    if request.method == "POST":

        section = request.form.get(
            "section"
        )


        if section == "content":

            caption = request.form.get(
                "caption",
                ""
            ).strip()


            media = save_file(

                request.files.get(
                    "media"
                ),

                f"bizcontent{business_record['id']}"
            )


            media_type = (

                "video"

                if is_video(
                    media
                )

                else (

                    "image"

                    if media

                    else ""
                )
            )


            if (
                caption
                or media
            ):

                connection.execute(
                    """
                    INSERT INTO business_content(

                        business_id,

                        content_type,

                        caption,

                        media_path,

                        media_type
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        business_record[
                            "id"
                        ],

                        request.form.get(
                            "content_type",
                            "post"
                        ),

                        caption,

                        media,

                        media_type,
                    )
                )


                connection.commit()


                flash(
                    "Content published to your Hosted App."
                )


        elif section == "item":

            title = request.form.get(
                "title",
                ""
            ).strip()


            if title:

                connection.execute(
                    """
                    INSERT INTO business_items(

                        business_id,

                        item_type,

                        title,

                        description,

                        price,

                        action_url
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        business_record[
                            "id"
                        ],

                        request.form.get(
                            "item_type",
                            "service"
                        ),

                        title,

                        request.form.get(
                            "description",
                            ""
                        ).strip(),

                        request.form.get(
                            "price",
                            ""
                        ).strip(),

                        request.form.get(
                            "action_url",
                            ""
                        ).strip(),
                    )
                )


                connection.commit()


                flash(
                    "Added to your Hosted App."
                )


    content = connection.execute(
        """
        SELECT *

        FROM business_content

        WHERE

            business_id=?

            AND active=1

        ORDER BY
            id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    items = connection.execute(
        """
        SELECT *

        FROM business_items

        WHERE

            business_id=?

            AND active=1

        ORDER BY
            id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business_manage.html",

        b=
            business_record,

        content=
            content,

        items=
            items,
    )


# ============================================================
# BUSINESS APP
# ============================================================

@app.route(
    "/app/<slug>"
)
def business_app(slug):

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            slug=?

            AND status='active'
        """,
        (
            slug,
        )
    ).fetchone()


    if not business_record:

        connection.close()

        abort(
            404
        )


    owner = connection.execute(
        """
        SELECT *

        FROM users

        WHERE id=?
        """,
        (
            business_record[
                "owner_id"
            ],
        )
    ).fetchone()


    content = connection.execute(
        """
        SELECT *

        FROM business_content

        WHERE

            business_id=?

            AND active=1

        ORDER BY id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    items = connection.execute(
        """
        SELECT *

        FROM business_items

        WHERE

            business_id=?

            AND active=1

        ORDER BY id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business_app.html",

        b=
            business_record,

        owner=
            owner,

        content=
            content,

        items=
            items,
    )


# ============================================================
# COLLABORATIONS
# ============================================================

@app.route(
    "/app/<slug>/collaborate",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def collaborate(slug):

    user = me()

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            slug=?

            AND status='active'
        """,
        (
            slug,
        )
    ).fetchone()


    if not business_record:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()


        request_type = request.form.get(
            "request_type",
            "Collaboration"
        )


        connection.execute(
            """
            INSERT INTO collaboration_requests(

                business_id,

                sender_id,

                request_type,

                message
            )

            VALUES(

                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                business_record[
                    "id"
                ],

                user[
                    "id"
                ],

                request_type,

                message,
            )
        )


        connection.execute(
            """
            INSERT INTO messages(

                sender_id,

                recipient_id,

                message_type,

                subject,

                body
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                user[
                    "id"
                ],

                business_record[
                    "owner_id"
                ],

                "business",

                "Collaboration Request",

                message,
            )
        )


        connection.commit()

        connection.close()


        flash(
            "Collaboration request sent."
        )


        return redirect(
            url_for(
                "business_app",
                slug=slug
            )
        )


    connection.close()


    return render_template(
        "collaborate.html",
        b=business_record
    )


# ============================================================
# INBOX
# ============================================================

@app.route("/messages")
@login_required
def messages():

    user = me()

    connection = conn()


    inbox = connection.execute(
        """
        SELECT

            m.*,

            u.name sender_name

        FROM messages m

        JOIN users u
        ON u.id=m.sender_id

        WHERE
            m.recipient_id=?

        ORDER BY
            m.id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "messages.html",
        inbox=inbox
    )


@app.route(
    "/message/<int:recipient_id>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def compose_message(
    recipient_id
):

    user = me()


    kind = request.args.get(
        "kind",
        "people"
    )


    connection = conn()


    recipient = connection.execute(
        """
        SELECT *

        FROM users

        WHERE id=?
        """,
        (
            recipient_id,
        )
    ).fetchone()


    if not recipient:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        subject = request.form.get(
            "subject",
            ""
        ).strip()


        if body:

            connection.execute(
                """
                INSERT INTO messages(

                    sender_id,

                    recipient_id,

                    message_type,

                    subject,

                    body
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    recipient_id,

                    kind,

                    subject,

                    body,
                )
            )


            connection.commit()

            connection.close()


            flash(
                "Message sent."
            )


            return redirect(
                url_for(
                    "messages"
                )
            )


    connection.close()


    return render_template(

        "compose_message.html",

        recipient=
            recipient,

        kind=
            kind,

        subject=
            "",
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    user = me()

    connection = conn()


    rows = connection.execute(
        """
        SELECT *

        FROM notifications

        WHERE user_id=?

        ORDER BY
            id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "notifications.html",
        notifications=rows
    )


# ============================================================
# RETREATS
# ============================================================

@app.route("/retreats")
def retreats():

    connection = conn()


    retreat_rows = connection.execute(
        """
        SELECT *

        FROM retreats

        WHERE status<>'cancelled'

        ORDER BY
            id DESC
        """
    ).fetchall()


    partners = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND retreat_participation=1

        ORDER BY

            featured_order,

            id
        """
    ).fetchall()


    connection.close()


    return render_template(

        "retreats.html",

        retreats=
            retreat_rows,

        partners=
            partners,
    )


@app.route(
    "/retreats/build",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def retreat_build():

    connection_mode = (
        request.args.get(
            "connection"
        )
        == "1"
    )


    if request.method == "POST":

        user = me()

        connection = conn()


        cursor = connection.execute(
            """
            INSERT INTO retreats(

                owner_id,

                title,

                season,

                retreat_type,

                area,

                preferred_dates,

                guests,

                budget,

                lodging_preferences,

                wellness_interests,

                connection_retreat
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                user[
                    "id"
                ],

                request.form.get(
                    "title",
                    "My Retreat"
                ).strip(),

                request.form.get(
                    "season",
                    ""
                ),

                request.form.get(
                    "retreat_type",
                    ""
                ),

                request.form.get(
                    "area",
                    ""
                ),

                request.form.get(
                    "preferred_dates",
                    ""
                ),

                int(
                    request.form.get(
                        "guests"
                    )
                    or 1
                ),

                request.form.get(
                    "budget",
                    ""
                ),

                request.form.get(
                    "lodging_preferences",
                    ""
                ),

                request.form.get(
                    "wellness_interests",
                    ""
                ),

                (
                    1
                    if request.form.get(
                        "connection_retreat"
                    )
                    == "1"
                    else 0
                ),
            )
        )


        connection.commit()


        retreat_id = (
            cursor.lastrowid
        )


        connection.close()


        return redirect(
            url_for(
                "retreat_detail",
                rid=retreat_id
            )
        )


    return render_template(

        "retreat_build.html",

        connection=
            connection_mode,
    )


@app.route(
    "/retreat/<int:rid>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def retreat_detail(rid):

    user = me()

    connection = conn()


    retreat_record = connection.execute(
        """
        SELECT *

        FROM retreats

        WHERE id=?
        """,
        (
            rid,
        )
    ).fetchone()


    if not retreat_record:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        action = request.form.get(
            "action"
        )


        if action == "partner":

            connection.execute(
                """
                INSERT OR IGNORE
                INTO retreat_partners(

                    retreat_id,

                    business_id
                )

                VALUES(

                    ?,
                    ?
                )
                """,
                (

                    rid,

                    int(
                        request.form.get(
                            "business_id"
                        )
                    ),
                )
            )


            connection.commit()


        elif action == "location":

            connection.execute(
                """
                UPDATE retreats

                SET
                    location_status='Search Requested'

                WHERE id=?
                """,
                (
                    rid,
                )
            )


            connection.commit()


        elif action == "message":

            body = request.form.get(
                "body",
                ""
            ).strip()


            if body:

                connection.execute(
                    """
                    INSERT INTO retreat_messages(

                        retreat_id,

                        sender_id,

                        body
                    )

                    VALUES(

                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        rid,

                        user[
                            "id"
                        ],

                        body,
                    )
                )


                connection.commit()


    partners = connection.execute(
        """
        SELECT

            rp.*,

            b.*

        FROM retreat_partners rp

        JOIN businesses b
        ON b.id=rp.business_id

        WHERE
            rp.retreat_id=?
        """,
        (
            rid,
        )
    ).fetchall()


    eligible = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND retreat_participation=1

        ORDER BY

            featured_order,

            id
        """
    ).fetchall()


    messages_rows = connection.execute(
        """
        SELECT

            rm.*,

            u.name sender_name

        FROM retreat_messages rm

        JOIN users u
        ON u.id=rm.sender_id

        WHERE
            retreat_id=?

        ORDER BY
            rm.id
        """,
        (
            rid,
        )
    ).fetchall()


    connection.close()


    return render_template(

        "retreat_detail.html",

        r=
            retreat_record,

        partners=
            partners,

        eligible=
            eligible,

        msgs=
            messages_rows,
    )


# ============================================================
# MEMBERSHIP
# ============================================================

@app.route("/membership")
def membership():

    return render_template(
        "membership.html"
    )


# ============================================================
# PRIVATE ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin_page():

    connection = conn()


    users = connection.execute(
        """
        SELECT *

        FROM users

        ORDER BY
            id DESC
        """
    ).fetchall()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        ORDER BY
            featured_order,
            id
        """
    ).fetchall()


    retreats_rows = connection.execute(
        """
        SELECT *

        FROM retreats

        ORDER BY
            id DESC
        """
    ).fetchall()


    connection.close()


    return render_template(

        "admin.html",

        users=
            users,

        businesses=
            businesses,

        retreats=
            retreats_rows,
    )


# ============================================================
# START DATABASE
# ============================================================

init_db()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        host=
            "0.0.0.0",

        port=
            int(
                os.environ.get(
                    "PORT",
                    "5055"
                )
            )
    )
        DATA / "uploads"
    )
)

UPLOADS.mkdir(
    parents=True,
    exist_ok=True
)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-me-in-render"
)


MEMBER_PRICE = "10.99"
BUSINESS_PRICE = "29.99"


GALAXY_EMAIL = os.environ.get(
    "GALAXY_EVE_EMAIL",
    "galaxyeve@theseasonswithin.local"
).strip().lower()


ADMIN_EMAILS = {
    x.strip().lower()
    for x in os.environ.get(
        "ADMIN_EMAILS",
        ""
    ).split(",")
    if x.strip()
}


SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]


DEMO_EMAILS = (
    "avery@example.com",
    "morgan@example.com",
    "nia@example.com",
    "marcus@example.com",
    "jordan@example.com",
    "sage@business.demo",
    "maya@business.demo",
)


DEMO_SLUGS = (
    "rise-flow-yoga",
    "sacred-soul-reiki",
    "sound-harmony",
    "nature-vibes",
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def conn():

    connection = sqlite3.connect(DB)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys=ON"
    )

    return connection


def table_columns(
    connection,
    table
):

    return {
        row[1]
        for row
        in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def ensure_column(
    connection,
    table,
    name,
    definition
):

    if name not in table_columns(
        connection,
        table
    ):

        connection.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {name} {definition}
            """
        )


# ============================================================
# ACCOUNT HELPERS
# ============================================================

def hp(password):

    return hashlib.sha256(
        (
            "tsw::"
            + password
        ).encode()
    ).hexdigest()


def slugify(text):

    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            (
                text
                or ""
            ).lower()
        )
        .strip("-")
        or secrets.token_hex(4)
    )


def me():

    user_id = session.get(
        "uid"
    )

    if not user_id:

        return None


    connection = conn()


    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE id=?
        """,
        (
            user_id,
        )
    ).fetchone()


    connection.close()


    return user


def admin(user):

    return bool(

        user

        and (

            user[
                "is_admin"
            ]

            or

            (
                user[
                    "email"
                ]
                or ""
            ).lower()

            in ADMIN_EMAILS
        )
    )


def login_required(function):

    @wraps(function)
    def wrapped(
        *args,
        **kwargs
    ):

        if not me():

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )


        return function(
            *args,
            **kwargs
        )


    return wrapped


def admin_required(function):

    @wraps(function)
    def wrapped(
        *args,
        **kwargs
    ):

        user = me()


        if not user:

            return redirect(
                url_for(
                    "login"
                )
            )


        if not admin(
            user
        ):

            return (
                "Admin access required",
                403
            )


        return function(
            *args,
            **kwargs
        )


    return wrapped


# ============================================================
# MEDIA
# ============================================================

def media_url(path):

    if not path:

        return ""


    return url_for(
        "uploads",
        filename=path
    )


def save_file(
    file_storage,
    prefix
):

    if (
        not file_storage
        or not file_storage.filename
    ):

        return ""


    extension = Path(
        secure_filename(
            file_storage.filename
        )
    ).suffix.lower()


    allowed = {

        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".mp4",
        ".mov",
        ".m4v",
    }


    if extension not in allowed:

        return ""


    filename = (

        f"{prefix}-"

        f"{secrets.token_hex(8)}"

        f"{extension}"
    )


    file_storage.save(
        UPLOADS / filename
    )


    return filename


def is_video(path):

    if not path:

        return False


    return (

        Path(path)
        .suffix
        .lower()

        in {
            ".mp4",
            ".mov",
            ".m4v",
        }
    )


# ============================================================
# CURRENT SKY
# ============================================================

def season_now():

    month = date.today().month


    if month in (
        12,
        1,
        2,
    ):

        return "Winter"


    if month in (
        3,
        4,
        5,
    ):

        return "Spring"


    if month in (
        6,
        7,
        8,
    ):

        return "Summer"


    return "Autumn"


def zdeg(degree):

    degree = (
        float(degree)
        % 360
    )


    index = int(
        degree // 30
    )


    return (

        SIGNS[
            index
        ],

        round(
            degree
            - index * 30,
            2
        ),
    )


def moon_symbol(
    phase
):

    return {

        "New Moon":
            "🌑",

        "Waxing Crescent":
            "🌒",

        "First Quarter":
            "🌓",

        "Waxing Gibbous":
            "🌔",

        "Full Moon":
            "🌕",

        "Waning Gibbous":
            "🌖",

        "Last Quarter":
            "🌗",

        "Waning Crescent":
            "🌘",

    }.get(
        phase,
        "☾"
    )


def current_sky():

    sky = {

        "moon_sign":
            "",

        "moon_phase":
            "",

        "moon_degree":
            None,

        "moon_symbol":
            "☾",

        "positions":
            {},

        "season":
            season_now(),
    }


    if not swe:

        return sky


    try:

        now = datetime.now(
            timezone.utc
        )


        julian_day = swe.julday(

            now.year,

            now.month,

            now.day,

            (
                now.hour

                + now.minute / 60

                + now.second / 3600
            ),
        )


        bodies = {

            "Sun":
                swe.SUN,

            "Moon":
                swe.MOON,

            "Mercury":
                swe.MERCURY,

            "Venus":
                swe.VENUS,

            "Mars":
                swe.MARS,

            "Jupiter":
                swe.JUPITER,

            "Saturn":
                swe.SATURN,

            "Uranus":
                swe.URANUS,

            "Neptune":
                swe.NEPTUNE,

            "Pluto":
                swe.PLUTO,
        }


        degrees = {}


        for (
            body_name,
            body_id
        ) in bodies.items():


            position = swe.calc_ut(
                julian_day,
                body_id
            )[0][0]


            sign, degree = zdeg(
                position
            )


            degrees[
                body_name
            ] = position


            sky[
                "positions"
            ][
                body_name
            ] = {

                "sign":
                    sign,

                "degree":
                    degree,
            }


        sky[
            "moon_sign"
        ] = sky[
            "positions"
        ][
            "Moon"
        ][
            "sign"
        ]


        sky[
            "moon_degree"
        ] = sky[
            "positions"
        ][
            "Moon"
        ][
            "degree"
        ]


        angle = (

            degrees[
                "Moon"
            ]

            -

            degrees[
                "Sun"
            ]

        ) % 360


        phases = [

            (
                22.5,
                "New Moon"
            ),

            (
                67.5,
                "Waxing Crescent"
            ),

            (
                112.5,
                "First Quarter"
            ),

            (
                157.5,
                "Waxing Gibbous"
            ),

            (
                202.5,
                "Full Moon"
            ),

            (
                247.5,
                "Waning Gibbous"
            ),

            (
                292.5,
                "Last Quarter"
            ),

            (
                337.5,
                "Waning Crescent"
            ),

            (
                361,
                "New Moon"
            ),
        ]


        for (
            cutoff,
            phase_name
        ) in phases:


            if angle < cutoff:

                sky[
                    "moon_phase"
                ] = phase_name

                break


        sky[
            "moon_symbol"
        ] = moon_symbol(
            sky[
                "moon_phase"
            ]
        )


    except Exception:

        pass


    return sky


# ============================================================
# NATAL CHART
# ============================================================

def chart_for(user):

    if (
        not swe
        or not user
        or not user[
            "birth_date"
        ]
    ):

        return {}


    try:

        birth_date = datetime.strptime(
            user[
                "birth_date"
            ],
            "%Y-%m-%d"
        )


        hour = 12.0


        if (
            user[
                "time_known"
            ]
            and user[
                "birth_time"
            ]
        ):

            hours, minutes = [

                int(value)

                for value

                in user[
                    "birth_time"
                ].split(":")[:2]
            ]


            hour = (
                hours
                + minutes / 60
            )


        julian_day = swe.julday(

            birth_date.year,

            birth_date.month,

            birth_date.day,

            hour,
        )


        bodies = {

            "Sun":
                swe.SUN,

            "Moon":
                swe.MOON,

            "Mercury":
                swe.MERCURY,

            "Venus":
                swe.VENUS,

            "Mars":
                swe.MARS,

            "Jupiter":
                swe.JUPITER,

            "Saturn":
                swe.SATURN,

            "Uranus":
                swe.URANUS,

            "Neptune":
                swe.NEPTUNE,

            "Pluto":
                swe.PLUTO,
        }


        result = {}


        for (
            name,
            body_id
        ) in bodies.items():


            position = swe.calc_ut(
                julian_day,
                body_id
            )[0][0]


            sign, degree = zdeg(
                position
            )


            result[
                name
            ] = {

                "sign":
                    sign,

                "degree":
                    degree,

                "absolute":
                    round(
                        position,
                        4
                    ),
            }


        return result


    except Exception:

        return {}


# ============================================================
# PRIVATE JOURNAL
# ============================================================

def journal_reflection(
    user
):

    sky = current_sky()


    natal_reference = (

        user[
            "moon"
        ]

        or

        user[
            "sun"
        ]

        or

        "your natal chart"

    ) if user else "your natal chart"


    return {

        "sky":
            sky,

        "headline":

            (
                f"Reflect through "
                f"{natal_reference} "
                f"and the current "
                f"{sky['moon_sign'] or 'Moon'}."
            ),

        "prompt":

            (
                "What are you noticing within yourself today, "
                "and what deserves your conscious attention?"
            ),
    }


# ============================================================
# CONSCIOUS COORDINATION
# ============================================================

def coord(
    person_a,
    person_b,
    mode="friendship"
):

    score = 50


    weights = {

        "dating": {

            "sun": 4,
            "moon": 10,
            "mercury": 6,
            "venus": 10,
            "mars": 8,
        },


        "friendship": {

            "sun": 7,
            "moon": 8,
            "mercury": 7,
            "venus": 4,
            "mars": 4,
        },


        "business": {

            "sun": 6,
            "moon": 3,
            "mercury": 10,
            "venus": 3,
            "mars": 7,
        },
    }


    selected = weights.get(
        mode,
        weights[
            "friendship"
        ]
    )


    for (
        placement,
        weight
    ) in selected.items():


        if (
            person_a[
                placement
            ]
            and
            person_b[
                placement
            ]
        ):


            if (
                person_a[
                    placement
                ]
                ==
                person_b[
                    placement
                ]
            ):

                score += weight


            else:

                difference = abs(

                    SIGNS.index(
                        person_a[
                            placement
                        ]
                    )

                    -

                    SIGNS.index(
                        person_b[
                            placement
                        ]
                    )
                )


                if difference in (
                    2,
                    4,
                    8,
                    10,
                ):

                    score += max(
                        2,
                        weight // 2
                    )


    return max(
        40,
        min(
            95,
            score
        )
    )


def date_idea(
    person_a,
    person_b,
    mode="dating"
):

    if mode == "friendship":

        return (
            "Try a wellness class, café conversation, "
            "nature walk, creator meetup or shared community experience."
        )


    combination = {

        person_a[
            "venus"
        ],

        person_b[
            "venus"
        ],

        person_a[
            "moon"
        ],

        person_b[
            "moon"
        ],
    }


    if (
        "Pisces"
        in combination
        or
        "Cancer"
        in combination
    ):

        return (
            "Consider a waterfront walk, relaxing wellness experience, "
            "sound session or intimate conversation setting."
        )


    if (
        "Leo"
        in combination
        or
        "Aries"
        in combination
    ):

        return (
            "Consider live music, a creative class, "
            "movement experience or energetic local event."
        )


    if (
        "Libra"
        in combination
        or
        "Taurus"
        in combination
    ):

        return (
            "Consider an art experience, beautiful dinner setting, "
            "massage or spa experience, or garden outing."
        )


    if (
        "Gemini"
        in combination
        or
        "Aquarius"
        in combination
    ):

        return (
            "Consider a bookstore, coffee conversation, "
            "unique workshop, community event or creative experience."
        )


    return (
        "Choose an experience that supports conversation, "
        "shared interests and the way both of you naturally connect."
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    connection = conn()


    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            city TEXT DEFAULT '',

            bio TEXT DEFAULT '',

            photo TEXT DEFAULT '',

            profile_headline TEXT DEFAULT '',

            birth_date TEXT DEFAULT '',

            birth_time TEXT DEFAULT '',

            time_known INTEGER DEFAULT 0,

            sun TEXT DEFAULT '',

            moon TEXT DEFAULT '',

            rising TEXT DEFAULT '',

            mercury TEXT DEFAULT '',

            venus TEXT DEFAULT '',

            mars TEXT DEFAULT '',

            jupiter TEXT DEFAULT '',

            saturn TEXT DEFAULT '',

            uranus TEXT DEFAULT '',

            neptune TEXT DEFAULT '',

            pluto TEXT DEFAULT '',

            is_admin INTEGER DEFAULT 0,

            is_creator INTEGER DEFAULT 0,

            creator_access INTEGER DEFAULT 0,

            business_access INTEGER DEFAULT 0,

            membership_access INTEGER DEFAULT 0,

            dating_active INTEGER DEFAULT 0,

            connection_intentions TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS businesses(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_id INTEGER UNIQUE NOT NULL
            REFERENCES users(id)
            ON DELETE CASCADE,

            slug TEXT UNIQUE NOT NULL,

            business_name TEXT NOT NULL,

            creator_title TEXT DEFAULT '',

            tagline TEXT DEFAULT '',

            description TEXT DEFAULT '',

            category TEXT DEFAULT '',

            city TEXT DEFAULT '',

            website TEXT DEFAULT '',

            contact_email TEXT DEFAULT '',

            phone TEXT DEFAULT '',

            logo TEXT DEFAULT '',

            instagram TEXT DEFAULT '',

            tiktok TEXT DEFAULT '',

            youtube TEXT DEFAULT '',

            booking_url TEXT DEFAULT '',

            paid_business INTEGER DEFAULT 0,

            media_kit_enabled INTEGER DEFAULT 0,

            followers TEXT DEFAULT '',

            likes TEXT DEFAULT '',

            views TEXT DEFAULT '',

            audience_info TEXT DEFAULT '',

            content_categories TEXT DEFAULT '',

            collaboration_interests TEXT DEFAULT '',

            retreat_participation INTEGER DEFAULT 0,

            featured_order INTEGER DEFAULT 999,

            status TEXT DEFAULT 'active'
        );


        CREATE TABLE IF NOT EXISTS posts(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS connection_posts(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            media_path TEXT DEFAULT '',

            media_type TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS journals(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            sky_json TEXT DEFAULT '{}',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS messages(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            recipient_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            message_type TEXT DEFAULT 'people',

            subject TEXT DEFAULT '',

            body TEXT NOT NULL,

            read_at TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS notifications(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            notification_type TEXT DEFAULT 'general',

            title TEXT NOT NULL,

            body TEXT NOT NULL,

            link TEXT DEFAULT '',

            read_at TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS retreats(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            title TEXT NOT NULL,

            season TEXT DEFAULT '',

            retreat_type TEXT DEFAULT '',

            area TEXT DEFAULT '',

            preferred_dates TEXT DEFAULT '',

            guests INTEGER DEFAULT 1,

            budget TEXT DEFAULT '',

            lodging_preferences TEXT DEFAULT '',

            wellness_interests TEXT DEFAULT '',

            location_status TEXT DEFAULT 'Searching',

            connection_retreat INTEGER DEFAULT 0,

            status TEXT DEFAULT 'planning',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS retreat_partners(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            retreat_id INTEGER
            REFERENCES retreats(id)
            ON DELETE CASCADE,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            availability_status TEXT DEFAULT 'requested',

            UNIQUE(
                retreat_id,
                business_id
            )
        );


        CREATE TABLE IF NOT EXISTS retreat_messages(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            retreat_id INTEGER
            REFERENCES retreats(id)
            ON DELETE CASCADE,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE CASCADE,

            body TEXT NOT NULL,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS business_content(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            content_type TEXT DEFAULT 'post',

            caption TEXT DEFAULT '',

            media_path TEXT DEFAULT '',

            media_type TEXT DEFAULT '',

            active INTEGER DEFAULT 1,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS business_items(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            item_type TEXT DEFAULT 'service',

            title TEXT NOT NULL,

            description TEXT DEFAULT '',

            price TEXT DEFAULT '',

            action_url TEXT DEFAULT '',

            active INTEGER DEFAULT 1,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS collaboration_requests(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            business_id INTEGER
            REFERENCES businesses(id)
            ON DELETE CASCADE,

            sender_id INTEGER
            REFERENCES users(id)
            ON DELETE SET NULL,

            request_type TEXT DEFAULT 'Collaboration',

            message TEXT DEFAULT '',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


    # --------------------------------------------------------
    # SAFE MIGRATIONS
    # --------------------------------------------------------

    user_migrations = {

        "community_enabled":
            "INTEGER DEFAULT 1",

        "conscious_connections_enabled":
            "INTEGER DEFAULT 0",

        "connection_type":
            "TEXT DEFAULT ''",

        "business_interest":
            "INTEGER DEFAULT 0",

        "last_moon_sign":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in user_migrations.items():

        ensure_column(
            connection,
            "users",
            column_name,
            definition
        )


    business_migrations = {

        "hero_image":
            "TEXT DEFAULT ''",

        "featured_video":
            "TEXT DEFAULT ''",

        "previous_collaborations":
            "TEXT DEFAULT ''",

        "engagement_rate":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in business_migrations.items():

        ensure_column(
            connection,
            "businesses",
            column_name,
            definition
        )


    post_migrations = {

        "media_path":
            "TEXT DEFAULT ''",

        "media_type":
            "TEXT DEFAULT ''",
    }


    for (
        column_name,
        definition
    ) in post_migrations.items():

        ensure_column(
            connection,
            "posts",
            column_name,
            definition
        )


    ensure_column(
        connection,
        "retreats",
        "connection_retreat",
        "INTEGER DEFAULT 0"
    )


    # --------------------------------------------------------
    # REMOVE OLD MOCK MEMBERS / BUSINESSES
    # --------------------------------------------------------

    for email in DEMO_EMAILS:

        row = connection.execute(
            """
            SELECT id
            FROM users
            WHERE lower(email)=?
            """,
            (
                email,
            )
        ).fetchone()


        if row:

            connection.execute(
                """
                DELETE FROM users
                WHERE id=?
                """,
                (
                    row[
                        "id"
                    ],
                )
            )


    placeholders = ",".join(
        "?"
        for _
        in DEMO_SLUGS
    )


    connection.execute(
        f"""
        DELETE FROM businesses
        WHERE slug IN ({placeholders})
        """,
        DEMO_SLUGS
    )


    # --------------------------------------------------------
    # GALAXY EVE
    # --------------------------------------------------------

    galaxy_user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE lower(email)=?
        """,
        (
            GALAXY_EMAIL,
        )
    ).fetchone()


    if not galaxy_user:

        cursor = connection.execute(
            """
            INSERT INTO users(

                name,

                email,

                password,

                bio,

                profile_headline,

                is_creator,

                creator_access,

                business_access,

                membership_access,

                community_enabled,

                conscious_connections_enabled,

                connection_type,

                business_interest
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,

                1,
                1,
                1,
                1,
                1,
                1,

                'Both',

                1
            )
            """,
            (

                "Galaxy Eve",

                GALAXY_EMAIL,

                hp(
                    os.environ.get(
                        "GALAXY_EVE_INITIAL_PASSWORD",
                        "ChangeMeGalaxyEve!"
                    )
                ),

                (
                    "Wellness creator documenting connection, "
                    "self-discovery, experiences and Conscious Coordination."
                ),

                (
                    "Conscious Coordinator • "
                    "Content Creator"
                ),
            )
        )


        galaxy_id = (
            cursor.lastrowid
        )


    else:

        galaxy_id = galaxy_user[
            "id"
        ]


        connection.execute(
            """
            UPDATE users

            SET

                is_creator=1,

                creator_access=1,

                business_access=1,

                membership_access=1,

                community_enabled=1,

                conscious_connections_enabled=1,

                connection_type=
                    CASE
                    WHEN connection_type=''
                    THEN 'Both'
                    ELSE connection_type
                    END,

                business_interest=1

            WHERE id=?
            """,
            (
                galaxy_id,
            )
        )


    galaxy_business = connection.execute(
        """
        SELECT *
        FROM businesses
        WHERE owner_id=?
        """,
        (
            galaxy_id,
        )
    ).fetchone()


    if not galaxy_business:

        connection.execute(
            """
            INSERT INTO businesses(

                owner_id,

                slug,

                business_name,

                creator_title,

                tagline,

                description,

                category,

                contact_email,

                paid_business,

                media_kit_enabled,

                retreat_participation,

                featured_order,

                status
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,

                1,
                1,
                1,
                1,

                'active'
            )
            """,
            (

                galaxy_id,

                "galaxy-eve",

                "Galaxy Eve",

                (
                    "Conscious Coordinator • "
                    "Content Creator"
                ),

                (
                    "Content • Collaborations • "
                    "Creator Experiences"
                ),

                (
                    "Content, collaborations, creator experiences, "
                    "meetups, retreats and Conscious Coordination."
                ),

                "Creator",

                GALAXY_EMAIL,
            )
        )


    else:

        connection.execute(
            """
            UPDATE businesses

            SET

                paid_business=1,

                media_kit_enabled=1,

                retreat_participation=1,

                featured_order=1,

                status='active'

            WHERE owner_id=?
            """,
            (
                galaxy_id,
            )
        )


    for email in ADMIN_EMAILS:

        connection.execute(
            """
            UPDATE users

            SET is_admin=1

            WHERE lower(email)=?
            """,
            (
                email,
            )
        )


    connection.commit()

    connection.close()


# ============================================================
# TEMPLATES
# ============================================================

T = {}


# ============================================================
# GLOBAL APP SHELL
# ============================================================

T["base.html"] = r'''
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
The Seasons Within
</title>

<style>

:root {

    --plum:#34204f;

    --purple:#8f63ba;

    --purple2:#a979c8;

    --lav:#f1e7f8;

    --blush:#fff1ef;

    --line:#eadff1;

    --muted:#786a85;

    --shadow:
        0 14px 36px
        rgba(72,42,96,.08);
}


* {
    box-sizing:border-box;
}


body {

    margin:0;

    background:
        linear-gradient(
            180deg,
            #fcf9fd,
            #fffaf8 55%,
            #faf6fc
        );

    color:
        var(--plum);

    font-family:
        Arial,
        Helvetica,
        sans-serif;
}


a {

    text-decoration:none;

    color:inherit;
}


img {

    max-width:100%;
}


.top {

    position:sticky;

    top:0;

    z-index:50;

    background:
        rgba(
            255,
            255,
            255,
            .96
        );

    backdrop-filter:
        blur(16px);

    border-bottom:
        1px solid
        var(--line);
}


.topin {

    width:
        min(
            1220px,
            94vw
        );

    min-height:
        82px;

    margin:auto;

    display:grid;

    grid-template-columns:
        auto 1fr auto;

    align-items:center;

    gap:24px;
}


.brand {

    display:flex;

    align-items:center;

    gap:10px;
}


.brand img {

    width:52px;

    height:52px;

    object-fit:contain;
}


.brandcopy {

    display:flex;

    flex-direction:column;
}


.brandcopy strong {

    font:
        700 20px
        Georgia;
}


.brandcopy small {

    font-size:10px;

    text-transform:uppercase;

    letter-spacing:1.2px;

    color:var(--muted);

    margin-top:4px;
}


.nav {

    display:flex;

    justify-content:center;

    gap:6px;

    flex-wrap:wrap;
}


.nav a {

    padding:
        10px 12px;

    border-radius:
        999px;

    font-size:14px;

    font-weight:700;

    color:#62546d;
}


.nav a:hover,

.nav a.active {

    background:
        var(--lav);

    color:#68428a;
}


.account {

    display:flex;

    align-items:center;

    gap:10px;
}


.acct {

    display:flex;

    align-items:center;

    gap:7px;

    padding:
        5px 9px;

    border:
        1px solid
        var(--line);

    border-radius:
        999px;

    background:white;
}


.acct img,

.initial {

    width:30px;

    height:30px;

    border-radius:50%;

    object-fit:cover;
}


.initial {

    display:grid;

    place-items:center;

    background:
        linear-gradient(
            135deg,
            var(--purple),
            #c58dbe
        );

    color:white;
}


.wrap {

    width:
        min(
            1140px,
            92vw
        );

    margin:
        30px auto
        90px;
}


.hero {

    background:
        linear-gradient(
            135deg,
            #f1e3fb,
            #fff0ec
        );

    border:
        1px solid
        var(--line);

    border-radius:
        26px;

    padding:32px;

    box-shadow:
        var(--shadow);

    display:flex;

    align-items:center;

    justify-content:
        space-between;

    gap:24px;
}


.hero h1 {

    font:
        700 44px/1.03
        Georgia;

    margin:
        8px 0 12px;
}


.hero-logo {

    width:140px;

    height:140px;

    object-fit:contain;
}


.card {

    background:white;

    border:
        1px solid
        var(--line);

    border-radius:
        20px;

    padding:20px;

    box-shadow:
        var(--shadow);

    margin:
        14px 0;
}


.grid {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                230px,
                1fr
            )
        );

    gap:16px;
}


.two {

    display:grid;

    grid-template-columns:
        1fr 1fr;

    gap:16px;
}


.sectionhead {

    display:flex;

    justify-content:
        space-between;

    align-items:end;

    gap:18px;
}


.kicker,

.sectionhead span {

    font-size:11px;

    letter-spacing:
        1.3px;

    font-weight:800;

    color:#8b6a9a;
}


h1,

h2,

h3 {

    font-family:
        Georgia,
        serif;
}


h2 {

    font-size:30px;
}


.btn,

.outline,

button {

    display:inline-flex;

    align-items:center;

    justify-content:center;

    min-height:42px;

    padding:
        10px 16px;

    border-radius:
        11px;

    font-weight:700;
}


.btn,

button {

    border:
        1px solid
        var(--purple);

    background:
        linear-gradient(
            135deg,
            var(--purple),
            var(--purple2)
        );

    color:white;
}


.outline {

    border:
        1px solid
        #cdb6dd;

    background:white;

    color:#68428a;
}


.actions {

    display:flex;

    gap:10px;

    flex-wrap:wrap;
}


input,

textarea,

select {

    width:100%;

    padding:11px;

    border:
        1px solid
        var(--line);

    border-radius:10px;

    background:#fff;

    margin:
        5px 0 12px;
}


textarea {

    min-height:105px;
}


.chips {

    display:flex;

    gap:7px;

    flex-wrap:wrap;
}


.chips span,

.chips a {

    background:
        var(--lav);

    padding:
        7px 9px;

    border-radius:
        999px;

    font-size:12px;
}


.muted {

    color:
        var(--muted);
}


.flash {

    width:
        min(
            1140px,
            92vw
        );

    margin:
        12px auto;

    background:
        #f0e4f8;

    padding:11px;

    border-radius:10px;
}


.portrait {

    width:110px;

    height:110px;

    object-fit:cover;

    border-radius:50%;
}


.empty {

    text-align:center;

    border:
        1px dashed
        #d9c8e5;

    border-radius:18px;

    padding:28px;

    color:
        var(--muted);
}


.moon-card {

    display:grid;

    grid-template-columns:
        130px 1fr;

    gap:20px;

    align-items:center;
}


.moon-picture {

    width:120px;

    height:120px;

    border-radius:50%;

    display:grid;

    place-items:center;

    background:
        radial-gradient(
            circle at 35% 30%,
            #fff,
            #ece6f0 58%,
            #c8bdd0 100%
        );

    font-size:78px;

    box-shadow:

        inset
        -12px
        -14px
        24px
        rgba(
            76,
            57,
            87,
            .18
        ),

        0 12px
        28px
        rgba(
            89,
            60,
            112,
            .12
        );
}


.business-store-card {

    padding:0;

    overflow:hidden;
}


.store-media {

    height:210px;

    background:
        linear-gradient(
            135deg,
            #e9d8f5,
            #fff0ed
        );

    display:grid;

    place-items:center;

    overflow:hidden;
}


.store-media img,

.store-media video {

    width:100%;

    height:100%;

    object-fit:cover;
}


.store-logo-fallback {

    width:110px !important;

    height:110px !important;

    object-fit:contain !important;
}


.store-body {

    padding:18px;
}


.store-links {

    display:flex;

    flex-wrap:wrap;

    gap:8px;

    margin-top:14px;
}


.badge {

    display:inline-block;

    padding:
        6px 8px;

    border-radius:
        999px;

    background:
        var(--lav);

    font-size:11px;

    font-weight:800;

    color:#68428a;
}


.posthead {

    display:flex;

    justify-content:
        space-between;

    gap:10px;

    align-items:center;
}


.postperson {

    display:flex;

    align-items:center;

    gap:9px;
}


.postperson img,

.avatar {

    width:42px;

    height:42px;

    border-radius:50%;

    object-fit:cover;
}


.post-image {

    width:100%;

    max-height:480px;

    object-fit:cover;

    border-radius:15px;

    margin-top:12px;
}


.content-media {

    width:100%;

    max-height:420px;

    object-fit:cover;

    border-radius:14px;
}


.content-video {

    width:100%;

    max-height:420px;

    border-radius:14px;

    background:#000;
}


.profile-tools {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                180px,
                1fr
            )
        );

    gap:12px;
}


.tool {

    border:
        1px solid
        var(--line);

    border-radius:16px;

    padding:16px;

    background:white;
}


.media-kit-grid {

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                150px,
                1fr
            )
        );

    gap:10px;
}


.stat {

    background:
        var(--lav);

    border-radius:14px;

    padding:14px;
}


.mobilebar {

    display:none;
}


@media(
    max-width:850px
) {

    .topin {

        grid-template-columns:
            auto 1fr;
    }


    .account {

        display:none;
    }


    .nav {

        justify-content:
            flex-end;
    }


    .two {

        grid-template-columns:
            1fr;
    }
}


@media(
    max-width:700px
) {

    body {

        padding-bottom:78px;
    }


    .topin {

        display:flex;

        justify-content:center;

        min-height:70px;
    }


    .brand img {

        width:45px;

        height:45px;
    }


    .brandcopy strong {

        font-size:18px;
    }


    .nav,

    .account {

        display:none;
    }


    .wrap {

        width:
            min(
                94vw,
                700px
            );

        margin-top:20px;
    }


    .hero {

        padding:22px;

        align-items:
            flex-start;
    }


    .hero h1 {

        font-size:35px;
    }


    .hero-logo {

        width:82px;

        height:82px;
    }


    .moon-card {

        grid-template-columns:
            90px 1fr;
    }


    .moon-picture {

        width:84px;

        height:84px;

        font-size:52px;
    }


    .mobilebar {

        position:fixed;

        left:50%;

        bottom:10px;

        transform:
            translateX(-50%);

        z-index:60;

        width:
            min(
                95vw,
                620px
            );

        display:flex;

        justify-content:
            space-around;

        gap:4px;

        padding:7px;

        background:
            rgba(
                255,
                255,
                255,
                .96
            );

        border:
            1px solid
            var(--line);

        border-radius:20px;

        box-shadow:
            0 14px 36px
            rgba(
                72,
                42,
                96,
                .18
            );
    }


    .mobilebar a {

        display:flex;

        flex-direction:
            column;

        align-items:center;

        gap:3px;

        padding:7px;

        border-radius:12px;

        font-size:9px;

        font-weight:800;

        color:
            var(--muted);
    }


    .mobilebar a.active {

        background:
            var(--lav);

        color:#68428a;
    }


    .mobilebar b {

        font-size:17px;
    }
}

</style>

</head>


<body>


<header class="top">


<div class="topin">


<a
    class="brand"
    href="{{url_for('public_home')}}"
>


<img

    src="{{url_for('static',filename='seasons-within-logo.png')}}"

    alt="The Seasons Within"
>


<span class="brandcopy">


<strong>
The Seasons Within
</strong>


<small>
Conscious Coordination
</small>


</span>


</a>


<nav class="nav">


<a
    href="{{url_for('public_home')}}"
    class="{% if request.endpoint in ['public_home','home'] %}active{% endif %}"
>

Home

</a>


{% if me %}


<a
    href="{{url_for('profile')}}"
    class="{% if request.endpoint in ['profile','profile_edit','journal','community','messages','notifications','connections','connection_profile'] %}active{% endif %}"
>

My Profile

</a>


{% endif %}


<a
    href="{{url_for('business')}}"
    class="{% if request.endpoint in ['business','business_setup','business_app','business_manage'] %}active{% endif %}"
>

Business Network

</a>


<a
    href="{{url_for('retreats')}}"
    class="{% if request.endpoint in ['retreats','retreat_build','retreat_detail'] %}active{% endif %}"
>

Retreats

</a>


<a
    href="{{url_for('membership')}}"
    class="{% if request.endpoint=='membership' %}active{% endif %}"
>

Membership

</a>


</nav>


<div class="account">


{% if me %}


<a
    class="acct"
    href="{{url_for('profile')}}"
>


{% if me.photo %}


<img
    src="{{media_url(me.photo)}}"
    alt=""
>


{% else %}


<span class="initial">
{{me.name[:1]}}
</span>


{% endif %}


<span>
{{me.name}}
</span>


</a>


<a href="{{url_for('logout')}}">

Log Out

</a>


{% else %}


<a href="{{url_for('login')}}">

Log In

</a>


<a
    class="btn"
    href="{{url_for('join')}}"
>

Join Free

</a>


{% endif %}


</div>


</div>


</header>


{% with messages=get_flashed_messages() %}


{% if messages %}


<div class="flash">

{{messages|join(' • ')}}

</div>


{% endif %}


{% endwith %}


<main class="wrap">

{% block content %}

{% endblock %}

</main>


<nav class="mobilebar">


<a
    href="{{url_for('public_home')}}"
>

<b>⌂</b>

Home

</a>


{% if me %}


<a
    href="{{url_for('profile')}}"
>

<b>◉</b>

Profile

</a>


{% endif %}


<a
    href="{{url_for('business')}}"
>

<b>◇</b>

Business

</a>


<a
    href="{{url_for('retreats')}}"
>

<b>✦</b>

Retreats

</a>


<a
    href="{{url_for('membership')}}"
>

<b>♡</b>

Membership

</a>


</nav>


</body>

</html>
'''


# ============================================================
# SHARED BUSINESS CARD
# ============================================================

T["business_card.html"] = r'''

<article class="card business-store-card">


<div class="store-media">


{% if b.paid_business and b.featured_video %}


<video
    src="{{media_url(b.featured_video)}}"
    muted
    playsinline
    controls
>
</video>


{% elif b.paid_business and b.hero_image %}


<img
    src="{{media_url(b.hero_image)}}"
    alt="{{b.business_name}}"
>


{% elif b.logo %}


<img
    class="store-logo-fallback"
    src="{{media_url(b.logo)}}"
    alt="{{b.business_name}}"
>


{% else %}


<img
    class="store-logo-fallback"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


</div>


<div class="store-body">


<span class="badge">

{{'Hosted App' if b.paid_business else 'Free Listing'}}

</span>


<h3>
{{b.business_name}}
</h3>


<p>

<b>

{{b.creator_title or b.category}}

</b>


{% if b.city %}

•
{{b.city}}

{% endif %}

</p>


<small>

{{b.tagline or b.description}}

</small>


<div class="store-links">


<a
    class="btn"
    href="{{url_for('business_app',slug=b.slug)}}"
>

{{'Open App' if b.paid_business else 'View Business'}}

</a>


{% if b.website %}


<a
    class="outline"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Business Link

</a>


{% endif %}


</div>


</div>


</article>
'''


# ============================================================
# HOME = MARKETPLACE
# ============================================================

T["public.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>

Connect With Intention.
Discover Your Seasons Within.

</h1>


<p>

The marketplace for wellness businesses,
hosted apps,
retreats
and conscious community.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('business')}}"
>

Explore Businesses & Apps

</a>


{% if me %}


<a
    class="outline"
    href="{{url_for('community')}}"
>

Enter Member Community

</a>


{% else %}


<a
    class="outline"
    href="{{url_for('join')}}"
>

Join Free

</a>


{% endif %}


</div>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<section class="card moon-card">


<div class="moon-picture">

{{sky.moon_symbol}}

</div>


<div>


<span class="kicker">
MOON TODAY
</span>


<h2>

Moon in

{{sky.moon_sign or 'the current sky'}}

</h2>


<p>


<b>

{{sky.moon_phase or 'Current lunar phase'}}

</b>


{% if sky.moon_degree is not none %}


•
{{sky.moon_degree}}°


{% endif %}


</p>


<div class="chips">


{% for p in ['Mercury','Venus','Mars','Jupiter','Saturn'] %}


{% if sky.positions.get(p) %}


<span>


<b>
{{p}}
</b>


{{sky.positions[p]['sign']}}


</span>


{% endif %}


{% endfor %}


</div>


<small class="muted">

Current sky information is reflective context,
not prediction.

</small>


</div>


</section>


<section>


<div class="sectionhead">


<div>


<span>
BUSINESS NETWORK
</span>


<h2>

Businesses & Apps Within
The Seasons Within

</h2>


</div>


<a href="{{url_for('business')}}">

View All →

</a>


</div>


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Real businesses will appear here
as they create profiles.

</div>


{% endfor %}


</div>


</section>


<section class="card">


<span class="kicker">
RETREAT CONSTELLATION
</span>


<h2>
Build a Wellness Retreat
</h2>


<p>

Choose your season,
dates,
group size,
budget
and participating wellness partners.

The Seasons Within can help coordinate
partner availability
and locate a private retreat property
that fits the experience.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('retreat_build')}}"
>

Build My Retreat Constellation

</a>


<a
    class="outline"
    href="{{url_for('retreats')}}"
>

Explore Retreats

</a>


</div>


</section>


{% endblock %}
'''


# ============================================================
# JOIN / ONBOARDING
# ============================================================

T["join.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Join The Seasons Within
</h1>


<form
    method="post"
    class="card"
>


<label>

Name

<input
    name="name"
    required
>

</label>


<label>

Email

<input
    name="email"
    type="email"
    required
>

</label>


<label>

Password

<input
    name="password"
    type="password"
    minlength="6"
    required
>

</label>


<h2>

How would you like to connect
within The Seasons Within?

</h2>


<label>

<input
    type="checkbox"
    name="community_enabled"
    value="1"
    checked
>

<b>
Community
</b>

—
wellness,
reflection,
conversations
and shared experiences

</label>


<br><br>


<label>

<input
    type="checkbox"
    name="conscious_connections_enabled"
    value="1"
>

<b>

Conscious Connections —
Love, Dating & Friendship

</b>

</label>


<br><br>


<label>

<input
    type="checkbox"
    name="business_interest"
    value="1"
>

<b>
Business
</b>

—
create a business profile
or connect professionally

</label>


<br><br>


<button class="btn">

Create Free Account

</button>


</form>


{% endblock %}
'''


T["onboarding.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Set Up Your Profile
</h1>


<form
    method="post"
    class="card"
>


{% if u.conscious_connections_enabled %}


<h2>
Conscious Connections
</h2>


<p>

What connections are you open to?

</p>


<select name="connection_type">


<option value="Love & Dating">

Love & Dating

</option>


<option value="Friendship">

Friendship

</option>


<option value="Both">

Both

</option>


</select>


<p>

Your normal Seasons Within profile
remains your main profile.

This choice activates your private
Love / Dating / Friendship community profile.

</p>


{% endif %}


{% if u.business_interest %}


<h2>
Business
</h2>


<p>

You can create your free business listing
after your member profile is saved.

</p>


{% endif %}


<button class="btn">

Continue to My Profile

</button>


</form>


{% endblock %}
'''


# ============================================================
# GENERAL COMMUNITY
# ============================================================

T["community.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
MEMBER COMMUNITY
</span>


<h1>
Community
</h1>


<p>

Post,
reflect
and connect privately
with other members.

</p>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<section class="two">


<article class="card">


<span class="kicker">
THE SEASON WE'RE IN
</span>


<h2>
{{reflection.sky.season}}
</h2>


<p>

<b>
Journal • Reflect
</b>

</p>


<p>

Let the current season
and Moon invite reflection
on your pace,
relationships
and what deserves conscious attention.

</p>


<a
    class="outline"
    href="{{url_for('journal')}}"
>

Open My Private Journal

</a>


</article>


<article class="card">


<span class="kicker">
MOON TODAY
</span>


<h2>

{{reflection.sky.moon_symbol}}

Moon in

{{reflection.sky.moon_sign or 'the current sky'}}

</h2>


<p>

{{reflection.sky.moon_phase or 'Current lunar phase'}}


{% if reflection.sky.moon_degree is not none %}

•
{{reflection.sky.moon_degree}}°

{% endif %}

</p>


</article>


</section>


<h2>
Share With Community
</h2>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<textarea
    name="body"
    placeholder="Share a thought, reflection, question or part of your journey..."
>
</textarea>


<label>

Add Photo
(optional)

<input
    type="file"
    name="photo"
    accept="image/*"
>

</label>


<button class="btn">

Post to Community

</button>


</form>


{% for p in posts %}


<article class="card">


<div class="posthead">


<div class="postperson">


{% if p.photo %}


<img
    src="{{media_url(p.photo)}}"
    alt=""
>


{% else %}


<span class="initial avatar">

{{p.name[:1]}}

</span>


{% endif %}


<div>


<b>
{{p.name}}
</b>


<small class="muted">

{{p.created_at}}

</small>


</div>


</div>


{% if p.user_id != me.id %}


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=p.user_id,kind='people')}}"
>

Message Member

</a>


{% endif %}


</div>


<p>

{{p.body}}

</p>


{% if p.media_path %}


<img
    class="post-image"
    src="{{media_url(p.media_path)}}"
    alt=""
>


{% endif %}


</article>


{% else %}


<div class="empty">

Member posts will appear here
as the community grows.

</div>


{% endfor %}


<section>


<div class="sectionhead">


<div>


<span>
WELLNESS WITHIN THE COMMUNITY
</span>


<h2>
Businesses & Apps
</h2>


</div>


<a href="{{url_for('business')}}">

View All →

</a>


</div>


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% endfor %}


</div>


</section>


{% endblock %}
'''


# ============================================================
# PROFILE
# ============================================================

T["profile.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="card">


<span class="kicker">
MY PROFILE
</span>


{% if u.photo %}


<img
    class="portrait"
    src="{{media_url(u.photo)}}"
    alt=""
>


{% endif %}


<h1>
{{u.name}}
</h1>


<h3>
{{u.profile_headline}}
</h3>


<p>
{{u.city}}
</p>


<p>
{{u.bio}}
</p>


<div class="chips">


<span>
Sun
{{u.sun or '—'}}
</span>


<span>
Moon
{{u.moon or '—'}}
</span>


<span>
Rising
{{u.rising or '—'}}
</span>


{% if u.membership_access %}


<span>
Mercury
{{u.mercury or '—'}}
</span>


<span>
Venus
{{u.venus or '—'}}
</span>


<span>
Mars
{{u.mars or '—'}}
</span>


<span>
Jupiter
{{u.jupiter or '—'}}
</span>


<span>
Saturn
{{u.saturn or '—'}}
</span>


<span>
Uranus
{{u.uranus or '—'}}
</span>


<span>
Neptune
{{u.neptune or '—'}}
</span>


<span>
Pluto
{{u.pluto or '—'}}
</span>


{% endif %}


</div>


<a
    class="btn"
    href="{{url_for('profile_edit')}}"
>

Edit My Profile

</a>


</section>


<section class="card">


<span class="kicker">
PRIVATE JOURNAL ENTRY — TODAY
</span>


<h2>

{{reflection.sky.moon_symbol}}

{{reflection.headline}}

</h2>


<p>
{{reflection.prompt}}
</p>


<a
    class="btn"
    href="{{url_for('journal')}}"
>

Open My Journal

</a>


</section>


<section class="profile-tools">


{% if u.community_enabled %}


<a
    class="tool"
    href="{{url_for('community')}}"
>

<b>
Community
</b>

<br>

<small>

Post and see member reflections.

</small>

</a>


{% endif %}


<a
    class="tool"
    href="{{url_for('messages')}}"
>

<b>
My Inbox
</b>

<br>

<small>

Private people,
dating,
business
and retreat messages.

</small>

</a>


<a
    class="tool"
    href="{{url_for('notifications')}}"
>

<b>
My Notifications
</b>

<br>

<small>

Private astrology,
connection
and business updates.

</small>

</a>


{% if u.conscious_connections_enabled %}


<a
    class="tool"
    href="{{url_for('connections')}}"
>

<b>
♡ Conscious Connections
</b>

<br>

<small>

{{u.connection_type or 'Love, Dating & Friendship'}}

•
private community,
compatibility
and date/friendship ideas.

</small>

</a>


{% else %}


<a
    class="tool"
    href="{{url_for('enable_connections')}}"
>

<b>
♡ Join Conscious Connections
</b>

<br>

<small>

Opt in to
Love,
Dating
& Friendship later.

</small>

</a>


{% endif %}


<a
    class="tool"
    href="{{url_for('business_setup')}}"
>

<b>
My Business Listing / App
</b>

<br>

<small>

Create or manage
your business presence.

</small>

</a>


{% if u.business_access %}


<a
    class="tool"
    href="{{url_for('business_manage')}}"
>

<b>
Manage Hosted App
</b>

<br>

<small>

Upload videos,
content,
services,
meetups
and more.

</small>

</a>


{% endif %}


</section>


{% endblock %}
'''


T["profile_edit.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Edit My Profile
</h1>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<label>

Profile Picture

<input
    type="file"
    name="photo"
>

</label>


<label>

Name

<input
    name="name"
    value="{{u.name}}"
>

</label>


<label>

City

<input
    name="city"
    value="{{u.city}}"
>

</label>


<label>

Headline

<input
    name="profile_headline"
    value="{{u.profile_headline}}"
>

</label>


<label>

About

<textarea
    name="bio"
>
{{u.bio}}
</textarea>

</label>


<label>

Birth Date

<input
    type="date"
    name="birth_date"
    value="{{u.birth_date}}"
>

</label>


<label>

Birth Time

<input
    type="time"
    name="birth_time"
    value="{{u.birth_time}}"
>

</label>


<label>

<input
    type="checkbox"
    name="time_known"
    {% if u.time_known %}checked{% endif %}
>

Exact birth time known

</label>


{% if u.conscious_connections_enabled %}


<label>

Conscious Connections

<select name="connection_type">


<option value="Love & Dating">

Love & Dating

</option>


<option value="Friendship">

Friendship

</option>


<option value="Both">

Both

</option>


</select>


</label>


{% endif %}


<button class="btn">

Save Profile

</button>


</form>


{% endblock %}
'''


# ============================================================
# JOURNAL
# ============================================================

T["journal.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Private Journal
</h1>


<article class="card">


<span class="kicker">
TODAY'S REFLECTION
</span>


<h2>

{{reflection.sky.moon_symbol}}

Moon in

{{reflection.sky.moon_sign or 'the current sky'}}

</h2>


<p>

{{reflection.sky.moon_phase or 'Current lunar phase'}}


{% if reflection.sky.moon_degree is not none %}

•
{{reflection.sky.moon_degree}}°

{% endif %}

</p>


<p>
{{reflection.prompt}}
</p>


<form method="post">


<textarea
    name="body"
    placeholder="What are you noticing within yourself today?"
>
</textarea>


<button class="btn">

Save Journal Entry

</button>


</form>


</article>


{% for e in entries %}


<article class="card">


<small>
{{e.created_at}}
</small>


<p>
{{e.body}}
</p>


</article>


{% endfor %}


{% endblock %}
'''


# ============================================================
# CONSCIOUS CONNECTIONS
# ============================================================

T["connections_join.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Join Conscious Connections
</h1>


<form
    method="post"
    class="card"
>


<p>

Conscious Connections is the private
Love,
Dating
& Friendship community
inside The Seasons Within.

</p>


<select name="connection_type">


<option>
Love & Dating
</option>


<option>
Friendship
</option>


<option>
Both
</option>


</select>


<button class="btn">

Join Conscious Connections

</button>


</form>


{% endblock %}
'''


T["connections.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
PRIVATE MEMBER COMMUNITY
</span>


<h1>
♡ Conscious Connections
</h1>


<p>

Love,
Dating
& Friendship

•
private posts

•
zodiac/natal compatibility

•
date
and friendship experiences

</p>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<div class="chips">


<a href="?mode=dating">

Love & Dating

</a>


<a href="?mode=friendship">

Friendship

</a>


<a href="?mode=all">

Both

</a>


</div>


<h2>
Conscious Connections Community
</h2>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<textarea
    name="body"
    placeholder="Post to the Love, Dating & Friendship community..."
>
</textarea>


{% if host_media %}


<label>

Host/Admin Photo or Video

<input
    type="file"
    name="media"
>

</label>


{% endif %}


<button class="btn">

Post

</button>


<small class="muted">

Regular members post text only.

Galaxy Eve and admins
may post photos and videos.

</small>


</form>


{% for p in posts %}


<article class="card">


<div class="posthead">


<div class="postperson">


{% if p.photo %}


<img
    src="{{media_url(p.photo)}}"
    alt=""
>


{% else %}


<span class="initial avatar">

{{p.name[:1]}}

</span>


{% endif %}


<div>


<b>
{{p.name}}
</b>


<small class="muted">

{{p.created_at}}

</small>


</div>


</div>


{% if p.user_id != me.id %}


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=p.user_id,kind='dating')}}"
>

Message Member

</a>


{% endif %}


</div>


<p>
{{p.body}}
</p>


{% if p.media_path %}


{% if p.media_type=='video' %}


<video
    class="content-video"
    src="{{media_url(p.media_path)}}"
    controls
>
</video>


{% else %}


<img
    class="post-image"
    src="{{media_url(p.media_path)}}"
    alt=""
>


{% endif %}


{% endif %}


</article>


{% else %}


<div class="empty">

Connection-community posts
will appear here.

</div>


{% endfor %}


<h2>
Discover Members
</h2>


<div class="grid">


{% for p,score in cards %}


<article class="card">


<h3>
{{p.name}}
</h3>


<p>
{{p.city}}
</p>


<p>
{{p.connection_type}}
</p>


<b>

{{score}}%
Conscious Coordination

</b>


<p>


<a
    class="btn"
    href="{{url_for('connection_profile',uid=p.id,mode=mode)}}"
>

View Compatibility

</a>


</p>


</article>


{% else %}


<div class="empty">

Other opted-in members
will appear here as they join.

</div>


{% endfor %}


</div>


<section>


<div class="sectionhead">


<div>


<span>
CONNECTION EXPERIENCES
</span>


<h2>

Businesses & Apps for
Dates,
Friendships
& Retreats

</h2>


</div>


</div>


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% endfor %}


</div>


</section>


{% endblock %}
'''


T["connection_profile.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
{{person.name}}
</h1>


<article class="card">


<h2>

{{score}}%
Conscious Coordination

</h2>


<p>
{{person.connection_type}}
</p>


<div class="chips">


<span>

Sun
{{person.sun or '—'}}

</span>


<span>

Moon
{{person.moon or '—'}}

</span>


{% if me.membership_access %}


<span>
Mercury
{{person.mercury or '—'}}
</span>


<span>
Venus
{{person.venus or '—'}}
</span>


<span>
Mars
{{person.mars or '—'}}
</span>


<span>
Jupiter
{{person.jupiter or '—'}}
</span>


<span>
Saturn
{{person.saturn or '—'}}
</span>


<span>
Uranus
{{person.uranus or '—'}}
</span>


<span>
Neptune
{{person.neptune or '—'}}
</span>


<span>
Pluto
{{person.pluto or '—'}}
</span>


{% endif %}


</div>


<p>


<b>

{{'Date idea' if mode=='dating' else 'Friendship idea'}}:

</b>


{{idea}}


</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('compose_message',recipient_id=person.id,kind='dating' if mode=='dating' else 'people')}}"
>

Message Privately

</a>


<a
    class="outline"
    href="{{url_for('retreat_build',connection=1)}}"
>

Build a
{{'Date' if mode=='dating' else 'Friendship'}}
Retreat

</a>


</div>


</article>


{% endblock %}
'''


# ============================================================
# BUSINESS NETWORK
# ============================================================

T["business.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>
Business Network
</h1>


<p>

Browse creators,
practitioners,
services,
classes,
retreats
and hosted business apps.

</p>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<form class="card">


<input
    name="q"
    value="{{q}}"
    placeholder="Search businesses, creators, services or categories..."
>


</form>


{% if me %}


<div class="actions">


<a
    class="btn"
    href="{{url_for('business_setup')}}"
>

Create / Manage My Business Listing

</a>


</div>


{% endif %}


<div class="grid">


{% for b in businesses %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Real businesses will appear here
as they create profiles.

</div>


{% endfor %}


</div>


<article class="card">


<b>
Free business listing:
</b>

picture/logo,
bio,
category,
contact
and business link.


<br><br>


<b>

Business Network —
${{BUSINESS_PRICE}}/month:

</b>

hosted Business App,
media,
content,
services,
events,
collaborations
and Retreat Constellation tools.


</article>


{% endblock %}
'''


T["business_setup.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Business Profile / App
</h1>


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<label>

Business Logo

<input
    type="file"
    name="logo"
>

</label>


{% if b and b.logo %}


<img
    style="
        width:100px;
        height:100px;
        object-fit:cover;
        border-radius:16px
    "
    src="{{media_url(b.logo)}}"
    alt=""
>


{% endif %}


<label>

Business Name

<input
    name="business_name"
    value="{{b.business_name if b else ''}}"
    required
>

</label>


<label>

Creator / Professional Title

<input
    name="creator_title"
    value="{{b.creator_title if b else ''}}"
>

</label>


<label>

Tagline

<input
    name="tagline"
    value="{{b.tagline if b else ''}}"
>

</label>


<label>

Description / Bio

<textarea
    name="description"
>
{{b.description if b else ''}}
</textarea>

</label>


<label>

Category

<input
    name="category"
    value="{{b.category if b else ''}}"
>

</label>


<label>

City

<input
    name="city"
    value="{{b.city if b else ''}}"
>

</label>


<label>

Business / Website Link

<input
    name="website"
    value="{{b.website if b else ''}}"
>

</label>


<label>

Contact Email

<input
    name="contact_email"
    value="{{b.contact_email if b else me.email}}"
>

</label>


<label>

Phone

<input
    name="phone"
    value="{{b.phone if b else ''}}"
>

</label>


{% if me.business_access %}


<hr>


<h2>
Hosted App Media
</h2>


<label>

App Cover Image

<input
    type="file"
    name="hero_image"
>

</label>


<label>

Featured App Video

<input
    type="file"
    name="featured_video"
>

</label>


<label>

Instagram

<input
    name="instagram"
    value="{{b.instagram if b else ''}}"
>

</label>


<label>

TikTok

<input
    name="tiktok"
    value="{{b.tiktok if b else ''}}"
>

</label>


<label>

YouTube

<input
    name="youtube"
    value="{{b.youtube if b else ''}}"
>

</label>


<label>

Booking Link

<input
    name="booking_url"
    value="{{b.booking_url if b else ''}}"
>

</label>


<label>

Content Categories

<input
    name="content_categories"
    value="{{b.content_categories if b else ''}}"
>

</label>


<label>

Audience Information

<textarea
    name="audience_info"
>
{{b.audience_info if b else ''}}
</textarea>

</label>


<label>

Previous Collaborations

<textarea
    name="previous_collaborations"
>
{{b.previous_collaborations if b else ''}}
</textarea>

</label>


<label>

Collaboration Interests

<textarea
    name="collaboration_interests"
>
{{b.collaboration_interests if b else ''}}
</textarea>

</label>


<div class="two">


<label>

Followers

<input
    name="followers"
    value="{{b.followers if b else ''}}"
>

</label>


<label>

Likes

<input
    name="likes"
    value="{{b.likes if b else ''}}"
>

</label>


<label>

Views

<input
    name="views"
    value="{{b.views if b else ''}}"
>

</label>


<label>

Engagement Rate

<input
    name="engagement_rate"
    value="{{b.engagement_rate if b else ''}}"
>

</label>


</div>


<label>


<input
    type="checkbox"
    name="retreat_participation"
    {% if b and b.retreat_participation %}checked{% endif %}
>


Participate in Retreat Constellations


</label>


{% endif %}


<button class="btn">

Save Business Profile

</button>


</form>


{% if b and me.business_access %}


<a
    class="btn"
    href="{{url_for('business_manage')}}"
>

Manage App Content,
Services & Events

</a>


{% endif %}


{% endblock %}
'''


T["business_manage.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Manage
{{b.business_name}}
Hosted App

</h1>


<div class="two">


<form
    method="post"
    enctype="multipart/form-data"
    class="card"
>


<input
    type="hidden"
    name="section"
    value="content"
>


<h2>
Add Content
</h2>


<select name="content_type">


<option value="post">
Update
</option>


<option value="photo">
Photo
</option>


<option value="video">
Video
</option>


<option value="media">
Featured Media
</option>


</select>


<textarea
    name="caption"
    placeholder="Caption or update..."
>
</textarea>


<input
    type="file"
    name="media"
>


<button class="btn">

Publish Content

</button>


</form>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="section"
    value="item"
>


<h2>
Add App Offering
</h2>


<select name="item_type">


<option value="service">
Service
</option>


<option value="class">
Class
</option>


<option value="event">
Event / Meetup
</option>


<option value="retreat">
Retreat
</option>


<option value="membership">
Membership
</option>


<option value="product">
Product
</option>


</select>


<input
    name="title"
    placeholder="Title"
>


<textarea
    name="description"
    placeholder="Description"
>
</textarea>


<input
    name="price"
    placeholder="Price"
>


<input
    name="action_url"
    placeholder="Booking / purchase link"
>


<button class="btn">

Add to App

</button>


</form>


</div>


<h2>
Published Content
</h2>


<div class="grid">


{% for x in content %}


<article class="card">


{% if x.media_path %}


{% if x.media_type=='video' %}


<video
    class="content-video"
    src="{{media_url(x.media_path)}}"
    controls
>
</video>


{% else %}


<img
    class="content-media"
    src="{{media_url(x.media_path)}}"
    alt=""
>


{% endif %}


{% endif %}


<p>
{{x.caption}}
</p>


</article>


{% else %}


<div class="empty">

Your app content
will appear here.

</div>


{% endfor %}


</div>


<h2>

Services,
Events
& Retreats

</h2>


<div class="grid">


{% for x in items %}


<article class="card">


<span class="badge">

{{x.item_type}}

</span>


<h3>
{{x.title}}
</h3>


<p>
{{x.description}}
</p>


<b>
{{x.price}}
</b>


</article>


{% else %}


<div class="empty">

Your app offerings
will appear here.

</div>


{% endfor %}


</div>


{% endblock %}
'''


T["business_app.html"] = r'''

{% extends 'base.html' %}

{% block content %}


{% if not b.paid_business %}


<section class="card">


{% if b.logo %}


<img
    style="
        width:120px;
        height:120px;
        object-fit:cover;
        border-radius:20px
    "
    src="{{media_url(b.logo)}}"
    alt=""
>


{% else %}


<img
    style="
        width:120px;
        height:120px;
        object-fit:contain
    "
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


<span class="badge">

Free Business Listing

</span>


<h1>
{{b.business_name}}
</h1>


<h3>
{{b.creator_title or b.category}}
</h3>


<p>
{{b.description}}
</p>


{% if b.city %}


<p>
{{b.city}}
</p>


{% endif %}


<div class="actions">


{% if b.website %}


<a
    class="btn"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Business Link

</a>


{% endif %}


{% if me and me.id!=owner.id %}


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Contact Business

</a>


{% endif %}


</div>


</section>


{% else %}


<section class="hero">


<div>


<span class="kicker">
HOSTED APP
</span>


<h1>
{{b.business_name}}
</h1>


<h3>
{{b.creator_title or b.category}}
</h3>


<p>
{{b.tagline}}
</p>


<div class="actions">


{% if me and me.id!=owner.id %}


<a
    class="btn"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Message / Contact

</a>


{% endif %}


{% if b.booking_url %}


<a
    class="outline"
    href="{{b.booking_url}}"
    target="_blank"
    rel="noopener"
>

Book / Apply

</a>


{% endif %}


{% if me and me.id==owner.id %}


<a
    class="outline"
    href="{{url_for('business_setup')}}"
>

Edit App

</a>


<a
    class="outline"
    href="{{url_for('business_manage')}}"
>

Manage Content

</a>


{% endif %}


</div>


</div>


{% if b.featured_video %}


<video
    style="
        width:min(430px,45%);
        border-radius:18px;
        background:#000
    "
    src="{{media_url(b.featured_video)}}"
    controls
    playsinline
>
</video>


{% elif b.hero_image %}


<img
    style="
        width:min(430px,45%);
        max-height:300px;
        object-fit:cover;
        border-radius:18px
    "
    src="{{media_url(b.hero_image)}}"
    alt=""
>


{% elif b.logo %}


<img
    class="hero-logo"
    src="{{media_url(b.logo)}}"
    alt=""
>


{% else %}


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


{% endif %}


</section>


<div class="grid">


<article class="card">


<h2>
About
</h2>


<p>
{{b.description}}
</p>


{% if b.city %}


<p>

<b>
Location:
</b>

{{b.city}}

</p>


{% endif %}


{% if b.website %}


<a
    class="outline"
    href="{{b.website}}"
    target="_blank"
    rel="noopener"
>

Website

</a>


{% endif %}


</article>


{% if b.media_kit_enabled %}


<article class="card">


<h2>
Media Kit
</h2>


<p>

<b>
Content:
</b>

{{b.content_categories}}

</p>


<p>

<b>
Audience:
</b>

{{b.audience_info}}

</p>


<div class="media-kit-grid">


<div class="stat">

<b>
{{b.followers or '—'}}
</b>

<br>

<small>
Followers
</small>

</div>


<div class="stat">

<b>
{{b.likes or '—'}}
</b>

<br>

<small>
Likes
</small>

</div>


<div class="stat">

<b>
{{b.views or '—'}}
</b>

<br>

<small>
Views
</small>

</div>


<div class="stat">

<b>
{{b.engagement_rate or '—'}}
</b>

<br>

<small>
Engagement
</small>

</div>


</div>


<p>

<b>
Previous Collaborations:
</b>

{{b.previous_collaborations}}

</p>


<p>

<b>
Collaboration Interests:
</b>

{{b.collaboration_interests}}

</p>


</article>


{% endif %}


</div>


<h2>
Content
</h2>


<div class="grid">


{% for x in content %}


<article class="card">


{% if x.media_path %}


{% if x.media_type=='video' %}


<video
    class="content-video"
    src="{{media_url(x.media_path)}}"
    controls
>
</video>


{% else %}


<img
    class="content-media"
    src="{{media_url(x.media_path)}}"
    alt=""
>


{% endif %}


{% endif %}


<p>
{{x.caption}}
</p>


</article>


{% else %}


<div class="empty">

New content
will appear here.

</div>


{% endfor %}


</div>


<h2>

Services
•
Events
•
Retreats
•
Meetups

</h2>


<div class="grid">


{% for x in items %}


<article class="card">


<span class="badge">

{{x.item_type}}

</span>


<h3>
{{x.title}}
</h3>


<p>
{{x.description}}
</p>


<b>
{{x.price}}
</b>


{% if x.action_url %}


<p>


<a
    class="outline"
    href="{{x.action_url}}"
    target="_blank"
    rel="noopener"
>

Open Link

</a>


</p>


{% endif %}


</article>


{% else %}


<div class="empty">

Offerings
and experiences
will appear here.

</div>


{% endfor %}


</div>


<section class="card">


<h2>

Connect With
{{b.business_name}}

</h2>


<div class="actions">


{% if me and me.id!=owner.id %}


<a
    class="btn"
    href="{{url_for('compose_message',recipient_id=owner.id,kind='business')}}"
>

Message / Contact

</a>


<a
    class="outline"
    href="{{url_for('collaborate',slug=b.slug)}}"
>

Collaborate

</a>


{% endif %}


{% if b.retreat_participation %}


<a
    class="outline"
    href="{{url_for('retreats')}}"
>

Retreats & Meetups

</a>


{% endif %}


{% if b.instagram %}


<a
    class="outline"
    href="{{b.instagram}}"
    target="_blank"
    rel="noopener"
>

Instagram

</a>


{% endif %}


{% if b.tiktok %}


<a
    class="outline"
    href="{{b.tiktok}}"
    target="_blank"
    rel="noopener"
>

TikTok

</a>


{% endif %}


{% if b.youtube %}


<a
    class="outline"
    href="{{b.youtube}}"
    target="_blank"
    rel="noopener"
>

YouTube

</a>


{% endif %}


</div>


</section>


{% endif %}


{% endblock %}
'''


# ============================================================
# COLLABORATION
# ============================================================

T["collaborate.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Collaborate With
{{b.business_name}}

</h1>


<form
    method="post"
    class="card"
>


<select name="request_type">


<option>
Creator Collaboration
</option>


<option>
Brand Collaboration
</option>


<option>
Business Visit / Feature
</option>


<option>
Retreat Collaboration
</option>


<option>
Event Appearance
</option>


<option>
Interview / Podcast
</option>


<option>
Content Collaboration
</option>


<option>
Other
</option>


</select>


<textarea
    name="message"
    placeholder="Tell {{b.business_name}} about the collaboration..."
>
</textarea>


<button class="btn">

Send Collaboration Request

</button>


</form>


{% endblock %}
'''


# ============================================================
# INBOX
# ============================================================

T["messages.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Inbox
</h1>


<div class="chips">


<span>
People
</span>


<span>
Dating
</span>


<span>
Business
</span>


<span>
Retreats
</span>


</div>


{% for m in inbox %}


<article class="card">


<span class="badge">

{{m.message_type|upper}}

</span>


<h3>

{{m.subject or 'Message'}}

</h3>


<b>
{{m.sender_name}}
</b>


<small>

{{m.created_at}}

</small>


<p>
{{m.body}}
</p>


<a
    class="outline"
    href="{{url_for('compose_message',recipient_id=m.sender_id,kind=m.message_type)}}"
>

Reply

</a>


</article>


{% else %}


<div class="empty">

Your private messages
will appear here.

</div>


{% endfor %}


{% endblock %}
'''


T["compose_message.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

Message
{{recipient.name}}

</h1>


<form
    method="post"
    class="card"
>


<span class="badge">

{{kind|upper}}

</span>


<input
    name="subject"
    placeholder="Subject"
    value="{{subject}}"
>


<textarea
    name="body"
    placeholder="Write your private message..."
>
</textarea>


<button class="btn">

Send Message

</button>


</form>


{% endblock %}
'''


# ============================================================
# NOTIFICATIONS
# ============================================================

T["notifications.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
My Notifications
</h1>


{% for n in notifications %}


<article class="card">


<span class="badge">

{{n.notification_type}}

</span>


<h3>
{{n.title}}
</h3>


<p>
{{n.body}}
</p>


{% if n.link %}


<a
    class="outline"
    href="{{n.link}}"
>

Open

</a>


{% endif %}


</article>


{% else %}


<div class="empty">

Your private astrology,
connection,
business
and retreat notifications
will appear here.

</div>


{% endfor %}


{% endblock %}
'''


# ============================================================
# RETREATS
# ============================================================

T["retreats.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
THE SEASONS WITHIN
</span>


<h1>
Retreats
</h1>


<p>

Private wellness experiences
and custom Retreat Constellations.

</p>


<div class="actions">


<a
    class="btn"
    href="{{url_for('retreat_build')}}"
>

Build My Retreat Constellation

</a>


<a
    class="outline"
    href="{{url_for('business')}}"
>

Explore Wellness Partners

</a>


</div>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<h2>

Participating Wellness Partners

</h2>


<div class="grid">


{% for b in partners %}


{% include 'business_card.html' %}


{% else %}


<div class="empty">

Participating businesses
will appear here.

</div>


{% endfor %}


</div>


<h2>
Upcoming Retreats
</h2>


<div class="grid">


{% for r in retreats %}


<a
    class="card"
    href="{{url_for('retreat_detail',rid=r.id)}}"
>


<h3>
{{r.title}}
</h3>


<p>

{{r.season}}
•
{{r.area}}

</p>


<small>
{{r.preferred_dates}}
</small>


{% if r.connection_retreat %}


<p>

<span class="badge">

Conscious Connections Retreat

</span>

</p>


{% endif %}


</a>


{% else %}


<div class="empty">

Custom retreats
will appear
after they are created.

</div>


{% endfor %}


</div>


{% endblock %}
'''


T["retreat_build.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>

{{'Build a Date / Friendship Retreat' if connection else 'Build My Retreat Constellation'}}

</h1>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="connection_retreat"
    value="{{1 if connection else 0}}"
>


<input
    name="title"
    placeholder="Retreat name"
    required
>


<select name="season">


<option>
Spring
</option>


<option>
Summer
</option>


<option>
Autumn
</option>


<option>
Winter
</option>


</select>


<input
    name="retreat_type"
    value="{{'Date / Friendship Retreat' if connection else ''}}"
    placeholder="Solo, Couples, Family, Creator..."
>


<input
    name="area"
    placeholder="Destination / preferred area"
>


<input
    name="preferred_dates"
    placeholder="Preferred dates"
>


<input
    name="guests"
    type="number"
    min="1"
    value="{{2 if connection else 1}}"
>


<input
    name="budget"
    placeholder="Accommodation budget"
>


<textarea
    name="lodging_preferences"
    placeholder="Private property, bedrooms, water, nature, accessibility, luxury preferences..."
>
</textarea>


<textarea
    name="wellness_interests"
    placeholder="Yoga, Reiki, massage, sound, creator meetup, meditation..."
>
</textarea>


<button class="btn">

Create Retreat Constellation

</button>


</form>


{% endblock %}
'''


T["retreat_detail.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
{{r.title}}
</h1>


<div class="two">


<article class="card">


<span class="kicker">
RETREAT PLAN
</span>


<p>

<b>
Season:
</b>

{{r.season}}

</p>


<p>

<b>
Area:
</b>

{{r.area}}

</p>


<p>

<b>
Dates:
</b>

{{r.preferred_dates}}

</p>


<p>

<b>
Guests:
</b>

{{r.guests}}

</p>


<p>

<b>
Budget:
</b>

{{r.budget}}

</p>


</article>


<article class="card">


<span class="kicker">
YOUR RETREAT LOCATION
</span>


<h2>
{{r.location_status}}
</h2>


<p>

The Seasons Within will help locate
a private retreat property
selected around your destination,
season,
group size,
experience
and lodging budget.

</p>


<form method="post">


<input
    type="hidden"
    name="action"
    value="location"
>


<button class="btn">

Request Retreat Location Search

</button>


</form>


</article>


</div>


<h2>
Retreat Constellation
</h2>


<div class="grid">


{% for p in partners %}


<article class="card">


<h3>
{{p.business_name}}
</h3>


<p>
{{p.creator_title or p.category}}
</p>


<p>

Status:
{{p.availability_status}}

</p>


<a
    class="outline"
    href="{{url_for('business_app',slug=p.slug)}}"
>

Open Business App

</a>


</article>


{% endfor %}


</div>


<form
    method="post"
    class="card"
>


<input
    type="hidden"
    name="action"
    value="partner"
>


<h3>

Add a Participating
Wellness Partner

</h3>


<select name="business_id">


{% for b in eligible %}


<option value="{{b.id}}">

{{b.business_name}}
—
{{b.category}}

</option>


{% endfor %}


</select>


<button class="btn">

Request Partner Availability

</button>


</form>


<h2>
Retreat Coordination
</h2>


<article class="card">


<p>

Use this private thread
to coordinate retreat dates,
business availability,
location
and retreat details.

</p>


<form method="post">


<input
    type="hidden"
    name="action"
    value="message"
>


<textarea
    name="body"
    placeholder="Message about dates, availability, location or retreat details..."
>
</textarea>


<button class="btn">

Send Retreat Message

</button>


</form>


</article>


{% for m in msgs %}


<article class="card">


<b>
{{m.sender_name}}
</b>


<small>
{{m.created_at}}
</small>


<p>
{{m.body}}
</p>


</article>


{% endfor %}


{% endblock %}
'''


# ============================================================
# MEMBERSHIP
# ============================================================

T["membership.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<section class="hero">


<div>


<span class="kicker">
MEMBERSHIP
</span>


<h1>

Connect With Intention.
Discover Your Seasons Within.

</h1>


</div>


<img
    class="hero-logo"
    src="{{url_for('static',filename='seasons-within-logo.png')}}"
    alt=""
>


</section>


<div class="grid">


<article class="card">


<h2>
Free
</h2>


<p>

Member Community

•
Basic profile

•
private journal

•
basic natal placements

•
free business listing

</p>


</article>


<article class="card">


<h2>

The Seasons Within Membership

—
${{MEMBER_PRICE}}/month

</h2>


<p>

Expanded natal chart

•
Conscious Coordination

•
dating compatibility

•
date ideas

•
private astrology
and connection notifications

</p>


</article>


<article class="card">


<h2>

Business Network

—
${{BUSINESS_PRICE}}/month

</h2>


<p>

Hosted Business App

•
photos/videos/content

•
media kit

•
services/classes/events

•
collaboration tools

•
Business Alignment Reflection

•
Retreat Constellation participation

</p>


</article>


</div>


{% endblock %}
'''


# ============================================================
# PRIVATE ADMIN
# ============================================================

T["admin.html"] = r'''

{% extends 'base.html' %}

{% block content %}


<h1>
Private Admin
</h1>


<div class="grid">


<article class="card">


<h2>
Users
</h2>


{% for u in users %}


<p>

{{u.name}}
—
{{u.email}}

{% if u.is_admin %}

<b>
ADMIN
</b>

{% endif %}

</p>


{% endfor %}


</article>


<article class="card">


<h2>
Businesses
</h2>


{% for b in businesses %}


<p>

{{b.business_name}}
—
{{b.status}}

</p>


{% endfor %}


</article>


<article class="card">


<h2>
Retreats
</h2>


{% for r in retreats %}


<p>

{{r.title}}
—
{{r.status}}

</p>


{% endfor %}


</article>


</div>


{% endblock %}
'''


# ============================================================
# JINJA
# ============================================================

app.jinja_loader = DictLoader(
    T
)


app.jinja_env.globals.update(

    media_url=
        media_url,

    is_admin=
        admin,

    is_video=
        is_video,

    MEMBER_PRICE=
        MEMBER_PRICE,

    BUSINESS_PRICE=
        BUSINESS_PRICE,
)


@app.context_processor
def context():

    return {
        "me":
            me()
    }


# ============================================================
# UPLOADS
# ============================================================

@app.route(
    "/uploads/<path:filename>"
)
def uploads(filename):

    return send_from_directory(
        UPLOADS,
        filename
    )


# ============================================================
# PUBLIC HOME
# ============================================================

@app.route("/")
def public_home():

    connection = conn()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE status='active'

        ORDER BY
            featured_order ASC,
            id ASC

        LIMIT 10
        """
    ).fetchall()


    connection.close()


    return render_template(

        "public.html",

        businesses=
            businesses,

        sky=
            current_sky(),
    )


@app.route("/home")
def home():

    return redirect(
        url_for(
            "public_home"
        )
    )


# ============================================================
# JOIN
# ============================================================

@app.route(
    "/join",
    methods=[
        "GET",
        "POST"
    ]
)
def join():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        if (
            not name
            or "@" not in email
            or len(password) < 6
        ):

            flash(
                "Enter your name, a valid email "
                "and a password of at least 6 characters."
            )


        else:

            connection = conn()


            try:

                cursor = connection.execute(
                    """
                    INSERT INTO users(

                        name,

                        email,

                        password,

                        community_enabled,

                        conscious_connections_enabled,

                        business_interest
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        name,

                        email,

                        hp(
                            password
                        ),

                        (
                            1
                            if request.form.get(
                                "community_enabled"
                            )
                            else 0
                        ),

                        (
                            1
                            if request.form.get(
                                "conscious_connections_enabled"
                            )
                            else 0
                        ),

                        (
                            1
                            if request.form.get(
                                "business_interest"
                            )
                            else 0
                        ),
                    )
                )


                connection.commit()


                session[
                    "uid"
                ] = cursor.lastrowid


                connection.close()


                return redirect(
                    url_for(
                        "onboarding"
                    )
                )


            except sqlite3.IntegrityError:

                connection.close()


                flash(
                    "That email already has an account."
                )


    return render_template(
        "join.html"
    )


# ============================================================
# ONBOARDING
# ============================================================

@app.route(
    "/onboarding",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def onboarding():

    user = me()


    if request.method == "POST":

        connection = conn()


        if user[
            "conscious_connections_enabled"
        ]:

            connection.execute(
                """
                UPDATE users

                SET connection_type=?

                WHERE id=?
                """,
                (

                    request.form.get(
                        "connection_type",
                        "Both"
                    ),

                    user[
                        "id"
                    ],
                )
            )


        connection.commit()

        connection.close()


        return redirect(
            url_for(
                "profile_edit"
            )
        )


    return render_template(
        "onboarding.html",
        u=user
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        connection = conn()


        user = connection.execute(
            """
            SELECT *

            FROM users

            WHERE lower(email)=?
            """,
            (
                email,
            )
        ).fetchone()


        connection.close()


        if (
            user
            and
            user[
                "password"
            ] == hp(
                password
            )
        ):

            session[
                "uid"
            ] = user[
                "id"
            ]


            return redirect(

                request.args.get(
                    "next"
                )

                or

                url_for(
                    "public_home"
                )
            )


        flash(
            "Email or password not recognized."
        )


    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    session.clear()


    return redirect(
        url_for(
            "public_home"
        )
    )


# ============================================================
# COMMUNITY
# ============================================================

@app.route(
    "/community",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def community():

    user = me()


    if not user[
        "community_enabled"
    ]:

        return redirect(
            url_for(
                "profile"
            )
        )


    connection = conn()


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        media = save_file(

            request.files.get(
                "photo"
            ),

            f"community{user['id']}"
        )


        if (
            media
            and is_video(
                media
            )
        ):

            media = ""


        if (
            body
            or media
        ):

            connection.execute(
                """
                INSERT INTO posts(

                    user_id,

                    body,

                    media_path,

                    media_type
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    body,

                    media,

                    (
                        "image"
                        if media
                        else ""
                    ),
                )
            )


            connection.commit()


    posts = connection.execute(
        """
        SELECT

            p.*,

            u.name,

            u.photo

        FROM posts p

        JOIN users u
        ON u.id=p.user_id

        ORDER BY
            p.id DESC

        LIMIT 50
        """
    ).fetchall()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE status='active'

        ORDER BY
            featured_order,
            id

        LIMIT 6
        """
    ).fetchall()


    connection.close()


    return render_template(

        "community.html",

        posts=
            posts,

        businesses=
            businesses,

        reflection=
            journal_reflection(
                user
            ),
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    user = me()


    return render_template(

        "profile.html",

        u=
            user,

        reflection=
            journal_reflection(
                user
            ),
    )


@app.route(
    "/profile/edit",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def profile_edit():

    user = me()


    if request.method == "POST":

        photo = (

            save_file(

                request.files.get(
                    "photo"
                ),

                f"user{user['id']}"
            )

            or

            user[
                "photo"
            ]
        )


        connection = conn()


        connection.execute(
            """
            UPDATE users

            SET

                name=?,

                city=?,

                profile_headline=?,

                bio=?,

                birth_date=?,

                birth_time=?,

                time_known=?,

                connection_type=?,

                photo=?

            WHERE id=?
            """,
            (

                request.form.get(
                    "name",
                    ""
                ).strip(),

                request.form.get(
                    "city",
                    ""
                ).strip(),

                request.form.get(
                    "profile_headline",
                    ""
                ).strip(),

                request.form.get(
                    "bio",
                    ""
                ).strip(),

                request.form.get(
                    "birth_date",
                    ""
                ).strip(),

                request.form.get(
                    "birth_time",
                    ""
                ).strip(),

                (
                    1
                    if request.form.get(
                        "time_known"
                    )
                    else 0
                ),

                request.form.get(
                    "connection_type",
                    user[
                        "connection_type"
                    ]
                ),

                photo,

                user[
                    "id"
                ],
            )
        )


        connection.commit()


        updated = connection.execute(
            """
            SELECT *
            FROM users
            WHERE id=?
            """,
            (
                user[
                    "id"
                ],
            )
        ).fetchone()


        chart = chart_for(
            updated
        )


        if chart:

            placements = [

                chart.get(
                    placement,
                    {}
                ).get(
                    "sign",
                    ""
                )

                for placement

                in (
                    "Sun",
                    "Moon",
                    "Mercury",
                    "Venus",
                    "Mars",
                    "Jupiter",
                    "Saturn",
                    "Uranus",
                    "Neptune",
                    "Pluto",
                )
            ]


            connection.execute(
                """
                UPDATE users

                SET

                    sun=?,

                    moon=?,

                    mercury=?,

                    venus=?,

                    mars=?,

                    jupiter=?,

                    saturn=?,

                    uranus=?,

                    neptune=?,

                    pluto=?

                WHERE id=?
                """,
                (
                    *placements,

                    user[
                        "id"
                    ],
                )
            )


            connection.commit()


        connection.close()


        flash(
            "Profile saved."
        )


        return redirect(
            url_for(
                "profile"
            )
        )


    return render_template(
        "profile_edit.html",
        u=user
    )


# ============================================================
# JOURNAL
# ============================================================

@app.route(
    "/journal",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def journal():

    user = me()

    connection = conn()


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        if body:

            connection.execute(
                """
                INSERT INTO journals(

                    user_id,

                    body,

                    sky_json
                )

                VALUES(

                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    body,

                    json.dumps(
                        current_sky()
                    ),
                )
            )


            connection.commit()


    entries = connection.execute(
        """
        SELECT *

        FROM journals

        WHERE user_id=?

        ORDER BY
            id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "journal.html",

        reflection=
            journal_reflection(
                user
            ),

        entries=
            entries,
    )


# ============================================================
# ENABLE CONSCIOUS CONNECTIONS
# ============================================================

@app.route(
    "/connections/join",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def enable_connections():

    user = me()


    if request.method == "POST":

        connection = conn()


        connection.execute(
            """
            UPDATE users

            SET

                conscious_connections_enabled=1,

                connection_type=?

            WHERE id=?
            """,
            (

                request.form.get(
                    "connection_type",
                    "Both"
                ),

                user[
                    "id"
                ],
            )
        )


        connection.commit()

        connection.close()


        return redirect(
            url_for(
                "connections"
            )
        )


    return render_template(
        "connections_join.html"
    )


# ============================================================
# CONSCIOUS CONNECTIONS COMMUNITY
# ============================================================

@app.route(
    "/connections",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def connections():

    user = me()


    if not user[
        "conscious_connections_enabled"
    ]:

        return redirect(
            url_for(
                "enable_connections"
            )
        )


    mode = request.args.get(
        "mode",
        "all"
    )


    connection = conn()


    host_media = bool(

        admin(
            user
        )

        or

        (
            user[
                "email"
            ]
            or ""
        ).lower()

        ==

        GALAXY_EMAIL
    )


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        media = ""

        media_type = ""


        if host_media:

            media = save_file(

                request.files.get(
                    "media"
                ),

                f"connections{user['id']}"
            )


            media_type = (

                "video"

                if is_video(
                    media
                )

                else (

                    "image"

                    if media

                    else ""
                )
            )


        if (
            body
            or media
        ):

            connection.execute(
                """
                INSERT INTO connection_posts(

                    user_id,

                    body,

                    media_path,

                    media_type
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    body,

                    media,

                    media_type,
                )
            )


            connection.commit()


    posts = connection.execute(
        """
        SELECT

            p.*,

            u.name,

            u.photo

        FROM connection_posts p

        JOIN users u
        ON u.id=p.user_id

        WHERE
            u.conscious_connections_enabled=1

        ORDER BY
            p.id DESC

        LIMIT 50
        """
    ).fetchall()


    people = connection.execute(
        """
        SELECT *

        FROM users

        WHERE

            id<>?

            AND conscious_connections_enabled=1

        ORDER BY
            id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    filtered = []


    for person in people:

        connection_type = (

            person[
                "connection_type"
            ]

            or

            "Both"
        )


        if mode == "dating":

            if connection_type in (
                "Love & Dating",
                "Both",
            ):

                filtered.append(
                    person
                )


        elif mode == "friendship":

            if connection_type in (
                "Friendship",
                "Both",
            ):

                filtered.append(
                    person
                )


        else:

            filtered.append(
                person
            )


    score_mode = (

        "friendship"

        if mode == "friendship"

        else "dating"
    )


    cards = [

        (
            person,

            coord(
                user,
                person,
                score_mode
            )
        )

        for person

        in filtered
    ]


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND retreat_participation=1

        ORDER BY
            featured_order,
            id

        LIMIT 8
        """
    ).fetchall()


    connection.close()


    return render_template(

        "connections.html",

        posts=
            posts,

        cards=
            cards,

        businesses=
            businesses,

        mode=
            mode,

        host_media=
            host_media,
    )


# ============================================================
# CONNECTION PROFILE / COMPATIBILITY
# ============================================================

@app.route(
    "/connections/profile/<int:uid>"
)
@login_required
def connection_profile(uid):

    user = me()


    if not user[
        "conscious_connections_enabled"
    ]:

        return redirect(
            url_for(
                "enable_connections"
            )
        )


    connection = conn()


    person = connection.execute(
        """
        SELECT *

        FROM users

        WHERE

            id=?

            AND conscious_connections_enabled=1
        """,
        (
            uid,
        )
    ).fetchone()


    connection.close()


    if not person:

        abort(
            404
        )


    mode = request.args.get(
        "mode",
        "dating"
    )


    if mode not in (
        "dating",
        "friendship",
    ):

        mode = "dating"


    return render_template(

        "connection_profile.html",

        person=
            person,

        mode=
            mode,

        score=
            coord(
                user,
                person,
                mode
            ),

        idea=
            date_idea(
                user,
                person,
                mode
            ),
    )


# ============================================================
# CREATORS ARE PART OF BUSINESS NETWORK
# ============================================================

@app.route("/creators")
def creators():

    return redirect(
        url_for(
            "business"
        )
    )


# ============================================================
# BUSINESS DIRECTORY
# ============================================================

@app.route("/business")
def business():

    query = request.args.get(
        "q",
        ""
    ).strip()


    connection = conn()


    rows = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND (

                ?=''

                OR business_name LIKE ?

                OR category LIKE ?

                OR description LIKE ?

                OR creator_title LIKE ?
            )

        ORDER BY

            featured_order,

            id
        """,
        (

            query,

            f"%{query}%",

            f"%{query}%",

            f"%{query}%",

            f"%{query}%",
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business.html",

        businesses=
            rows,

        q=
            query,
    )


# ============================================================
# BUSINESS SETUP
# ============================================================

@app.route(
    "/business/setup",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def business_setup():

    user = me()

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE owner_id=?
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchone()


    if request.method == "POST":

        business_name = request.form.get(
            "business_name",
            ""
        ).strip()


        if not business_name:

            flash(
                "Business name required."
            )


            connection.close()


            return render_template(
                "business_setup.html",
                b=business_record
            )


        logo = (

            save_file(

                request.files.get(
                    "logo"
                ),

                f"biz{user['id']}-logo"
            )

            or

            (
                business_record[
                    "logo"
                ]

                if business_record

                else ""
            )
        )


        hero_image = (

            business_record[
                "hero_image"
            ]

            if business_record

            else ""
        )


        featured_video = (

            business_record[
                "featured_video"
            ]

            if business_record

            else ""
        )


        if user[
            "business_access"
        ]:

            hero_image = (

                save_file(

                    request.files.get(
                        "hero_image"
                    ),

                    f"biz{user['id']}-hero"
                )

                or hero_image
            )


            featured_video = (

                save_file(

                    request.files.get(
                        "featured_video"
                    ),

                    f"biz{user['id']}-video"
                )

                or featured_video
            )


        values = {

            "business_name":
                business_name,

            "creator_title":
                request.form.get(
                    "creator_title",
                    ""
                ).strip(),

            "tagline":
                request.form.get(
                    "tagline",
                    ""
                ).strip(),

            "description":
                request.form.get(
                    "description",
                    ""
                ).strip(),

            "category":
                request.form.get(
                    "category",
                    ""
                ).strip(),

            "city":
                request.form.get(
                    "city",
                    ""
                ).strip(),

            "website":
                request.form.get(
                    "website",
                    ""
                ).strip(),

            "contact_email":
                request.form.get(
                    "contact_email",
                    ""
                ).strip(),

            "phone":
                request.form.get(
                    "phone",
                    ""
                ).strip(),

            "logo":
                logo,

            "hero_image":
                hero_image,

            "featured_video":
                featured_video,

            "instagram":

                request.form.get(
                    "instagram",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "instagram"
                    ]

                    if business_record

                    else ""
                ),

            "tiktok":

                request.form.get(
                    "tiktok",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "tiktok"
                    ]

                    if business_record

                    else ""
                ),

            "youtube":

                request.form.get(
                    "youtube",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "youtube"
                    ]

                    if business_record

                    else ""
                ),

            "booking_url":

                request.form.get(
                    "booking_url",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "booking_url"
                    ]

                    if business_record

                    else ""
                ),

            "content_categories":

                request.form.get(
                    "content_categories",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "content_categories"
                    ]

                    if business_record

                    else ""
                ),

            "audience_info":

                request.form.get(
                    "audience_info",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "audience_info"
                    ]

                    if business_record

                    else ""
                ),

            "previous_collaborations":

                request.form.get(
                    "previous_collaborations",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "previous_collaborations"
                    ]

                    if business_record

                    else ""
                ),

            "collaboration_interests":

                request.form.get(
                    "collaboration_interests",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "collaboration_interests"
                    ]

                    if business_record

                    else ""
                ),

            "followers":

                request.form.get(
                    "followers",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "followers"
                    ]

                    if business_record

                    else ""
                ),

            "likes":

                request.form.get(
                    "likes",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "likes"
                    ]

                    if business_record

                    else ""
                ),

            "views":

                request.form.get(
                    "views",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "views"
                    ]

                    if business_record

                    else ""
                ),

            "engagement_rate":

                request.form.get(
                    "engagement_rate",
                    ""
                ).strip()

                if user[
                    "business_access"
                ]

                else (

                    business_record[
                        "engagement_rate"
                    ]

                    if business_record

                    else ""
                ),

            "retreat_participation":

                1

                if (

                    user[
                        "business_access"
                    ]

                    and

                    request.form.get(
                        "retreat_participation"
                    )
                )

                else (

                    business_record[
                        "retreat_participation"
                    ]

                    if (
                        business_record
                        and
                        not user[
                            "business_access"
                        ]
                    )

                    else 0
                ),
        }


        if business_record:

            connection.execute(
                """
                UPDATE businesses

                SET

                    business_name=:business_name,

                    creator_title=:creator_title,

                    tagline=:tagline,

                    description=:description,

                    category=:category,

                    city=:city,

                    website=:website,

                    contact_email=:contact_email,

                    phone=:phone,

                    logo=:logo,

                    hero_image=:hero_image,

                    featured_video=:featured_video,

                    instagram=:instagram,

                    tiktok=:tiktok,

                    youtube=:youtube,

                    booking_url=:booking_url,

                    content_categories=:content_categories,

                    audience_info=:audience_info,

                    previous_collaborations=:previous_collaborations,

                    collaboration_interests=:collaboration_interests,

                    followers=:followers,

                    likes=:likes,

                    views=:views,

                    engagement_rate=:engagement_rate,

                    retreat_participation=:retreat_participation,

                    status='active'

                WHERE owner_id=:owner_id
                """,
                {

                    **values,

                    "owner_id":
                        user[
                            "id"
                        ],
                }
            )


        else:

            connection.execute(
                """
                INSERT INTO businesses(

                    owner_id,

                    slug,

                    business_name,

                    creator_title,

                    tagline,

                    description,

                    category,

                    city,

                    website,

                    contact_email,

                    phone,

                    logo,

                    hero_image,

                    featured_video,

                    instagram,

                    tiktok,

                    youtube,

                    booking_url,

                    content_categories,

                    audience_info,

                    previous_collaborations,

                    collaboration_interests,

                    followers,

                    likes,

                    views,

                    engagement_rate,

                    retreat_participation,

                    paid_business,

                    media_kit_enabled,

                    status
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,

                    'active'
                )
                """,
                (

                    user[
                        "id"
                    ],

                    slugify(
                        business_name
                    ),

                    values[
                        "business_name"
                    ],

                    values[
                        "creator_title"
                    ],

                    values[
                        "tagline"
                    ],

                    values[
                        "description"
                    ],

                    values[
                        "category"
                    ],

                    values[
                        "city"
                    ],

                    values[
                        "website"
                    ],

                    values[
                        "contact_email"
                    ],

                    values[
                        "phone"
                    ],

                    values[
                        "logo"
                    ],

                    values[
                        "hero_image"
                    ],

                    values[
                        "featured_video"
                    ],

                    values[
                        "instagram"
                    ],

                    values[
                        "tiktok"
                    ],

                    values[
                        "youtube"
                    ],

                    values[
                        "booking_url"
                    ],

                    values[
                        "content_categories"
                    ],

                    values[
                        "audience_info"
                    ],

                    values[
                        "previous_collaborations"
                    ],

                    values[
                        "collaboration_interests"
                    ],

                    values[
                        "followers"
                    ],

                    values[
                        "likes"
                    ],

                    values[
                        "views"
                    ],

                    values[
                        "engagement_rate"
                    ],

                    values[
                        "retreat_participation"
                    ],

                    (
                        1
                        if user[
                            "business_access"
                        ]
                        else 0
                    ),

                    (
                        1
                        if user[
                            "creator_access"
                        ]
                        else 0
                    ),
                )
            )


        connection.commit()

        connection.close()


        flash(
            "Business profile saved."
        )


        return redirect(
            url_for(
                "business"
            )
        )


    connection.close()


    return render_template(
        "business_setup.html",
        b=business_record
    )


# ============================================================
# BUSINESS APP MANAGER
# ============================================================

@app.route(
    "/business/manage",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def business_manage():

    user = me()


    if not user[
        "business_access"
    ]:

        return (
            "Hosted Business App access required.",
            403
        )


    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE owner_id=?
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchone()


    if not business_record:

        connection.close()


        return redirect(
            url_for(
                "business_setup"
            )
        )


    if request.method == "POST":

        section = request.form.get(
            "section"
        )


        if section == "content":

            caption = request.form.get(
                "caption",
                ""
            ).strip()


            media = save_file(

                request.files.get(
                    "media"
                ),

                f"bizcontent{business_record['id']}"
            )


            media_type = (

                "video"

                if is_video(
                    media
                )

                else (

                    "image"

                    if media

                    else ""
                )
            )


            if (
                caption
                or media
            ):

                connection.execute(
                    """
                    INSERT INTO business_content(

                        business_id,

                        content_type,

                        caption,

                        media_path,

                        media_type
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        business_record[
                            "id"
                        ],

                        request.form.get(
                            "content_type",
                            "post"
                        ),

                        caption,

                        media,

                        media_type,
                    )
                )


                connection.commit()


                flash(
                    "Content published to your Hosted App."
                )


        elif section == "item":

            title = request.form.get(
                "title",
                ""
            ).strip()


            if title:

                connection.execute(
                    """
                    INSERT INTO business_items(

                        business_id,

                        item_type,

                        title,

                        description,

                        price,

                        action_url
                    )

                    VALUES(

                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        business_record[
                            "id"
                        ],

                        request.form.get(
                            "item_type",
                            "service"
                        ),

                        title,

                        request.form.get(
                            "description",
                            ""
                        ).strip(),

                        request.form.get(
                            "price",
                            ""
                        ).strip(),

                        request.form.get(
                            "action_url",
                            ""
                        ).strip(),
                    )
                )


                connection.commit()


                flash(
                    "Added to your Hosted App."
                )


    content = connection.execute(
        """
        SELECT *

        FROM business_content

        WHERE

            business_id=?

            AND active=1

        ORDER BY
            id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    items = connection.execute(
        """
        SELECT *

        FROM business_items

        WHERE

            business_id=?

            AND active=1

        ORDER BY
            id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business_manage.html",

        b=
            business_record,

        content=
            content,

        items=
            items,
    )


# ============================================================
# BUSINESS APP
# ============================================================

@app.route(
    "/app/<slug>"
)
def business_app(slug):

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            slug=?

            AND status='active'
        """,
        (
            slug,
        )
    ).fetchone()


    if not business_record:

        connection.close()

        abort(
            404
        )


    owner = connection.execute(
        """
        SELECT *

        FROM users

        WHERE id=?
        """,
        (
            business_record[
                "owner_id"
            ],
        )
    ).fetchone()


    content = connection.execute(
        """
        SELECT *

        FROM business_content

        WHERE

            business_id=?

            AND active=1

        ORDER BY id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    items = connection.execute(
        """
        SELECT *

        FROM business_items

        WHERE

            business_id=?

            AND active=1

        ORDER BY id DESC
        """,
        (
            business_record[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(

        "business_app.html",

        b=
            business_record,

        owner=
            owner,

        content=
            content,

        items=
            items,
    )


# ============================================================
# COLLABORATIONS
# ============================================================

@app.route(
    "/app/<slug>/collaborate",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def collaborate(slug):

    user = me()

    connection = conn()


    business_record = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            slug=?

            AND status='active'
        """,
        (
            slug,
        )
    ).fetchone()


    if not business_record:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()


        request_type = request.form.get(
            "request_type",
            "Collaboration"
        )


        connection.execute(
            """
            INSERT INTO collaboration_requests(

                business_id,

                sender_id,

                request_type,

                message
            )

            VALUES(

                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                business_record[
                    "id"
                ],

                user[
                    "id"
                ],

                request_type,

                message,
            )
        )


        connection.execute(
            """
            INSERT INTO messages(

                sender_id,

                recipient_id,

                message_type,

                subject,

                body
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                user[
                    "id"
                ],

                business_record[
                    "owner_id"
                ],

                "business",

                "Collaboration Request",

                message,
            )
        )


        connection.commit()

        connection.close()


        flash(
            "Collaboration request sent."
        )


        return redirect(
            url_for(
                "business_app",
                slug=slug
            )
        )


    connection.close()


    return render_template(
        "collaborate.html",
        b=business_record
    )


# ============================================================
# INBOX
# ============================================================

@app.route("/messages")
@login_required
def messages():

    user = me()

    connection = conn()


    inbox = connection.execute(
        """
        SELECT

            m.*,

            u.name sender_name

        FROM messages m

        JOIN users u
        ON u.id=m.sender_id

        WHERE
            m.recipient_id=?

        ORDER BY
            m.id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "messages.html",
        inbox=inbox
    )


@app.route(
    "/message/<int:recipient_id>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def compose_message(
    recipient_id
):

    user = me()


    kind = request.args.get(
        "kind",
        "people"
    )


    connection = conn()


    recipient = connection.execute(
        """
        SELECT *

        FROM users

        WHERE id=?
        """,
        (
            recipient_id,
        )
    ).fetchone()


    if not recipient:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()


        subject = request.form.get(
            "subject",
            ""
        ).strip()


        if body:

            connection.execute(
                """
                INSERT INTO messages(

                    sender_id,

                    recipient_id,

                    message_type,

                    subject,

                    body
                )

                VALUES(

                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (

                    user[
                        "id"
                    ],

                    recipient_id,

                    kind,

                    subject,

                    body,
                )
            )


            connection.commit()

            connection.close()


            flash(
                "Message sent."
            )


            return redirect(
                url_for(
                    "messages"
                )
            )


    connection.close()


    return render_template(

        "compose_message.html",

        recipient=
            recipient,

        kind=
            kind,

        subject=
            "",
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    user = me()

    connection = conn()


    rows = connection.execute(
        """
        SELECT *

        FROM notifications

        WHERE user_id=?

        ORDER BY
            id DESC
        """,
        (
            user[
                "id"
            ],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "notifications.html",
        notifications=rows
    )


# ============================================================
# RETREATS
# ============================================================

@app.route("/retreats")
def retreats():

    connection = conn()


    retreat_rows = connection.execute(
        """
        SELECT *

        FROM retreats

        WHERE status<>'cancelled'

        ORDER BY
            id DESC
        """
    ).fetchall()


    partners = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND retreat_participation=1

        ORDER BY

            featured_order,

            id
        """
    ).fetchall()


    connection.close()


    return render_template(

        "retreats.html",

        retreats=
            retreat_rows,

        partners=
            partners,
    )


@app.route(
    "/retreats/build",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def retreat_build():

    connection_mode = (
        request.args.get(
            "connection"
        )
        == "1"
    )


    if request.method == "POST":

        user = me()

        connection = conn()


        cursor = connection.execute(
            """
            INSERT INTO retreats(

                owner_id,

                title,

                season,

                retreat_type,

                area,

                preferred_dates,

                guests,

                budget,

                lodging_preferences,

                wellness_interests,

                connection_retreat
            )

            VALUES(

                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (

                user[
                    "id"
                ],

                request.form.get(
                    "title",
                    "My Retreat"
                ).strip(),

                request.form.get(
                    "season",
                    ""
                ),

                request.form.get(
                    "retreat_type",
                    ""
                ),

                request.form.get(
                    "area",
                    ""
                ),

                request.form.get(
                    "preferred_dates",
                    ""
                ),

                int(
                    request.form.get(
                        "guests"
                    )
                    or 1
                ),

                request.form.get(
                    "budget",
                    ""
                ),

                request.form.get(
                    "lodging_preferences",
                    ""
                ),

                request.form.get(
                    "wellness_interests",
                    ""
                ),

                (
                    1
                    if request.form.get(
                        "connection_retreat"
                    )
                    == "1"
                    else 0
                ),
            )
        )


        connection.commit()


        retreat_id = (
            cursor.lastrowid
        )


        connection.close()


        return redirect(
            url_for(
                "retreat_detail",
                rid=retreat_id
            )
        )


    return render_template(

        "retreat_build.html",

        connection=
            connection_mode,
    )


@app.route(
    "/retreat/<int:rid>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def retreat_detail(rid):

    user = me()

    connection = conn()


    retreat_record = connection.execute(
        """
        SELECT *

        FROM retreats

        WHERE id=?
        """,
        (
            rid,
        )
    ).fetchone()


    if not retreat_record:

        connection.close()

        abort(
            404
        )


    if request.method == "POST":

        action = request.form.get(
            "action"
        )


        if action == "partner":

            connection.execute(
                """
                INSERT OR IGNORE
                INTO retreat_partners(

                    retreat_id,

                    business_id
                )

                VALUES(

                    ?,
                    ?
                )
                """,
                (

                    rid,

                    int(
                        request.form.get(
                            "business_id"
                        )
                    ),
                )
            )


            connection.commit()


        elif action == "location":

            connection.execute(
                """
                UPDATE retreats

                SET
                    location_status='Search Requested'

                WHERE id=?
                """,
                (
                    rid,
                )
            )


            connection.commit()


        elif action == "message":

            body = request.form.get(
                "body",
                ""
            ).strip()


            if body:

                connection.execute(
                    """
                    INSERT INTO retreat_messages(

                        retreat_id,

                        sender_id,

                        body
                    )

                    VALUES(

                        ?,
                        ?,
                        ?
                    )
                    """,
                    (

                        rid,

                        user[
                            "id"
                        ],

                        body,
                    )
                )


                connection.commit()


    partners = connection.execute(
        """
        SELECT

            rp.*,

            b.*

        FROM retreat_partners rp

        JOIN businesses b
        ON b.id=rp.business_id

        WHERE
            rp.retreat_id=?
        """,
        (
            rid,
        )
    ).fetchall()


    eligible = connection.execute(
        """
        SELECT *

        FROM businesses

        WHERE

            status='active'

            AND retreat_participation=1

        ORDER BY

            featured_order,

            id
        """
    ).fetchall()


    messages_rows = connection.execute(
        """
        SELECT

            rm.*,

            u.name sender_name

        FROM retreat_messages rm

        JOIN users u
        ON u.id=rm.sender_id

        WHERE
            retreat_id=?

        ORDER BY
            rm.id
        """,
        (
            rid,
        )
    ).fetchall()


    connection.close()


    return render_template(

        "retreat_detail.html",

        r=
            retreat_record,

        partners=
            partners,

        eligible=
            eligible,

        msgs=
            messages_rows,
    )


# ============================================================
# MEMBERSHIP
# ============================================================

@app.route("/membership")
def membership():

    return render_template(
        "membership.html"
    )


# ============================================================
# PRIVATE ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin_page():

    connection = conn()


    users = connection.execute(
        """
        SELECT *

        FROM users

        ORDER BY
            id DESC
        """
    ).fetchall()


    businesses = connection.execute(
        """
        SELECT *

        FROM businesses

        ORDER BY
            featured_order,
            id
        """
    ).fetchall()


    retreats_rows = connection.execute(
        """
        SELECT *

        FROM retreats

        ORDER BY
            id DESC
        """
    ).fetchall()


    connection.close()


    return render_template(

        "admin.html",

        users=
            users,

        businesses=
            businesses,

        retreats=
            retreats_rows,
    )


# ============================================================
# START DATABASE
# ============================================================

init_db()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        host=
            "0.0.0.0",

        port=
            int(
                os.environ.get(
                    "PORT",
                    "5055"
                )
            )
    )
