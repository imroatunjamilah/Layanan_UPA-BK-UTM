/* Skrining DASS-21 - UPA BK UTM
   Kebijakan: hasil/skor TIDAK ditampilkan ke mahasiswa. */
(function () {
  const needRegister = document.getElementById("need-register");
  const quizWrapper = document.getElementById("quiz-wrapper");
  const questionsEl = document.getElementById("questions");
  const quizForm = document.getElementById("quiz-form");
  const donePanel = document.getElementById("done-panel");
  const errorBanner = document.getElementById("error-banner");
  const submitBtn = document.getElementById("submit-btn");

  const reg = JSON.parse(sessionStorage.getItem("upa_reg") || "null");
  if (!reg) {
    needRegister.classList.remove("hidden");
    return;
  }
  quizWrapper.classList.remove("hidden");

  const OPTION_LABELS = {
    0: "Tidak sama sekali",
    1: "Sedikit, atau sesekali",
    2: "Sedang, atau sering",
    3: "Sangat cocok, atau hampir selalu",
  };

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function loadQuestions() {
    try {
      const res = await fetch("/api/dass21/questions");
      const data = await res.json();
      document.getElementById("intro-text").textContent = data.pengantar;

      data.pertanyaan.forEach((q) => {
        const item = document.createElement("div");
        item.className = "q-item";

        const p = document.createElement("p");
        p.className = "q-text";
        const no = document.createElement("span");
        no.className = "no";
        no.textContent = q.no + ".";
        p.appendChild(no);
        p.appendChild(document.createTextNode(q.teks));
        item.appendChild(p);

        const row = document.createElement("div");
        row.className = "opt-row";
        [0, 1, 2, 3].forEach((val) => {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "radio";
          input.name = "q" + q.no;
          input.value = val;
          label.appendChild(input);
          label.appendChild(document.createTextNode(OPTION_LABELS[val]));
          row.appendChild(label);
        });
        item.appendChild(row);
        questionsEl.appendChild(item);
      });
    } catch (e) {
      showError("Gagal memuat pertanyaan. Pastikan server berjalan lalu muat ulang halaman.");
    }
  }

  quizForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBanner.classList.add("hidden");

    const jawaban = {};
    let missing = [];
    for (let i = 1; i <= 21; i++) {
      const checked = quizForm.querySelector(`input[name="q${i}"]:checked`);
      if (checked) { jawaban[String(i)] = parseInt(checked.value, 10); }
      else { missing.push(i); }
    }
    if (missing.length) {
      showError("Masih ada pertanyaan yang belum dijawab: nomor " + missing.join(", ") + ".");
      return;
    }

    submitBtn.disabled = true;
    try {
      const res = await fetch("/api/dass21/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          registration_id: reg.registration_id,
          chat_token: reg.chat_token,
          jawaban: jawaban,
        }),
      });
      const data = await res.json();
      if (!res.ok) { throw new Error(typeof data.detail === "string" ? data.detail : "Gagal menyimpan jawaban."); }
      quizForm.classList.add("hidden");
      donePanel.classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      showError(err.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  loadQuestions();
})();
