from flask import Flask, request, jsonify
from flask_cors import CORS
import re, json, os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# ════════════════════════════════════════════
# HISTORY FILE — Local JSON storage
# Stores poster history for 7 days
# ════════════════════════════════════════════
HISTORY_FILE = "poster_history.json"

def load_history():
    """Load poster history from JSON file."""
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_history(history):
    """Save poster history to JSON file."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def clean_old_history(history):
    """
    Remove entries older than 7 days.
    Runs every time history is loaded.
    """
    cutoff = datetime.now() - timedelta(days=7)
    cleaned = {}
    for key, data in history.items():
        try:
            seen_date = datetime.fromisoformat(data["first_seen"])
            if seen_date >= cutoff:
                cleaned[key] = data
        except Exception:
            pass
    return cleaned

def make_poster_key(poster_name, poster_title):
    """
    Create a unique key from poster name + title.
    Lowercased and stripped for reliable matching.
    """
    name  = re.sub(r"\s+", " ", poster_name.strip().lower())
    title = re.sub(r"\s+", " ", poster_title.strip().lower())
    return f"{name}||{title}"

def check_and_update_history(final_posts):
    """
    For each post:
    1. Check if poster key exists in history → mark as REPEAT
    2. If new → add to history with timestamp + count
    3. If repeat → increment count, update last_seen
    Returns:
      - new_posts     : list of posts NOT seen before (safe to show)
      - repeat_posts  : list of posts from repeat posters (flagged)
    """
    history = load_history()
    history = clean_old_history(history)  # clean expired entries

    new_posts    = []
    repeat_posts = []

    for item in final_posts:
        key = make_poster_key(item["poster"], item["title"])

        if key in history:
            # ── REPEAT POSTER DETECTED ──
            history[key]["count"]     += 1
            history[key]["last_seen"]  = datetime.now().isoformat()
            repeat_posts.append({
                **item,
                "repeat_count": history[key]["count"],
                "first_seen":   history[key]["first_seen"],
                "last_seen":    history[key]["last_seen"],
            })
        else:
            # ── NEW POSTER ──
            history[key] = {
                "poster":     item["poster"],
                "title":      item["title"],
                "first_seen": datetime.now().isoformat(),
                "last_seen":  datetime.now().isoformat(),
                "count":      1,
            }
            new_posts.append(item)

    save_history(history)
    return new_posts, repeat_posts


# ════════════════════════════════════════════
# INDIA ALLOWLIST
# ════════════════════════════════════════════
INDIA_TERMS = [
    "india", "bharat", r"\bIND\b", "pan india", "pan-india",
    "remote india", "work from india", "wfh india", "hybrid india",
    "ncr", "pan-india",
    "andhra pradesh", "arunachal pradesh", "assam", "bihar",
    "chhattisgarh", "goa", "gujarat", "haryana", "himachal pradesh",
    "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra",
    "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "punjab",
    "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu", "kashmir", "ladakh", "chandigarh", "puducherry",
    "pondicherry", "andaman", "nicobar", "lakshadweep", "dadra", "daman", "diu",
    "mumbai", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata",
    "pune", "ahmedabad", "surat", "jaipur", "lucknow", "kanpur", "nagpur",
    "indore", "thane", "bhopal", "visakhapatnam", "vizag", "patna",
    "vadodara", "ghaziabad", "ludhiana", "agra", "nashik", "faridabad",
    "meerut", "rajkot", "kalyan", "vasai", "varanasi", "srinagar",
    "aurangabad", "dhanbad", "amritsar", "navi mumbai", "allahabad",
    "prayagraj", "ranchi", "coimbatore", "jabalpur", "gwalior", "vijayawada",
    "jodhpur", "madurai", "raipur", "kota", "guwahati", "solapur",
    "hubli", "dharwad", "bareilly", "moradabad", "mysore", "mysuru",
    "gurugram", "gurgaon", "noida", "greater noida", "noidaext",
]

# ════════════════════════════════════════════
# ALL 50 US STATES + MAJOR CITIES
# ════════════════════════════════════════════
US_STATES_FULL = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California",
    "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
    "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
    "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
    "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma",
    "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]

US_STATE_CODES = [
    r"\bAL\b", r"\bAK\b", r"\bAZ\b", r"\bAR\b",
    r"\bCO\b", r"\bCT\b", r"\bDE\b", r"\bFL\b",
    r"\bGA\b", r"\bHI\b", r"\bID\b", r"\bIL\b",
    r"\bIN\b", r"\bIA\b", r"\bKS\b", r"\bKY\b",
    r"\bLA\b", r"\bME\b", r"\bMD\b", r"\bMA\b",
    r"\bMI\b", r"\bMN\b", r"\bMS\b", r"\bMO\b",
    r"\bMT\b", r"\bNE\b", r"\bNV\b", r"\bNH\b",
    r"\bNM\b", r"\bNC\b", r"\bND\b", r"\bOH\b",
    r"\bOK\b", r"\bOR\b", r"\bRI\b", r"\bSC\b",
    r"\bSD\b", r"\bTN\b", r"\bUT\b", r"\bVT\b",
    r"\bWA\b", r"\bWV\b", r"\bWI\b", r"\bWY\b",
]

US_CITIES = [
    "Detroit", "Nashville", "Charlotte", "Portland", "Las Vegas",
    "Memphis", "Louisville", "Baltimore", "Milwaukee", "Albuquerque",
    "Tucson", "Fresno", "Sacramento", "Mesa", "Kansas City",
    "Omaha", "Raleigh", "Minneapolis", "Cleveland", "Wichita",
    "Arlington", "Tampa", "New Orleans", "Cincinnati", "Pittsburgh",
    "Riverside", "Lexington", "Stockton", "Corpus Christi", "Anchorage",
    "St. Louis", "Saint Louis", "Indianapolis", "Columbus", "Oklahoma City",
    "Fort Worth", "Jacksonville", "San Antonio", "San Diego", "San Jose",
    "Houston", "Austin", "Dallas", "Denver", "Phoenix",
    "Los Angeles", "San Francisco", "Seattle", "Chicago", "Boston",
    "New York", "Atlanta", "Miami", "Orlando", "Jersey City",
    "Exton", "Los Alamitos", "Plano", "Irving", "Scottsdale",
    "Henderson", "Chandler", "Gilbert", "Glendale", "Madison",
    "Durham", "Baton Rouge", "Des Moines", "Richmond", "Spokane",
    "Tacoma", "Akron", "Fremont", "Aurora", "Chesapeake",
]

FOREIGN_TERMS = (
    [r"\bUSA\b", r"\bU\.S\.A\b", r"\bU\.S\.\b", r"\bUnited States\b",
     r"\bAmerica\b", r"\bthe States\b"]
    + [r"\b" + re.escape(s) + r"\b" for s in US_STATES_FULL]
    + US_STATE_CODES
    + [r"\b" + re.escape(c) + r"\b" for c in US_CITIES]
    + [r"\b[A-Z][a-zA-Z\s]+,\s*("
       r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|"
       r"MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|"
       r"RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b"]
    + [r"\bUK\b", r"\bU\.K\.\b", r"\bUnited Kingdom\b", r"\bBritain\b",
       r"\bGreat Britain\b", r"\bEngland\b", r"\bScotland\b", r"\bWales\b",
       r"\bNorthern Ireland\b", r"\bLondon\b"]
    + [r"\bCanada\b", r"\bOntario\b", r"\bToronto\b", r"\bVancouver\b",
       r"\bCalgary\b", r"\bMontreal\b", r"\bOttawa\b"]
    + [r"\bAustralia\b", r"\bAUS\b", r"\bSydney\b", r"\bMelbourne\b",
       r"\bBrisbane\b", r"\bPerth\b", r"\bAdelaide\b"]
    + [r"\bUAE\b", r"\bU\.A\.E\.\b", r"\bDubai\b", r"\bAbu Dhabi\b",
       r"\bSharjah\b", r"\bAjman\b", r"\bUnited Arab Emirates\b"]
    + [r"\bSaudi Arabia\b", r"\bKSA\b", r"\bRiyadh\b", r"\bJeddah\b"]
    + [r"\bQatar\b", r"\bDoha\b"]
    + [r"\bSingapore\b"]
    + [r"\bGermany\b", r"\bDeutschland\b", r"\bBerlin\b",
       r"\bMunich\b", r"\bFrankfurt\b", r"\bHamburg\b"]
    + [r"\bFrance\b", r"\bParis\b"]
    + [r"\bNetherlands\b", r"\bHolland\b", r"\bAmsterdam\b"]
    + [r"\bNew Zealand\b", r"\bNZ\b", r"\bAuckland\b"]
    + [r"\bIreland\b", r"\bDublin\b"]
    + [r"\bSouth Africa\b", r"\bJohannesburg\b", r"\bCape Town\b"]
    + [r"\bMalaysia\b", r"\bKuala Lumpur\b"]
    + [r"\bPhilippines\b", r"\bManila\b"]
    + [r"\bPakistan\b", r"\bKarachi\b", r"\bLahore\b", r"\bIslamabad\b"]
    + [r"\bSri Lanka\b", r"\bColombo\b"]
    + [r"\bBangladesh\b", r"\bDhaka\b"]
    + [r"\bNepal\b", r"\bKathmandu\b"]
    + [r"\bChina\b", r"\bJapan\b", r"\bKorea\b", r"\bBrazil\b",
       r"\bMexico\b", r"\bItaly\b", r"\bSpain\b", r"\bRussia\b",
       r"\bSweden\b", r"\bNorway\b", r"\bDenmark\b", r"\bFinland\b",
       r"\bSwitzerland\b", r"\bPoland\b", r"\bBelgium\b"]
)

CONTEXT_GUARD_PHRASES = [
    r"(client|customer|customers|team|teams|project|projects|market|"
    r"based clients|serving|support|experience with|worked with|"
    r"working with|offices in|collaborat|partner|stakeholder)",
]

LOCATION_SIGNALS = [
    "based in", "location:", "location :", "hiring in", "opening in",
    "position in", "office in", "role in", "job in", "onsite", "on-site",
    "remote", "hybrid", "work from", "relocate to", "must be in",
    "require to be in", "opportunity in", "opening at", "based out of",
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
    invisible = [
        "\u200b", "\u200c", "\u200d", "\u200e", "\u200f",
        "\u00ad", "\ufeff", "\u2060", "\u180e",
    ]
    for char in invisible:
        text = text.replace(char, "")
    return text


# ════════════════════════════════════════════
# EXPERIENCE FILTER
# ════════════════════════════════════════════
KEEP_EXPERIENCE_PATTERNS = [
    r"\bfresher\b", r"\bfreshers\b",
    r"\bno experience required\b", r"\bno experience needed\b",
    r"\b0[\s\-]*1\s*(?:year|yr|yrs)\b",
    r"\bless than 1\s*(?:year|yr|yrs)\b",
    r"\b6\s*months?\b", r"\b3\s*months?\b",
    r"\bentry[\s\-]*level\b", r"\bintern\b",
    r"\btrainee\b", r"\bjunior\b",
    r"\bapprentice\b", r"\bgraduate\s+hire\b",
    r"\bcampus\s+hire\b",
]

_EXP_PREFIX = r"(?:[:\|\s]*)"
_EXP_SUFFIX = r"(?:years?|yrs?)"

REMOVE_EXPERIENCE_PATTERNS = [
    _EXP_PREFIX + r"\b\d+\.\d+\+?\s*" + _EXP_SUFFIX + r"\b",
    _EXP_PREFIX + r"\b\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX + r"\b",
    _EXP_PREFIX + r"\b([2-9]|1[0-9]|20)\+?\s*" + _EXP_SUFFIX + r"\b",
    r"\bminimum\s+[2-9]\s*" + _EXP_SUFFIX + r"\b",
    r"\bat\s+least\s+[2-9]\s*" + _EXP_SUFFIX + r"\b",
    r"\b[2-9]\s*to\s*\d+\s*" + _EXP_SUFFIX + r"\b",
    r"exp(?:erience)?\s*[:\|]\s*\d+[\s\-–]+\d+\s*" + _EXP_SUFFIX,
    r"exp(?:erience)?\s*[:\|]\s*\d+\+?\s*" + _EXP_SUFFIX,
    r"exp(?:erience)?\s*:\s*\d+\s*[-–]\s*\d+\s*" + _EXP_SUFFIX,
    r"exp(?:erience)?\s*:\s*\d+\+\s*" + _EXP_SUFFIX,
    r"\b(hiring|looking\s+for|seeking|need|require|must\s+have|want)"
    r"\s+(an?\s+)?(highly\s+|very\s+)?experienced\b",
    r"\bexperienced\s+\w+\s*(consultant|developer|engineer|analyst|"
    r"architect|manager|professional|specialist|lead|expert)\b",
    r"\bwe\s+are\s+(hiring|looking\s+for|seeking)\s+(an?\s+)?experienced\b",
    r"\bstrong\s+expertise\s+in\b",
    r"\bhands[\s\-]*on\s+(SAP\s+)?\w*\s*experience\b",
    r"\bseasoned\s+(professional|consultant|developer|engineer|analyst|expert)\b",
    r"\b(hiring|looking\s+for|seeking|need|require)\s+(a\s+)?senior\b",
    r"\b[2-9]\+?\s*(full\s+life\s+cycle|full\s+lifecycle|end[\s\-]to[\s\-]end)\b",
]

KEEP_EXP_RE   = re.compile("|".join(KEEP_EXPERIENCE_PATTERNS), re.IGNORECASE)
REMOVE_EXP_RE = re.compile("|".join(REMOVE_EXPERIENCE_PATTERNS), re.IGNORECASE)


def should_remove_by_experience(post):
    has_fresher = bool(KEEP_EXP_RE.search(post))
    has_exp     = bool(REMOVE_EXP_RE.search(post))
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
INDIA_RE       = re.compile(
    "|".join([r"\b" + term + r"\b" for term in INDIA_TERMS]),
    re.IGNORECASE,
)
FOREIGN_RE     = re.compile("|".join(FOREIGN_TERMS), re.IGNORECASE)
FOREIGN_FL_RE  = re.compile("|".join(re.escape(f) for f in FOREIGN_FLAGS))
INDIA_FLAG_RE  = re.compile(r"🇮🇳")
SIGNAL_RE      = re.compile(
    "|".join([re.escape(s) for s in LOCATION_SIGNALS]), re.IGNORECASE
)
CONTEXT_RE     = re.compile(
    "|".join(CONTEXT_GUARD_PHRASES), re.IGNORECASE
)


def is_location_mention(post, term_match):
    start      = max(0, term_match.start() - 60)
    end        = min(len(post), term_match.end() + 60)
    surrounding = post[start:end]
    if CONTEXT_RE.search(surrounding):
        return False
    if SIGNAL_RE.search(surrounding):
        return True
    return True


def should_remove_by_location(post):
    if INDIA_RE.search(post):
        return False
    if INDIA_FLAG_RE.search(post):
        return False
    if FOREIGN_FL_RE.search(post):
        return True
    for match in FOREIGN_RE.finditer(post):
        if is_location_mention(post, match):
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
        r"\u2600-\u26FF\u2700-\u27BF]+", "", text,
    )
    ui_patterns = [
        r"Skip to main content", r"^Home$", r"^My Network$",
        r"^Jobs$", r"^Messaging$", r"^Notifications$", r"^Me$",
        r"^For Business$", r"Try Premium for.*", r"^Posts$",
        r"^Latest$", r"^Date posted$", r"^Content type$",
        r"^From member$", r"^All filters$", r"^Reset$",
        r"\d+ notifications", r"Are these results helpful\?",
        r"Your feedback helps us improve search results",
        r"Only connections can comment on this post.*",
        r"You can still react or share it\.",
        r"LinkedIn Corporation.*\d{4}",
        r"About\s+Accessibility.*",
        r"^Join$", r"^Connect$", r"^Share$",
        r"^Show translation$", r"^\s*…\s*more\s*$",
        r"^\s*…\s*$", r"^more$",
        r"\b\d+[mhd]\s*•", r"•\s*(1st|2nd|3rd\+?)",
        r"^\s*\d+\s*$", r"^Edited\s*•?\s*$",
    ]
    for pattern in ui_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()


# ════════════════════════════════════════════
# SPLIT + EXTRACT POSTER INFO
# ════════════════════════════════════════════
def split_into_posts(raw_text):
    chunks = re.split(r"Feed\s+post", raw_text, flags=re.IGNORECASE)
    return [c.strip() for c in chunks if len(c.strip()) > 60]


def extract_poster_info(chunk):
    follow_split = re.split(
        r"\bFollow\b", chunk, maxsplit=1, flags=re.IGNORECASE
    )
    if len(follow_split) == 2:
        metadata_block = follow_split[0].strip()
        body_block     = follow_split[1].strip()
    else:
        metadata_block = ""
        body_block     = chunk.strip()

    meta_lines = [l.strip() for l in metadata_block.splitlines() if l.strip()]
    clean_meta = []
    for line in meta_lines:
        line = re.sub(r"•\s*(1st|2nd|3rd\+?)\s*", "", line).strip()
        line = re.sub(r"\b\d+[mhd]\s*•?\s*", "", line).strip()
        line = re.sub(r"^[\d•\-–|]+$", "", line).strip()
        if line:
            clean_meta.append(line)

    poster_name  = clean_meta[0] if len(clean_meta) > 0 else "Unknown"
    poster_title = clean_meta[1] if len(clean_meta) > 1 else ""
    return poster_name, poster_title, body_block


# ════════════════════════════════════════════
# DEDUPLICATION
# ════════════════════════════════════════════
def deduplicate(parsed_posts):
    seen, unique = set(), []
    for item in parsed_posts:
        fp = re.sub(r"\s+", " ", item["body"][:150]).strip().lower()
        if fp not in seen:
            seen.add(fp)
            unique.append(item)
    return unique


# ════════════════════════════════════════════
# EXTRA ENDPOINT — VIEW HISTORY
# GET /history → returns all stored poster history
# ════════════════════════════════════════════
@app.route("/history", methods=["GET"])
def get_history():
    history = load_history()
    history = clean_old_history(history)
    save_history(history)

    # Sort by count descending (most repeated first)
    sorted_history = sorted(
        history.values(),
        key=lambda x: x["count"],
        reverse=True,
    )
    return jsonify({
        "total_tracked": len(sorted_history),
        "entries": sorted_history,
    })


# ════════════════════════════════════════════
# EXTRA ENDPOINT — CLEAR HISTORY
# DELETE /history → wipes poster_history.json
# ════════════════════════════════════════════
@app.route("/history", methods=["DELETE"])
def clear_history():
    save_history({})
    return jsonify({"message": "History cleared successfully."})


# ════════════════════════════════════════════
# MAIN ENDPOINT
# ════════════════════════════════════════════
@app.route("/clean", methods=["POST"])
def clean():
    data     = request.get_json()
    raw_text = data.get("text", "")

    if not raw_text.strip():
        return jsonify({"error": "No text provided"}), 400

    raw_text   = strip_invisible_chars(raw_text)
    raw_chunks = split_into_posts(raw_text)

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

    parsed    = deduplicate(parsed)
    total_raw = len(parsed)

    removed_exp = 0
    removed_loc = 0
    passed      = []

    for item in parsed:
        full_text = item["poster"] + " " + item["title"] + " " + item["body"]
        if should_remove_by_experience(full_text):
            removed_exp += 1
            continue
        if should_remove_by_location(full_text):
            removed_loc += 1
            continue
        passed.append(item)

    # ── History check ──
    new_posts, repeat_posts = check_and_update_history(passed)
    removed_repeat = len(repeat_posts)

    return jsonify({
        "posts": new_posts,
        "repeat_posters": repeat_posts,
        "stats": {
            "total_raw":          total_raw,
            "removed_experience": removed_exp,
            "removed_location":   removed_loc,
            "removed_repeat":     removed_repeat,
            "kept":               len(new_posts),
        },
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)