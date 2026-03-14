import base64
import json
import re
import time
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

st.set_page_config(page_title="Story Spark Club", page_icon="\U0001F4DA", layout="centered")

# -----------------------------------------------------------------------------
# APP SECTION KEY
# -----------------------------------------------------------------------------
# 1) Configuration and theme constants (lines ~1-60): page setup, story themes, voice map
# 2) State initialization (lines ~62-118): st.session_state defaults and UI defaults setup
# 3) Utility functions (lines ~120-220): word count, text split, chunking, audio + PDF generation
# 4) Story generation logic (lines ~222-330): prompt builders, generate_story_with_length_guard, choice parsing
# 5) UI render functions (lines ~332-430): render_category_selector, mode selector, hero section, progress bar
# 6) Step-based flow (lines ~432-700): Step 1 Dream It, Step 2 Spin the Tale, Step 3 Paint + Print, Step 4 Storytime
# 7) Analytics (lines ~702-end): usage logging, Analytics panel display
# -----------------------------------------------------------------------------

THEME_CONFIG = {
    "Adventure Stories": {
        "icon": "\U0001F5FA",
        "scene": "jungle mountains and hidden paths",
        "header": "Mountain Quest",
        "hero_image": "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1600&q=80",
    },
    "Animal Stories": {
        "icon": "\U0001F43E",
        "scene": "friendly woodland animals",
        "header": "Woodland Friends",
        "hero_image": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1600&q=80",
    },
    "Science Stories": {
        "icon": "\U0001F52C",
        "scene": "friendly science lab, stars, planets, and curious inventions",
        "header": "Curious Cosmos Lab",
        "hero_image": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&w=1600&q=80",
    },
    "Confidence & Courage Stories": {
        "icon": "\U0001FA84",
        "scene": "gentle sunrise path, supportive friends, and brave first steps",
        "header": "Brave Heart Journey",
        "hero_image": "https://images.unsplash.com/photo-1502082553048-f009c37129b9?auto=format&fit=crop&w=1600&q=80",
    },
    "Friendship Stories": {
        "icon": "\U0001F91D",
        "scene": "cozy neighborhood, teamwork, and kind-hearted companions",
        "header": "Kindness Circle",
        "hero_image": "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?auto=format&fit=crop&w=1600&q=80",
    },
    "Funny Stories": {
        "icon": "\U0001F923",
        "scene": "silly surprises, playful scenes, and laugh-out-loud moments",
        "header": "Giggle Quest",
        "hero_image": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=1600&q=80",
    },
}

CHALLENGE_OPTIONS = [
    "Afraid of getting hurt",
    "First day of school",
    "Making new friends",
    "Feeling shy",
    "Being brave",
    "Bullying",
    "Trying something new",
    "Sports confidence",
]

# & C:/Users/trome/anaconda3/python.exe -m streamlit run app.py


VOICE_MAP = {
    "Olivia (Warm)": "nova",
    "James (Storyteller)": "alloy",
    "Mia (Playful)": "shimmer",
    "Noah (Calm)": "echo",
    "Sophia (Gentle)": "fable",
}

LENGTH_RULES = {
    "Short": {"min_words": 480, "word_target": 600, "max_tokens": 1200},
    "Medium": {"min_words": 900, "word_target": 1100, "max_tokens": 2200},
    "Long": {"min_words": 1500, "word_target": 1800, "max_tokens": 3200},
    "7-Night Adventure": {"min_words": 900, "word_target": 1100, "max_tokens": 2200},
}

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"], timeout=60.0)


