from flask import Flask, request, jsonify
from flask_cors import CORS
import re, json, os
from datetime import datetime, timedelta

app  = Flask(__name__)
CORS(app)

# ════════════════════════════════════════════
# ENV VARS
# ════════════════════════════════════════════
DATABASE_URL  = os.environ.get("DATABASE_URL")
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY")
HISTORY_FILE  = "poster_history.json"


# ════════════════════════════════════════════
# DATABASE SETUP — PostgreSQL
# ════════════════════════════════════════════
def get_db():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not DATABASE_URL:
        return
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS poster_history (
                id           SERIAL PRIMARY KEY,
                poster_key   TEXT UNIQUE NOT NULL,
                poster_name  TEXT NOT NULL,
                poster_title TEXT,
                first_seen   TIMESTAMP DEFAULT NOW(),
                last_seen    TIMESTAMP DEFAULT NOW(),
                count        INTEGER DEFAULT 1
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ PostgreSQL ready.")
    except Exception as e:
        print(f"❌ DB init error: {e}")

init_db()


# ════════════════════════════════════════════
# POSTER KEY HELPER
# ════════════════════════════════════════════
def make_poster_key(name, title):
    n = re.sub(r"\s+", " ", name.strip().lower())
    t = re.sub(r"\s+", " ", title.strip().lower())
    return f"{n}||{t}"


# ════════════════════════════════════════════
# HISTORY — PostgreSQL
# ════════════════════════════════════════════
def check_and_update_history_pg(posts):
    new_posts, repeat_posts = [], []
    cutoff = datetime.now() - timedelta(days=7)
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM poster_history WHERE last_seen < %s;", (cutoff,))
        for item in posts:
            key = make_poster_key(item["poster"], item["title"])
            cur.execute(
                "SELECT count, first_seen FROM poster_history WHERE poster_key=%s;",
                (key,)
            )
            row = cur.fetchone()
            if row:
                new_count = row[0] + 1
                cur.execute(
                    "UPDATE poster_history SET count=%s, last_seen=NOW() "
                    "WHERE poster_key=%s;",
                    (new_count, key)
                )
                repeat_posts.append({
                    **item,
                    "repeat_count": new_count,
                    "first_seen":   row[1].isoformat(),
                })
            else:
                cur.execute(
                    "INSERT INTO poster_history(poster_key,poster_name,poster_title)"
                    " VALUES(%s,%s,%s);",
                    (key, item["poster"], item["title"])
                )
                new_posts.append(item)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
        new_posts = posts
    return new_posts, repeat_posts

def get_top_spammers_pg(limit=10):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT poster_name, poster_title, count, first_seen, last_seen
            FROM poster_history WHERE count > 1
            ORDER BY count DESC LIMIT %s;
        """, (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{"poster": r[0], "title": r[1], "count": r[2],
                 "first_seen": r[3].isoformat() if r[3] else "",
                 "last_seen":  r[4].isoformat() if r[4] else ""}
                for r in rows]
    except Exception as e:
        print(f"DB Error: {e}")
        return []

def clear_history_pg():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM poster_history;")
        conn.commit()
        cur.close(); conn.close()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False


# ════════════════════════════════════════════
# HISTORY — JSON fallback (local)
# ════════════════════════════════════════════
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:    return json.load(f)
        except: return {}

def save_history(h):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=2, ensure_ascii=False)

def clean_old_history(h):
    cutoff = datetime.now() - timedelta(days=7)
    return {k: v for k, v in h.items()
            if datetime.fromisoformat(v["first_seen"]) >= cutoff}

def check_and_update_history_json(posts):
    history = clean_old_history(load_history())
    new_posts, repeat_posts = [], []
    for item in posts:
        key = make_poster_key(item["poster"], item["title"])
        if key in history:
            history[key]["count"]    += 1
            history[key]["last_seen"] = datetime.now().isoformat()
            repeat_posts.append({
                **item,
                "repeat_count": history[key]["count"],
                "first_seen":   history[key]["first_seen"],
            })
        else:
            history[key] = {
                "poster": item["poster"], "title": item["title"],
                "first_seen": datetime.now().isoformat(),
                "last_seen":  datetime.now().isoformat(),
                "count": 1,
            }
            new_posts.append(item)
    save_history(history)
    return new_posts, repeat_posts

def get_top_spammers_json(limit=10):
    history = clean_old_history(load_history())
    return sorted(
        [v for v in history.values() if v.get("count", 1) > 1],
        key=lambda x: x["count"], reverse=True
    )[:limit]

def clear_history_json():
    save_history({})
    return True

# ── Unified wrappers ──
def check_and_update_history(posts):
    return check_and_update_history_pg(posts) if DATABASE_URL \
           else check_and_update_history_json(posts)

def get_top_spammers():
    return get_top_spammers_pg() if DATABASE_URL \
           else get_top_spammers_json()

def clear_history():
    return clear_history_pg() if DATABASE_URL \
           else clear_history_json()


# ════════════════════════════════════════════
# INDIA ALLOWLIST
# ════════════════════════════════════════════
INDIA_TERMS = [
    "india","bharat",r"\bIND\b","pan india","pan-india",
    "remote india","work from india","wfh india","hybrid india","ncr",
    "andhra pradesh","arunachal pradesh","assam","bihar","chhattisgarh",
    "goa","gujarat","haryana","himachal pradesh","jharkhand","karnataka",
    "kerala","madhya pradesh","maharashtra","manipur","meghalaya",
    "mizoram","nagaland","odisha","punjab","rajasthan","sikkim",
    "tamil nadu","telangana","tripura","uttar pradesh","uttarakhand",
    "west bengal","delhi","jammu","kashmir","ladakh","chandigarh",
    "puducherry","pondicherry","andaman","nicobar","lakshadweep",
    "dadra","daman","diu",
    "mumbai","bangalore","bengaluru","hyderabad","chennai","kolkata",
    "pune","ahmedabad","surat","jaipur","lucknow","kanpur","nagpur",
    "indore","thane","bhopal","visakhapatnam","vizag","patna",
    "vadodara","ghaziabad","ludhiana","agra","nashik","faridabad",
    "meerut","rajkot","kalyan","vasai","varanasi","srinagar",
    "aurangabad","dhanbad","amritsar","navi mumbai","allahabad",
    "prayagraj","ranchi","coimbatore","jabalpur","gwalior","vijayawada",
    "jodhpur","madurai","raipur","kota","guwahati","solapur",
    "hubli","dharwad","bareilly","moradabad","mysore","mysuru",
    "gurugram","gurgaon","noida","greater noida","noidaext",
]

US_STATES_FULL = [
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado",
    "Connecticut","Delaware","Florida","Georgia","Hawaii","Idaho",
    "Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine",
    "Maryland","Massachusetts","Michigan","Minnesota","Mississippi",
    "Missouri","Montana","Nebraska","Nevada","New Hampshire","New Jersey",
    "New Mexico","New York","North Carolina","North Dakota","Ohio",
    "Oklahoma","Oregon","Pennsylvania","Rhode Island","South Carolina",
    "South Dakota","Tennessee","Texas","Utah","Vermont","Virginia",
    "Washington","West Virginia","Wisconsin","Wyoming",
]
US_STATE_CODES = [
    r"\bAL\b",r"\bAK\b",r"\bAZ\b",r"\bAR\b",r"\bCO\b",r"\bCT\b",
    r"\bDE\b",r"\bFL\b",r"\bGA\b",r"\bHI\b",r"\bID\b",r"\bIL\b",
    r"\bIN\b",r"\bIA\b",r"\bKS\b",r"\bKY\b",r"\bLA\b",r"\bME\b",
    r"\bMD\b",r"\bMA\b",r"\bMI\b",r"\bMN\b",r"\bMS\b",r"\bMO\b",
    r"\bMT\b",r"\bNE\b",r"\bNV\b",r"\bNH\b",r"\bNM\b",r"\bNC\b",
    r"\bND\b",r"\bOH\b",r"\bOK\b",r"\bOR\b",r"\bRI\b",r"\bSC\b",
    r"\bSD\b",r"\bTN\b",r"\bUT\b",r"\bVT\b",r"\bWA\b",r"\bWV\b",
    r"\bWI\b",r"\bWY\b",
]
US_CITIES = [
    "Detroit","Nashville","Charlotte","Portland","Las Vegas","Memphis",
    "Louisville","Baltimore","Milwaukee","Albuquerque","Tucson","Fresno",
    "Sacramento","Mesa","Kansas City","Omaha","Raleigh","Minneapolis",
    "Cleveland","Wichita","Arlington","Tampa","New Orleans","Cincinnati",
    "Pittsburgh","Riverside","Lexington","Stockton","Corpus Christi",
    "Anchorage","St. Louis","Saint Louis","Indianapolis","Columbus",
    "Oklahoma City","Fort Worth","Jacksonville","San Antonio","San Diego",
    "San Jose","Houston","Austin","Dallas","Denver","Phoenix",
    "Los Angeles","San Francisco","Seattle","Chicago","Boston",
    "New York","Atlanta","Miami","Orlando","Jersey City","Exton",
    "Los Alamitos","Plano","Irving","Scottsdale","Henderson","Chandler",
    "Gilbert","Glendale","Madison","Durham","Baton Rouge","Des Moines",
    "Richmond","Spokane","Tacoma","Akron","Fremont","Aurora","Chesapeake",
]
FOREIGN_TERMS = (
    [r"\bUSA\b",r"\bU\.S\.A\b",r"\bU\.S\.\b",r"\bUnited States\b",
     r"\bAmerica\b",r"\bthe States\b"]
    + [r"\b" + re.escape(s) + r"\b" for s in US_STATES_FULL]
    + US_STATE_CODES
    + [r"\b" + re.escape(c) + r"\b" for c in US_CITIES]
    + [r"\b[A-Z][a-zA-Z\s]+,\s*("
       r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|"
       r"MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|"
       r"RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b"]
    + [r"\bUK\b",r"\bU\.K\.\b",r"\bUnited Kingdom\b",r"\bBritain\b",
       r"\bGreat Britain\b",r"\bEngland\b",r"\bScotland\b",r"\bWales\b",
       r"\bNorthern Ireland\b",r"\bLondon\b"]
    + [r"\bCanada\b",r"\bOntario\b",r"\bToronto\b",r"\bVancouver\b",
       r"\bCalgary\b",r"\bMontreal\b",r"\bOttawa\b"]
    + [r"\bAustralia\b",r"\bAUS\b",r"\bSydney\b",r"\bMelbourne\b",
       r"\bBrisbane\b",r"\bPerth\b",r"\bAdelaide\b"]
    + [r"\bUAE\b",r"\bU\.A\.E\.\b",r"\bDubai\b",r"\bAbu Dhabi\b",
       r"\bSharjah\b",r"\bAjman\b",r"\bUnited Arab Emirates\b"]
    + [r"\bSaudi Arabia\b",r"\bKSA\b",r"\bRiyadh\b",r"\bJeddah\b"]
    + [r"\bQatar\b",r"\bDoha\b",r"\bSingapore\b"]
    + [r"\bGermany\b",r"\bDeutschland\b",r"\bBerlin\b",
       r"\bMunich\b",r"\bFrankfurt\b",r"\bHamburg\b"]
    + [r"\bFrance\b",r"\bParis\b"]
    + [r"\bNetherlands\b",r"\bHolland\b",r"\bAmsterdam\b"]
    + [r"\bNew Zealand\b",r"\bNZ\b",r"\bAuckland\b"]
    + [r"\bIreland\b",r"\bDublin\b"]
    + [r"\bSouth Africa\b",r"\bJohannesburg\b",r"\bCape Town\b"]
    + [r"\bMalaysia\b",r"\bKuala Lumpur\b"]
    + [r"\bPhilippines\b",r"\bManila\b"]
    + [r"\bPakistan\b",r"\bKarachi\b",r"\bLahore\b",r"\bIslamabad\b"]
    + [r"\bSri Lanka\b",r"\bColombo\b"]
    + [r"\bBangladesh\b",r"\bDhaka\b"]
    + [r"\bNepal\b",r"\bKathmandu\b"]
    + [r"\bChina\b",r"\bJapan\b",r"\bKorea\b",r"\bBrazil\b",
       r"\bMexico\b",r"\bItaly\b",r"\bSpain\b",r"\bRussia\b",
       r"\bSweden\b",r"\bNorway\b",r"\bDenmark\b",r"\bFinland\b",
       r"\bSwitzerland\b",r"\bPoland\b",r"\bBelgium\b"]
)
CONTEXT_GUARD_PHRASES = [
    r"(client|customer|customers|team|teams|project|projects|market|"
    r"based clients|serving|support|experience with|worked with|"
    r"working with|offices in|collaborat|partner|stakeholder)",
]
LOCATION_SIGNALS = [
    "based in","location:","location :","hiring in","opening in",
    "position in","office in","role in","job in","onsite","on-site",
    "remote","hybrid","work from","relocate to","must be in",
    "require to be in","opportunity in","opening at","based out of",
]
FOREIGN_FLAGS = [
    "🇺🇸","🇬🇧","🇨🇦","🇦🇺","🇩🇪","🇫🇷","🇳🇱","🇸🇬","🇦🇪",
    "🇸🇦","🇶🇦","🇳🇿","🇮🇪","🇿🇦","🇲🇾","🇵🇭","🇵🇰","🇱🇰",
    "🇧🇩","🇳🇵","🇯🇵","🇨🇳","🇰🇷","🇧🇷","🇲🇽","🇮🇹","🇪🇸",
    "🇷🇺","🇸🇪","🇳🇴","🇩🇰","🇫🇮","🇨🇭","🇵🇱","🇧🇪",
]


# ════════════════════════════════════════════
# STRIP INVISIBLE CHARACTERS
# ════════════════════════════════════════════
def strip_invisible_chars(text):
    for c in ["\u200b","\u200c","\u200d","\u200e","\u200f",
              "\u00ad","\ufeff","\u2060","\u180e"]:
        text = text.replace(c, "")
    return text


# ════════════════════════════════════════════
# ✅ EXPERIENCE FILTER — ALL 11 PATTERNS
# IMPORTANT: Runs on post BODY only
# Never runs on poster name or title
# ════════════════════════════════════════════

# ── KEEP patterns ──
KEEP_EXPERIENCE_PATTERNS = [
    r"\bfresher\b",
    r"\bfreshers\b",
    r"\bno experience required\b",
    r"\bno experience needed\b",
    r"\b0[\s\-]*1\s*(?:year|yr|yrs)\b",
    r"\bless than 1\s*(?:year|yr|yrs)\b",
    r"\b6\s*months?\b",
    r"\b3\s*months?\b",
    r"\bentry[\s\-]*level\b",
    r"\bintern\b",
    r"\btrainee\b",
    r"\bjunior\b",
    r"\bapprentice\b",
    r"\bgraduate\s+hire\b",
    r"\bcampus\s+hire\b",
    # Pattern 5: "Fresher to X Years" — keep only if X<=1
    r"\bfresher\s+to\s+[01]\s*(?:year|yr|yrs)\b",
    # Pattern 11: "0-3 years (immediate joiners)" type — keep 0-1 range
    r"\b0\s*[-–]\s*1\s*(?:year|yr|yrs)\b",
]

_EXP_SUFFIX = r"(?:years?|yrs?)"

REMOVE_EXPERIENCE_PATTERNS = [

    # ── PATTERN 1: Briefcase emoji + experience ──
    # "💼 Experience: 3–5 Years" / "💼 Experience: 5+ Years"
    r"experience\s*[:\-]\s*\d+\s*[-–+]\s*\d*\s*" + _EXP_SUFFIX,
    r"experience\s*[:\-]\s*\d+\+\s*" + _EXP_SUFFIX,

    # ── PATTERN 2: Plain text experience labels ──
    # "Experience: 4 to 5 years" / "Experience: 5+ years"
    r"experience\s*[:\|]\s*\d+\s*(?:to|[-–])\s*\d+\s*" + _EXP_SUFFIX,
    r"experience\s*[:\|]\s*\d+\+?\s*" + _EXP_SUFFIX,

    # ── PATTERN 3: Abbreviated Exp labels ──
    # "Exp: 2-3 years" / "Exp: 5+ yrs"
    r"\bexp\s*[:\|]\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,
    r"\bexp\s*[:\|]\s*\d+\+?\s*" + _EXP_SUFFIX,

    # ── PATTERN 4: Bullet/symbol prefix ──
    # "✔ 5–8 years" / "✦ 8-12 years" / "• 5+ years"
    r"[✔✦•★▸►*]\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,
    r"[✔✦•★▸►*]\s*\d+\+\s*" + _EXP_SUFFIX,

    # ── PATTERN 5: "Fresher to X Years" where X > 1 ──
    # "Fresher to 3 Years" / "Freshers & Experienced"
    r"\bfresher\s+to\s+[2-9]\s*" + _EXP_SUFFIX,
    r"\bfreshers?\s*[&and]+\s*experienced\b",

    # ── PATTERN 6: Parenthetical formats ──
    # "SAP MM (2-5 yrs)" / "Module (3+ years)"
    r"\(\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX + r"\s*\)",
    r"\(\s*\d+\+\s*" + _EXP_SUFFIX + r"\s*\)",

    # ── PATTERN 7: Inline sentence ──
    # "at least 2 years of experience" / "minimum 3 years"
    r"\bat[\s\-]*least\s+\d+\s*[-–]?\s*\d*\s*" + _EXP_SUFFIX,
    r"\bminimum\s+\d+\s*[-–]?\s*\d*\s*" + _EXP_SUFFIX,
    r"\bminimum\s+of\s+\d+\s*" + _EXP_SUFFIX,

    # ── PATTERN 8: Role title with hyphenated suffix ──
    # "SAP MM Consultant – 3+ Years" / "Developer - 5+ yrs"
    r"\b\w+\s*[-–]\s*\d+\+\s*" + _EXP_SUFFIX,
    r"\b\w+\s*[-–]\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,

    # ── PATTERN 9: Search emoji + explicit text ──
    # "🔍 Experience Required: 4–6 Years"
    r"experience\s+required\s*[:\-]\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,
    r"experience\s+required\s*[:\-]\s*\d+\+\s*" + _EXP_SUFFIX,

    # ── PATTERN 10: Tool/domain specific ──
    # "3+ years in D365" / "5+ years in SAP"
    r"\b\d+\+\s*" + _EXP_SUFFIX + r"\s+in\s+\w+",
    r"\b\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX + r"\s+in\s+\w+",

    # ── PATTERN 11: Experience with joining context ──
    # "Experience: 0–3 Years (Immediate joiners)"
    # Only remove if lower bound > 1
    r"experience\s*[:\|]\s*[2-9]\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,

    # ── General numeric catch-all (with yrs fix) ──
    r"\b\d+\.\d+\+?\s*" + _EXP_SUFFIX + r"\b",
    r"\b\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX + r"\b",
    r"\b([2-9]|1[0-9]|20)\+?\s*" + _EXP_SUFFIX + r"\b",
    r"\b[2-9]\s*to\s*\d+\s*" + _EXP_SUFFIX + r"\b",

    # ── Word-based senior signals ──
    r"\b(hiring|looking\s+for|seeking|need|require|must\s+have)"
    r"\s+(an?\s+)?(highly\s+|very\s+)?experienced\b",
    r"\bexperienced\s+\w+\s*(consultant|developer|engineer|analyst|"
    r"architect|manager|professional|specialist|lead|expert)\b",
    r"\bwe\s+are\s+(hiring|looking\s+for|seeking)\s+(an?\s+)?experienced\b",
    r"\bstrong\s+expertise\s+in\b",
    r"\bhands[\s\-]*on\s+(SAP\s+)?\w*\s*experience\b",
    r"\bseasoned\s+(professional|consultant|developer|engineer|"
    r"analyst|expert)\b",
    r"\b(hiring|looking\s+for|seeking|need|require)\s+(a\s+)?senior\b",
    r"\b[2-9]\+?\s*(full\s+life\s+cycle|full\s+lifecycle)\b",
]

KEEP_EXP_RE   = re.compile("|".join(KEEP_EXPERIENCE_PATTERNS), re.IGNORECASE)
REMOVE_EXP_RE = re.compile("|".join(REMOVE_EXPERIENCE_PATTERNS), re.IGNORECASE)


# ✅ FIX: Run ONLY on body text — never on poster name/title
def should_remove_by_experience(body_only):
    has_fresher = bool(KEEP_EXP_RE.search(body_only))
    has_exp     = bool(REMOVE_EXP_RE.search(body_only))
    if has_fresher and has_exp:
        return False   # Dual opening → KEEP
    if has_fresher:
        return False
    if has_exp:
        return True
    return False


# ════════════════════════════════════════════
# LOCATION FILTER
# ════════════════════════════════════════════
INDIA_RE      = re.compile(
    "|".join([r"\b" + t + r"\b" for t in INDIA_TERMS]), re.IGNORECASE)
FOREIGN_RE    = re.compile("|".join(FOREIGN_TERMS), re.IGNORECASE)
FOREIGN_FL_RE = re.compile("|".join(re.escape(f) for f in FOREIGN_FLAGS))
INDIA_FLAG_RE = re.compile(r"🇮🇳")
SIGNAL_RE     = re.compile(
    "|".join([re.escape(s) for s in LOCATION_SIGNALS]), re.IGNORECASE)
CONTEXT_RE    = re.compile(
    "|".join(CONTEXT_GUARD_PHRASES), re.IGNORECASE)

def is_location_mention(post, match):
    start = max(0, match.start() - 60)
    end   = min(len(post), match.end() + 60)
    surr  = post[start:end]
    if CONTEXT_RE.search(surr): return False
    if SIGNAL_RE.search(surr):  return True
    return True

def should_remove_by_location(text):
    if INDIA_RE.search(text):      return False
    if INDIA_FLAG_RE.search(text): return False
    if FOREIGN_FL_RE.search(text): return True
    for m in FOREIGN_RE.finditer(text):
        if is_location_mention(text, m):
            return True
    return False


# ════════════════════════════════════════════
# CLEAN TEXT
# ════════════════════════════════════════════
def clean_text(text):
    text = strip_invisible_chars(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^(\s*#\w+\s*)+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(
        r"[\U0001F300-\U0001F9FF\U00002700-\U000027BF"
        r"\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
        r"\u2600-\u26FF\u2700-\u27BF]+", "", text)
    for p in [
        r"Skip to main content",r"^Home$",r"^My Network$",r"^Jobs$",
        r"^Messaging$",r"^Notifications$",r"^Me$",r"^For Business$",
        r"Try Premium for.*",r"^Posts$",r"^Latest$",r"^Date posted$",
        r"^Content type$",r"^From member$",r"^All filters$",r"^Reset$",
        r"\d+ notifications",r"Are these results helpful\?",
        r"Your feedback helps us improve search results",
        r"Only connections can comment on this post.*",
        r"You can still react or share it\.",
        r"LinkedIn Corporation.*\d{4}",r"About\s+Accessibility.*",
        r"^Join$",r"^Connect$",r"^Share$",r"^Show translation$",
        r"^\s*…\s*more\s*$",r"^\s*…\s*$",r"^more$",
        r"\b\d+[mhd]\s*•",r"•\s*(1st|2nd|3rd\+?)",
        r"^\s*\d+\s*$",r"^Edited\s*•?\s*$",
    ]:
        text = re.sub(p, "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(l.strip() for l in text.splitlines())
    return text.strip()


# ════════════════════════════════════════════
# SPLIT + EXTRACT POSTER
# ════════════════════════════════════════════
def split_into_posts(raw):
    chunks = re.split(r"Feed\s+post", raw, flags=re.IGNORECASE)
    return [c.strip() for c in chunks if len(c.strip()) > 60]

def extract_poster_info(chunk):
    parts = re.split(r"\bFollow\b", chunk, maxsplit=1, flags=re.IGNORECASE)
    meta  = parts[0].strip() if len(parts) == 2 else ""
    body  = parts[1].strip() if len(parts) == 2 else chunk.strip()

    clean_meta = []
    for line in [l.strip() for l in meta.splitlines() if l.strip()]:
        line = re.sub(r"•\s*(1st|2nd|3rd\+?)\s*", "", line).strip()
        line = re.sub(r"\b\d+[mhd]\s*•?\s*", "", line).strip()
        line = re.sub(r"^[\d•\-–|]+$", "", line).strip()
        if line:
            clean_meta.append(line)

    return (
        clean_meta[0] if len(clean_meta) > 0 else "Unknown",
        clean_meta[1] if len(clean_meta) > 1 else "",
        body,
    )

def deduplicate(posts):
    seen, unique = set(), []
    for item in posts:
        fp = re.sub(r"\s+", " ", item["body"][:150]).strip().lower()
        if fp not in seen:
            seen.add(fp)
            unique.append(item)
    return unique


# ════════════════════════════════════════════
# ✅ GROQ AI — SECOND PASS VERIFICATION
# Only runs AFTER regex + repeat poster filter
# Sends minimal extracted text to save tokens
# Returns only structured extracted data
# ════════════════════════════════════════════
def extract_minimal_text(body):
    """
    Extract only the most relevant lines from post body.
    This drastically reduces tokens sent to Groq.
    Looks for lines containing key signals only.
    """
    KEY_SIGNALS = re.compile(
        r"(experience|exp|location|role|position|years|yrs|"
        r"hiring|looking|opening|remote|hybrid|onsite|"
        r"fresher|junior|intern|trainee|entry)",
        re.IGNORECASE,
    )
    lines = body.splitlines()
    relevant = [l.strip() for l in lines
                if l.strip() and KEY_SIGNALS.search(l)]
    # Max 8 lines to keep token usage minimal
    return " | ".join(relevant[:8])


















# ════════════════════════════════════════════
# ✅ GROQ AI — SECOND PASS VERIFICATION
# Model  : qwen/qwen3-32b (free tier)
# Format : 1:true / 2:false  (batch, 1 API call)
# Output : minimal tokens — just number:bool per post
# ════════════════════════════════════════════
def groq_verify_batch(posts):
    """
    Send ALL posts in ONE Groq API call.
    AI returns only:  1:true / 2:false
    true  = KEEP  (fresher, India or no location, genuine job)
    false = REMOVE (exp > 1yr, foreign, not a real job)
    """
    if not GROQ_API_KEY or not posts:
        return posts, []

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        # ── Build numbered batch ──
        # Each post → 1 line of minimal extracted signals only
        batch_lines = []
        for i, item in enumerate(posts, start=1):
            mini = extract_minimal_text(item["body"])
            batch_lines.append(f"{i}. {mini}")

        batch_text = "\n".join(batch_lines)

        # ── Prompt ──
        # /nothink disables qwen3-32b chain-of-thought → saves tokens + latency
        prompt = (
            "/nothink\n\n"
            "You are a strict job post filter for INDIA-based FRESHERS only.\n\n"
            "For each numbered post below, output EXACTLY:\n"
            "  number:true   → KEEP\n"
            "  number:false  → REMOVE\n\n"
            "KEEP rules:\n"
            "- Fresher / 0–1 year / entry-level / intern / trainee\n"
            "- Location is India OR location not mentioned at all\n"
            "- Looks like a genuine job opening\n\n"
            "REMOVE rules:\n"
            "- Requires more than 1 year of experience\n"
            "- Job is outside India (USA, UK, Canada, UAE, etc.)\n"
            "- Not a real job post (advertisement, motivational, spam)\n\n"
            "⚠️ Output ONLY lines like:\n"
            "1:true\n"
            "2:false\n"
            "3:true\n"
            "No explanation. No extra text. No blank lines.\n\n"
            f"Posts:\n{batch_text}"
        )

        # ── API call ──
        # max_tokens: ~6 tokens per post (e.g. "12:false\n") + small buffer
        max_out = max(len(posts) * 8, 60)

        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,          # fully deterministic
            max_tokens=max_out,
        )

        raw_output = response.choices[0].message.content.strip()
        print(f"[Groq qwen3-32b] raw output:\n{raw_output}")

        # ── Parse response ──
        # Only accept lines that strictly match   digit(s):true/false
        # Ignores any stray <think>…</think> or explanation lines
        DECISION_RE = re.compile(r"^(\d+)\s*:\s*(true|false)$", re.IGNORECASE)
        decisions   = {}

        for line in raw_output.splitlines():
            line = line.strip()
            m    = DECISION_RE.match(line)
            if m:
                idx      = int(m.group(1))
                decision = m.group(2).lower()   # "true" or "false"
                decisions[idx] = decision

        # ── Apply decisions ──
        passed  = []
        removed = []

        for i, item in enumerate(posts, start=1):
            # Default → "true" (KEEP) if AI skipped or was unclear
            decision = decisions.get(i, "true")
            if decision == "true":
                passed.append(item)
            else:
                removed.append({
                    **item,
                    "removed_reason": "AI filter",
                })

        print(
            f"[Groq] Total={len(posts)} | "
            f"Kept={len(passed)} | Removed={len(removed)} | "
            f"Parsed={len(decisions)}"
        )
        return passed, removed

    except Exception as e:
        print(f"[Groq Error] {e}")
        return posts, []    # ← safe fallback: keep all posts if Groq fails












# ════════════════════════════════════════════
# EXTRACT STRUCTURED OUTPUT
# Returns only key fields — saves frontend tokens
# ════════════════════════════════════════════
def extract_structured_data(item):
    """
    Extract only the important fields from a post.
    Instead of returning full post body, return:
    - Role / Position
    - Location
    - Experience
    - Contact email
    - Short summary (first 2 relevant lines)
    """
    body  = item["body"]
    lines = [l.strip() for l in body.splitlines() if l.strip()]

    # ── Extract Role ──
    role = ""
    role_re = re.compile(
        r"(?:role|position|opening|hiring for|we are hiring)[:\s]+(.+)",
        re.IGNORECASE,
    )
    m = role_re.search(body)
    if m:
        role = m.group(1).strip()[:80]
    else:
        # Fallback: use first meaningful line as role hint
        for line in lines[:5]:
            if len(line) > 10 and not re.match(r"^(hi|hello|dear)", line, re.I):
                role = line[:80]
                break

    # ── Extract Location ──
    location = ""
    loc_re = re.compile(
        r"(?:location|city|place)[:\s]+(.+)", re.IGNORECASE
    )
    m = loc_re.search(body)
    if m:
        location = m.group(1).strip()[:60]

    # ── Extract Experience ──
    experience = ""
    exp_re = re.compile(
        r"(?:experience|exp)[:\s]+(.+)", re.IGNORECASE
    )
    m = exp_re.search(body)
    if m:
        experience = m.group(1).strip()[:60]

    # ── Extract Contact Email ──
    email = ""
    email_re = re.compile(r"[\w.\-+]+@[\w.\-]+\.[a-zA-Z]{2,}")
    m = email_re.search(body)
    if m:
        email = m.group(0)

    # ── Short Summary ──
    # First 2 non-empty lines that look like content
    summary_lines = []
    for line in lines:
        if len(line) > 20 and not re.match(
            r"^(hi|hello|dear|greetings|we are|i am|"
            r"please|kindly|thanks|regards)", line, re.IGNORECASE
        ):
            summary_lines.append(line)
        if len(summary_lines) == 2:
            break

    return {
        "poster":     item["poster"],
        "title":      item["title"],
        "role":       role,
        "location":   location,
        "experience": experience,
        "email":      email,
        "summary":    " | ".join(summary_lines),
    }


# ════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

@app.route("/spammers", methods=["GET"])
def spammers():
    return jsonify({"spammers": get_top_spammers()})

@app.route("/history", methods=["DELETE"])
def delete_history():
    success = clear_history()
    if success:
        return jsonify({"message": "History cleared."})
    return jsonify({"error": "Failed to clear."}), 500


@app.route("/clean", methods=["POST"])
def clean():
    data     = request.get_json()
    raw_text = data.get("text", "")

    if not raw_text.strip():
        return jsonify({"error": "No text provided"}), 400

    # ── Step 1: Strip invisible chars ──
    raw_text = strip_invisible_chars(raw_text)

    # ── Step 2: Split by Feed post ──
    raw_chunks = split_into_posts(raw_text)

    # ── Step 3: Extract poster info ──
    parsed = []
    for chunk in raw_chunks:
        name, title, body = extract_poster_info(chunk)
        body_cleaned = clean_text(body)
        if len(body_cleaned) > 60:
            parsed.append({
                "poster": name,
                "title":  title,
                "body":   body_cleaned,
            })

    # ── Step 4: Deduplicate ──
    parsed    = deduplicate(parsed)
    total_raw = len(parsed)

    # ── Step 5: Regex filters ──
    # ✅ FIX: Pass ONLY body to experience filter
    removed_exp = 0
    removed_loc = 0
    passed_regex = []

    for item in parsed:
        if should_remove_by_experience(item["body"]):   # body only!
            removed_exp += 1
            continue
        if should_remove_by_location(item["body"]):
            removed_loc += 1
            continue
        passed_regex.append(item)

    # ── Step 6: Repeat poster filter ──
    # Done BEFORE Groq to minimize API tokens
    new_posts, repeat_posts = check_and_update_history(passed_regex)
    removed_repeat = len(repeat_posts)

    # ── Step 7: Groq AI second-pass ──
    # Only runs on posts that passed ALL previous filters
    groq_passed, groq_removed = groq_verify_batch(new_posts)
    removed_ai = len(groq_removed)

    # ── Step 8: Extract structured output ──
    # Returns only key fields — not full post body
    structured_output = [extract_structured_data(item) for item in groq_passed]

    return jsonify({
        "posts":          structured_output,
        "repeat_posters": repeat_posts,
        "stats": {
            "total_raw":          total_raw,
            "removed_experience": removed_exp,
            "removed_location":   removed_loc,
            "removed_repeat":     removed_repeat,
            "removed_ai":         removed_ai,
            "kept":               len(structured_output),
        },
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)