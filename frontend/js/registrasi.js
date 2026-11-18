/* Pendaftaran layanan - UPA BK UTM */
(function () {
  const form = document.getElementById("reg-form");
  const successPanel = document.getElementById("success-panel");
  const errorBanner = document.getElementById("error-banner");
  const submitBtn = document.getElementById("submit-btn");

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function fillSelect(selectEl, items, placeholder) {
    selectEl.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = placeholder;
    selectEl.appendChild(ph);
    items.forEach((it) => {
      const opt = document.createElement("option");
      opt.value = it;
      opt.textContent = it;
      selectEl.appendChild(opt);
    });
  }

  async function loadOptions() {
    try {
      const res = await fetch("/api/registrations/options");
      const data = await res.json();
      fillSelect(document.getElementById("jenis_layanan"), data.jenis_layanan, "Pilih jenis layanan...");
      fillSelect(document.getElementById("preferensi_hari"), data.hari, "Pilih hari...");
      fillSelect(document.getElementById("preferensi_waktu"), data.waktu, "Pilih rentang waktu...");
    } catch (e) {
      showError("Gagal memuat opsi form. Pastikan server berjalan, lalu muat ulang halaman.");
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBanner.classList.add("hidden");

    const payload = {
      nama: document.getElementById("nama").value.trim(),
      nim: document.getElementById("nim").value.trim(),
      kontak: document.getElementById("kontak").value.trim(),
      jenis_layanan: document.getElementById("jenis_layanan").value,
      preferensi_hari: document.getElementById("preferensi_hari").value,
      preferensi_waktu: document.getElementById("preferensi_waktu").value,
      keluhan: document.getElementById("keluhan").value.trim() || null,
      setuju_penggunaan_data: document.getElementById("setuju").checked,
    };

    if (!payload.nama || !payload.nim || !payload.kontak) { showError("Nama, NIM, dan kontak wajib diisi."); return; }
    if (!payload.jenis_layanan || !payload.preferensi_hari || !payload.preferensi_waktu) { showError("Pilih jenis layanan, hari, dan waktu."); return; }
    if (!payload.setuju_penggunaan_data) { showError("Persetujuan penggunaan data wajib diberikan."); return; }

    submitBtn.disabled = true;
    try {
      const res = await fetch("/api/registrations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Periksa kembali isian formulir.");
      }
      // Simpan konteks mahasiswa untuk halaman skrining & obrolan.
      sessionStorage.setItem("upa_reg", JSON.stringify({
        registration_id: data.registration_id,
        chat_token: data.chat_token,
        nama: data.nama,
      }));
      form.classList.add("hidden");
      successPanel.classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      showError(err.message || "Terjadi kesalahan jaringan.");
    } finally {
      submitBtn.disabled = false;
    }
  });

  loadOptions();
})();