def init_state():
    defaults = {
        "current_step": 1,
        "hero_name": "",
        "hero_age": 7,
        "pronoun": "They",
        "story_mode": "Sleepy Story",
        "story_category": "Adventure Stories",
        "challenge": CHALLENGE_OPTIONS[0],
        "length": "Medium",
        "topic": "",
        "book_type": "Story Book (Color Cover)",
        "story": None,
        "story_sections": [],
        "story_image": None,
        "story_images": [],
        "per_paragraph_images": False,
        "pdf_data": None,
        "audio_bytes": None,
        "audio_generating": False,
        "selected_voice_name": "Olivia (Warm)",
        "preview_page": 1,
        "guided_reading_on": False,
        "typewriter_requested": False,
        "chosen_path": [],
        "series_active": False,
        "series_night": 0,
        "series_episodes": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.story_category not in THEME_CONFIG:
        st.session_state.story_category = "Adventure Stories"
    if st.session_state.challenge not in CHALLENGE_OPTIONS:
        st.session_state.challenge = CHALLENGE_OPTIONS[0]
    ui_defaults = {
        "ui_hero_name": st.session_state.hero_name,
        "ui_hero_age": st.session_state.hero_age,
        "ui_pronoun": st.session_state.pronoun,
        "ui_story_category": st.session_state.story_category,
        "ui_challenge": st.session_state.challenge,
        "ui_length": st.session_state.length,
        "ui_topic": st.session_state.topic,
        "ui_book_type": st.session_state.book_type,
        "ui_per_paragraph_images": st.session_state.per_paragraph_images,
    }
    for key, value in ui_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,700&display=swap');
:root {
  --font-ui: 'Plus Jakarta Sans', sans-serif;
  --font-display: 'Fraunces', serif;
  --night-950: #060814;
  --night-900: #0b1023;
  --night-800: #111a3b;
  --violet-700: #4f46e5;
  --violet-500: #7c72f8;
  --gold-400: #f4c56c;
  --text-strong: #f8f9ff;
  --text-body: #d8ddf3;
  --text-muted: #a8b0d9;
  --glass-bg: rgba(14, 21, 46, 0.52);
  --glass-border: rgba(180, 193, 255, 0.24);
  --glass-inner: rgba(255, 255, 255, 0.07);
  --shadow-elev: 0 24px 60px rgba(2, 5, 20, 0.52);
  --space-1: 8px;
  --space-2: 16px;
  --space-3: 24px;
  --space-4: 32px;
  --space-6: 48px;
  --space-7: 64px;
  --card-radius: 22px;
  --pill-radius: 999px;
}
.stApp {
  background:
    radial-gradient(1200px 520px at 8% -10%, rgba(244, 197, 108, 0.18), transparent 58%),
    radial-gradient(1000px 520px at 88% -12%, rgba(124, 114, 248, 0.26), transparent 55%),
    linear-gradient(156deg, var(--night-950) 0%, var(--night-900) 34%, var(--night-800) 100%);
  background-attachment: fixed;
}
.block-container {
  max-width: 920px;
  padding-top: var(--space-6);
  padding-bottom: var(--space-7);
}
.storybook-shell {
  border-radius: 28px;
  padding: 30px;
  background:
    linear-gradient(155deg, rgba(19, 27, 58, 0.82), rgba(9, 14, 36, 0.72)),
    var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-elev), inset 0 1px 0 var(--glass-inner);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  position: relative;
}
.hero-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(2.1rem, 1.58rem + 2.3vw, 3.5rem);
  line-height: 1.12;
  letter-spacing: 0.01em;
  color: var(--text-strong);
  text-shadow: 0 6px 20px rgba(0,0,0,0.34);
}
.hero-sub {
  margin: 12px 0 0;
  color: var(--text-body);
  font-family: var(--font-ui);
  font-size: 1rem;
  font-weight: 500;
  max-width: 58ch;
  line-height: 1.65;
}
.hero-illustration {
  margin-top: var(--space-4);
  width: 100%;
  height: 272px;
  border-radius: var(--card-radius);
  overflow: hidden;
  border: 1px solid rgba(216, 222, 255, 0.22);
  background-size: cover;
  background-position: center;
  box-shadow: var(--shadow-elev);
  position: relative;
}
.hero-illustration::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(6, 10, 30, 0.18) 6%, rgba(6, 10, 30, 0.75) 85%),
    radial-gradient(760px 240px at 0% 0%, rgba(244, 197, 108, 0.2), transparent 70%);
}
.hero-overlay {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 28px 30px;
  color: white;
  position: relative;
  z-index: 1;
}
.hero-kicker {
  margin: 0;
  color: #f7deb0;
  font-family: var(--font-ui);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hero-line {
  margin: 4px 0 0;
  font-family: var(--font-display);
  font-size: clamp(1.65rem, 1.35rem + 1vw, 2.3rem);
  color: #f7f9ff;
  text-shadow: 0 4px 16px rgba(0,0,0,0.36);
}
.step-tracker {
  margin-top: var(--space-3);
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.step-item {
  border-radius: var(--pill-radius);
  padding: 11px 10px;
  text-align: center;
  background: rgba(149, 162, 228, 0.16);
  border: 1px solid rgba(156, 172, 245, 0.2);
  color: var(--text-muted);
  font-family: var(--font-ui);
  font-size: 0.9rem;
  font-weight: 600;
  transition: transform 0.25s ease, box-shadow 0.25s ease, color 0.25s ease;
}
.step-item.current {
  background: linear-gradient(130deg, rgba(106, 98, 248, 0.5), rgba(90, 157, 255, 0.35));
  border-color: rgba(226, 232, 255, 0.56);
  color: #ffffff;
  box-shadow: 0 10px 26px rgba(42, 48, 133, 0.44), inset 0 0 0 1px rgba(255, 255, 255, 0.32);
  transform: translateY(-1px);
}
.step-card-title,
h3 {
  font-family: var(--font-display) !important;
  font-size: clamp(1.6rem, 1.45rem + 0.7vw, 2rem) !important;
  font-weight: 700 !important;
  margin-top: var(--space-4) !important;
  margin-bottom: 10px !important;
  color: var(--text-strong) !important;
  letter-spacing: 0.01em;
}
h4, strong {
  color: var(--text-strong);
}
p, li, .stMarkdown, .stCaption, .st-emotion-cache-10trblm, .st-emotion-cache-16idsys p {
  font-family: var(--font-ui) !important;
  color: var(--text-body);
}
label, .stRadio label, .stSelectbox label, .stTextInput label, .stTextArea label, .stNumberInput label {
  font-family: var(--font-ui) !important;
  font-size: 0.96rem !important;
  font-weight: 700 !important;
  color: #eef1ff !important;
}
.glass-card,
.preview-card,
.choice-box,
.page-panel {
  border-radius: var(--card-radius);
  padding: 28px;
  background:
    linear-gradient(145deg, rgba(20, 30, 63, 0.66), rgba(8, 13, 32, 0.66)),
    var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-elev), inset 0 1px 0 var(--glass-inner);
  margin-top: 14px;
  margin-bottom: var(--space-2);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.mode-title {
  font-family: var(--font-display);
  font-size: 1.65rem;
  margin: 0 0 var(--space-1) 0;
  color: var(--text-strong);
}
.mode-copy {
  margin: 0;
  color: var(--text-body);
  line-height: 1.5;
}
.mode-selected {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: var(--pill-radius);
  padding: 6px 12px;
  background: rgba(244, 197, 108, 0.16);
  border: 1px solid rgba(244, 197, 108, 0.46);
  color: #ffde9f;
  font-family: var(--font-ui);
  font-size: 0.8rem;
  font-weight: 700;
}
.mode-card {
  transition: transform 0.24s ease, box-shadow 0.24s ease, border-color 0.24s ease;
  border: 1px solid rgba(179, 191, 255, 0.2);
}
.selected-card {
  border-color: rgba(244, 197, 108, 0.58);
  box-shadow: 0 20px 40px rgba(8, 11, 29, 0.52), 0 0 0 1px rgba(244, 197, 108, 0.24) inset;
}
.mode-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 24px 40px rgba(5, 7, 20, 0.55);
  border-color: rgba(216, 224, 255, 0.4);
}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] > div,
div[data-testid="stMultiSelect"] > div {
  min-height: 52px;
  border-radius: 14px !important;
  border: 1px solid rgba(169, 183, 247, 0.34) !important;
  box-shadow: none !important;
  background: rgba(9, 14, 33, 0.82) !important;
  color: #f8f9ff !important;
  font-family: var(--font-ui) !important;
}
div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder {
  color: #94a0cf !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus,
div[data-testid="stNumberInput"] input:focus {
  border: 1px solid rgba(201, 214, 255, 0.74) !important;
  box-shadow: 0 0 0 3px rgba(104, 117, 255, 0.28) !important;
}
div[data-baseweb="select"] > div {
  background: rgba(9, 14, 33, 0.82) !important;
  color: #f8f9ff !important;
}
div[data-testid="stNumberInput"] button {
  border-radius: 10px !important;
  border: 1px solid rgba(169, 183, 247, 0.34) !important;
  background: rgba(17, 27, 56, 0.9) !important;
  color: #ebeeff !important;
}
div[data-testid="stRadio"] [role="radiogroup"] {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
div[data-testid="stRadio"] [role="radiogroup"] > label {
  margin: 0 !important;
  border-radius: var(--pill-radius);
  border: 1px solid rgba(169, 183, 247, 0.36);
  background: rgba(11, 17, 39, 0.8);
  padding: 10px 14px;
}
div[data-testid="stRadio"] [role="radiogroup"] > label:hover {
  border-color: rgba(221, 229, 255, 0.56);
}
div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
  background: linear-gradient(132deg, rgba(93, 83, 245, 0.6), rgba(66, 124, 228, 0.5));
  border-color: rgba(229, 236, 255, 0.74);
  box-shadow: 0 10px 22px rgba(36, 44, 123, 0.45);
}
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
  min-height: 54px;
  border-radius: var(--pill-radius) !important;
  font-family: var(--font-ui);
  font-size: 0.98rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em;
  transition: transform 0.22s ease, box-shadow 0.22s ease, filter 0.22s ease, border-color 0.22s ease;
}
div[data-testid="stButton"] > button {
  border: 1px solid rgba(178, 191, 255, 0.26) !important;
}
div[data-testid="stButton"] > button[kind="secondary"],
div[data-testid="stDownloadButton"] > button {
  background: linear-gradient(140deg, rgba(32, 43, 88, 0.88), rgba(18, 25, 55, 0.9)) !important;
  color: #f2f5ff !important;
  box-shadow: 0 10px 22px rgba(5, 9, 28, 0.38) !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover,
div[data-testid="stDownloadButton"] > button:hover {
  transform: translateY(-2px);
  border-color: rgba(229, 236, 255, 0.62) !important;
  box-shadow: 0 14px 26px rgba(8, 13, 35, 0.48) !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
  color: #fff !important;
  border: 1px solid rgba(240, 223, 174, 0.44) !important;
  background:
    radial-gradient(circle at 15% 22%, rgba(244,197,108,0.46), transparent 36%),
    linear-gradient(95deg, #5c53f2 0%, #4f46e5 52%, #365cd7 100%) !important;
  box-shadow: 0 14px 30px rgba(63, 78, 221, 0.5), 0 0 0 1px rgba(255,255,255,0.14) inset !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  transform: translateY(-2px);
  filter: brightness(1.04);
  box-shadow: 0 18px 36px rgba(66, 88, 241, 0.56), 0 0 24px rgba(244,197,108,0.34) !important;
}
.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible {
  outline: 3px solid rgba(245, 198, 109, 0.5) !important;
  outline-offset: 2px;
}
.premium-note {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 0.9rem;
}
.step-divider {
  margin: 18px 0 6px;
  border: 0;
  border-top: 1px solid rgba(190, 201, 253, 0.2);
}
.stAlert {
  border-radius: 16px !important;
}
hr {
  border-top-color: rgba(190, 201, 253, 0.28) !important;
}
@media (max-width: 760px) {
  .block-container { padding-top: 24px; }
  .storybook-shell { padding: 22px; }
  .hero-illustration { height: 232px; }
  .step-tracker { grid-template-columns: 1fr 1fr; }
  .preview-card, .choice-box, .page-panel { padding: 20px; }
}
</style>
""",
    unsafe_allow_html=True,
)


def count_words(text: str) -> int:
    return len((text or "").split())


def split_sections(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if not parts:
        return []
    grouped = []
    for idx in range(0, len(parts), 2):
        grouped.append("\n\n".join(parts[idx : idx + 2]))
    return grouped


def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(" "))
            if cut > 0:
                end = start + cut
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def generate_audio_bytes(text, voice="nova"):
    for attempt in range(1, 3):
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                response_format="mp3",
            )
            return response.content
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.0)
    return b""


def narrate_full_story(story_text: str, voice: str = "nova") -> bytes:
    chunks = chunk_text(story_text, max_chars=3000)
    audio_all = b""
    for chunk in chunks:
        audio_all += generate_audio_bytes(chunk, voice=voice)
    return audio_all


@st.cache_data(show_spinner=False)
def tts_cached(story_text: str, voice: str) -> bytes:
    return narrate_full_story(story_text, voice=voice)


def log_story(name, age, story_category, topic, challenge=None, tokens_used=None):
    data = {
        "timestamp": str(datetime.now()),
        "name": name,
        "age": age,
        "story_category": story_category,
        "theme": story_category,
        "challenge": challenge if story_category == "Confidence & Courage Stories" else "",
        "topic": topic,
        "tokens_used": tokens_used,
    }
    with open("usage_log.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


def progress_markup(step: int) -> str:
    labels = ["✨ Dream It", "🪄 Spin", "🎨 Paint", "🎙 Listen"]
    chips = []
    for idx, label in enumerate(labels, start=1):
        css_class = "step-item current" if idx == step else "step-item"
        chips.append(f"<div class='{css_class}'>{label}</div>")
    return f"<div class='step-tracker'>{''.join(chips)}</div>"


def render_category_selector():
    st.markdown("<p class='step-card-title' style='margin-top:0 !important;'>Choose a story category</p>", unsafe_allow_html=True)
    st.markdown("<p class='premium-note'>Pick the kind of story your child wants tonight.</p>", unsafe_allow_html=True)
    categories = [
        "Adventure Stories",
        "Animal Stories",
        "Confidence & Courage Stories",
        "Science Stories",
        "Friendship Stories",
        "Funny Stories",
    ]
    selected_category = st.selectbox("Story Category", categories, key="ui_story_category")
    if selected_category == "Confidence & Courage Stories":
        st.selectbox("What challenge is your child facing?", CHALLENGE_OPTIONS, key="ui_challenge")


def render_story_mode_selector():
    mode_option = st.selectbox(
        "Choose story mode:",
        ["Sleepy Story", "Adventure Story", "Confidence & Courage Story"],
        key="ui_story_mode",
    )
    st.session_state.story_mode = mode_option
    st.markdown(
        "<div class='premium-note'>Sleepy = calm linear flow. Adventure = fun branching choices. Confidence & Courage = growth-focused with empathy and comfort.</div>",
        unsafe_allow_html=True,
    )


def render_hero_section() -> None:
    category = st.session_state.story_category
    category_cfg = THEME_CONFIG[category]
    st.markdown(
        f"""
<section class="hero-illustration" style="background-image: url('{category_cfg['hero_image']}');">
  <div class="hero-overlay">
    <p class="hero-kicker">{category}</p>
    <p class="hero-line">{category_cfg['header']}</p>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def build_prompt(episode_num: int = 1, last_episode_text: str = "") -> str:
    length_cfg = LENGTH_RULES[st.session_state.length]
    name = st.session_state.hero_name or "a brave child"
    pronoun = st.session_state.pronoun.lower()
    category = st.session_state.story_category
    topic = st.session_state.topic or "a magical journey under the stars"
    challenge = st.session_state.challenge
    age = int(st.session_state.hero_age)
    mode = st.session_state.story_mode

    if category == "Confidence & Courage Stories":
        return f"""
Write a children's bedtime story designed to help a child work through a challenge.

Main Character:
{name}

Age:
{age}

Challenge:
{challenge}

Requirements:
- Target about {length_cfg['word_target']} words (±10%)
- Use vocabulary appropriate for a {age}-year-old
- Break the story into 4-8 short paragraphs
- Show the character facing the challenge
- Show them learning courage or confidence
- Include encouragement and emotional growth
- End with a positive empowering message
- Include a fun science or nature fact
- Include a clear story title at the top

Story arc should generally follow:
- fear or problem
- learning moment
- practice or support
- confidence
- positive ending

Important:
- Keep the tone warm, encouraging, and kid-friendly
- Do not use clinical or therapeutic language
- Do not use words like therapy, counseling, trauma, or mental health in the story
- This category should feel empowering and parent-friendly

Return only the story text.
"""

    is_series = st.session_state.length == "7-Night Adventure"
    base = f"""
Write a {category} children's bedtime story for a {age}-year-old.
Main character name: {name}
Main character pronouns: {pronoun}/{pronoun}/{pronoun}
Story concept: {topic}

Requirements:
- Write at least {length_cfg['min_words']} words.
- Target around {length_cfg['word_target']} words.
- Use age-appropriate language.
- Keep a cozy, safe bedtime tone.
- Promote kindness, confidence, imagination.
- Include 5-8 short paragraphs.
- Use the chosen pronoun naturally throughout the story.
"""
    if is_series:
        base += f"""
- This is Night {episode_num} of a 7-night bedtime story arc.
- Keep continuity with previous nights.
- End with a gentle cliffhanger unless this is Night 7.
"""
        if last_episode_text.strip():
            base += f"""
Context from prior night ending:
{last_episode_text.strip()[-1200:]}
"""

    if mode == "Sleepy Story":
        base += """
- Keep it fully linear with no branching.
- Make the ending calming and sleep-friendly.
"""
    elif mode == "Confidence & Courage Story":
        base += """
- Keep it fully linear with no branching.
- Focus on gentle courage, self-kindness, and overcoming small fears.
- End with a positive, empowering message.
"""
    else:
        base += """
- Include 1 or 2 "choice moments" inside the story.
- Format each choice moment exactly like:
[CHOICE]
Prompt: ...
A) ...
B) ...
[/CHOICE]
- Continue the story after each choice moment with gentle momentum.
"""
    base += "\nReturn only the story text."
    return base


def build_cover_prompt() -> str:
    name = st.session_state.hero_name or "storybook hero"
    category = st.session_state.story_category
    topic = st.session_state.topic or "a bedtime adventure"
    scene = THEME_CONFIG[category]["scene"]
    if st.session_state.book_type == "Coloring Book (Black & White)":
        return f"""
Children's coloring page cover. Clean black lines only.
No grayscale shading. White background. Printable US letter.
Character: {name}. Category: {category}. Scene: {scene}. Topic: {topic}.
"""
    return f"""
Children's bedtime book cover illustration, vibrant and dreamy.
Character: {name}. Category: {category}. Scene: {scene}. Topic: {topic}.
Warm magical lighting, high detail, kid-friendly.
"""


def generate_story_with_length_guard(user_prompt: str, min_words: int, max_tokens: int, max_attempts: int = 4):
    story_text = ""
    total_tokens_used = 0
    system_message = "You are an expert children's bedtime story author."

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            messages = [{"role": "system", "content": system_message}, {"role": "user", "content": user_prompt}]
        else:
            remaining = max(min_words - count_words(story_text), 0)
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": story_text},
                {
                    "role": "user",
                    "content": (
                        "Continue from the exact ending. Do not restart. "
                        f"Add at least {remaining} words. Keep continuity and tone."
                    ),
                },
            ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )

        new_text = (response.choices[0].message.content or "").strip()
        story_text = f"{story_text}\n\n{new_text}".strip() if story_text else new_text
        if response.usage and response.usage.total_tokens:
            total_tokens_used += response.usage.total_tokens
        if count_words(story_text) >= min_words:
            break
    return story_text, total_tokens_used


def build_pdf(story_text: str, image_bytes: bytes, title: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 0.3 * inch)]
    if image_bytes:
        img_buffer = BytesIO(image_bytes)
        story_img = Image(img_buffer, width=5 * inch, height=7 * inch)
        story_img.keepAspect = True
        elements.extend([story_img, PageBreak()])
    for line in (story_text or "").split("\n"):
        if line.strip():
            elements.append(Paragraph(line, styles["Normal"]))
            elements.append(Spacer(1, 0.2 * inch))
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


