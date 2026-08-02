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

# The 12 A2 lesson topics from the vhs-Lernportal A2 course curriculum.
# All practice scenarios/questions must stay within these topics.
A2_TOPICS = [
    "Was machen wir am Wochenende? (Freizeitplaene, Vorschlaege machen, Wochenendaktivitaeten)",
    "Unterwegs (Verkehrsmittel, Fahrkarten, Reisen, sich orientieren)",
    "Wir ziehen um. (Umzug, neue Wohnung, Wohnungssuche)",
    "Aemter und Behoerden (Formulare, Termine, amtliche Angelegenheiten)",
    "Lebenswege (Biografie, wichtige Lebensstationen, ueber die Vergangenheit erzaehlen)",
    "Jobsuche und Bewerbung (Stellenanzeigen, Lebenslauf, Vorstellungsgespraech)",
    "Im Kaufhaus (Einkaufen, Kleidung, Groessen, Umtausch, Reklamation)",
    "Am Arbeitsplatz (Arbeitsalltag, Kolleg*innen, Aufgaben, Arbeitszeiten)",
    "Schulzeit (Schule frueher, Erinnerungen, Faecher, Lehrer*innen)",
    "Gesund und fit (Gesundheit, Sport, Ernaehrung, beim Arzt)",
    "Mein Bankkonto (Bank, Konto eroeffnen, Geld ueberweisen, Zahlungen)",
    "Sport, Spass und Spiel (Sportarten, Hobbys, Freizeitaktivitaeten)",
]

CONVERSATION_SYSTEM_PROMPT = """You are "Anna", a friendly and patient German language conversation coach
for an A2 (elementary/waystage) learner. You are having a spoken conversation with the learner entirely in
German (Deutsch).

Allowed topics (choose ONLY from this fixed list, matching the learner's A2 course curriculum):
{topics}

Rules:
- Respond ONLY in German. Never use English or any other language, and never include translations.
- Use A2-level language: moderately short, clear sentences. You may use Perfekt and simple Praeteritum
  (e.g. "war", "hatte", modal verbs) for talking about the past, modal verbs (koennen, muessen, wollen,
  sollen, duerfen, moechten), simple subordinate clauses with "weil", "dass", or "wenn", and basic
  comparatives. Use everyday vocabulary related to the allowed topics (travel, moving house, offices,
  jobs, shopping, workplace, school, health, banking, sports). Avoid complex or literary language,
  idioms, and rare vocabulary. Assume the learner has a basic but solid foundation (has completed A1).
- Every question or scenario you ask about must come from the allowed topics list above. Do not
  introduce unrelated topics (no politics, abstract opinions, complex hypotheticals, etc.).
- Keep every message short: one to three sentences.
- Always end your message with a single, clear follow-up question that reacts to what the learner just
  said and stays within the allowed topics, so the conversation naturally continues.
- Do NOT correct the learner's grammar or vocabulary during the conversation - just respond naturally
  and keep the conversation flowing. Detailed feedback is given later, separately.
- You may move to another allowed topic after a few exchanges, but never to a topic outside the list.
- Be warm and encouraging, like a friendly tutor, not a robot."""


def _pick_topic():
    topic_number = random.randint(1, 12)  # random integer in [1, 12], both boundaries included
    return A2_TOPICS[topic_number - 1]


def _build_start_prompt():
    topic = _pick_topic()
    return (
        "Beginne ein freundliches Gespraech auf Deutsch fuer einen A2-Lernenden, passend zum Thema: "
        f'"{topic}". '
        "Begruesse den Lernenden kurz und stelle eine klare Eroeffnungsfrage zu diesem Thema, um das "
        "Gespraech zu starten. Benutze A2-Niveau-Deutsch und halte dich kurz (1-3 Saetze)."
    )

FEEDBACK_PROMPT_TEMPLATE = """You are an expert German language coach. Below is a transcript of a spoken
German conversation practice session between the coach ("Coach") and an A2-level (elementary/waystage)
learner ("You"), based on the learner's official A2 course topics (weekend plans, getting around,
moving house, offices/authorities, life stories, job search, shopping, workplace, school days, health
and fitness, banking, sports and hobbies).

Transcript:
{transcript}

Analyze ONLY the learner's ("You") German responses, judged against A2-level expectations (Perfekt and
simple Praeteritum, modal verbs, simple subordinate clauses with weil/dass/wenn, basic comparatives,
everyday topic-related vocabulary, and generally correct word order), and provide constructive
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
    topics_list = "\n".join(f"- {topic}" for topic in A2_TOPICS)
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
