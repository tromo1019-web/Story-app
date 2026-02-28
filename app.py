
import streamlit as st
from openai import OpenAI
import pandas as pd
import base64
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from reportlab.platypus import Image
from reportlab.lib.units import inch
import time

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"], timeout=60.0) # increased timeout for longer story generation and audio processing Probably can remove later

# & C:/Users/trome/anaconda3/python.exe -m streamlit run app.py

# ---- session state defaults (mobile-safe) ----
if "story" not in st.session_state:
    st.session_state.story = None
if "image" not in st.session_state:
    st.session_state.image = None
if "pdf_data" not in st.session_state:
    st.session_state.pdf_data = None
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "audio_generating" not in st.session_state:
    st.session_state.audio_generating = False

# generating audio, TTS call
def generate_audio_bytes(text, voice="nova"):

    for attempt in range(1, 3):
        try:
            t0 = time.time()
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                response_format="mp3"
            )
            # no st.write here (cache-safe)
            return response.content

        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.0)

def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + max_chars, n)

        # try to break on a newline or space close to the end
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(" "))
            if cut > 0:
                end = start + cut

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end

    return chunks



# added to help audio on mobile play
def narrate_full_story(story_text: str, voice: str = "nova") -> bytes:
    if not story_text:
        return b""

    chunks = chunk_text(story_text, max_chars=3000)

    # TEMP DEBUG (remove later)
    max_len = max(len(c) for c in chunks) if chunks else 0
    print("Max chunk length:", max_len)

    if not chunks:
        return b""

    audio_all = b""
    for chunk in chunks:
        audio_part = generate_audio_bytes(chunk, voice=voice)
        audio_all += audio_part
    return audio_all

@st.cache_data(show_spinner=False)
def tts_cached(story_text: str, voice: str) -> bytes:
    return narrate_full_story(story_text, voice=voice)

# JSON data capture
import json
from datetime import datetime

def log_story(name, age, story_theme, topic, tokens_used=None):
    data = {
        "timestamp": str(datetime.now()),
        "name": name,
        "age": age,
        "theme": story_theme,
        "topic": topic,
        "tokens_used": tokens_used
    }

    with open("usage_log.json", "a") as f:
        f.write(json.dumps(data) + "\n")

# The App Header
st.title("📖 My AI Story Generator")
st.subheader("Turn your ideas into stories instantly.")



name = st.text_input("Enter your name", placeholder="e.g. Alice")
age = st.number_input("Enter your age", min_value=1, max_value=120, step=1)
story_theme = st.selectbox("Choose a story theme", ["Adventure", "Mystery", "Fantasy", "Sci-Fi", "Romance"])

# length dropdown
story_length = st.selectbox(
    "Choose story length",
    ["Short (5 min)", "Medium (10 min)", "Long (20 min)"],
    index=1
)

# The Input Box
# This creates a variable called 'topic' that saves whatever you type
topic = st.text_input("What should the story be about?", placeholder="e.g. A space-traveling cat")

def get_length_settings(length_choice: str) -> dict:
    # Word targets are approximate; max_tokens must scale with length
    mapping = {
        "Short (5 min)":  {"word_target": 700,  "max_tokens": 1100},
        "Medium (10 min)": {"word_target": 1400, "max_tokens": 2000},
        "Long (20 min)":  {"word_target": 2800, "max_tokens": 3800},
    }
    return mapping.get(length_choice, {"word_target": 1400, "max_tokens": 2000})

def build_prompt(name, age, story_theme, topic, word_target):
    prompt = f"""
Write a {story_theme} children's story about {topic} for a {age}-year-old child named {name}.

Requirements:
- Include a clear and catchy story title at the top.
- Target about {word_target} words (±10%). Do NOT exceed {int(word_target * 1.10)} words.
- Use age-appropriate vocabulary for a {age}-year-old.
- Break the story into 4–8 short paragraphs.
- Make the message of the story about building confidence, kindness, and creativity.
- Include fun science or nature facts related to the story theme.
- Naturally incorporate current, age-appropriate kid slang to make the story relatable and fun. Adjust the type and amount of slang based on the character’s age, and avoid overusing it so it feels organic and readable.
- End with a positive lesson or uplifting message.
- Make {name} the main character.

Write only the story.
"""
    return prompt

book_type = st.radio(
    "Choose your book type:",
    ["Story Book (Color Cover)", "Coloring Book (Black & White)"]
)

