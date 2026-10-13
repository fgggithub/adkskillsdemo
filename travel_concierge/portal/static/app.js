// StreamAssist Enterprise Web Portal Frontend Logic

let currentSessionId = null;
let currentDestination = "Tokyo Shinjuku";
let isStreaming = false;

document.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  setupEventListeners();
  initNewSession();
});

async function loadConfig() {
  try {
    const res = await fetch("/portal/config");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("cfg-project-id").textContent = data.project_id || "qwiklabs-gcp-01-f54046474f73";
    document.getElementById("cfg-region").textContent = data.region || "us-central1";
    document.getElementById("cfg-engine-id").textContent = data.default_engine_id || "travel-concierge-app";
    
    if (data.budget) {
      const spent = data.budget.cumulative_cost_usd || 0.045;
      const limit = data.budget.budget_limit_usd || 5.0;
      const pct = data.budget.budget_utilized_percent || 0.9;
      document.getElementById("badge-budget-text").textContent = `$${spent.toFixed(4)} / $${limit.toFixed(2)} (${pct.toFixed(1)}%)`;
    }
  } catch (err) {
    console.warn("Failed to load portal configuration:", err);
  }
}

function initNewSession() {
  currentSessionId = "session-" + Math.random().toString(36).substring(2, 10);
  document.getElementById("cfg-session-id").textContent = currentSessionId;
  appendSystemMessage(
    "👋 **Welcome to the Gemini Enterprise & Travel Concierge Web Portal!**\n\n" +
    "This webapp is front-ended by Google Cloud Discovery Engine's **`streamAssist` API**.\n\n" +
    "- Select a scenario on the left or type your own travel planning request.\n" +
    "- Watch real-time **`plannerSteps`** stream as subagents coordinate via A2A protocol.\n" +
    "- Try multi-turn refinements or test Model Armor security policy guardrails."
  );
}

function setupEventListeners() {
  const sendBtn = document.getElementById("send-btn");
  const queryInput = document.getElementById("query-input");
  const destInput = document.getElementById("destination-input");
  const newSessionBtn = document.getElementById("new-session-btn");

  sendBtn.addEventListener("click", () => handleSend());
  
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  destInput.addEventListener("change", (e) => {
    currentDestination = e.target.value.trim() || "Tokyo Shinjuku";
  });

  newSessionBtn.addEventListener("click", () => {
    initNewSession();
  });

  // Demo Prompt Buttons
  document.querySelectorAll(".demo-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      const dest = btn.getAttribute("data-dest");
      if (dest) {
        document.getElementById("destination-input").value = dest;
        currentDestination = dest;
      }
      queryInput.value = prompt;
      handleSend();
    });
  });
}

async function handleSend(customText = null) {
  if (isStreaming) return;
  const queryInput = document.getElementById("query-input");
  const text = customText || queryInput.value.trim();
  if (!text) return;

  queryInput.value = "";
  appendUserMessage(text);

  isStreaming = true;
  updateUIStreamingState(true);

  const assistantMsgEl = createAssistantMessagePlaceholder();
  const stepsContainer = assistantMsgEl.querySelector(".streamassist-steps-body");
  const stepsHeader = assistantMsgEl.querySelector(".streamassist-steps-header");
  const answerBody = assistantMsgEl.querySelector(".answer-body");
  const statusBadge = assistantMsgEl.querySelector(".step-count-badge");

  let stepCount = 0;
  const autoConfirm = document.getElementById("auto-confirm-check").checked;
  const backendMode = document.getElementById("backend-select").value;

  try {
    const response = await fetch("/portal/api/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        session_id: currentSessionId,
        destination: currentDestination,
        backend: backendMode,
        auto_confirm: autoConfirm,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      answerBody.innerHTML = `<div style="color: var(--danger-color)">Error: ${response.status} - ${errText}</div>`;
      isStreaming = false;
      updateUIStreamingState(false);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // Keep incomplete chunk in buffer

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const dataStr = line.slice(6).trim();
        if (dataStr === "[DONE]") {
          statusBadge.textContent = "✓ Completed";
          statusBadge.style.color = "var(--success-color)";
          break;
        }

        try {
          const payload = JSON.parse(dataStr);
          renderStreamAssistChunk(payload, stepsContainer, answerBody, statusBadge, assistantMsgEl);
        } catch (e) {
          console.warn("Error parsing chunk JSON:", e, dataStr);
        }
      }
    }
  } catch (err) {
    answerBody.innerHTML = `<div style="color: var(--danger-color)">Stream error: ${err.message}</div>`;
  } finally {
    isStreaming = false;
    updateUIStreamingState(false);
    loadConfig(); // Refresh budget counters
  }
}

