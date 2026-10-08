"""
REBOOT - Your Personal Rhythm
=============================
A personal daily-rhythm dashboard built with Streamlit.

HOW THE FILE IS ORGANISED (read top to bottom):
  1. SETTINGS        - names, version, goals, weights, texts (edit these freely)
  2. HELPERS         - safe number conversion, dates, saving/loading
  3. SCORE LOGIC     - how the Reboot Score, status and advice are worked out
  4. DISPLAY PIECES  - the animated ring, header, footer
  5. THE PAGE        - the dashboard itself, from top to bottom

REBOOT only uses information the user types in. It does not read phone
health data, and the score is a personal wellbeing/productivity score,
not a medical measurement.
"""

import base64
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from PIL import Image  # installed together with Streamlit
except Exception:  # pragma: no cover
    Image = None


# =====================================================================
# 1. SETTINGS  (the owner edits this section)
# =====================================================================

APP_NAME = "REBOOT"
TAGLINE = "Your Personal Rhythm"
MOTTO = "Small steps. Better days. Reboot yourself."

# Owner-controlled version. Change it ONLY when you publish an update,
# e.g. "1.0.0" -> "1.1.0", then add a line to RELEASE_NOTES below.
VERSION = "1.0.0"
RELEASE_NOTES = {
    "1.0.0": "First public release of REBOOT: Reboot Score, daily check-in, "
             "weekly progress, personal best and gentle daily guidance.",
}

# Icon file: place it in the SAME folder as this file (repository root).
ICON_FILE = "reboot_icon.png"

# Time zone used to decide what "today" is.
TIMEZONE = "Asia/Dubai"

# Saving data:
#   False -> each visitor's data stays in their own browser session (private).
#            Use the Backup/Restore buttons in the Privacy section to keep it.
#   True  -> also writes to DATA_FILE on the computer running the app.
#            Only use this for personal use on your own computer, because on a
#            public website every visitor would share the same file.
SAVE_TO_SERVER_FILE = False
DATA_FILE = "reboot_data.json"

# Daily goals used by the score
SLEEP_MIN_HOURS = 7.0       # 7-9 hours earns full sleep points
SLEEP_MAX_HOURS = 9.0
STUDY_GOAL_HOURS = 2.0      # focused study/work
ACTIVITY_GOAL_MINUTES = 30  # exercise/movement
STEPS_GOAL = 8000           # optional, only used if steps are entered
SCREEN_GOOD_HOURS = 3.0     # at or below this = full screen-time points
SCREEN_BAD_HOURS = 8.0      # at or above this = zero screen-time points

# How much each area matters. They add up to 100.
WEIGHTS = {
    "sleep": 25,
    "activity": 20,
    "study": 15,
    "screen": 15,
    "mood": 15,
    "energy": 10,
}

LABELS = {
    "sleep": "Sleep",
    "activity": "Activity",
    "study": "Study / Focus",
    "screen": "Screen time",
    "mood": "Mood",
    "energy": "Energy",
}

# Score status: (minimum score, label, colour). Checked from top to bottom.
STATUS_LEVELS = [
    (85, "Excellent", "#0D9488"),
    (70, "Good", "#0891B2"),
    (50, "Fair", "#D97706"),
    (0, "Needs attention", "#DC2626"),
]

# If even the weakest area scores at least this, we say the day is balanced.
BALANCED_THRESHOLD = 80
# An area scoring below this counts as "needing attention" for messages.
WEAK_THRESHOLD = 60

# Recommendation text (short, polite, practical)
RECOMMENDATIONS = {
    "sleep": "Your sleep was a little low today. Try giving yourself some extra time to rest tonight.",
    "activity": "Your activity was lower today. A short walk or some movement could help you stay active.",
    "screen": "Your screen time was a little high today. Try taking a few short screen-free breaks.",
    "study": "You could use a little more focused study time. Try one short distraction-free session.",
    "mood": "Your mood felt a bit low today. Be kind to yourself: a short break, some fresh air, or a chat with someone you trust can help.",
    "energy": "Your energy was a little low today. A glass of water, a short stretch and an earlier night may help.",
}
BALANCED_TEXT = "Everything looks nicely balanced today. Keep the same easy rhythm going."

