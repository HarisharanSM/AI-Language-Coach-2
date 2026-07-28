import os
import random
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Models to try, in order, for every Gemini request. If a model is unavailable
# (rate limited, over capacity, or fails for any other reason), the next model
# in the list is tried until one succeeds or the list is exhausted.
DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
]
_gemini_models_env = os.environ.get("GEMINI_MODELS")
GEMINI_MODELS = (
    [m.strip() for m in _gemini_models_env.split(",") if m.strip()]
    if _gemini_models_env
    else DEFAULT_GEMINI_MODELS
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# The 12 A1 lesson topics from the vhs-Lernportal A1 course curriculum.
# All practice scenarios/questions must stay within these topics.
A1_TOPICS = [
    "Hallo! Wie geht's? (Begruessung, Small Talk, sich vorstellen)",
    "Meine Familie und ich (Familie, Verwandte, ueber sich erzaehlen)",
    "Deutsch lernen (Sprachenlernen, Kurs, Lernen im Alltag)",
    "Essen und trinken (Lebensmittel, Mahlzeiten, im Restaurant/Supermarkt)",
    "Mein Tag (Tagesablauf, Uhrzeiten, Alltagsroutine)",
    "Meine Wohnung (Zimmer, Moebel, Wohnort beschreiben)",
    "In der Stadt (Orte in der Stadt, Wegbeschreibung, unterwegs sein)",
    "Arbeit und Beruf (Berufe, Arbeitsalltag, Arbeitsplatz)",
    "Beim Arzt (Gesundheit, Koerperteile, Termin beim Arzt)",
    "Gestern und heute (Vergangenheit, was man gestern gemacht hat)",
    "Was ziehe ich an? (Kleidung, Farben, Wetter passend anziehen)",
    "Jahreszeiten und Wetter (Jahreszeiten, Wetter, Monate)",
]

CONVERSATION_SYSTEM_PROMPT = """You are "Anna", a friendly and patient German language conversation coach
for an A1 (absolute beginner) learner. You are having a spoken conversation with the learner entirely in
German (Deutsch).

Allowed topics (choose ONLY from this fixed list, matching the learner's A1 course curriculum):
{topics}

Rules:
- Respond ONLY in German. Never use English or any other language, and never include translations.
- Use STRICT A1-level language: very short, simple sentences (present tense, basic Perfekt for the
  "Gestern und heute" topic only), high-frequency everyday vocabulary, no subordinate clauses, no
  idioms. Assume the learner knows only basic words and simple structures.
- Every question or scenario you ask about must come from the allowed topics list above. Do not
  introduce unrelated topics (no politics, abstract opinions, complex hypotheticals, etc.).
- Keep every message very short: one or two simple sentences.
- Always end your message with a single, clear, simple follow-up question that reacts to what the
  learner just said and stays within the allowed topics, so the conversation naturally continues.
- Do NOT correct the learner's grammar or vocabulary during the conversation - just respond naturally
  and keep the conversation flowing. Detailed feedback is given later, separately.
- You may move to another allowed topic after a few exchanges, but never to a topic outside the list.
- Be warm and encouraging, like a friendly tutor, not a robot."""


def _build_start_prompt():
    topic = random.choice(A1_TOPICS)
    return (
        "Beginne ein freundliches Gespraech auf Deutsch fuer einen A1-Anfaenger, passend zum Thema: "
        f'"{topic}". '
        "Begruesse den Lernenden kurz und stelle eine sehr einfache Eroeffnungsfrage zu diesem Thema, "
        "um das Gespraech zu starten. Benutze nur einfache A1-Woerter und halte dich kurz (1-2 Saetze)."
    )

FEEDBACK_PROMPT_TEMPLATE = """You are an expert German language coach. Below is a transcript of a spoken
German conversation practice session between the coach ("Coach") and an A1-level (absolute beginner)
learner ("You"), based on the learner's official A1 course topics (greetings, family, learning German,
food & drink, daily routine, home, city, work, doctor, past tense basics, clothing, seasons & weather).

Transcript:
{transcript}

Analyze ONLY the learner's ("You") German responses, judged against A1-level expectations (simple
present tense, basic Perfekt, core vocabulary, simple sentence structure), and provide constructive
feedback in clear, well formatted Markdown, using exactly these sections:

### Overall Impression
A short, encouraging summary of how the learner did.

### Grammar Feedback
List specific grammar issues you noticed. For each one show the learner's original sentence and a
corrected version (Original -> Correction), with a one-line explanation.

### Vocabulary Feedback
Point out any word choice issues and suggest richer or more natural vocabulary, with examples from
what the learner actually said.

### Sentence Structure & Word Order
Comment on German sentence structure and word order (e.g. verb position), with corrected examples.

### Next Steps
2-3 concrete, encouraging tips for what to practice next.

If the learner did not make a particular type of mistake, briefly say so in that section instead of
inventing issues. Be specific and reference the learner's actual sentences."""


def _get_model(model_name):
    topics_list = "\n".join(f"- {topic}" for topic in A1_TOPICS)
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=CONVERSATION_SYSTEM_PROMPT.format(topics=topics_list),
    )


def _serialize_history(history):
    return [
        {"role": item.role, "parts": [part.text for part in item.parts]}
        for item in history
    ]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def start_conversation():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the server."}), 500

    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            chat = _get_model(model_name).start_chat(history=[])
            response = chat.send_message(_build_start_prompt())
            question = response.text.strip()

            session["history"] = _serialize_history(chat.history)
            return jsonify({"question": question})
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            last_error = exc
            continue

    return jsonify({"error": str(last_error)}), 500


@app.route("/api/next", methods=["POST"])
def next_question():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the server."}), 500

    data = request.get_json(silent=True) or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "No answer text was provided."}), 400

    history = session.get("history", [])

    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            chat = _get_model(model_name).start_chat(history=history)
            response = chat.send_message(answer)
            question = response.text.strip()

            session["history"] = _serialize_history(chat.history)
            return jsonify({"question": question})
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            last_error = exc
            continue

    return jsonify({"error": str(last_error)}), 500


@app.route("/api/end", methods=["POST"])
def end_conversation():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the server."}), 500

    data = request.get_json(silent=True) or {}
    log = data.get("log", [])

    transcript_lines = [
        f"{('Coach' if entry.get('speaker') == 'coach' else 'You')}: {entry.get('text', '')}"
        for entry in log
    ]
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no conversation recorded)"

    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name=model_name)
            response = model.generate_content(FEEDBACK_PROMPT_TEMPLATE.format(transcript=transcript))
            feedback = response.text.strip()

            session.pop("history", None)
            return jsonify({"feedback": feedback})
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            last_error = exc
            continue

    return jsonify({"error": str(last_error)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