function renderStreamAssistChunk(payload, stepsContainer, answerBody, statusBadge, msgWrapper) {
  if (!payload || !payload.answer) return;
  const ans = payload.answer;

  // Render Planner Steps
  if (ans.diagnosticInfo && ans.diagnosticInfo.plannerSteps) {
    ans.diagnosticInfo.plannerSteps.forEach((step) => {
      if (step.queryStep) {
        addPlannerStep(stepsContainer, "🔍 Ingress Query", step.queryStep.parts?.[0]?.text || "Query registered", "query-step");
      } else if (step.planStep) {
        const text = step.planStep.parts?.[0]?.text || "";
        let stepClass = "";
        let title = "🤖 Planner Step";
        if (text.includes("Model Armor") || text.includes("BLOCKED")) {
          stepClass = "security-step";
          title = "🛡️ Gateway Policy & Security";
        } else if (text.includes("Escalation") || text.includes("Model")) {
          title = "🧠 Model Escalation Assessment";
        } else if (text.includes("Delegating") || text.includes("Hotel") || text.includes("Restaurant")) {
          title = "🤝 A2A Subagent Delegation";
        } else if (text.includes("Context Caching") || text.includes("Telemetry")) {
          stepClass = "cache-step";
          title = "⚡ Vertex AI Context Cache & Telemetry";
        }
        addPlannerStep(stepsContainer, title, text, stepClass);
      }
    });

    const stepCount = stepsContainer.children.length;
    statusBadge.textContent = `Streaming (${stepCount} steps)...`;
  }

  // Render Progressive or Final Answer Text
  if (ans.answerText) {
    answerBody.innerHTML = formatMarkdown(ans.answerText);
  }

  // Handle Security Block State
  if (ans.state === "FAILED" && ans.safetyRatings) {
    statusBadge.textContent = "🛑 Blocked by Model Armor";
    statusBadge.style.color = "var(--danger-color)";
  }

  // Handle Succeeded State & Grounded Cards
  if (ans.state === "SUCCEEDED") {
    statusBadge.textContent = "✓ Succeeded (Grounded)";
    statusBadge.style.color = "var(--success-color)";

    // Add interactive action buttons if not already present
    if (!msgWrapper.querySelector(".interactive-hitl-box")) {
      const hitlBox = document.createElement("div");
      hitlBox.className = "interactive-hitl-box";
      hitlBox.innerHTML = `
        <div>
          <strong>⚡ Interactive Multi-Turn Actions:</strong>
          <span style="font-size: 11px; color: var(--text-secondary); margin-left: 6px;">Hotel held with A2A Task ID</span>
        </div>
        <div class="hitl-actions">
          <button class="btn-hitl-confirm" onclick="triggerHitlConfirmation()">Confirm & Pay ($420.00)</button>
          <button class="btn-hitl-refine" onclick="triggerRefinePrompt()">Switch to Halal / Kosher</button>
        </div>
      `;
      msgWrapper.appendChild(hitlBox);
    }
  }

  // Auto-scroll to bottom
  const chatHistory = document.getElementById("chat-history");
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function addPlannerStep(container, title, text, extraClass = "") {
  // Prevent duplicate text in same container
  const existing = Array.from(container.children).find(el => el.textContent.includes(text.substring(0, 40)));
  if (existing) return;

  const item = document.createElement("div");
  item.className = `planner-step-item ${extraClass}`;
  item.innerHTML = `
    <div class="planner-step-title">${title}</div>
    <div class="planner-step-text">${formatMarkdown(text)}</div>
  `;
  container.appendChild(item);
}

function appendUserMessage(text) {
  const container = document.getElementById("chat-history");
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper";
  wrapper.innerHTML = `<div class="message-user">${escapeHtml(text)}</div>`;
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
}

function appendSystemMessage(markdownText) {
  const container = document.getElementById("chat-history");
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper";
  wrapper.innerHTML = `
    <div class="message-assistant">
      <div class="answer-body">${formatMarkdown(markdownText)}</div>
    </div>
  `;
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
}

function createAssistantMessagePlaceholder() {
  const container = document.getElementById("chat-history");
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper";
  wrapper.innerHTML = `
    <div class="message-assistant">
      <div class="streamassist-steps-container">
        <div class="streamassist-steps-header" onclick="toggleSteps(this)">
          <span>📋 StreamAssist Planner Steps (<span class="step-count-badge">Initializing...</span>)</span>
          <span>▼</span>
        </div>
        <div class="streamassist-steps-body"></div>
      </div>
      <div class="answer-body"><span class="spinner"></span> <em>Receiving StreamAssist stream...</em></div>
    </div>
  `;
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  return wrapper;
}

function toggleSteps(header) {
  const body = header.nextElementSibling;
  if (body.style.display === "none") {
    body.style.display = "flex";
    header.querySelector("span:last-child").textContent = "▼";
  } else {
    body.style.display = "none";
    header.querySelector("span:last-child").textContent = "▶";
  }
}

function updateUIStreamingState(streaming) {
  const sendBtn = document.getElementById("send-btn");
  if (streaming) {
    sendBtn.disabled = true;
    sendBtn.innerHTML = `<span class="spinner"></span> Streaming...`;
  } else {
    sendBtn.disabled = false;
    sendBtn.innerHTML = `Send ➔`;
  }
}

function triggerHitlConfirmation() {
  handleSend("Confirmed. Please proceed with payment of $420.00 via Visa ending in 4242.");
}

function triggerRefinePrompt() {
  handleSend("Switch dining to vegan and kosher ramen in Shibuya with severe celiac nut allergy and compare tokyo hygiene scores");
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`([^`]+)`/gim, '<code>$1</code>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/^- (.*$)/gim, '<li>$1</li>');

  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  return html.replace(/\n\n/g, '<br/><br/>');
}