def parse_choices(text: str):
    pattern = re.compile(r"\[CHOICE\](.*?)\[/CHOICE\]", re.S | re.I)
    blocks = pattern.findall(text or "")
    parsed = []
    for raw in blocks[:2]:
        prompt_match = re.search(r"Prompt:\s*(.*)", raw)
        a_match = re.search(r"A\)\s*(.*)", raw)
        b_match = re.search(r"B\)\s*(.*)", raw)
        if prompt_match and a_match and b_match:
            parsed.append(
                {
                    "prompt": prompt_match.group(1).strip(),
                    "a": a_match.group(1).strip(),
                    "b": b_match.group(1).strip(),
                }
            )
    return parsed


def generate_branch_continuation(choice_text: str):
    name = st.session_state.hero_name or "the hero"
    pronoun = st.session_state.pronoun
    prompt = f"""
Continue this bedtime story for one short section.
Hero: {name}
Pronoun: {pronoun}
Chosen path: {choice_text}
Keep it gentle and cozy, 120-180 words, and conclude this scene smoothly.
Return only the continuation paragraph.
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=320,
        temperature=0.7,
    )
    return (response.choices[0].message.content or "").strip()


st.markdown("<div class='storybook-shell'>", unsafe_allow_html=True)
st.markdown("<h1 class='hero-title'>Story Spark Club</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='hero-sub'>Calm, cinematic bedtime adventures designed for little dreamers and built with the polish parents trust.</p>",
    unsafe_allow_html=True,
)
st.markdown(progress_markup(st.session_state.current_step), unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)
render_hero_section()

if st.session_state.current_step > 1:
    quick_col_l, quick_col_r = st.columns([2, 1])
    with quick_col_l:
        st.caption("Need to update hero details, pronouns, or story mode? Jump back anytime.")
    with quick_col_r:
        if st.button("Edit Step 1 Options", key="jump_to_step1", use_container_width=True, type="secondary"):
            st.session_state.current_step = 1
            st.rerun()

if st.session_state.current_step == 1:
    st.subheader("Step 1: Dream It")
    st.caption("Start with your hero's details and choose the storytelling style for tonight.")
    st.text_input("Who is tonight's hero?", key="ui_hero_name", placeholder="e.g. Luna")
    st.number_input("How old is our adventurer?", key="ui_hero_age", min_value=1, max_value=12, step=1)
    st.radio("Main character pronouns", ["He", "She", "They"], key="ui_pronoun", horizontal=True)
    st.markdown("<hr class='step-divider'/>", unsafe_allow_html=True)
    st.markdown("<p class='step-card-title' style='margin-top:0 !important;'>Choose your story mode</p>", unsafe_allow_html=True)
    st.markdown("<p class='premium-note'>Pick a gentle linear bedtime flow or an interactive branch adventure.</p>", unsafe_allow_html=True)
    render_story_mode_selector()
    st.session_state.hero_name = st.session_state.ui_hero_name
    st.session_state.hero_age = int(st.session_state.ui_hero_age)
    st.session_state.pronoun = st.session_state.ui_pronoun

if st.session_state.current_step == 2:
    st.subheader("Step 2: Spin the Tale")
    render_category_selector()
    st.selectbox("How long should tonight's story be?", list(LENGTH_RULES.keys()), key="ui_length")
    st.text_area(
        "What magical adventure should we create tonight?",
        key="ui_topic",
        height=110,
        placeholder="A moonlit treasure map that only appears at bedtime",
    )
    st.radio(
        "Would you like a color storybook or a coloring cover?",
        ["Story Book (Color Cover)", "Coloring Book (Black & White)"],
        key="ui_book_type",
        horizontal=True,
    )
    st.checkbox(
        "Use unique illustration for each paragraph (slower, more images)",
        key="ui_per_paragraph_images",
    )
    st.caption("If enabled, the app sends more image requests; use this setting with awareness of API usage/cost.")

    st.session_state.story_category = st.session_state.ui_story_category
    st.session_state.challenge = st.session_state.ui_challenge
    st.session_state.length = st.session_state.ui_length
    st.session_state.topic = st.session_state.ui_topic
    st.session_state.book_type = st.session_state.ui_book_type
    st.session_state.per_paragraph_images = st.session_state.ui_per_paragraph_images

    preview_name = st.session_state.hero_name or "Your Hero"
    preview_topic = st.session_state.topic or "A cozy magical quest"
    preview_category = st.session_state.story_category
    preview_icon = THEME_CONFIG[preview_category]["icon"]
    preview_challenge = st.session_state.challenge if preview_category == "Confidence & Courage Stories" else "N/A"
    st.markdown(
        f"""
