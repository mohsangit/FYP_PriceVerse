(function () {

  const root = document.getElementById("pvChatbot");

  const bubble = document.getElementById("pvChatbotBubble");

  const panel = document.getElementById("pvChatbotPanel");

  const closeBtn = document.getElementById("pvChatbotClose");

  const form = document.getElementById("pvChatbotForm");

  const input = document.getElementById("pvChatbotText");

  const messages = document.getElementById("pvChatbotMessages");

  const sendBtn = form?.querySelector(".pv-chatbot__send");



  if (!bubble || !panel || !form || !input || !messages) return;



  const chatUrl = window.PV_CHAT_URL || "/chat/";

  const streamUrl = window.PV_CHAT_STREAM_URL || chatUrl.replace(/\/?$/, "/stream/");

  const useStreaming = window.PV_CHAT_STREAM !== false;

  const clientTimeoutMs = Number(window.PV_CHAT_TIMEOUT_MS) || 180000;



  let welcomeCleared = false;

  let inFlight = false;

  let abortController = null;



  if (window.marked) {

    marked.setOptions({ breaks: true, gfm: true });

  }



  function getCookie(name) {

    const value = `; ${document.cookie}`;

    const parts = value.split(`; ${name}=`);

    if (parts.length === 2) return parts.pop().split(";").shift();

    return "";

  }



  function clearWelcome() {

    if (welcomeCleared) return;

    const welcome = messages.querySelector(".pv-chatbot__welcome");

    if (welcome) welcome.remove();

    welcomeCleared = true;

  }



  function renderContent(text, who) {

    if (who === "bot" && window.marked) {

      return marked.parse(text || "");

    }

    const escaped = (text || "")

      .replace(/&/g, "&amp;")

      .replace(/</g, "&lt;")

      .replace(/>/g, "&gt;");

    return escaped.replace(/\n/g, "<br>");

  }



  function addMsg(text, who) {

    const div = document.createElement("div");

    div.className = `pv-chatbot__msg pv-chatbot__msg--${who}`;

    if (who === "bot") {

      div.classList.add("pv-chatbot__msg--markdown");

    }

    div.innerHTML = renderContent(text, who);

    messages.appendChild(div);

    messages.scrollTop = messages.scrollHeight;

    return div;

  }



  function addTyping(label) {

    const div = document.createElement("div");

    div.className = "pv-chatbot__msg pv-chatbot__msg--bot pv-chatbot__typing";

    div.dataset.status = label || "Thinking";

    div.innerHTML = `<span class="pv-chatbot__status">${label || "Thinking"}</span><span></span><span></span><span></span>`;

    messages.appendChild(div);

    messages.scrollTop = messages.scrollHeight;

    return div;

  }



  function setLoading(loading) {

    inFlight = loading;

    input.disabled = loading;

    if (sendBtn) sendBtn.disabled = loading;

    if (root) root.classList.toggle("is-loading", loading);

  }



  function openChat() {

    panel.classList.add("is-open");

    panel.setAttribute("aria-hidden", "false");

    if (root) root.classList.add("is-open");

    setTimeout(() => input.focus(), 250);

  }



  function closeChat() {

    panel.classList.remove("is-open");

    panel.setAttribute("aria-hidden", "true");

    if (root) root.classList.remove("is-open");

  }



  bubble.addEventListener("click", () => {

    if (panel.classList.contains("is-open")) closeChat();

    else openChat();

  });



  closeBtn?.addEventListener("click", closeChat);



  document.addEventListener("keydown", (e) => {

    if (e.key === "Escape" && panel.classList.contains("is-open")) closeChat();

  });



  async function sendJson(userText) {

    const csrf = getCookie("csrftoken");

    abortController = new AbortController();

    const timeoutId = setTimeout(() => abortController.abort(), clientTimeoutMs);



    try {

      const res = await fetch(chatUrl, {

        method: "POST",

        headers: {

          "Content-Type": "application/json",

          "X-CSRFToken": csrf,

        },

        body: JSON.stringify({ message: userText }),

        signal: abortController.signal,

      });

      clearTimeout(timeoutId);

      if (!res.ok) return { reply: "Sorry, server error. Please try again." };

      return await res.json();

    } catch (err) {

      clearTimeout(timeoutId);

      if (err.name === "AbortError") {

        return { reply: "Request timed out. The model may still be loading — please try again." };

      }

      throw err;

    }

  }



  async function sendStream(userText, botNode, typingNode) {

    const csrf = getCookie("csrftoken");

    abortController = new AbortController();

    const timeoutId = setTimeout(() => abortController.abort(), clientTimeoutMs);



    let fullText = "";

    let markdownScheduled = false;



    function scheduleMarkdown() {

      if (markdownScheduled) return;

      markdownScheduled = true;

      requestAnimationFrame(() => {

        markdownScheduled = false;

        if (window.marked) {

          botNode.innerHTML = marked.parse(fullText || "");

        } else {

          botNode.textContent = fullText;

        }

        messages.scrollTop = messages.scrollHeight;

      });

    }



    const res = await fetch(streamUrl, {

      method: "POST",

      headers: {

        "Content-Type": "application/json",

        "X-CSRFToken": csrf,

      },

      body: JSON.stringify({ message: userText }),

      signal: abortController.signal,

    });



    if (!res.ok) {

      clearTimeout(timeoutId);

      return { reply: "Sorry, server error. Please try again." };

    }



    const reader = res.body.getReader();

    const decoder = new TextDecoder();

    let buffer = "";



    typingNode.remove();

    botNode.classList.add("pv-chatbot__msg--markdown");



    while (true) {

      const { done, value } = await reader.read();

      if (done) break;



      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");

      buffer = lines.pop() || "";



      for (const line of lines) {

        if (!line.startsWith("data:")) continue;

        const payload = line.slice(5).trim();

        if (!payload) continue;



        let event;

        try {

          event = JSON.parse(payload);

        } catch (_) {

          continue;

        }



        if (event.type === "chunk" && event.content) {

          fullText += event.content;

          scheduleMarkdown();

        } else if (event.type === "done") {

          fullText = event.reply || fullText;

        }

      }

    }



    clearTimeout(timeoutId);

    botNode.innerHTML = renderContent(fullText || "Okay.", "bot");

    messages.scrollTop = messages.scrollHeight;

    return { reply: fullText };

  }



  async function handleSend(text) {

    text = (text || "").trim();

    if (!text || inFlight) return;



    clearWelcome();

    addMsg(text, "user");

    input.value = "";

    setLoading(true);



    const typingNode = addTyping("Searching WhatMobile…");

    let botNode = null;



    try {

      if (useStreaming) {

        botNode = document.createElement("div");

        botNode.className = "pv-chatbot__msg pv-chatbot__msg--bot";

        messages.appendChild(botNode);

        await sendStream(text, botNode, typingNode);

      } else {

        const data = await sendJson(text);

        typingNode.remove();

        addMsg(data.reply || "Okay.", "bot");

      }

    } catch (err) {

      if (typingNode.parentNode) typingNode.remove();

      if (botNode && !botNode.textContent) botNode.remove();

      addMsg(

        err.name === "AbortError"

          ? "Request timed out. Please try again — the AI model may still be warming up."

          : "Network issue. Please try again.",

        "bot"

      );

    } finally {

      setLoading(false);

      abortController = null;

      input.focus();

    }

  }



  form.addEventListener("submit", (e) => {

    e.preventDefault();

    handleSend(input.value);

  });

})();

