(() => {
  "use strict";

  const GERMAN_LANG = "de-DE";

  const conversationBtn = document.getElementById("conversationBtn");
  const recordBtn = document.getElementById("recordBtn");
  const statusEl = document.getElementById("status");
  const logEl = document.getElementById("conversationLog");
  const feedbackSection = document.getElementById("feedbackSection");
  const feedbackContent = document.getElementById("feedbackContent");

  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
  const speechSynthesisSupported = "speechSynthesis" in window;

  let conversationActive = false;
  let isRecording = false;
  let recognition = null;
  let finalTranscript = "";
  let conversationLog = []; // [{speaker: 'coach'|'user', text: string}]
  let germanVoice = null;

  function pickGermanVoice() {
    if (!speechSynthesisSupported) return;
    const voices = window.speechSynthesis.getVoices();
    germanVoice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("de")) || null;
  }

  if (speechSynthesisSupported) {
    pickGermanVoice();
    window.speechSynthesis.onvoiceschanged = pickGermanVoice;
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function addLogEntry(speaker, text) {
    conversationLog.push({ speaker, text });
    const bubble = document.createElement("div");
    bubble.className = `bubble ${speaker}`;
    const label = document.createElement("span");
    label.className = "speaker";
    label.textContent = speaker === "coach" ? "Coach" : "You";
    const body = document.createElement("span");
    body.textContent = text;
    bubble.appendChild(label);
    bubble.appendChild(body);
    logEl.appendChild(bubble);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function speakGerman(text) {
    return new Promise((resolve) => {
      if (!speechSynthesisSupported) {
        resolve();
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = GERMAN_LANG;
      if (germanVoice) utterance.voice = germanVoice;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.speak(utterance);
    });
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `Request to ${url} failed`);
    }
    return data;
  }

  async function startConversation() {
    conversationBtn.disabled = true;
    recordBtn.disabled = true;
    logEl.innerHTML = "";
    conversationLog = [];
    feedbackSection.classList.add("hidden");
    setStatus("Coach is preparing a question...");

    try {
      const data = await postJSON("/api/start");
      conversationActive = true;
      addLogEntry("coach", data.question);
      conversationBtn.textContent = "End Conversation";
      conversationBtn.classList.add("ending");
      conversationBtn.disabled = false;
      setStatus("Listen to the question, then click \"Record Answer\" to reply in German.");

      await speakGerman(data.question);
      if (conversationActive) {
        recordBtn.disabled = false;
      }
    } catch (err) {
      setStatus(`Error: ${err.message}`);
      conversationBtn.disabled = false;
    }
  }

  async function endConversation() {
    conversationBtn.disabled = true;
    recordBtn.disabled = true;
    if (isRecording && recognition) {
      recognition.stop();
    }
    setStatus("Generating your feedback...");

    try {
      const data = await postJSON("/api/end", { log: conversationLog });
      renderFeedback(data.feedback);
      setStatus("Feedback ready. Click \"Start Conversation\" to practice again.");
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      conversationActive = false;
      conversationBtn.textContent = "Start Conversation";
      conversationBtn.classList.remove("ending");
      conversationBtn.disabled = false;
      recordBtn.disabled = true;
    }
  }

  async function sendAnswerAndGetNextQuestion(answerText) {
    setStatus("Coach is thinking of a follow-up question...");
    recordBtn.disabled = true;
    try {
      const data = await postJSON("/api/next", { answer: answerText });
      addLogEntry("coach", data.question);
      setStatus("Click \"Record Answer\" to reply in German.");
      await speakGerman(data.question);
      if (conversationActive) {
        recordBtn.disabled = false;
      }
    } catch (err) {
      setStatus(`Error: ${err.message}`);
      recordBtn.disabled = false;
    }
  }

  const RECOGNITION_ERROR_MESSAGES = {
    "service-not-allowed":
      "Microphone access was blocked. If you're viewing this inside an embedded preview " +
      "(e.g. a Codespaces/VS Code preview pane), open the page in a full browser tab instead, " +
      "then allow microphone access when prompted.",
    "not-allowed":
      "Microphone permission was denied. Click the microphone/lock icon in the address bar and " +
      "allow access for this site, then try again.",
    "no-speech": "Didn't catch that - no speech was detected.",
    "audio-capture": "No microphone was found. Check that a microphone is connected and enabled.",
    network: "A network error occurred reaching the speech recognition service. Check your connection.",
  };

  function startRecording() {
    if (!SpeechRecognitionImpl) {
      setStatus("Speech recognition is not supported in this browser. Try Chrome.");
      return;
    }
    recognition = new SpeechRecognitionImpl();
    recognition.lang = GERMAN_LANG;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    finalTranscript = "";

    recognition.onstart = () => {
      isRecording = true;
      recordBtn.classList.add("recording");
      recordBtn.textContent = "Recording... (click to stop)";
      setStatus("Recording - speak your answer in German. Click again when you're done.");
    };

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const segment = event.results[i][0].transcript.trim();
          if (segment) {
            finalTranscript = finalTranscript ? `${finalTranscript} ${segment}` : segment;
          }
        }
      }
    };

    recognition.onerror = (event) => {
      const friendlyMessage = RECOGNITION_ERROR_MESSAGES[event.error];
      setStatus(
        friendlyMessage
          ? `Recording error: ${friendlyMessage}`
          : `Recording error: ${event.error}. Click "Record Answer" to try again.`
      );
    };

    recognition.onend = () => {
      isRecording = false;
      recordBtn.classList.remove("recording");
      recordBtn.textContent = "Record Answer";

      const transcript = finalTranscript.trim();
      if (transcript) {
        addLogEntry("user", transcript);
        sendAnswerAndGetNextQuestion(transcript);
      } else {
        setStatus("Didn't catch that. Click \"Record Answer\" to try again.");
        recordBtn.disabled = false;
      }
    };

    recognition.start();
  }

  function stopRecording() {
    if (recognition) {
      recognition.stop();
    }
  }

  function renderFeedback(markdown) {
    feedbackContent.innerHTML = simpleMarkdownToHtml(markdown || "");
    feedbackSection.classList.remove("hidden");
    feedbackSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function simpleMarkdownToHtml(md) {
    const escapeHtml = (s) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    const formatInline = (line) => escapeHtml(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    const parseTableRow = (line) =>
      line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim());

    const isTableSeparatorRow = (line) => {
      const cells = parseTableRow(line);
      return cells.length > 0 && cells.every((cell) => /^:?-+:?$/.test(cell));
    };

    const renderTable = (headerCells, bodyRows) => {
      let table = "<table><thead><tr>";
      for (const cell of headerCells) {
        table += `<th>${formatInline(cell)}</th>`;
      }
      table += "</tr></thead><tbody>";
      for (const row of bodyRows) {
        table += "<tr>";
        for (let c = 0; c < headerCells.length; c++) {
          table += `<td>${formatInline(row[c] || "")}</td>`;
        }
        table += "</tr>";
      }
      table += "</tbody></table>";
      return table;
    };

    const lines = md.split("\n");
    let html = "";
    let inList = false;

    const closeList = () => {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) {
        closeList();
        continue;
      }

      if (line.startsWith("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
        closeList();
        const headerCells = parseTableRow(line);
        const bodyRows = [];
        i += 2; // skip header row and separator row
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          bodyRows.push(parseTableRow(lines[i]));
          i++;
        }
        i--; // compensate for the outer loop's increment
        html += renderTable(headerCells, bodyRows);
        continue;
      }

      const text = formatInline(line);

      if (text.startsWith("### ")) {
        closeList();
        html += `<h3>${text.slice(4)}</h3>`;
      } else if (text.startsWith("## ")) {
        closeList();
        html += `<h2>${text.slice(3)}</h2>`;
      } else if (text.startsWith("- ") || text.startsWith("* ")) {
        if (!inList) {
          html += "<ul>";
          inList = true;
        }
        html += `<li>${text.slice(2)}</li>`;
      } else {
        closeList();
        html += `<p>${text}</p>`;
      }
    }
    closeList();
    return html;
  }

  conversationBtn.addEventListener("click", () => {
    if (!conversationActive) {
      startConversation();
    } else {
      endConversation();
    }
  });

  recordBtn.addEventListener("click", () => {
    if (!isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  });

  if (!SpeechRecognitionImpl) {
    setStatus("Note: this browser doesn't support speech recognition. Try Google Chrome.");
  }
})();