# Daily messages. One is picked per day, so it changes from day to day.
MESSAGES = {
    "great": [
        "Great rhythm today. Keep it up!",
        "You are in a good flow. Enjoy it.",
        "A strong day. Small habits are paying off.",
        "Nicely done. Today's rhythm looks steady and balanced.",
    ],
    "one_area": [
        "A good day overall. A small boost to {area} could make it even better.",
        "You are close. Just give {area} a little attention.",
        "Nearly there. A gentle focus on {area} is all it needs.",
    ],
    "several": [
        "Some days are slower, and that is okay. Pick one small thing to improve tonight.",
        "Start small: choose one area and give it a little care today.",
        "Every reboot starts with one step. Choose just one thing to improve.",
    ],
    "empty": [
        "Add your first check-in to see your Reboot Score.",
    ],
}

MOOD_LABELS = {1: "Very low", 2: "Low", 3: "Okay", 4: "Good", 5: "Great"}
ENERGY_LABELS = {1: "Very low", 2: "Low", 3: "Okay", 4: "High", 5: "Very high"}

# Colours
CYAN = "#14B8A6"
CYAN_LIGHT = "#22D3EE"
INK = "#0F172A"
MUTED = "#64748B"


# =====================================================================
# PAGE SET-UP (must be the first Streamlit call)
# =====================================================================

def load_page_icon():
    """Return the icon image for the browser tab, or an emoji if missing."""
    try:
        path = Path(__file__).parent / ICON_FILE
        if Image is not None and path.exists():
            return Image.open(path)
    except Exception:
        pass
    return "🔄"  # simple fallback if reboot_icon.png is missing


st.set_page_config(
    page_title=f"{APP_NAME} · {TAGLINE}",
    page_icon=load_page_icon(),
    layout="centered",
    initial_sidebar_state="collapsed",
)


# =====================================================================
# 2. HELPERS
# =====================================================================

def to_float(value, default=0.0, low=None, high=None):
    """Turn anything into a safe number. Bad input becomes `default`."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN check
        return default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def optional_number(value, high):
    """For optional health numbers: 0 or blank means 'not entered' (None)."""
    number = to_float(value, 0.0, 0.0, high)
    return number if number > 0 else None


def clean_entry(raw):
    """Check and tidy one day's data so the rest of the app can trust it."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "sleep": to_float(raw.get("sleep"), 0.0, 0.0, 24.0),
        "study": to_float(raw.get("study"), 0.0, 0.0, 16.0),
        "activity": to_float(raw.get("activity"), 0.0, 0.0, 600.0),
        "screen": to_float(raw.get("screen"), 0.0, 0.0, 24.0),
        "mood": int(to_float(raw.get("mood"), 3, 1, 5)),
        "energy": int(to_float(raw.get("energy"), 3, 1, 5)),
        # Optional health & activity details
        "steps": optional_number(raw.get("steps"), 100000),
        "distance": optional_number(raw.get("distance"), 200),
        "calories": optional_number(raw.get("calories"), 10000),
        "heart_rate": optional_number(raw.get("heart_rate"), 250),
        "weight": optional_number(raw.get("weight"), 500),
        "source": "manual",
    }


