import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

CONVERSATION_SYSTEM_PROMPT = """You are "Anna", a friendly and patient German language conversation coach.
You are having a spoken conversation with a language learner entirely in German (Deutsch).

Rules:
- Respond ONLY in German. Never use English or any other language, and never include translations.
- Keep every message short: one or two simple sentences, suitable for an A2-B1 level learner.
- Always end your message with a single, clear, relevant follow-up question that reacts to what the
  learner just said, so the conversation naturally continues.
- Do NOT correct the learner's grammar or vocabulary during the conversation - just respond naturally
  and keep the conversation flowing. Detailed feedback is given later, separately.
- Vary topics naturally (daily life, hobbies, travel, food, work, family, weather, opinions, etc.)
  based on what the learner says.
- Be warm and encouraging, like a friendly tutor, not a robot."""

START_PROMPT = (
    "Beginne ein freundliches Gespraech auf Deutsch, um dem Lernenden beim Deutschlernen zu helfen. "
    "Begruesse den Lernenden kurz und stelle eine einfache Eroeffnungsfrage, um das Gespraech zu starten. "
    "Halte dich kurz (1-2 Saetze)."
)

FEEDBACK_PROMPT_TEMPLATE = """You are an expert German language coach. Below is a transcript of a spoken
German conversation practice session between the coach ("Coach") and a learner ("You").

Transcript:
{transcript}

Analyze ONLY the learner's ("You") German responses and provide constructive feedback in clear, well
formatted Markdown, using exactly these sections:

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


def _get_model():
    return genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=CONVERSATION_SYSTEM_PROMPT,
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

    try:
        chat = _get_model().start_chat(history=[])
        response = chat.send_message(START_PROMPT)
        question = response.text.strip()

        session["history"] = _serialize_history(chat.history)
        return jsonify({"question": question})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


@app.route("/api/next", methods=["POST"])
def next_question():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the server."}), 500

    data = request.get_json(silent=True) or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "No answer text was provided."}), 400

    history = session.get("history", [])

    try:
        chat = _get_model().start_chat(history=history)
        response = chat.send_message(answer)
        question = response.text.strip()

        session["history"] = _serialize_history(chat.history)
        return jsonify({"question": question})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


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

    try:
        model = genai.GenerativeModel(model_name=GEMINI_MODEL)
        response = model.generate_content(FEEDBACK_PROMPT_TEMPLATE.format(transcript=transcript))
        feedback = response.text.strip()

        session.pop("history", None)
        return jsonify({"feedback": feedback})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