<div class="preview-card">
<strong>Tonight's Story Preview</strong><br/><br/>
Hero: {preview_name}<br/>
Category: {preview_category} {preview_icon}<br/>
Story Idea: {preview_topic}<br/>
Challenge: {preview_challenge}<br/>
Mode: {st.session_state.story_mode}<br/>
Pronoun: {st.session_state.pronoun}<br/>
Format: {st.session_state.length}
</div>
""",
        unsafe_allow_html=True,
    )

    if st.button("Generate Magical Story", use_container_width=True, type="primary"):
        if not st.session_state.hero_name.strip():
            st.warning("Please add the hero's name first.")
            st.stop()
        if not st.session_state.topic.strip():
            st.warning("Please describe tonight's adventure first.")
            st.stop()

        length_cfg = LENGTH_RULES[st.session_state.length]
        try:
            with st.spinner("\U0001FA84 Wand sparkles... writing your storybook pages..."):
                initial_night = 1
                story_text, tokens_used = generate_story_with_length_guard(
                    user_prompt=build_prompt(episode_num=initial_night),
                    min_words=length_cfg["min_words"],
                    max_tokens=length_cfg["max_tokens"],
                )

            with st.spinner("\U0001F4D6 Flipping pages... painting your cover..."):
                image_response = client.images.generate(
                    model="dall-e-3",
                    prompt=build_cover_prompt(),
                    size="1024x1024",
                    response_format="b64_json",
                )
                image_base64 = image_response.data[0].b64_json
                image_bytes = base64.b64decode(image_base64)

            with st.spinner("\u2728 Stars are forming your printable book..."):
                story_title = f"{st.session_state.hero_name}'s Magical Bedtime Story"
                pdf_data = build_pdf(story_text, image_bytes, story_title)

            st.session_state.story = story_text
            st.session_state.story_sections = [story_text]
            st.session_state.story_image = image_bytes
            st.session_state.story_images = []

            if st.session_state.per_paragraph_images:
                paragraphs = [p.strip() for p in story_text.split("\n\n") if p.strip()]
                for i, para in enumerate(paragraphs, start=1):
                    if i > 6:
                        break
                    with st.spinner(f"Creating illustration {i} of {len(paragraphs)}..."):
                        prompt = (
                            f"Children's bedtime book scene illustration, vibrant and dreamy. "
                            f"Include details from this paragraph: {para[:250]}"
                        )
                        para_image_response = client.images.generate(
                            model="dall-e-3",
                            prompt=prompt,
                            size="1024x1024",
                            response_format="b64_json",
                        )
                        para_bytes = base64.b64decode(para_image_response.data[0].b64_json)
                        st.session_state.story_images.append(para_bytes)

            st.session_state.pdf_data = pdf_data
            st.session_state.preview_page = 1
            st.session_state.audio_bytes = None
            st.session_state.chosen_path = []
            if st.session_state.length == "7-Night Adventure":
                st.session_state.series_active = True
                st.session_state.series_night = 1
                st.session_state.series_episodes = [story_text]
            else:
                st.session_state.series_active = False
                st.session_state.series_night = 0
                st.session_state.series_episodes = []
            st.session_state.current_step = 3
            log_story(
                st.session_state.hero_name,
                int(st.session_state.hero_age),
                st.session_state.story_category,
                st.session_state.topic,
                challenge=st.session_state.challenge if st.session_state.story_category == "Confidence & Courage Stories" else None,
                tokens_used=tokens_used,
            )
            st.rerun()
        except Exception as e:
            st.error(f"Generation error: {e}")

if st.session_state.current_step == 3:
    st.subheader("Step 3: Paint + Print")
    st.caption("Review your story on one page, explore choice moments, and download your polished printable storybook.")
    if st.session_state.story_image:
        st.image(st.session_state.story_image, caption="Theme Header Illustration")

    story_text = st.session_state.story or ""
    paragraphs = [p.strip() for p in story_text.split("\n\n") if p.strip()]

    if paragraphs:
        st.markdown("<div class='preview-card'><strong>Full story view</strong><br/>All content appears in one page with inline visuals.</div>", unsafe_allow_html=True)
        for i, para in enumerate(paragraphs, start=1):
            st.write(para)
            if st.session_state.per_paragraph_images and i - 1 < len(st.session_state.story_images):
                st.image(st.session_state.story_images[i - 1], caption=f"Illustration {i}", use_container_width=True)

    else:
        st.info("No story generated yet. Please generate a story on Step 2 first.")

    if st.session_state.series_active:
        st.markdown("### 7-Night Adventure Progress")
        night = int(st.session_state.series_night)
        st.caption(f"Currently on Night {night} of 7")
        if night < 7:
            if st.button(f"Generate Night {night + 1}", use_container_width=True, type="secondary"):
                length_cfg = LENGTH_RULES["7-Night Adventure"]
                try:
                    with st.spinner(f"Writing Night {night + 1}..."):
                        next_story, next_tokens = generate_story_with_length_guard(
                            user_prompt=build_prompt(
                                episode_num=night + 1,
                                last_episode_text=st.session_state.series_episodes[-1],
                            ),
                            min_words=length_cfg["min_words"],
                            max_tokens=length_cfg["max_tokens"],
                        )
                    with st.spinner("Updating printable storybook pages..."):
                        title = f"{st.session_state.hero_name}'s 7-Night Adventure - Night {night + 1}"
                        st.session_state.pdf_data = build_pdf(next_story, st.session_state.story_image, title)
                    st.session_state.story = next_story
                    st.session_state.story_sections = [next_story]
                    st.session_state.story_images = []
                    if st.session_state.per_paragraph_images:
                        paragraphs = [p.strip() for p in next_story.split("\n\n") if p.strip()]
                        for i, para in enumerate(paragraphs, start=1):
                            if i > 6:
                                break
                            with st.spinner(f"Creating Night {night+1} illustration {i}/{len(paragraphs)}..."):
                                prompt = (
                                    f"Children's bedtime book scene illustration, vibrant and dreamy. "
                                    f"Include details from this paragraph: {para[:250]}"
                                )
                                para_image_response = client.images.generate(
                                    model="dall-e-3",
                                    prompt=prompt,
                                    size="1024x1024",
                                    response_format="b64_json",
                                )
                                para_bytes = base64.b64decode(para_image_response.data[0].b64_json)
                                st.session_state.story_images.append(para_bytes)
                    st.session_state.preview_page = 1
                    st.session_state.audio_bytes = None
                    st.session_state.series_night = night + 1
                    st.session_state.series_episodes.append(next_story)
                    log_story(
                        st.session_state.hero_name,
                        int(st.session_state.hero_age),
                        st.session_state.story_category,
                        f"{st.session_state.topic} (Night {night + 1})",
                        challenge=st.session_state.challenge if st.session_state.story_category == "Confidence & Courage Stories" else None,
                        tokens_used=next_tokens,
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Night generation error: {e}")
        else:
            st.success("Night 7 complete. Your full bedtime series is finished.")

    choices = parse_choices(st.session_state.story) if st.session_state.story_mode == "Adventure Story" else []
    if choices:
        st.markdown("### Optional Choice Moments")
        for i, choice in enumerate(choices, start=1):
            st.markdown(
                f"<div class='choice-box'><strong>Choice {i}</strong><br/>{choice['prompt']}</div>",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            if c1.button(f"A) {choice['a']}", key=f"choice_a_{i}", use_container_width=True, type="secondary"):
                with st.spinner("Weaving your selected path..."):
                    continuation = generate_branch_continuation(choice["a"])
                st.session_state.chosen_path.append(f"Choice {i}: {choice['a']}")
                st.session_state.story = f"{st.session_state.story}\n\n{continuation}"
                st.session_state.story_sections = [st.session_state.story]
                st.rerun()
            if c2.button(f"B) {choice['b']}", key=f"choice_b_{i}", use_container_width=True, type="secondary"):
                with st.spinner("Weaving your selected path..."):
                    continuation = generate_branch_continuation(choice["b"])
                st.session_state.chosen_path.append(f"Choice {i}: {choice['b']}")
                st.session_state.story = f"{st.session_state.story}\n\n{continuation}"
                st.session_state.story_sections = [st.session_state.story]
                st.rerun()

    if st.session_state.story:
        st.markdown("### Narrate This Story")
        st.selectbox("Choose your narrator voice", list(VOICE_MAP.keys()), key="selected_voice_name")
        step3_voice = VOICE_MAP[st.session_state.selected_voice_name]
        if st.button(
            "Generate Storytime Audio",
            key="generate_audio_step3",
            use_container_width=True,
            disabled=st.session_state.audio_generating,
            type="primary",
        ):
            st.session_state.audio_generating = True
            try:
                with st.spinner("\u2728 Stars are syncing your narrator..."):
                    st.session_state.audio_bytes = tts_cached(st.session_state.story, step3_voice)
            except Exception as e:
                st.error(f"Audio error: {e}")
            finally:
                st.session_state.audio_generating = False
        if st.session_state.audio_bytes:
            st.audio(st.session_state.audio_bytes, format="audio/mpeg")

    if st.session_state.pdf_data:
        st.download_button(
            label="Download My Story Book (PDF)",
            data=st.session_state.pdf_data,
            file_name=f"{st.session_state.hero_name or 'story'}_storybook.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

if st.session_state.current_step == 4:
    st.subheader("Step 4: Storytime Voice")
    st.caption("Choose a narrator and create a soothing audio bedtime reading.")
    st.selectbox("Choose your narrator voice", list(VOICE_MAP.keys()), key="selected_voice_name")
    internal_voice = VOICE_MAP[st.session_state.selected_voice_name]
    st.caption(f"Narrator profile: `{st.session_state.selected_voice_name}` -> `{internal_voice}`")

    if st.button("Generate Storytime Audio", use_container_width=True, disabled=st.session_state.audio_generating, type="primary"):
        if not st.session_state.story:
            st.warning("Generate a story first.")
        else:
            st.session_state.audio_generating = True
            try:
                with st.spinner("\u2728 Stars are syncing your narrator..."):
                    st.session_state.audio_bytes = tts_cached(st.session_state.story, internal_voice)
            except Exception as e:
                st.error(f"Audio error: {e}")
            finally:
                st.session_state.audio_generating = False

    if st.session_state.audio_bytes:
        st.audio(st.session_state.audio_bytes, format="audio/mpeg")
        st.markdown("#### Guided Reading Highlight")
        st.caption("Use this to simulate sentence-by-sentence focus while narration is playing.")
        if st.button("Start Guided Highlight", use_container_width=True, type="secondary"):
            story_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", st.session_state.story or "") if s.strip()]
            display = st.empty()
            history = []
            for sentence in story_sentences[:45]:
                current = f"<div style='padding:8px;border-radius:10px;background:#ede9fe;border:1px solid #c4b5fd;'><strong>{sentence}</strong></div>"
                faded = "".join(
                    f"<div style='opacity:0.45;padding-top:6px;font-size:0.92rem;'>{line}</div>"
                    for line in history[-3:]
                )
                display.markdown(current + faded, unsafe_allow_html=True)
                history.append(sentence)
                time.sleep(0.6)

nav_prev, nav_next = st.columns(2)
if nav_prev.button("Back", use_container_width=True, disabled=st.session_state.current_step <= 1, type="secondary"):
    st.session_state.current_step -= 1
    st.rerun()
if nav_next.button("Next", use_container_width=True, disabled=st.session_state.current_step >= 4, type="secondary"):
    st.session_state.current_step += 1
    st.rerun()


def show_analytics():
    try:
        df = pd.read_json("usage_log.json", lines=True)
        st.divider()
        st.subheader("App Analytics")
        st.write("Total Stories Generated:", len(df))
        st.write("Average Age:", round(df["age"].mean(), 1))
        category_col = "story_category" if "story_category" in df.columns else "theme"
        st.write("Most Popular Categories:")
        st.write(df[category_col].value_counts().head(3))
        if "challenge" in df.columns:
            challenges = df["challenge"].fillna("").astype(str).str.strip()
            challenges = challenges[challenges != ""]
            if len(challenges) > 0:
                st.write("Most Common Confidence Challenges:")
                st.write(challenges.value_counts().head(5))
        if "tokens_used" in df.columns:
            st.write("Total Tokens Used:", int(df["tokens_used"].fillna(0).sum()))
    except Exception:
        st.info("No analytics data yet.")