def today_local():
    """Today's date in the configured time zone."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TIMEZONE)).date()
    except Exception:
        return date.today()


def load_entries():
    """Load saved entries (only reads a file if SAVE_TO_SERVER_FILE is True)."""
    if not SAVE_TO_SERVER_FILE:
        return {}
    try:
        path = Path(DATA_FILE)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return parse_entries(data)
    except Exception:
        st.session_state["flash_error"] = "Saved data could not be read, so REBOOT started fresh."
    return {}


def parse_entries(data):
    """Convert a loaded dictionary into clean entries. Skips anything invalid."""
    result = {}
    if not isinstance(data, dict):
        return result
    for key, raw in data.items():
        try:
            date.fromisoformat(str(key))
            result[str(key)] = clean_entry(raw)
        except ValueError:
            continue
    return result


def persist_entries():
    """Write entries to a file if that option is switched on."""
    if not SAVE_TO_SERVER_FILE:
        return
    try:
        Path(DATA_FILE).write_text(
            json.dumps(st.session_state["entries"], indent=2), encoding="utf-8"
        )
    except Exception:
        st.session_state["flash_error"] = "Your check-in was saved for now, but could not be written to a file."


def sorted_dates(entries):
    return sorted(entries.keys())


def best_score(entries, exclude=None):
    """Highest score so far (optionally ignoring one date). Returns (score, date) or (None, None)."""
    best, best_day = None, None
    for day, entry in entries.items():
        if day == exclude:
            continue
        score = overall_score(entry)
        if best is None or score > best:
            best, best_day = score, day
    return best, best_day


# =====================================================================
# 3. SCORE LOGIC
# =====================================================================

def category_scores(entry):
    """Give each area a score from 0 to 100."""
    # Sleep: full points between 7-9 h, fewer points below or far above
    sleep = entry["sleep"]
    if sleep < SLEEP_MIN_HOURS:
        sleep_score = sleep / SLEEP_MIN_HOURS * 100
    elif sleep <= SLEEP_MAX_HOURS:
        sleep_score = 100
    else:
        sleep_score = max(60, 100 - (sleep - SLEEP_MAX_HOURS) * 10)

    # Activity: minutes of exercise, or steps if entered (whichever is better)
    activity_score = min(entry["activity"] / ACTIVITY_GOAL_MINUTES, 1) * 100
    if entry.get("steps"):
        activity_score = max(activity_score, min(entry["steps"] / STEPS_GOAL, 1) * 100)

    # Study: hours of focused work compared with the goal
    study_score = min(entry["study"] / STUDY_GOAL_HOURS, 1) * 100

    # Screen time: LOWER is better
    screen = entry["screen"]
    if screen <= SCREEN_GOOD_HOURS:
        screen_score = 100
    elif screen >= SCREEN_BAD_HOURS:
        screen_score = 0
    else:
        screen_score = (SCREEN_BAD_HOURS - screen) / (SCREEN_BAD_HOURS - SCREEN_GOOD_HOURS) * 100

    # Mood and energy: 1-5 scale mapped to 0-100
    mood_score = (entry["mood"] - 1) / 4 * 100
    energy_score = (entry["energy"] - 1) / 4 * 100

    return {
        "sleep": round(sleep_score),
        "activity": round(activity_score),
        "study": round(study_score),
        "screen": round(screen_score),
        "mood": round(mood_score),
        "energy": round(energy_score),
    }


def overall_score(entry):
    """Weighted average of all areas -> whole number 0-100."""
    scores = category_scores(entry)
    total_weight = sum(WEIGHTS.values())
    total = sum(scores[key] * WEIGHTS[key] for key in WEIGHTS)
    return int(round(total / total_weight))


def status_for(score):
    """Return (label, colour) for a score."""
    for minimum, label, colour in STATUS_LEVELS:
        if score >= minimum:
            return label, colour
    return STATUS_LEVELS[-1][1], STATUS_LEVELS[-1][2]


def weakest_area(entry):
    """Find the area losing the most points. Returns key, or None if balanced."""
    scores = category_scores(entry)
    # Points lost = (100 - score) x weight, so important areas count more
    lost = {key: (100 - scores[key]) * WEIGHTS[key] for key in WEIGHTS}
    worst = max(lost, key=lost.get)
    if scores[worst] >= BALANCED_THRESHOLD:
        return None
    return worst


def daily_message(entry, day_key):
    """Pick one short message. Same day = same message, new day = may change."""
    rng = random.Random(f"{day_key}-{overall_score(entry)}")
    scores = category_scores(entry)
    weak = [key for key in WEIGHTS if scores[key] < WEAK_THRESHOLD]
    if len(weak) >= 3:
        return rng.choice(MESSAGES["several"])
    if weak:
        area = LABELS[weak[0]].lower()
        return rng.choice(MESSAGES["one_area"]).format(area=area)
    return rng.choice(MESSAGES["great"])


def weekly_trend(scores):
    """Compare the older half with the newer half of the week."""
    if len(scores) < 4:
        return "Add more check-ins to see your trend"
    half = len(scores) // 2
    older = sum(scores[:half]) / half
    newer = sum(scores[half:]) / (len(scores) - half)
    if newer - older >= 3:
        return "Improving ↑"
    if older - newer >= 3:
        return "Slipping a little ↓"
    return "Steady →"


# ---- Future health-data connection --------------------------------
def get_automatic_health_data():
    """
    FUTURE: a native Android app using Health Connect could send steps,
    sleep, heart rate and more to this function (for example through a
    secure API). A normal Streamlit website cannot read phone health data,
    so for now this honestly returns None and the app uses manual entry.

    When an integration exists, return a dictionary like:
        {"steps": 7421, "sleep": 7.2, "calories": 2100}
    """
    return None


# =====================================================================
# 4. DISPLAY PIECES
# =====================================================================

def icon_data_uri():
    """Icon as inline data for the header. Returns None if file is missing."""
    try:
        path = Path(__file__).parent / ICON_FILE
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return None


def inject_css():
    st.markdown(
        f"""
        <style>
        .stApp {{ background: #F6F8FB; }}
        html, body, [class*="css"] {{
            font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        .block-container {{
            max-width: 820px;
            padding-top: 1.6rem;
            padding-bottom: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }}
        h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
        h3 {{ font-size: 1.15rem !important; margin-bottom: 0.2rem; }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #FFFFFF;
            border-radius: 16px;
            border-color: #E2E8F0;
        }}
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
            min-height: 48px;
            border-radius: 12px;
            font-weight: 600;
            transition: box-shadow 0.15s ease;
        }}
        .stButton > button:hover, .stFormSubmitButton > button:hover {{
            box-shadow: 0 2px 8px rgba(20, 184, 166, 0.25);
        }}
        input, textarea {{ font-size: 16px !important; }}  /* avoids zoom on iPhone */
        .rb-header {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
        .rb-logo {{ width: 56px; height: 56px; border-radius: 14px; flex-shrink: 0; }}
        .rb-title {{ font-size: clamp(1.8rem, 7vw, 2.4rem); font-weight: 800;
                     color: {INK}; line-height: 1.05; letter-spacing: 0.04em; }}
        .rb-tagline {{ font-size: 1rem; color: {CYAN}; font-weight: 600; }}
        .rb-motto {{ color: {MUTED}; margin: 0.5rem 0 1.2rem 0; font-size: 1rem; }}
        .rb-badge {{ display: inline-block; padding: 4px 14px; border-radius: 999px;
                     color: #fff; font-weight: 700; font-size: 0.95rem; }}
        .rb-center {{ text-align: center; }}
        .rb-footer {{ text-align: center; color: {MUTED}; font-size: 0.8rem;
                      margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #E2E8F0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    logo = icon_data_uri()
    logo_html = f'<img class="rb-logo" src="{logo}" alt="REBOOT logo">' if logo else ""
    st.markdown(
        f"""
        <div class="rb-header">
            {logo_html}
            <div>
                <div class="rb-title">{APP_NAME}</div>
                <div class="rb-tagline">{TAGLINE}</div>
            </div>
        </div>
        <div class="rb-motto">“{MOTTO}”</div>
        """,
        unsafe_allow_html=True,
    )


RING_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; padding: 0; background: transparent;
               font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { display: flex; justify-content: center; padding: 6px 0; }
  .ring { --size: min(68vw, 220px); position: relative; width: var(--size); height: var(--size); }
  svg { width: 100%; height: 100%; display: block; }
  .track { fill: none; stroke: #E2E8F0; stroke-width: 10; }
  .prog  { fill: none; stroke: url(#grad); stroke-width: 10; stroke-linecap: round; }
  .center { position: absolute; inset: 0; display: flex; flex-direction: column;
            align-items: center; justify-content: center; }
  .num { font-size: calc(var(--size) * 0.34); font-weight: 800; color: #0F172A; line-height: 1; }
  .max { font-size: calc(var(--size) * 0.11); color: #64748B; margin-top: 4px; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="ring" role="img" aria-label="Reboot Score __LABEL__">
      <svg viewBox="0 0 120 120">
        <defs>
          <linearGradient id="grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#22D3EE"/>
            <stop offset="100%" stop-color="#14B8A6"/>
          </linearGradient>
        </defs>
        <circle class="track" cx="60" cy="60" r="52"></circle>
        <circle id="prog" class="prog" cx="60" cy="60" r="52" transform="rotate(-90 60 60)"></circle>
      </svg>
      <div class="center">
        <div class="num" id="num">0</div>
        <div class="max">/100</div>
      </div>
    </div>
  </div>
<script>
  var target = __SCORE__;
  var hasScore = __HAS__;
  var C = 2 * Math.PI * 52;
  var prog = document.getElementById("prog");
  var num = document.getElementById("num");
  prog.style.strokeDasharray = C;

  function draw(percent) {
    prog.style.strokeDashoffset = C * (1 - percent / 100);
    prog.style.opacity = percent > 0.4 ? 1 : 0;   // hide the round dot at 0
  }

  if (!hasScore) {
    num.textContent = "–";
    draw(0);
  } else {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var duration = reduce ? 0 : 1200;     // 1.2 seconds, short and subtle
    var start = null;
    function step(now) {
      if (start === null) start = now;
      var t = duration ? Math.min((now - start) / duration, 1) : 1;
      var eased = 1 - Math.pow(1 - t, 3);          // smooth slow-down at the end
      var value = target * eased;
      draw(value);
      num.textContent = Math.round(value);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
</script>
</body>
</html>
"""


def render_score_ring(score):
    """Animated circular score. `score` is 0-100, or None when there is no data."""
    has_score = score is not None
    value = int(score) if has_score else 0
    html = (
        RING_HTML.replace("__SCORE__", str(value))
        .replace("__HAS__", "true" if has_score else "false")
        .replace("__LABEL__", f"{value} out of 100" if has_score else "not available")
    )
    components.html(html, height=250)


def render_footer():
    st.markdown(
        f'<div class="rb-footer">{APP_NAME} · {TAGLINE} · Version {VERSION}</div>',
        unsafe_allow_html=True,
    )


# =====================================================================
# SAVING A CHECK-IN (runs when the Save button is pressed)
# =====================================================================

def save_checkin():
    """Callback for the Save button. Runs BEFORE the page redraws."""
    try:
        state = st.session_state
        chosen_date = state.get("ci_date") or today_local()
        key = chosen_date.isoformat()

        entry = clean_entry({
            "sleep": state.get("ci_sleep"),
            "study": state.get("ci_study"),
            "activity": state.get("ci_activity"),
            "screen": state.get("ci_screen"),
            "mood": state.get("ci_mood"),
            "energy": state.get("ci_energy"),
            "steps": state.get("ci_steps"),
            "distance": state.get("ci_distance"),
            "calories": state.get("ci_calories"),
            "heart_rate": state.get("ci_heart_rate"),
            "weight": state.get("ci_weight"),
        })

        previous_best, _ = best_score(state["entries"], exclude=key)
        state["entries"][key] = entry
        persist_entries()

        new_score = overall_score(entry)
        message = f"Check-in saved for {chosen_date.strftime('%d %b %Y')}."
        if previous_best is not None and new_score > previous_best:
            message += f" 🎉 New personal best: {new_score}/100!"
        state["flash"] = message
    except Exception:
        st.session_state["flash_error"] = (
            "Something went wrong while saving. Please check your values and try again."
        )


def load_sample_week():
    """Fill in 7 clearly-labelled sample days so the dashboard can be explored."""
    rng = random.Random(7)
    today = today_local()
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        st.session_state["entries"][day.isoformat()] = clean_entry({
            "sleep": round(rng.uniform(5.5, 8.5) * 2) / 2,
            "study": round(rng.uniform(0.5, 3) * 2) / 2,
            "activity": rng.choice([10, 20, 30, 45, 60]),
            "screen": round(rng.uniform(2, 7) * 2) / 2,
            "mood": rng.randint(2, 5),
            "energy": rng.randint(2, 5),
            "steps": rng.choice([4500, 6200, 8100, 9500]),
        })
    persist_entries()
    st.session_state["flash"] = "Sample week loaded. Replace it with your own check-ins any time."


# =====================================================================
# 5. THE PAGE
# =====================================================================

inject_css()

if "entries" not in st.session_state:
    st.session_state["entries"] = load_entries()

entries = st.session_state["entries"]

render_header()

# Messages from the last action
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))
if st.session_state.get("flash_error"):
    st.warning(st.session_state.pop("flash_error"))

# Pick the entry to show on the dashboard: the most recent check-in
latest_key = sorted_dates(entries)[-1] if entries else None
latest = entries.get(latest_key) if latest_key else None

# Safe calculations (an unexpected problem should never crash the app)
score, status_label, status_colour, scores, attention_key, message = None, "", MUTED, {}, None, ""
try:
    if latest:
        score = overall_score(latest)
        status_label, status_colour = status_for(score)
        scores = category_scores(latest)
        attention_key = weakest_area(latest)
        message = daily_message(latest, latest_key)
except Exception:
    latest = None
    st.warning("Today's data could not be read. Please save a new check-in.")

# ---------------- Reboot Score + Today's Status ----------------
col_score, col_info = st.columns([1, 1], gap="medium")

with col_score:
    with st.container(border=True):
        st.markdown("### Reboot Score")
        render_score_ring(score)
        if latest:
            shown = datetime.strptime(latest_key, "%Y-%m-%d").strftime("%a, %d %b")
            st.markdown(
                f'<div class="rb-center"><span class="rb-badge" style="background:{status_colour}">'
                f"{status_label}</span><br><span style='color:{MUTED};font-size:0.85rem'>"
                f"Based on your check-in for {shown}</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="rb-center" style="color:{MUTED}">No check-in yet</div>',
                unsafe_allow_html=True,
            )

with col_info:
    with st.container(border=True):
        st.markdown("### Today's Status")
        if latest:
            st.write(message)
        else:
            st.write(random.choice(MESSAGES["empty"]))

    with st.container(border=True):
        st.markdown("### What Needs Attention?")
        if latest:
            if attention_key:
                st.markdown(f"**{LABELS[attention_key]}**")
                st.write(RECOMMENDATIONS[attention_key])
            else:
                st.write(BALANCED_TEXT)
        else:
            st.write("Your weakest area will appear here after your first check-in.")

# Score breakdown (transparent scoring)
if latest:
    with st.expander("How is my score calculated?"):
        st.caption(
            "Each area earns 0-100 points. Your Reboot Score is the weighted average. "
            "It is a personal wellbeing and productivity score, not a medical measurement."
        )
        for key in WEIGHTS:
            st.markdown(f"**{LABELS[key]}** · {scores[key]}/100 · counts for {WEIGHTS[key]}%")
            st.progress(int(scores[key]))

# ---------------- Health & Activity ----------------
with st.container(border=True):
    st.markdown("### Health & Activity")

    auto_data = None
    try:
        auto_data = get_automatic_health_data()
    except Exception:
        auto_data = None

    def health_value(key, unit, fmt="{:,.0f}"):
        """Show a health value: automatic if available, otherwise the manual one."""
        value = None
        if isinstance(auto_data, dict) and auto_data.get(key):
            value = auto_data.get(key)
        elif latest and latest.get(key):
            value = latest.get(key)
        return f"{fmt.format(value)} {unit}".strip() if value else "—"

    if latest:
        row1 = st.columns(3)
        row1[0].metric("Sleep", f"{latest['sleep']:.1f} h")
        row1[1].metric("Active time", f"{latest['activity']:.0f} min")
        row1[2].metric("Steps", health_value("steps", ""))
        row2 = st.columns(3)
        row2[0].metric("Distance", health_value("distance", "km", "{:.1f}"))
        row2[1].metric("Calories", health_value("calories", "kcal"))
        row2[2].metric("Heart rate", health_value("heart_rate", "bpm"))
        if latest.get("weight"):
            st.caption(f"Weight: {latest['weight']:.1f} kg")
        st.caption("Values marked — were not entered. Optional details can be added in the check-in below.")
    else:
        st.write("Your health and activity details will appear here after your first check-in.")

    with st.expander("Connect Health Data"):
        st.write(
            "REBOOT is a web app, so it cannot read health data from your phone directly. "
            "For now, you can enter your numbers in the Quick Daily Check-In below. "
            "It only takes a minute."
        )
        st.write(
            "A future Android version of REBOOT could use Health Connect, with your "
            "permission, to bring in steps, sleep and other activity data automatically."
        )
        st.button("Connect Health Connect (coming with the Android app)", disabled=True)

# ---------------- Quick Daily Check-In ----------------
with st.container(border=True):
    st.markdown("### Quick Daily Check-In")
    st.caption("Takes about a minute. Pick a date, then fill in your day.")

    today = today_local()
    st.date_input("Date", value=today, max_value=today, key="ci_date")

    with st.form("checkin_form", border=False):
        st.slider("Sleep (hours)", 0.0, 14.0, 7.0, 0.5, key="ci_sleep")
        st.slider("Screen time (hours, not counting study)", 0.0, 16.0, 4.0, 0.5, key="ci_screen")
        c1, c2 = st.columns(2)
        c1.number_input("Study / focus (hours)", 0.0, 16.0, 1.0, 0.5, key="ci_study")
        c2.number_input("Exercise / activity (minutes)", 0, 600, 20, 5, key="ci_activity")
        st.select_slider("Mood", options=[1, 2, 3, 4, 5], value=3,
                         format_func=lambda v: MOOD_LABELS[v], key="ci_mood")
        st.select_slider("Energy", options=[1, 2, 3, 4, 5], value=3,
                         format_func=lambda v: ENERGY_LABELS[v], key="ci_energy")

        with st.expander("Optional health details (leave at 0 if unknown)"):
            o1, o2 = st.columns(2)
            o1.number_input("Steps", 0, 100000, 0, 500, key="ci_steps")
            o2.number_input("Distance (km)", 0.0, 200.0, 0.0, 0.5, key="ci_distance")
            o3, o4 = st.columns(2)
            o3.number_input("Calories (kcal)", 0, 10000, 0, 50, key="ci_calories")
            o4.number_input("Heart rate (bpm)", 0, 250, 0, 1, key="ci_heart_rate")
            st.number_input("Weight (kg)", 0.0, 500.0, 0.0, 0.5, key="ci_weight")

        st.form_submit_button("Save check-in", type="primary",
                              use_container_width=True, on_click=save_checkin)

    if not entries:
        st.button("Or explore with a sample week", on_click=load_sample_week,
                  use_container_width=True)

# ---------------- Weekly Progress ----------------
with st.container(border=True):
    st.markdown("### Weekly Progress")
    try:
        recent_keys = sorted_dates(entries)[-7:]
        if recent_keys:
            recent_scores = [overall_score(entries[k]) for k in recent_keys]
            labels = [datetime.strptime(k, "%Y-%m-%d").strftime("%a %d") for k in recent_keys]
            chart_data = pd.DataFrame({"Day": labels, "Score": recent_scores}).set_index("Day")

            st.caption(f"Your last {len(recent_keys)} check-in(s)")
            st.bar_chart(chart_data, color=CYAN, height=240)

            m1, m2, m3 = st.columns(3)
            m1.metric("Average", f"{sum(recent_scores) / len(recent_scores):.0f}")
            m2.metric("Highest", f"{max(recent_scores)}")
            m3.metric("Lowest", f"{min(recent_scores)}")
            st.markdown(f"**Trend:** {weekly_trend(recent_scores)}")

            best, best_day = best_score(entries)
            if best is not None:
                best_label = datetime.strptime(best_day, "%Y-%m-%d").strftime("%d %b %Y")
                st.markdown(f"**Personal Best: {best}/100** · {best_label}")
                if latest and score == best and len(entries) > 1:
                    st.caption("Today's score matches your personal best. Nicely done.")
        else:
            st.write("Save a few check-ins to see your weekly progress here.")
    except Exception:
        st.warning("The weekly chart could not be drawn. Please try saving a new check-in.")

# ---------------- Privacy, Data and About ----------------
with st.expander("Privacy"):
    st.write(
        f"{APP_NAME} only uses the information you type in. It does not read your phone's "
        "health data, contacts, location or messages. Unless you choose to connect a supported "
        "health-data source in a future version, nothing else is collected."
    )
    st.write(
        "Your check-ins stay in your browser session and are not shared with other visitors. "
        "Use the backup option below to keep a copy, since closing the page can clear them."
    )

with st.expander("Your data: backup, restore, clear"):
    try:
        st.download_button(
            "Download backup",
            data=json.dumps(entries, indent=2),
            file_name="reboot_backup.json",
            mime="application/json",
            use_container_width=True,
            disabled=not entries,
        )
        uploaded = st.file_uploader("Restore from a backup file", type=["json"])
        if uploaded is not None and st.button("Restore this backup", use_container_width=True):
            restored = parse_entries(json.loads(uploaded.getvalue().decode("utf-8")))
            if restored:
                st.session_state["entries"].update(restored)
                persist_entries()
                st.session_state["flash"] = f"Restored {len(restored)} check-in(s)."
                st.rerun()
            else:
                st.warning("That file did not contain any valid REBOOT check-ins.")
    except Exception:
        st.warning("That backup file could not be read. Please choose a file downloaded from REBOOT.")

    confirm = st.checkbox("I want to delete all my check-ins")
    if st.button("Clear all data", disabled=not confirm, use_container_width=True):
        st.session_state["entries"] = {}
        persist_entries()
        st.session_state["flash"] = "All check-ins were cleared."
        st.rerun()

with st.expander("About REBOOT"):
    st.write(
        f"**{APP_NAME} · {TAGLINE}** helps you understand your daily rhythm and make small "
        "improvements in sleep, activity, focus, screen time, mood and energy."
    )
    st.write("The Reboot Score is a personal wellbeing and productivity score. It is not medical advice.")
    st.markdown(f"**Version {VERSION}**")
    st.caption(RELEASE_NOTES.get(VERSION, ""))

render_footer()