if st.button("Generate Story"):

    if not topic:
        st.warning("Please type a topic first!")
        st.stop()

    with st.spinner("Creating your magical story... ✨"):

        try:
            # =========================
            # 1️⃣ Generate Story
            # =========================
            length_settings = get_length_settings(story_length)
            word_target = length_settings["word_target"]
            max_tokens = length_settings["max_tokens"]
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional children's book author who writes engaging, age-appropriate stories with positive themes and clear structure."
                    },
                    {
                        "role": "user",
                        "content": build_prompt(name, age, story_theme, topic, word_target)
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )

            story_text = response.choices[0].message.content
            tokens_used = response.usage.total_tokens

            # Save story
            st.session_state.story = story_text

            # Log usage ONCE
            log_story(name, age, story_theme, topic, tokens_used)

            # =========================
            # 2️⃣ Build Image Prompt
            # =========================
            if book_type == "Story Book (Color Cover)":
                image_prompt = f"""
                Children's book cover illustration.
                Colorful, magical, Pixar-style.
                Main character: {name}.
                Theme: {story_theme}.
                Scene about: {topic}.
                Bright, detailed, high quality.
                """
            else:
                image_prompt = f"""
                High contrast black lines.
                No gray.
                Pure white background.
                Centered composition.
                Printable on US Letter paper.
                Main character: {name}.
                Theme: {story_theme}.
                Scene about: {topic}.
                """

            # =========================
            # 3️⃣ Generate Image
            # =========================
            image_response = client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                response_format="b64_json"
            )

            image_base64 = image_response.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)

            # Save image
            st.session_state.image = image_bytes

            # =========================
            # 4️⃣ Create Printable PDF
            # =========================
            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )

            elements = []
            styles = getSampleStyleSheet()

            # Title
            elements.append(Paragraph(f"{name}'s Magical Story", styles["Title"]))
            elements.append(Spacer(1, 0.3 * inch))

            # Image Page
            img_buffer = BytesIO(image_bytes)
            story_img = Image(img_buffer, width=5 * inch, height=7 * inch)
            story_img.keepAspect = True
            elements.append(story_img)

            elements.append(PageBreak())

            # Story Text Page
            for line in story_text.split("\n"):
                if line.strip():
                    elements.append(Paragraph(line, styles["Normal"]))
                    elements.append(Spacer(1, 0.2 * inch))

            doc.build(elements)

            st.session_state.pdf_data = buffer.getvalue()
            buffer.close()

        except Exception as e:
            st.error(f"Something went wrong: {e}")


# ===============================
# DISPLAY SECTION (ALWAYS IN ORDER)
# ===============================
if st.session_state.get("story"):

    st.divider()

    # 1️⃣ IMAGE FIRST
    if st.session_state.get("image"):
        st.image(st.session_state.image, caption="Your Book Cover")

    # 2️⃣ STORY SECOND
    st.subheader("📖 Your Magical Story")
    st.write(st.session_state.story)
    st.caption(f"Word count: {len(st.session_state.story.split())}")

    # 3️⃣ DOWNLOAD PDF THIRD
    if st.session_state.get("pdf_data"):
        st.download_button(
            label="📥 Download My Story Book",
            data=st.session_state.pdf_data,
            file_name=f"{name}_book.pdf",
            mime="application/pdf"
        )

    st.divider()

    # 4️⃣ AUDIO LAST
    st.subheader("🔊 Listen to Your Story")

    voice_choice = st.selectbox("Choose a voice:", ["nova", "alloy", "shimmer"])

    if st.button("Read Story Out Loud", disabled=st.session_state.audio_generating):
        st.session_state.audio_generating = True
        try:
            with st.spinner("Preparing narrator... 🎙️"):

            # (optional debug, keep it if you already added it)
                story_text = st.session_state.story
                chunks = chunk_text(story_text, max_chars=3500)
                st.write(f"Story chars: {len(story_text)} | Chunks: {len(chunks)}")

                audio_bytes = tts_cached(story_text, voice_choice)

                if audio_bytes:
                    st.session_state.audio_bytes = audio_bytes
                    st.audio(audio_bytes, format="audio/mpeg")
                else:
                    st.error("No story text to narrate.")

        except Exception as e:
            st.error(f"Audio error: {e}")
        finally:
            st.session_state.audio_generating = False




# Analytics Dashboard (for the author to see usage trends)
def show_analytics():
    try:
        df = pd.read_json("usage_log.json", lines=True)

        st.divider()
        st.subheader("📊 App Analytics")

        st.write("Total Stories Generated:", len(df))
        st.write("Average Age:", round(df["age"].mean(), 1))
        st.write("Most Popular Theme:")
        st.write(df["theme"].value_counts().head(3))

        if "tokens_used" in df.columns:
            st.write("Total Tokens Used:", df["tokens_used"].sum())

    except Exception:
        st.info("No analytics data yet.")
        show_analytics()
    


