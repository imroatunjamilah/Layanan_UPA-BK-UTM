/* Dashboard admin - UPA BK UTM */
(function () {
  const token = localStorage.getItem("upa_admin_token");
  if (!token) { location.href = "/admin-login.html"; return; }

  const STATUS_CLASS = {
    menunggu_ditinjau: "st-menunggu",
    sedang_diproses: "st-proses",
    dijadwalkan: "st-jadwal",
    selesai: "st-selesai",
    perlu_ditinjau_segera: "st-urgent",
  };
  const STATUS_LABELS = {
    menunggu_ditinjau: "Menunggu Ditinjau",
    sedang_diproses: "Sedang Diproses",
    dijadwalkan: "Dijadwalkan",
    selesai: "Selesai",
    perlu_ditinjau_segera: "Perlu Ditinjau Segera",
  };
  const STATUS_ORDER = [
    "perlu_ditinjau_segera", "menunggu_ditinjau", "sedang_diproses", "dijadwalkan", "selesai",
  ];
  const JADWAL_STATUS_LABEL = {
    terjadwal: "Terjadwal", selesai: "Selesai", dibatalkan: "Dibatalkan", ditunda: "Ditunda",
  };
  const JADWAL_BADGE_CLASS = {
    terjadwal: "st-jadwal", selesai: "st-selesai", dibatalkan: "st-menunggu", ditunda: "st-proses",
  };
  const URGENSI_BADGE = {
    darurat: '<span class="badge urg-badge-darurat">DARURAT</span>',
    tinggi: '<span class="badge urg-badge-tinggi">TINGGI</span>',
    normal: '<span class="badge urg-badge-normal">NORMAL</span>',
  };
  let page = 1;
  let petugasList = [];
  let weekAnchor = null; // tanggal acuan (ISO) minggu yang sedang ditampilkan
  let schedRegId = null; // kasus yang sedang dijadwalkan pada modal

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function fmtDate(iso) {
    if (!iso) return "-";
    try {
      return new Date(iso).toLocaleString("id-ID", {
        timeZone: "Asia/Jakarta", dateStyle: "medium", timeStyle: "short",
      });
    } catch (e) { return iso; }
  }

  // Pesan status form: tampil mencolok (merah = gagal, hijau = sukses)
  // agar validasi/galat tidak terlihat seperti tombol yang tidak berfungsi.
  function setMsg(el, text, type) {
    if (!el) return;
    el.textContent = text;
    el.className = "form-msg show " + (type || "info");
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
        ...(opts.headers || {}),
      },
    });
    if (res.status === 401) {
      localStorage.removeItem("upa_admin_token");
      location.href = "/admin-login.html";
      throw new Error("Sesi berakhir, silakan login ulang.");
    }
    return res;
  }

  // ---------- profil & logout ----------
  api("/api/admin/me").then((r) => r.json()).then((u) => {
    document.getElementById("admin-name").textContent =
      "Halo, " + (u.nama_lengkap || u.username);
  }).catch(() => {});

  document.getElementById("logout-btn").addEventListener("click", async () => {
    try { await api("/api/admin/logout", { method: "POST" }); } catch (e) { /* abaikan */ }
    localStorage.removeItem("upa_admin_token");
    localStorage.removeItem("upa_admin_name");
    location.href = "/admin-login.html";
  });

  // ---------- statistik ----------
  async function loadStats() {
    try {
      const res = await api("/api/admin/stats");
      const s = await res.json();
      const cards = [
        { num: s.total_registrasi, lbl: "Total pendaftaran" },
        { num: s.total_skrining_dass21, lbl: "Skrining DASS-21 terisi" },
        { num: s.total_percakapan, lbl: "Sesi obrolan" },
        { num: s.total_pesan, lbl: "Total pesan" },
        { num: s.perlu_ditinjau_segera, lbl: "Perlu ditinjau segera", urgent: true },
      ];
      const grid = document.getElementById("stats-grid");
      grid.innerHTML = cards.map((c) =>
        `<div class="stat-card${c.urgent ? " urgent" : ""}">
           <div class="num">${c.num}</div><div class="lbl">${c.lbl}</div>
         </div>`).join("")
        + `<div class="stat-card" style="grid-column:1/-1;">
             <div class="lbl" style="margin-bottom:4px;">Per status: ${
               Object.entries(s.per_status).map(([k, v]) => `${STATUS_LABELS[k] || k}: <strong>${v}</strong>`).join(" &nbsp;|&nbsp; ")
             }</div>
             <div class="lbl">Per layanan: ${
               Object.entries(s.per_jenis_layanan).map(([k, v]) => `${escapeHtml(k)}: <strong>${v}</strong>`).join(" &nbsp;|&nbsp; ")
             }</div>
             <div class="lbl">Kasus per petugas: ${
               Object.keys(s.per_petugas || {}).length
                 ? Object.entries(s.per_petugas).map(([k, v]) => `${escapeHtml(k)}: <strong>${v}</strong>`).join(" &nbsp;|&nbsp; ")
                 : "-"
             }</div>
           </div>`;
    } catch (e) { /* sudah ditangani api() */ }
  }

  // ---------- opsi filter layanan ----------
  fetch("/api/registrations/options").then((r) => r.json()).then((d) => {
    const sel = document.getElementById("f-layanan");
    d.jenis_layanan.forEach((j) => {
      const o = document.createElement("option");
      o.value = j; o.textContent = j;
      sel.appendChild(o);
    });
  });

  // ---------- jadwal mingguan (kalender WIB) ----------
  function isoOfUTC(d) {
    return d.getUTCFullYear() + "-" +
      String(d.getUTCMonth() + 1).padStart(2, "0") + "-" +
      String(d.getUTCDate()).padStart(2, "0");
  }
  // Tanggal hari ini menurut WIB (Asia/Jakarta, UTC+7).
  function wibTodayISO() { return isoOfUTC(new Date(Date.now() + 7 * 3600 * 1000)); }
  function mondayOfISO(iso) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); // mundur ke Senin
    return isoOfUTC(d);
  }
  function addDaysISO(iso, n) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return isoOfUTC(d);
  }
  function fmtTanggalID(iso) {
    try {
      return new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", {
        timeZone: "Asia/Jakarta", day: "numeric", month: "short", year: "numeric",
      });
    } catch (e) { return iso; }
  }

  async function loadWeek() {
    const grid = document.getElementById("week-grid");
    const params = new URLSearchParams();
    if (weekAnchor) params.set("start", weekAnchor);
    const wkP = document.getElementById("wk-petugas").value;
    if (wkP) params.set("petugas_id", wkP);
    try {
      const res = await api("/api/admin/schedule/week?" + params.toString());
      if (!res.ok) throw new Error((await res.json()).detail || "gagal memuat");
      const data = await res.json();
      weekAnchor = data.start; // ternormalisasi ke Senin oleh server
      document.getElementById("wk-label").textContent =
        `${fmtTanggalID(data.start)} s.d. ${fmtTanggalID(data.end)}` +
        (data.total_darurat > 0 ? ` - ${data.total_darurat} sesi kasus DARURAT` : "");
      document.getElementById("wk-empty").classList.toggle("hidden", data.total > 0);
      renderWeek(data);
    } catch (e) {
      grid.innerHTML = `<p class="sub">Gagal memuat jadwal: ${escapeHtml(e.message)}</p>`;
    }
  }

  function renderWeek(data) {
    const grid = document.getElementById("week-grid");
    grid.innerHTML = data.days.map((d) => {
      const items = d.items.map((it) => `
        <div class="wk-item urg-${escapeHtml(it.urgensi || "normal")} st-${escapeHtml(it.status)}"
             data-reg="${it.registration_id}" title="Klik untuk membuka detail kasus">
          <div class="wk-time">${escapeHtml(it.jam_mulai)}-${escapeHtml(it.jam_selesai)} WIB</div>
          <div class="wk-nama">${escapeHtml(it.nama || "-")}</div>
          <div class="wk-petugas">${it.petugas ? escapeHtml(it.petugas.nama) : "tanpa konselor"}</div>
          <div class="wk-meta">${escapeHtml(it.metode)}${it.lokasi ? " - " + escapeHtml(it.lokasi) : ""}</div>
          <div class="wk-status">${JADWAL_STATUS_LABEL[it.status] || it.status}${
            it.followup_status === "perlu_ditinjau_segera" ? " \u2022 DARURAT" : ""}</div>
        </div>`).join("");
      return `<div class="wk-day${d.is_today ? " wk-today" : ""}">
        <div class="wk-head"><span>${d.hari}</span><span class="wk-tanggal">${fmtTanggalID(d.tanggal)}</span></div>
        <div class="wk-body">${items || '<div class="wk-none">Tidak ada sesi</div>'}</div>
      </div>`;
    }).join("");
    grid.querySelectorAll(".wk-item").forEach((el) => {
      el.addEventListener("click", () => openDetail(Number(el.dataset.reg)));
    });
  }

  document.getElementById("wk-prev").addEventListener("click", () => {
    weekAnchor = addDaysISO(weekAnchor || wibTodayISO(), -7); loadWeek();
  });
  document.getElementById("wk-next").addEventListener("click", () => {
    weekAnchor = addDaysISO(weekAnchor || wibTodayISO(), 7); loadWeek();
  });
  document.getElementById("wk-today").addEventListener("click", () => {
    weekAnchor = wibTodayISO(); loadWeek();
  });
  document.getElementById("wk-petugas").addEventListener("change", () => loadWeek());

  // ---------- antrean prioritas penjadwalan ----------
  async function loadQueue() {
    try {
      const res = await api("/api/admin/schedule/queue?limit=25");
      if (!res.ok) return;
      const data = await res.json();
      const s = data.ringkasan;
      document.getElementById("queue-summary").innerHTML =
        `Menunggu penjadwalan: <strong>${data.total}</strong> kasus &nbsp;|&nbsp; ` +
        `Darurat: <strong>${s.darurat}</strong> &nbsp;|&nbsp; Tinggi: <strong>${s.tinggi}</strong> &nbsp;|&nbsp; Normal: <strong>${s.normal}</strong>`;
      const list = document.getElementById("queue-list");
      list.innerHTML = data.items.map((it) => `
        <div class="queue-item urg-${escapeHtml(it.urgensi)}">
          <div class="q-main">
            <div class="q-title">${URGENSI_BADGE[it.urgensi] || ""}
              <strong>${escapeHtml(it.nama)}</strong>
              <span class="q-nim">(${escapeHtml(it.nim)})</span></div>
            <div class="q-reason">${escapeHtml(it.alasan)}</div>
            <div class="q-meta">
              Layanan: ${escapeHtml(it.jenis_layanan)} - Menunggu ${it.menunggu_hari} hari -
              Preferensi: ${escapeHtml(it.preferensi_hari)}, ${escapeHtml(it.preferensi_waktu)} -
              ${it.petugas ? `Penangan saat ini: ${escapeHtml(it.petugas.nama)}` : "Belum ada penangan"}
            </div>
          </div>
          <div class="q-act">
            <button class="btn small" data-sched="${it.registration_id}">Jadwalkan</button>
          </div>
        </div>`).join("");
      document.getElementById("queue-empty").classList.toggle("hidden", data.total > 0);
      list.querySelectorAll("button[data-sched]").forEach((btn) => {
        btn.addEventListener("click", () => openSchedModal(Number(btn.dataset.sched)));
      });
    } catch (e) { /* sudah ditangani api() */ }
  }

  // ---------- modal penjadwalan ----------
  const schedBackdrop = document.getElementById("sched-backdrop");

  (function fillJamOptions() {
    const sel = document.getElementById("sc-jam");
    for (let m = 7 * 60; m <= 20 * 60; m += 30) {
      const o = document.createElement("option");
      o.value = o.textContent =
        String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
      sel.appendChild(o);
    }
  })();

  async function openSchedModal(regId) {
    schedRegId = regId;
    const msg = document.getElementById("sc-msg");
    msg.textContent = ""; msg.className = "form-msg";
    let kasus = {};
    try {
      const res = await api("/api/admin/registrations/" + regId);
      if (res.ok) kasus = await res.json();
    } catch (e) { /* tetap buka modal dengan konteks minim */ }

    document.getElementById("sc-kasus").textContent =
      `Kasus: ${kasus.nama || ""} (${kasus.nim || "-"}) - ${kasus.jenis_layanan || ""}`;
    const pr = kasus.prioritas_penjadwalan;
    document.getElementById("sc-urgensi").innerHTML =
      pr && pr.urgensi && pr.urgensi !== "normal"
        ? `<p class="sc-urgensi urg-${escapeHtml(pr.urgensi)}"><strong>Prioritas ${escapeHtml(String(pr.urgensi).toUpperCase())}:</strong> ${escapeHtml(pr.alasan || "")}</p>`
        : "";

    const sel = document.getElementById("sc-petugas");
    const assigned = kasus.followup && kasus.followup.petugas ? kasus.followup.petugas.id : "";
    sel.innerHTML = '<option value="">- Pilih konselor -</option>' +
      petugasList.filter((p) => p.aktif).map((p) =>
        `<option value="${p.id}">${escapeHtml(p.nama)} (${escapeHtml(p.peran)})</option>`).join("");
    sel.value = String(assigned);
    if (sel.value !== String(assigned)) sel.value = "";

    document.getElementById("sc-tanggal").value = wibTodayISO();
    document.getElementById("sc-jam").value = "09:00";
    document.getElementById("sc-durasi").value = "60";
    document.getElementById("sc-metode").value = "Tatap Muka";
    document.getElementById("sc-lokasi").value = "";
    document.getElementById("sc-catatan").value = "";
    schedBackdrop.classList.remove("hidden");
  }

  document.getElementById("sched-close").addEventListener("click", () =>
    schedBackdrop.classList.add("hidden"));
  schedBackdrop.addEventListener("click", (e) => {
    if (e.target === schedBackdrop) schedBackdrop.classList.add("hidden");
  });

  document.getElementById("sc-save").addEventListener("click", async () => {
    if (schedRegId === null) return;
    const msg = document.getElementById("sc-msg");
    const petugasId = document.getElementById("sc-petugas").value;
    const tanggal = document.getElementById("sc-tanggal").value;
    if (!petugasId) { setMsg(msg, "Pilih dulu konselor penanggung jawab.", "err"); return; }
    if (!tanggal) { setMsg(msg, "Pilih tanggal sesi.", "err"); return; }
    const body = {
      registration_id: schedRegId,
      petugas_id: Number(petugasId),
      tanggal,
      jam_mulai: document.getElementById("sc-jam").value,
      durasi_menit: Number(document.getElementById("sc-durasi").value),
      metode: document.getElementById("sc-metode").value,
      lokasi: document.getElementById("sc-lokasi").value.trim() || null,
      catatan: document.getElementById("sc-catatan").value.trim() || null,
    };
    setMsg(msg, "Menyimpan jadwal...", "info");
    try {
      const res = await api("/api/admin/schedule", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Gagal menyimpan jadwal.");
      }
      setMsg(msg, "Jadwal tersimpan dan tampil pada kalender mingguan.", "ok");
      loadWeek(); loadQueue(); loadList(); loadStats();
      setTimeout(() => schedBackdrop.classList.add("hidden"), 800);
    } catch (err) { setMsg(msg, "Gagal: " + err.message, "err"); }
  });

  // ---------- petugas penangani ----------
  async function loadPetugas() {
    const res = await api("/api/admin/petugas");
    if (!res.ok) return;
    const data = await res.json();
    petugasList = data.items || [];

    // opsi filter "Petugas penangani"
    const fSel = document.getElementById("f-petugas");
    const current = fSel.value;
    fSel.innerHTML = `
      <option value="">Semua penangan</option>
      <option value="tanpa">Belum ada penangani</option>
      ${petugasList.filter((p) => p.aktif).map((p) =>
        `<option value="${p.id}">${escapeHtml(p.nama)}</option>`).join("")}`;
    fSel.value = current;
    if (fSel.value !== current) fSel.value = "";

    // opsi filter konselor pada kalender mingguan
    const wkSel = document.getElementById("wk-petugas");
    const wkCurrent = wkSel.value;
    wkSel.innerHTML = '<option value="">Semua konselor</option>' +
      petugasList.filter((p) => p.aktif).map((p) =>
        `<option value="${p.id}">${escapeHtml(p.nama)}</option>`).join("");
    wkSel.value = wkCurrent;
    if (wkSel.value !== wkCurrent) wkSel.value = "";

    renderPetugasTable();
  }

  function renderPetugasTable() {
    const tbody = document.getElementById("petugas-tbody");
    tbody.innerHTML = petugasList.map((p) => `
      <tr>
        <td><strong>${escapeHtml(p.nama)}</strong></td>
        <td>${escapeHtml(p.peran)}</td>
        <td>${escapeHtml(p.kontak || "-")}</td>
        <td>${p.jumlah_kasus}</td>
        <td>${p.aktif
          ? '<span class="badge st-selesai">Aktif</span>'
          : '<span class="badge st-menunggu">Nonaktif</span>'}</td>
        <td>
          <button class="btn ghost small" data-act="toggle" data-id="${p.id}">${p.aktif ? "Nonaktifkan" : "Aktifkan"}</button>
          <button class="btn ghost small" data-act="rename" data-id="${p.id}">Ganti nama</button>
          <button class="btn danger small" data-act="delete" data-id="${p.id}">Hapus</button>
        </td>
      </tr>`).join("");
    document.getElementById("petugas-empty").classList.toggle("hidden", petugasList.length > 0);

    tbody.querySelectorAll("button[data-act]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = Number(btn.dataset.id);
        const p = petugasList.find((x) => x.id === id);
        if (!p) return;
        try {
          if (btn.dataset.act === "toggle") {
            const r = await api(`/api/admin/petugas/${id}`, {
              method: "PATCH", body: JSON.stringify({ aktif: !p.aktif }),
            });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
          } else if (btn.dataset.act === "rename") {
            const nama = prompt("Nama baru:", p.nama);
            if (!nama || nama.trim().length < 2) return;
            const r = await api(`/api/admin/petugas/${id}`, {
              method: "PATCH", body: JSON.stringify({ nama: nama.trim() }),
            });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
          } else if (btn.dataset.act === "delete") {
            if (!confirm(`Hapus petugas "${p.nama}"? Penugasan pada kasus akan dilepas (kasus tidak ikut terhapus).`)) return;
            const r = await api(`/api/admin/petugas/${id}`, { method: "DELETE" });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
          }
          await loadPetugas();
          loadList(); loadStats();
        } catch (err) { alert("Gagal: " + err.message); }
      });
    });
  }

  document.getElementById("p-add").addEventListener("click", async () => {
    const msg = document.getElementById("p-msg");
    const nama = document.getElementById("p-nama").value.trim();
    const peran = document.getElementById("p-peran").value.trim() || "Konselor";
    const kontak = document.getElementById("p-kontak").value.trim();
    if (nama.length < 2) {
      setMsg(msg, "Isi dulu nama petugas (minimal 2 huruf).", "err");
      return;
    }
    setMsg(msg, "Menyimpan...", "info");
    try {
      const r = await api("/api/admin/petugas", {
        method: "POST",
        body: JSON.stringify({ nama, peran, kontak: kontak || null }),
      });
      if (!r.ok) {
        let detail = "Gagal menambah petugas (kode " + r.status + ").";
        try { detail = (await r.json()).detail || detail; } catch (e) { /* biarkan default */ }
        throw new Error(detail);
      }
      document.getElementById("p-nama").value = "";
      document.getElementById("p-peran").value = "";
      document.getElementById("p-kontak").value = "";
      setMsg(msg, "Petugas ditambahkan.", "ok");
      await loadPetugas();
    } catch (err) { setMsg(msg, "Gagal: " + err.message, "err"); }
  });

  // ---------- manajemen akun admin ----------
  const ADMIN_BADGE = {
    aktif: '<span class="badge st-selesai">Aktif</span>',
    nonaktif: '<span class="badge st-menunggu">Nonaktif</span>',
    kedaluwarsa: '<span class="badge st-urgent">Kedaluwarsa</span>',
  };
  let adminList = [];
  let editingAdminId = null;

  async function loadAdmins() {
    try {
      const res = await api("/api/admin/admins");
      const data = await res.json();
      adminList = data.items || [];
      renderAdminsTable();
    } catch (e) { /* ditangani api() */ }
  }

  function fmtMasa(iso) {
    if (!iso) return "Selamanya";
    try {
      return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", {
        timeZone: "Asia/Jakarta", day: "numeric", month: "short", year: "numeric",
      });
    } catch (e) { return iso; }
  }

  function renderAdminsTable() {
    const tbody = document.getElementById("admins-tbody");
    tbody.innerHTML = adminList.map((u) => `
      <tr>
        <td><strong>${escapeHtml(u.username)}</strong></td>
        <td>${escapeHtml(u.nama_lengkap || "-")}</td>
        <td>${escapeHtml(u.nim || "-")}</td>
        <td>${escapeHtml(u.fakultas || "-")}</td>
        <td>${escapeHtml(u.no_whatsapp || '-')}</td>
        <td>${fmtMasa(u.masa_aktif_akhir)}</td>
        <td>${ADMIN_BADGE[u.status] || escapeHtml(u.status)}</td>
        <td>
          <button class="btn ghost small" data-act="toggle" data-id="${u.id}">${u.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
          <button class="btn ghost small" data-act="edit" data-id="${u.id}">Edit</button>
          <button class="btn ghost small" data-act="resetpw" data-id="${u.id}">Reset sandi</button>
          <button class="btn danger small" data-act="delete" data-id="${u.id}">Hapus</button>
        </td>
      </tr>`).join("");
    document.getElementById("admins-empty").classList.toggle("hidden", adminList.length > 0);

    tbody.querySelectorAll("button[data-act]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = Number(btn.dataset.id);
        const u = adminList.find((x) => x.id === id);
        if (!u) return;
        const msg = document.getElementById("a-msg");
        try {
          if (btn.dataset.act === "toggle") {
            const r = await api(`/api/admin/admins/${id}`, {
              method: "PUT", body: JSON.stringify({ is_active: !u.is_active }),
            });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
            setMsg(msg, u.is_active
              ? `Akun '${u.username}' dinonaktifkan (tidak bisa login).`
              : `Akun '${u.username}' diaktifkan.`, "ok");
          } else if (btn.dataset.act === "edit") {
            openAdminEdit(u);
            return;
          } else if (btn.dataset.act === "resetpw") {
            const pw = prompt(`Kata sandi baru untuk '${u.username}' (min. 8 karakter):`);
            if (pw === null) return;
            if (pw.length < 8) { setMsg(msg, "Kata sandi minimal 8 karakter.", "err"); return; }
            const r = await api(`/api/admin/admins/${id}/reset-password`, {
              method: "POST", body: JSON.stringify({ password_baru: pw }),
            });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
            setMsg(msg, (await r.json()).pesan || "Kata sandi direset.", "ok");
          } else if (btn.dataset.act === "delete") {
            if (!confirm(`Hapus permanen akun '${u.username}'? Tindakan ini tidak bisa dibatalkan.`)) return;
            const r = await api(`/api/admin/admins/${id}`, { method: "DELETE" });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
            setMsg(msg, `Akun '${u.username}' telah dihapus.`, "ok");
          }
          await loadAdmins();
        } catch (err) { setMsg(msg, "Gagal: " + err.message, "err"); }
      });
    });
  }

  document.getElementById("a-add").addEventListener("click", async () => {
    const msg = document.getElementById("a-msg");
    const val = (id) => document.getElementById(id).value.trim();
    const payload = {
      username: val("a-username"),
      password: document.getElementById("a-pass").value,
      nama_lengkap: val("a-nama"),
      nim: val("a-nim"),
      fakultas: val("a-fak"),
      no_whatsapp: val("a-wa"),
      masa_aktif_akhir: val("a-masa") || null,
    };
    if (payload.username.length < 3) { setMsg(msg, "Username minimal 3 karakter (huruf/angka/._-).", "err"); return; }
    if (payload.password.length < 8) { setMsg(msg, "Kata sandi awal minimal 8 karakter.", "err"); return; }
    if (payload.nama_lengkap.length < 2) { setMsg(msg, "Isi nama lengkap admin.", "err"); return; }
    if (!payload.nim) { setMsg(msg, "Isi NIM admin.", "err"); return; }
    if (payload.fakultas.length < 2) { setMsg(msg, "Isi fakultas admin.", "err"); return; }
    if (!/^[0-9+ -]{9,25}$/.test(payload.no_whatsapp)) {
      setMsg(msg, "Nomor WhatsApp tidak valid (contoh: 08123456789).", "err");
      return;
    }
    setMsg(msg, "Menyimpan akun baru...", "info");
    try {
      const r = await api("/api/admin/admins", {
        method: "POST", body: JSON.stringify(payload),
      });
      if (!r.ok) {
        let detail = "Gagal membuat akun (kode " + r.status + ").";
        try { detail = (await r.json()).detail || detail; } catch (e) { /* biarkan */ }
        throw new Error(detail);
      }
      ["a-username", "a-pass", "a-nama", "a-nim", "a-fak", "a-wa", "a-masa"]
        .forEach((id) => { document.getElementById(id).value = ""; });
      setMsg(msg, `Akun '${payload.username}' dibuat dan langsung aktif.`, "ok");
      await loadAdmins();
    } catch (err) { setMsg(msg, "Gagal: " + err.message, "err"); }
  });

  // ---------- modal edit akun admin ----------
  const editBackdrop = document.getElementById("admin-edit-backdrop");

  function openAdminEdit(u) {
    editingAdminId = u.id;
    document.getElementById("ae-username").textContent =
      "Akun: " + u.username + (u.is_active ? "" : " (saat ini nonaktif)");
    document.getElementById("ae-nama").value = u.nama_lengkap || "";
    document.getElementById("ae-nim").value = u.nim || "";
    document.getElementById("ae-fak").value = u.fakultas || "";
    document.getElementById("ae-wa").value = u.no_whatsapp || "";
    document.getElementById("ae-masa").value = u.masa_aktif_akhir || "";
    const msg = document.getElementById("ae-msg");
    msg.textContent = ""; msg.className = "form-msg";
    editBackdrop.classList.remove("hidden");
  }

  document.getElementById("admin-edit-close").addEventListener("click", () =>
    editBackdrop.classList.add("hidden"));
  editBackdrop.addEventListener("click", (e) => {
    if (e.target === editBackdrop) editBackdrop.classList.add("hidden");
  });

  document.getElementById("ae-save").addEventListener("click", async () => {
    if (editingAdminId === null) return;
    const msg = document.getElementById("ae-msg");
    const val = (id) => document.getElementById(id).value.trim();
    const body = {
      nama_lengkap: val("ae-nama"),
      nim: val("ae-nim"),
      fakultas: val("ae-fak"),
      no_whatsapp: val("ae-wa"),
      masa_aktif_akhir: val("ae-masa") || null, // kosong = hapus batas (selamanya)
    };
    if (body.nama_lengkap.length < 2) { setMsg(msg, "Nama lengkap minimal 2 huruf.", "err"); return; }
    if (!body.nim) { setMsg(msg, "NIM tidak boleh kosong.", "err"); return; }
    if (body.fakultas.length < 2) { setMsg(msg, "Fakultas tidak boleh kosong.", "err"); return; }
    setMsg(msg, "Menyimpan...", "info");
    try {
      const r = await api(`/api/admin/admins/${editingAdminId}`, {
        method: "PUT", body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error((await r.json()).detail || "Gagal menyimpan.");
      setMsg(msg, "Perubahan tersimpan.", "ok");
      setTimeout(() => editBackdrop.classList.add("hidden"), 700);
      await loadAdmins();
    } catch (err) { setMsg(msg, "Gagal: " + err.message, "err"); }
  });

  // ---------- daftar pendaftar ----------
  async function loadList() {
    const params = new URLSearchParams({
      page: String(page), per_page: "10",
      sort: document.getElementById("f-sort").value,
    });
    const search = document.getElementById("f-search").value.trim();
    if (search) params.set("search", search);
    const st = document.getElementById("f-status").value;
    if (st) params.set("status", st);
    const ln = document.getElementById("f-layanan").value;
    if (ln) params.set("jenis_layanan", ln);
    const from = document.getElementById("f-from").value;
    if (from) params.set("date_from", from);
    const to = document.getElementById("f-to").value;
    if (to) params.set("date_to", to);
    const pg = document.getElementById("f-petugas").value;
    if (pg === "tanpa") params.set("assigned", "tidak");
    else if (pg) { params.set("assigned", "ya"); params.set("petugas_id", pg); }

    const res = await api("/api/admin/registrations?" + params.toString());
    const data = await res.json();
    const tbody = document.getElementById("reg-tbody");
    tbody.innerHTML = "";
    document.getElementById("reg-empty").classList.toggle("hidden", data.items.length > 0);

    data.items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.className = "rowlink";
      const skor = item.sudah_skrining
        ? `<span class="score-chip" title="Depresi">${item.skor_depresi}</span>
           <span class="score-chip" title="Kecemasan">${item.skor_kecemasan}</span>
           <span class="score-chip" title="Stres">${item.skor_stres}</span>`
        : "-";
      tr.innerHTML = `
        <td><strong>${escapeHtml(item.nama)}</strong>${item.punya_keluhan ? ' <span title="Ada keluhan tertulis">&bull;</span>' : ""}</td>
        <td>${escapeHtml(item.nim)}</td>
        <td>${escapeHtml(item.jenis_layanan)}</td>
        <td>${escapeHtml(item.preferensi_hari)}, ${escapeHtml(item.preferensi_waktu)}</td>
        <td><span class="badge ${STATUS_CLASS[item.status] || ""}">${item.status_label}</span></td>
        <td>${item.petugas ? escapeHtml(item.petugas.nama) : '<span style="color:var(--muted);">-</span>'}</td>
        <td>${skor}</td>
        <td>${fmtDate(item.created_at)}</td>`;
      tr.addEventListener("click", () => openDetail(item.id));
      tbody.appendChild(tr);
    });

    const totalPages = Math.max(1, Math.ceil(data.total / data.per_page));
    document.getElementById("page-info").textContent =
      `Halaman ${data.page} dari ${totalPages} (${data.total} data)`;
  }

  document.getElementById("apply-btn").addEventListener("click", () => { page = 1; loadList(); });
  document.getElementById("prev-btn").addEventListener("click", () => { if (page > 1) { page--; loadList(); } });
  document.getElementById("next-btn").addEventListener("click", () => { page++; loadList(); });

  // ---------- detail ----------
  const backdrop = document.getElementById("detail-backdrop");
  const body = document.getElementById("detail-body");

  async function openDetail(id) {
    const res = await api("/api/admin/registrations/" + id);
    if (!res.ok) { alert("Gagal memuat detail."); return; }
    const d = await res.json();
    document.getElementById("detail-title").textContent = `Detail: ${d.nama} (${d.nim})`;
    body.innerHTML = renderDetail(d);
    bindFollowupForm(d);
    bindAssignForm(d);
    bindAnalysisForm(d);
    bindScheduleSection(d);
    backdrop.classList.remove("hidden");
  }

  const TINGKAT_CLASS = {
    rendah: "st-selesai",
    sedang: "st-jadwal",
    tinggi: "st-urgent",
  };
  const TINGKAT_LABEL = { rendah: "Rendah", sedang: "Sedang", tinggi: "Tinggi" };

  function renderDetail(d) {
    const dass = d.dass21 ? renderDass(d.dass21) : `<p class="sub">Belum mengisi skrining DASS-21.</p>`;
    const conv = d.conversations.length
      ? d.conversations.map(renderConversation).join("")
      : `<p class="sub">Belum ada percakapan.</p>`;
    const f = d.followup;
    return `
      <div class="kv-grid">
        <div><span class="k">Kontak:</span> ${escapeHtml(d.kontak)}</div>
        <div><span class="k">Layanan:</span> ${escapeHtml(d.jenis_layanan)}</div>
        <div><span class="k">Preferensi:</span> ${escapeHtml(d.preferensi_hari)}, ${escapeHtml(d.preferensi_waktu)} <em>(preferensi, bukan jadwal final)</em></div>
        <div><span class="k">Tanggal daftar:</span> ${fmtDate(d.created_at)}</div>
        <div><span class="k">Persetujuan data:</span> ${escapeHtml(d.consent_status)}</div>
      </div>

      <div class="detail-section">
        <h4>Keluhan mahasiswa</h4>
        ${d.keluhan ? `<p style="white-space:pre-wrap;">${escapeHtml(d.keluhan)}</p>` : `<p class="sub">Tidak diisi.</p>`}
      </div>

      <div class="detail-section"><h4>Skrining DASS-21</h4>${dass}</div>

      <div class="detail-section"><h4>Obrolan</h4>${conv}</div>

      <div class="detail-section">
        <h4>Jadwal konseling terkonfirmasi</h4>
        <p class="sub" style="margin-bottom:10px;">Sesi final yang sudah ditetapkan (beda dengan preferensi awal mahasiswa di atas).</p>
        ${renderJadwalList(d)}
        <button class="btn small" id="dj-add" style="margin-top:8px;">+ Tambah jadwal sesi</button>
      </div>

      <div class="detail-section">
        <h4>Analisis AI Terpadu (keluhan + DASS-21 + obrolan)</h4>
        <p class="sub" style="margin-bottom:10px;">Ringkasan otomatis dari ketiga sumber data kasus ini. Bukan diagnosis - keputusan tetap milik petugas.</p>
        <div id="ai-analysis-body"><p class="sub">Klik tombol di bawah untuk membuat analisis.</p></div>
        <button class="btn small" id="ai-analyze">Buat analisis AI</button>
        <p id="ai-msg" class="form-msg" role="status" aria-live="polite"></p>
      </div>

      <div class="detail-section">
        <h4>Tindak lanjut</h4>
        <div class="kv-grid" style="margin-bottom:12px;">
          <div><span class="k">Status:</span> <span class="badge ${STATUS_CLASS[f.status] || ""}">${f.status_label}</span></div>
          <div><span class="k">Petugas penangani:</span> ${f.petugas ? `<strong>${escapeHtml(f.petugas.nama)}</strong> <em>(${escapeHtml(f.petugas.peran)})</em>` : "-"}</div>
          <div><span class="k">Terakhir diperbarui:</span> ${f.assigned_admin ? escapeHtml(f.assigned_admin) : "-"} / ${fmtDate(f.updated_at)}</div>
        </div>
        <div class="field">
          <label for="fu-petugas">Tetapkan petugas penangani</label>
          <select id="fu-petugas">
            <option value="">- Belum ada penangani -</option>
            ${petugasList.filter((p) => p.aktif || (f.petugas && p.id === f.petugas.id)).map((p) =>
              `<option value="${p.id}" ${f.petugas && p.id === f.petugas.id ? "selected" : ""}>${escapeHtml(p.nama)} (${escapeHtml(p.peran)})</option>`).join("")}
          </select>
        </div>
        <button class="btn ghost small" id="fu-assign">Simpan penugasan</button>
        <p id="fu-assign-msg" class="form-msg" role="status" aria-live="polite"></p>
        <div class="field" style="margin-top:14px;">
          <label for="fu-status">Ubah status</label>
          <select id="fu-status">
            ${STATUS_ORDER.map((s) => `<option value="${s}" ${s === f.status ? "selected" : ""}>${STATUS_LABELS[s]}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label for="fu-catatan">Catatan petugas</label>
          <textarea id="fu-catatan" placeholder="Catatan tindak lanjut...">${f.catatan_petugas ? escapeHtml(f.catatan_petugas) : ""}</textarea>
        </div>
        <button class="btn small" id="fu-save">Simpan tindak lanjut</button>
        <p id="fu-msg" class="form-msg" role="status" aria-live="polite"></p>
      </div>

      <p class="note-disclaimer" style="margin-top:14px;">${escapeHtml(d.meta_akses)}</p>`;
  }

  function renderJadwalList(d) {
    const items = d.jadwal || [];
    if (!items.length) return `<p class="sub">Belum ada sesi terkonfirmasi. Gunakan tombol di bawah untuk menjadwalkan.</p>`;
    return `<div class="jadwal-list">${items.map((j) => `
      <div class="jadwal-row st-${escapeHtml(j.status)}">
        <div>
          <strong>${escapeHtml(j.hari)}, ${fmtTanggalID(j.tanggal)}</strong> -
          ${escapeHtml(j.jam_mulai)}-${escapeHtml(j.jam_selesai)} WIB
          <span class="badge ${JADWAL_BADGE_CLASS[j.status] || ""}">${JADWAL_STATUS_LABEL[j.status] || j.status}</span>
          ${j.followup_status === "perlu_ditinjau_segera" && j.status === "terjadwal" ? '<span class="badge st-urgent">Kasus darurat</span>' : ""}<br>
          <span class="sub">Konselor: ${j.petugas ? escapeHtml(j.petugas.nama) : "-"} - ${escapeHtml(j.metode)}${j.lokasi ? " - " + escapeHtml(j.lokasi) : ""}${j.catatan ? " - " + escapeHtml(j.catatan) : ""}</span>
        </div>
        <div class="jadwal-act">
          ${j.status === "terjadwal" || j.status === "ditunda" ? `
            <button class="btn ghost small" data-js="selesai" data-id="${j.id}">Tandai selesai</button>
            <button class="btn ghost small" data-js="batal" data-id="${j.id}">Batalkan</button>
            <button class="btn danger small" data-js="hapus" data-id="${j.id}">Hapus</button>`
          : `<button class="btn ghost small" data-js="aktif" data-id="${j.id}">Aktifkan kembali</button>`}
        </div>
      </div>`).join("")}</div>`;
  }

  function bindScheduleSection(d) {
    const addBtn = document.getElementById("dj-add");
    if (addBtn) addBtn.addEventListener("click", () => openSchedModal(d.id));
    document.querySelectorAll("#detail-body button[data-js]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = Number(btn.dataset.id);
        const act = btn.dataset.js;
        try {
          if (act === "hapus") {
            if (!confirm("Hapus permanen jadwal ini? Gunakan 'Batalkan' bila ingin tercatat.")) return;
            const r = await api(`/api/admin/schedule/${id}`, { method: "DELETE" });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
          } else {
            const status = act === "selesai" ? "selesai" : act === "batal" ? "dibatalkan" : "terjadwal";
            const r = await api(`/api/admin/schedule/${id}`, {
              method: "PATCH", body: JSON.stringify({ status }),
            });
            if (!r.ok) throw new Error((await r.json()).detail || "Gagal.");
          }
          await openDetail(d.id);
          loadWeek(); loadQueue(); loadList(); loadStats();
        } catch (err) { alert("Gagal: " + err.message); }
      });
    });
  }

  function renderDass(dass) {
    const s = dass.skor, k = dass.kategori_umum;
    const rows = Object.entries(dass.jawaban)
      .map(([no, v]) => `<tr><td>${no}</td><td>${v}</td></tr>`).join("");
    return `
      <div class="score-cards">
        <div class="sc"><div class="v">${s.depresi}</div><div class="l">Depresi - ${k.depresi}</div></div>
        <div class="sc"><div class="v">${s.kecemasan}</div><div class="l">Kecemasan - ${k.kecemasan}</div></div>
        <div class="sc"><div class="v">${s.stres}</div><div class="l">Stres - ${k.stres}</div></div>
      </div>
      <p class="note-disclaimer">
        ${escapeHtml(dass.catatan_kategori)}<br>
        Versi penilaian: ${escapeHtml(dass.scoring_version)} - Dikirim: ${fmtDate(dass.submitted_at)}
      </p>
      <details>
        <summary style="cursor:pointer;font-weight:600;color:var(--primary-dark);">Lihat 21 jawaban</summary>
        <table class="data" style="margin-top:8px;max-width:240px;">
          <thead><tr><th>No</th><th>Nilai (0-3)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>`;
  }

  function renderConversation(c) {
    const msgs = c.messages.map((m) => {
      const who = m.sender === "mahasiswa" ? "Mahasiswa" : m.sender === "bot" ? "Asisten" : "Sistem (audit)";
      return `<div class="msg-admin ${m.sender}">
                <strong>${who}</strong> <span style="color:var(--muted);font-size:0.78rem;">${fmtDate(m.created_at)}</span><br>
                ${escapeHtml(m.text)}
              </div>`;
    }).join("");
    return `<details style="margin-bottom:10px;">
              <summary style="cursor:pointer;font-weight:600;color:var(--primary-dark);">Sesi #${c.id} - mulai ${fmtDate(c.created_at)}</summary>
              <div style="margin-top:10px;">${msgs}</div>
            </details>`;
  }

  function bindAnalysisForm(d) {
    const msg = document.getElementById("ai-msg");
    document.getElementById("ai-analyze").addEventListener("click", async () => {
      setMsg(msg, "Menganalisis kasus (keluhan + DASS-21 + obrolan)...", "info");
      const btn = document.getElementById("ai-analyze");
      btn.disabled = true;
      try {
        const res = await api(`/api/admin/registrations/${d.id}/analysis`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Gagal membuat analisis.");
        }
        const data = await res.json();
        document.getElementById("ai-analysis-body").innerHTML = renderAnalysis(data);
        const src = data.analisis.sumber === "fallback"
          ? " (mode cadangan - penyedia LLM tidak merespons)"
          : "";
        setMsg(msg, `Analisis selesai (penyedia: ${data.penyedia}${src}).`, "ok");
      } catch (err) {
        setMsg(msg, "Gagal: " + err.message, "err");
      } finally {
        btn.disabled = false;
      }
    });
  }

  function renderAnalysis(data) {
    const a = data.analisis;
    const tingkat = TINGKAT_LABEL[a.tingkat_perhatian] || a.tingkat_perhatian;
    const tema = (a.tema || []).map((t) =>
      `<span class="badge st-jadwal" style="margin:2px 4px 2px 0;">${escapeHtml(String(t))}</span>`).join("");
    const saran = (a.saran_tindak_lanjut || []).map((s) => `<li>${escapeHtml(String(s))}</li>`).join("");
    return `
      <div class="kv-grid" style="margin-bottom:10px;">
        <div><span class="k">Tingkat perhatian:</span>
          <span class="badge ${TINGKAT_CLASS[a.tingkat_perhatian] || ""}">${escapeHtml(tingkat)}</span></div>
        <div><span class="k">Penyedia:</span> ${escapeHtml(String(data.penyedia))} &middot; ${fmtDate(data.dibuat_pada)}</div>
      </div>
      <p style="margin:0 0 8px;white-space:pre-wrap;">${escapeHtml(String(a.ringkasan || "-"))}</p>
      ${tema ? `<div style="margin-bottom:8px;">${tema}</div>` : ""}
      <div class="detail-section" style="margin:8px 0 10px;">
        <strong style="font-size:0.92rem;">Kaitan dengan DASS-21:</strong>
        <p style="margin:4px 0 0;white-space:pre-wrap;">${escapeHtml(String(a.kaitan_dass21 || "-"))}</p>
      </div>
      ${saran ? `<strong style="font-size:0.92rem;">Saran tindak lanjut:</strong><ol style="margin:4px 0 10px;padding-left:20px;">${saran}</ol>` : ""}
      <p class="note-disclaimer" style="margin:0;">${escapeHtml(data.disclaimer)}</p>`;
  }

  function bindFollowupForm(d) {
    const msg = document.getElementById("fu-msg");
    document.getElementById("fu-save").addEventListener("click", async () => {
      setMsg(msg, "Menyimpan...", "info");
      try {
        const res = await api(`/api/admin/registrations/${d.id}/followup`, {
          method: "PATCH",
          body: JSON.stringify({
            status: document.getElementById("fu-status").value,
            catatan_petugas: document.getElementById("fu-catatan").value || null,
          }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Gagal menyimpan.");
        }
        setMsg(msg, "Tindak lanjut berhasil disimpan.", "ok");
        loadList(); loadStats();
      } catch (err) {
        setMsg(msg, "Gagal: " + err.message, "err");
      }
    });
  }

  function bindAssignForm(d) {
    const msg = document.getElementById("fu-assign-msg");
    document.getElementById("fu-assign").addEventListener("click", async () => {
      setMsg(msg, "Menyimpan...", "info");
      const raw = document.getElementById("fu-petugas").value;
      try {
        const res = await api(`/api/admin/registrations/${d.id}/assign`, {
          method: "PUT",
          body: JSON.stringify({ petugas_id: raw ? Number(raw) : null }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Gagal menyimpan penugasan.");
        }
        setMsg(msg, raw ? "Penugasan tersimpan." : "Penugasan dilepas.", "ok");
        loadList(); loadStats(); loadPetugas();
      } catch (err) {
        setMsg(msg, "Gagal: " + err.message, "err");
      }
    });
  }

  document.getElementById("detail-close").addEventListener("click", () => backdrop.classList.add("hidden"));
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.classList.add("hidden"); });

  // ---------- ekspor ----------
  async function downloadExport(includeSensitive) {
    try {
      const res = await api(`/api/admin/export/registrations.csv?include_sensitive=${includeSensitive}`);
      if (!res.ok) { alert("Ekspor gagal."); return; }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = includeSensitive ? "registrations_sensitive.csv" : "registrations.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) { alert("Ekspor gagal: " + e.message); }
  }

  document.getElementById("export-basic").addEventListener("click", () => downloadExport(false));
  document.getElementById("export-sensitive").addEventListener("click", () =>
    document.getElementById("confirm-sensitive").classList.remove("hidden"));
  document.getElementById("export-no").addEventListener("click", () =>
    document.getElementById("confirm-sensitive").classList.add("hidden"));
  document.getElementById("export-yes").addEventListener("click", () => {
    document.getElementById("confirm-sensitive").classList.add("hidden");
    downloadExport(true);
  });

  loadStats();
  loadPetugas();
  loadAdmins();
  loadList();
  weekAnchor = wibTodayISO();
  loadWeek();
  loadQueue();
})();
