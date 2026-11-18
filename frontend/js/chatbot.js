/* Ruang obrolan chatbot - UPA BK UTM */
(function () {
  const needRegister = document.getElementById("need-register");
  const chatWrapper = document.getElementById("chat-wrapper");
  const messagesEl = document.getElementById("chat-messages");
  const textEl = document.getElementById("chat-text");
  const sendBtn = document.getElementById("send-btn");
  const handoffBtn = document.getElementById("handoff-btn");
  const crisisBanner = document.getElementById("crisis-banner");

  const reg = JSON.parse(sessionStorage.getItem("upa_reg") || "null");
  if (!reg) {
    needRegister.classList.remove("hidden");
    return;
  }
  chatWrapper.classList.remove("hidden");

  let conversationId = null;
  let busy = false;

  function appendBubble(sender, text) {
    const div = document.createElement("div");
    div.className = "bubble " + (sender === "mahasiswa" ? "mahasiswa" : "bot");
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showCrisis() {
    crisisBanner.classList.remove("hidden");
  }

  async function start() {
    try {
      const res = await fetch("/api/chat/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ registration_id: reg.registration_id, chat_token: reg.chat_token }),
      });
      const data = await res.json();
      if (!res.ok) { throw new Error(typeof data.detail === "string" ? data.detail : "Gagal membuka obrolan."); }
      conversationId = data.conversation_id;
      if (data.disclaimer) {
        document.getElementById("disclaimer-text").innerHTML =
          data.disclaimer.replace("BUKAN pengganti konseling profesional", "<strong>bukan pengganti konseling profesional</strong>");
      }
      if (data.pesan_pembuka) { appendBubble("bot", data.pesan_pembuka); }
      (data.riwayat || []).forEach((m) => appendBubble(m.sender, m.text));
    } catch (err) {
      appendBubble("bot", "Terjadi kendala membuka obrolan: " + err.message);
    }
  }

  async function send(text) {
    if (busy) return;
    busy = true;
    sendBtn.disabled = true;
    appendBubble("mahasiswa", text);
    textEl.value = "";
    try {
      const res = await fetch("/api/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          registration_id: reg.registration_id,
          chat_token: reg.chat_token,
          conversation_id: conversationId,
          text: text,
        }),
      });
      const data = await res.json();
      if (!res.ok) { throw new Error(typeof data.detail === "string" ? data.detail : "Gagal mengirim pesan."); }
      appendBubble("bot", data.reply);
      if (data.eskalasi) { showCrisis(); }
    } catch (err) {
      appendBubble("bot", "Maaf, pesan gagal terkirim: " + err.message);
    } finally {
      busy = false;
      sendBtn.disabled = false;
      textEl.focus();
    }
  }

  sendBtn.addEventListener("click", () => {
    const text = textEl.value.trim();
    if (text) { send(text); }
  });
  textEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = textEl.value.trim();
      if (text) { send(text); }
    }
  });
  handoffBtn.addEventListener("click", () => {
    send("Saya ingin berbicara dengan konselor/petugas UPA BK.");
  });

  start();
})();
