import os
import random
import uuid

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

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


def _system_prompt():
    topics_list = "\n".join(f"- {topic}" for topic in A1_TOPICS)
    return CONVERSATION_SYSTEM_PROMPT.format(topics=topics_list)


def _extract_text(response):
    return "".join(block.text for block in response.content if block.type == "text").strip()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def start_conversation():
    if not client:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server."}), 500

    try:
        history = [{"role": "user", "content": _build_start_prompt()}]
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            output_config={"effort": "low"},
            messages=history,
        )
        question = _extract_text(response)

        history.append({"role": "assistant", "content": question})
        session["history"] = history
        return jsonify({"question": question})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


@app.route("/api/next", methods=["POST"])
def next_question():
    if not client:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server."}), 500

    data = request.get_json(silent=True) or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "No answer text was provided."}), 400

    history = session.get("history", [])
    history.append({"role": "user", "content": answer})

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            output_config={"effort": "low"},
            messages=history,
        )
        question = _extract_text(response)

        history.append({"role": "assistant", "content": question})
        session["history"] = history
        return jsonify({"question": question})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


@app.route("/api/end", methods=["POST"])
def end_conversation():
    if not client:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server."}), 500

    data = request.get_json(silent=True) or {}
    log = data.get("log", [])

    transcript_lines = [
        f"{('Coach' if entry.get('speaker') == 'coach' else 'You')}: {entry.get('text', '')}"
        for entry in log
    ]
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no conversation recorded)"

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": FEEDBACK_PROMPT_TEMPLATE.format(transcript=transcript)}],
        )
        feedback = _extract_text(response)

        session.pop("history", None)
        return jsonify({"feedback": feedback})
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
