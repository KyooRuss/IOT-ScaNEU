// Helpers shared by every dashboard page: DOM building, labels, the live socket,
// the header clock and the sidebar Alerts badge.
window.ScaNEU = (() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const FLAG_LABELS = JSON.parse(document.getElementById("flag-labels").textContent);

  // el("span", {class: "chip"}, "text", childNode, ...) - builds DOM without innerHTML,
  // so plates and names from the database are never interpreted as HTML.
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : String(child));
    }
    return node;
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  // ---- labels -------------------------------------------------------------

  function status(log) {
    if (log.pending_lane) return { label: "Pending", cls: "pending" };
    if (log.access_result === "Denied") return { label: "Denied", cls: "denied" };
    if (log.access_result === "Pending") return { label: "Pending", cls: "pending" };
    return { label: "Approved", cls: "approved" };
  }

  function statusPill(log) {
    const s = status(log);
    return el("span", { class: `status-pill status-${s.cls}` }, el("span", { class: "dot" }), s.label);
  }

  function ownerType(log) {
    if (log.owner_type === "NEU") return { label: "NEU Card Holder", cls: "neu" };
    if (log.owner_type === "Non-NEU") {
      return log.flags.includes("first_visit")
        ? { label: "First-time Visitor", cls: "first" }
        : { label: "Returning Visitor", cls: "returning" };
    }
    return { label: "Unknown", cls: "unknown" };
  }

  function typeLabel(log) {
    const t = ownerType(log);
    return el("span", { class: `type-label type-${t.cls}` }, el("span", { class: "dot" }), t.label);
  }

  function vehicleText(log) {
    if (!log.vehicle_type && !log.vehicle_color) return "—";
    return log.vehicle_color ? `${log.vehicle_type || "Vehicle"} (${log.vehicle_color})` : log.vehicle_type;
  }

  function vehicleIcon(type) {
    const t = (type || "").toLowerCase();
    if (t.includes("motor")) return "bi-scooter";
    if (t.includes("truck") || t.includes("van")) return "bi-truck";
    if (t.includes("bus")) return "bi-bus-front";
    return "bi-car-front-fill";
  }

  function imageUrl(path) {
    return path ? `/images/${path.split("/").map(encodeURIComponent).join("/")}` : null;
  }

  // Photo if the camera saved one, otherwise an icon for the vehicle type.
  function photo(log, path, cls) {
    const url = imageUrl(path);
    if (url) return el("img", { class: cls, src: url, alt: `Vehicle ${log.plate_read || ""}` });
    return el("span", { class: `${cls} photo-placeholder`, "aria-hidden": "true" }, el("i", { class: `bi ${vehicleIcon(log.vehicle_type)}` }));
  }

  // "returning" / "first_visit" are already shown by typeLabel, so no chip for them.
  const TYPE_FLAGS = ["returning", "first_visit"];

  function flagChips(flags) {
    return flags.filter((f) => !TYPE_FLAGS.includes(f)).map((f) => el("span", { class: "chip chip-flag" }, FLAG_LABELS[f] || f));
  }

  // Stored plates have no spaces ("ABC1234"); show them the way they are printed ("ABC 1234").
  function formatPlate(plate) {
    const m = /^([A-Z]+)(\d+)$/.exec(plate || "");
    return m ? `${m[1]} ${m[2]}` : plate;
  }

  const timeShort = (stamp) => (stamp ? stamp.slice(11, 16) : "—");

  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h ? `${h}h ${m}m` : `${m}m`;
  }

  // ---- live socket ----------------------------------------------------------

  const socket = io();
  const connPill = document.querySelector("[data-conn]");
  const connDot = document.querySelector("[data-conn-dot]");

  function setConnection(online) {
    connPill.textContent = online ? "Live" : "Offline";
    connPill.classList.toggle("is-online", online);
    connDot.classList.toggle("is-online", online);
  }
  socket.on("connect", () => setConnection(true));
  socket.on("disconnect", () => setConnection(false));

  // Sidebar badges: "pending" (vehicles waiting) and "alert" (alerts to review).
  function setCount(kind, count) {
    document.querySelectorAll(`[data-count="${kind}"]`).forEach((badge) => {
      badge.textContent = count;
      badge.hidden = !count;
    });
  }
  socket.on("alert_update", (update) => setCount("alert", update.alert_count));

  // ---- waiting-vehicle pop-up + beep ------------------------------------------

  // Pages can take over the pop-up's Review button (Live Log opens its window directly).
  const hooks = { review: null };
  const toastBox = document.getElementById("toasts");
  const toasts = new Map();  // log id -> bootstrap.Toast

  // Browsers only allow sound after the user has interacted with the page once.
  let audio = null;
  document.addEventListener("pointerdown", () => {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === "suspended") audio.resume();
  }, { once: true });

  function beep() {
    if (!audio || audio.state !== "running") return;
    [[880, 0], [660, 0.18]].forEach(([freq, start]) => {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.15, audio.currentTime + start);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + start + 0.16);
      osc.connect(gain).connect(audio.destination);
      osc.start(audio.currentTime + start);
      osc.stop(audio.currentTime + start + 0.17);
    });
  }

  function review(logId) {
    if (hooks.review) hooks.review(logId);
    else window.location.href = `${toastBox.dataset.liveUrl}?review=${logId}`;
  }

  function showWaiting(log) {
    if (toasts.has(log.id)) return;
    const lane = log.pending_lane === "exit" ? "Exit" : "Entrance";
    const node = el("div", { class: "toast waiting-toast", role: "alert", "aria-live": "assertive", "aria-atomic": "true" },
      el("div", { class: "toast-body" },
        el("i", { class: "bi bi-exclamation-triangle-fill toast-icon" }),
        el("div", { class: "flex-grow-1" },
          el("div", { class: "fw-semibold" }, `${formatPlate(log.plate_read) || "Unreadable plate"} is waiting`),
          el("div", { class: "small text-muted-2" }, `${lane} lane · ${ownerType(log).label}`)),
        el("button", { class: "btn btn-review btn-sm", type: "button", onclick: () => { review(log.id); toast.hide(); } }, "Review"),
        el("button", { class: "btn-close", type: "button", "data-bs-dismiss": "toast", "aria-label": "Close" })));
    toastBox.append(node);
    const toast = new bootstrap.Toast(node, { autohide: false });
    node.addEventListener("hidden.bs.toast", () => { toasts.delete(log.id); node.remove(); });
    toasts.set(log.id, toast);
    toast.show();
    beep();
  }

  socket.on("gate_event", (event) => {
    setCount("pending", event.pending_count);
    setCount("alert", event.alert_count);
    const { log } = event;
    if (log.pending_lane) showWaiting(log);
    else if (toasts.has(log.id)) toasts.get(log.id).hide();  // decided, maybe by another guard
  });

  // Guard's Open / Deny. Resolves on success, rejects with a message to show.
  function decide(logId, action) {
    return new Promise((resolve, reject) => {
      socket.timeout(5000).emit("guard_decision", { log_id: logId, action }, (err, ack) => {
        if (err) reject(new Error("No response from the server."));
        else if (!ack.ok) reject(new Error(ack.error));
        else resolve();
      });
    });
  }

  // ---- header clock ---------------------------------------------------------

  const clockDate = document.querySelector("[data-clock-date]");
  const clockTime = document.querySelector("[data-clock-time]");
  function tick() {
    const now = new Date();
    clockDate.textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    clockTime.textContent = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  tick();
  setInterval(tick, 10000);

  return {
    el, postJSON, socket, decide, hooks, FLAG_LABELS,
    status, statusPill, ownerType, typeLabel, vehicleText, vehicleIcon, photo, flagChips, formatPlate, timeShort, duration,
  };
})();
