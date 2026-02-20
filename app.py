
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

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])



# generating audio
def generate_audio_stream(text, voice="nova"): #check and and make sure the other voices are an option
    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text
    )
    return response.content

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

# The Input Box
# This creates a variable called 'topic' that saves whatever you type
topic = st.text_input("What should the story be about?", placeholder="e.g. A space-traveling cat")

def build_prompt(name, age, story_theme, topic):
    prompt = f"""
Write a {story_theme} children's story about {topic} for a {age}-year-old child named {name}.

Requirements:
- Include a clear and catchy story title at the top.
- Make the story 500–700 words.
- Use age-appropriate vocabulary for a {age}-year-old.
- Break the story into 4–6 short paragraphs.
- Make the message of the story about building confidence, kindness, and creativity.
- Include fun science or nature facts related to the story theme.
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
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional children's book author who writes engaging, age-appropriate stories with positive themes and clear structure."
                    },
                    {
                        "role": "user",
                        "content": build_prompt(name, age, story_theme, topic)
                    }
                ],
                max_tokens=900,
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
if "story" in st.session_state:

    st.divider()

    # 1️⃣ IMAGE FIRST
    if "image" in st.session_state:
        st.image(st.session_state.image, caption="Your Book Cover")

    # 2️⃣ STORY SECOND
    st.subheader("📖 Your Magical Story")
    st.write(st.session_state.story)

    # 3️⃣ DOWNLOAD PDF THIRD
    if "pdf_data" in st.session_state:
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

    if st.button("Read Story Out Loud"):

        try:
            with st.spinner("Preparing narrator... 🎙️"):
                audio_path = generate_audio_stream(
                    st.session_state.story,
                    voice=voice_choice
                )

                if audio_path:
                    st.audio(audio_path, format="audio/mp3")
                else:
                    st.error("Audio data was empty")

        except Exception as e:
            st.error(f"Audio error: {e}")




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

    except:
        st.info("No analytics data yet.")
        show_analytics()
    


