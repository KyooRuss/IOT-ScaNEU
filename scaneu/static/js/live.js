// Live Log: both camera cards, the recent activity table and the vehicle details window.
(() => {
  const S = window.ScaNEU;
  const { el } = S;
  const state = JSON.parse(document.getElementById("initial-state").textContent);

  const recent = new Map(state.recent.map((log) => [log.id, log]));  // newest first
  // Waiting vehicles may be older than the recent list; the pop-up's Review still needs them.
  const waiting = new Map(state.pending.map((log) => [log.id, log]));
  const reasons = new Map();  // log id -> latest reason text from a gate event
  const lastEvents = state.last_events;  // lane -> latest gate event
  for (const event of Object.values(lastEvents)) reasons.set(event.log.id, event.reason);

  const modalEl = document.getElementById("vehicle-modal");
  const modal = new bootstrap.Modal(modalEl);
  let modalLogId = null;

  // ---- camera cards -------------------------------------------------------

  function renderCamera(lane) {
    const view = document.querySelector(`[data-lane="${lane}"] [data-view]`);
    const event = lastEvents[lane];
    if (!event) {
      view.replaceChildren(el("div", { class: "camera-empty" },
        el("i", { class: "bi bi-camera-video" }), el("span", {}, "Waiting for a vehicle")));
      return;
    }
    const log = recent.get(event.log.id) || event.log;
    const path = lane === "exit" ? log.exit_image_path || log.entry_image_path : log.entry_image_path;
    const waiting = log.pending_lane === lane;
    view.replaceChildren(
      S.photo(log, path, "camera-photo"),
      el("div", { class: "camera-top" }, el("span", { class: "camera-chip" }, S.timeShort(event.at)), S.statusPill(log)),
      el("div", { class: "camera-bottom" },
        el("div", { class: "plate-overlay" }, "Detected Plate: ", el("strong", {}, S.formatPlate(log.plate_read) || "Unreadable")),
        waiting ? el("button", { class: "btn btn-review", type: "button", onclick: () => openModal(log.id) },
          el("i", { class: "bi bi-shield-exclamation" }), " Review") : null),
    );
  }

  function renderBarrier(lane, barrier) {
    const pill = document.querySelector(`[data-lane="${lane}"] [data-barrier]`);
    let cls = "neutral";
    let text = "Barrier closed";
    if (barrier.barrier === "open") [cls, text] = ["approved", "Barrier open"];
    else if (barrier.led === "red") [cls, text] = ["denied", "Stop · wait"];
    pill.className = `status-pill status-${cls} ms-auto`;
    pill.replaceChildren(el("span", { class: "dot" }), text);
    if (barrier.vehicle_present) pill.append(el("i", { class: "bi bi-car-front-fill ms-1", title: "Vehicle under barrier" }));
  }

  // ---- recent activity ----------------------------------------------------

  function renderRecent(flashId) {
    const rows = [...recent.values()].slice(0, 10).map((log) =>
      el("tr", { class: [log.pending_lane ? "is-pending" : "", log.id === flashId ? "flash" : ""].join(" ").trim() || null },
        el("td", { class: "thumb-col" }, S.photo(log, log.entry_image_path || log.exit_image_path, "thumb")),
        el("td", { class: "text-nowrap" }, S.timeShort(log.last_activity)),
        el("td", { class: "plate-cell" }, S.formatPlate(log.plate_read) || "—"),
        el("td", { class: "text-muted-2" }, S.vehicleText(log)),
        el("td", {}, S.typeLabel(log)),
        el("td", {}, el("button", { class: "btn btn-view", type: "button", onclick: () => openModal(log.id) }, "View")),
      ));
    if (!rows.length) {
      rows.push(el("tr", {}, el("td", { colspan: 6, class: "text-center text-muted-2 py-4" }, "No activity yet.")));
    }
    document.getElementById("recent").replaceChildren(...rows);
  }

  // ---- vehicle details window ---------------------------------------------

  function renderModal() {
    const log = recent.get(modalLogId) || waiting.get(modalLogId);
    if (!log) return;
    const body = modalEl.querySelector("[data-modal-body]");
    const actions = modalEl.querySelector("[data-modal-actions]");

    body.replaceChildren(S.vehicleDetails(log, {
      note: reasons.get(log.id),
      rows: [S.detail("Waiting at", log.pending_lane ? (log.pending_lane === "exit" ? "Exit lane" : "Entrance lane") : "—")],
    }));

    if (!log.pending_lane) {
      actions.replaceChildren(el("button", { class: "btn btn-light", type: "button", "data-bs-dismiss": "modal" }, "Close"));
      return;
    }
    const error = el("span", { class: "text-danger small me-auto", role: "alert" });
    const buttons = [
      el("button", { class: "btn btn-outline-danger", type: "button", onclick: () => act("deny") },
        el("i", { class: "bi bi-x-lg" }), log.pending_lane === "exit" ? " Keep closed" : " Deny"),
      el("button", { class: "btn btn-success", type: "button", onclick: () => act("open") },
        el("i", { class: "bi bi-unlock" }), " Open barrier"),
    ];
    actions.replaceChildren(error, ...buttons);

    function act(action) {
      buttons.forEach((b) => (b.disabled = true));
      error.textContent = "";
      S.decide(log.id, action)
        .then(() => modal.hide())
        .catch((err) => {
          error.textContent = err.message;
          buttons.forEach((b) => (b.disabled = false));
        });
    }
  }

  function openModal(logId) {
    if (!recent.has(logId) && !waiting.has(logId)) return;
    modalLogId = logId;
    renderModal();
    modal.show();
  }
  modalEl.addEventListener("hidden.bs.modal", () => (modalLogId = null));
  S.hooks.review = openModal;

  // ---- live updates -------------------------------------------------------

  let connectedBefore = false;
  S.socket.on("connect", () => {
    // After a reconnect the page may have missed events; reload to resync.
    if (connectedBefore) window.location.reload();
    connectedBefore = true;
  });

  S.socket.on("gate_event", (event) => {
    const { log } = event;
    reasons.set(log.id, event.reason);
    lastEvents[event.lane] = event;
    if (log.pending_lane) waiting.set(log.id, log);
    else waiting.delete(log.id);
    recent.delete(log.id);
    const rest = [...recent];
    recent.clear();
    recent.set(log.id, log);
    rest.forEach(([id, item]) => recent.set(id, item));

    renderCamera(event.lane);
    // The other lane may show the same vehicle (e.g. its entry); refresh it too.
    for (const lane of Object.keys(lastEvents)) if (lane !== event.lane) renderCamera(lane);
    renderRecent(log.id);
    if (modalLogId === log.id) renderModal();
  });

  S.socket.on("barrier", (barrier) => renderBarrier(barrier.lane, barrier));

  for (const [lane, barrier] of Object.entries(state.barriers)) {
    renderBarrier(lane, barrier);
    renderCamera(lane);
  }
  renderRecent();

  // Arrived from another page's pop-up: /guard?review=<log id>
  const reviewId = Number(new URLSearchParams(window.location.search).get("review"));
  if (reviewId) {
    history.replaceState(null, "", window.location.pathname);
    openModal(reviewId);
  }
})();
