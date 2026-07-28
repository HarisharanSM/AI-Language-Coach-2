# AI Language Coach

A web app for practicing spoken German with an AI conversation coach powered by Google **Gemini**.

## How it works

1. Click **Start Conversation** — the coach asks a question in German (spoken aloud via the
   browser's text-to-speech, with the German text logged in the conversation window). The button
   turns into **End Conversation**, and **Record Answer** becomes enabled.
2. Click **Record Answer** to start answering in German (the button text becomes bold while
   recording). Click it again to stop. Your speech is converted to text (via the browser's speech
   recognition) and logged in the conversation window.
3. The coach asks a relevant follow-up question based on your answer, and the cycle repeats.
4. Click **End Conversation** at any time to end the session. The coach analyzes the whole
   conversation and gives feedback on grammar, sentence structure, and vocabulary.

## Stack

- **Backend:** Python (Flask) + Google Gemini (`google-generativeai`)
- **Frontend:** Plain HTML/CSS/JS, using the browser's Web Speech API for text-to-speech (asking
  questions) and speech-to-text (transcribing answers)
- **Dev environment:** GitHub Codespaces (`.devcontainer/devcontainer.json` included)

## Setup

1. Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python app.py
   ```
5. Open the forwarded port (5000) in your browser — use **Google Chrome** for best speech
   recognition support.

## Notes

- Speech recognition (`SpeechRecognition` / `webkitSpeechRecognition`) is currently best supported
  in Chrome-based browsers. Firefox/Safari support may be limited or unavailable.
- Conversation state is kept server-side in the Flask session for the duration of a session.
- Every Gemini request tries a fixed, ordered list of models — Gemini 2.5 Flash, 2.5 Flash Lite,
  3 Flash, 3.1 Flash Lite, 3.5 Flash, 3.5 Flash Lite, and 3.6 Flash — and automatically falls back to
  the next model if one is unavailable (rate limited, over capacity, or fails for any other reason).
  Override the list with the `GEMINI_MODELS` env var (comma-separated model IDs).

## Troubleshooting

**"Recording error: service-not-allowed"** — the browser blocked microphone access for the speech
recognition service. This almost always happens when the app is opened inside an embedded preview
frame (e.g. VS Code's "Simple Browser" or the Codespaces port-preview panel), which doesn't grant
microphone permission to the embedded page. Fix: open the forwarded port URL in a full browser tab
instead (in Codespaces, use the "Open in Browser" option on the port-forward notification, or copy
the `https://<codespace-name>-5000.app.github.dev` URL into a new Chrome tab), then allow microphone
access when prompted.

**"Recording error: not-allowed"** — microphone permission was denied for the site. Click the
microphone/lock icon in the browser's address bar, allow microphone access, and try again.
