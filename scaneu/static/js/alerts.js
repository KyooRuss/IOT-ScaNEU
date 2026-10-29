// Alerts: a notification feed of finished records the guard should check.
// Click one for its photo and details. Open / Deny lives on Live Log only.
(() => {
  const S = window.ScaNEU;
  const { el } = S;
  const state = JSON.parse(document.getElementById("initial-state").textContent);
  const LABELS = JSON.parse(document.getElementById("alert-labels").textContent);
  const showingReviewed = state.reviewed;
  const reason = state.reason;  // the filter, or null for all reasons
  const items = new Map(state.alerts.map((log) => [log.id, log]));
  const fresh = new Set();  // ids that arrived after the page opened
  const restored = new Set();  // ids this page moved back with Undo: not "new"
  let hasMore = state.has_more;
  let counts = state.counts;
  const reviewAll = document.getElementById("review-all");

  // Most serious first: a row's icon and color come from its most serious reason.
  const ICONS = {
    card_blocked: ["bi-slash-circle", "bad"],
    denied: ["bi-x-octagon", "bad"],
    card_expired: ["bi-calendar-x", "warn"],
    exit_only: ["bi-box-arrow-right", "info"],
    plate_unreadable: ["bi-eye-slash", "warn"],
  };
  const DECISIONS = { Granted: "Opened automatically", "Granted by guard": "Opened by guard", Denied: "Denied by guard" };

  const belongs = (log) => log.alert_reasons.length > 0 && Boolean(log.reviewed_at) === showingReviewed
    && (!reason || log.alert_reasons.includes(reason));
  const titleOf = (log) => log.alert_reasons.map((r) => LABELS[r] || r).join(" · ");
  const laneOf = (log) => (log.flags.includes("exit_only") ? "Exit" : "Entrance");
  const plateOf = (log) => S.formatPlate(log.plate_read) || "Unreadable plate";
  const listUrl = (path, params = {}) => `${path}?${new URLSearchParams({
    ...(showingReviewed && { show: "reviewed" }), ...(reason && { reason }), ...params,
  })}`;

  // "Just now", "5 min ago", "2 h ago", "Yesterday 10:46", "Oct 26 10:46"
  function timeAgo(stamp) {
    if (!stamp) return "—";
    const then = new Date(stamp.replace(" ", "T"));
    const minutes = Math.floor((Date.now() - then) / 60000);
    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes} min ago`;
    if (minutes < 12 * 60) return `${Math.floor(minutes / 60)} h ago`;
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const time = stamp.slice(11, 16);
    if (then.toDateString() === new Date().toDateString()) return `Today ${time}`;
    if (then.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
    return `${then.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${time}`;
  }
  const reviewedAgo = (stamp) => `Reviewed ${timeAgo(stamp).replace(/^(Just|Today|Yesterday)/, (w) => w.toLowerCase())}`;
  const AGO = { visit: timeAgo, reviewed: reviewedAgo };

  // Same order as the server: on Reviewed, latest review first; then latest activity.
  const cmp = (a, b) => ((a || "") < (b || "") ? -1 : (a || "") > (b || "") ? 1 : 0);
  const newestFirst = (a, b) =>
    (showingReviewed && cmp(b.reviewed_at, a.reviewed_at)) || cmp(b.last_activity, a.last_activity) || b.id - a.id;

  // ---- review / undo --------------------------------------------------------

  const toastBox = document.getElementById("notices");

  function undoToast(log) {
    const text = el("div", { class: "flex-grow-1" }, `${plateOf(log)} marked as reviewed`);
    const undo = el("button", { class: "btn btn-link btn-sm p-0 fw-semibold", type: "button" }, "Undo");
    const node = el("div", { class: "toast notice-toast", role: "status", "aria-atomic": "true" },
      el("div", { class: "toast-body" },
        el("i", { class: "bi bi-check2-circle toast-icon" }), text, undo,
        el("button", { class: "btn-close", type: "button", "data-bs-dismiss": "toast", "aria-label": "Close" })));
    toastBox.append(node);
    const toast = new bootstrap.Toast(node, { delay: 8000 });
    node.addEventListener("hidden.bs.toast", () => node.remove());
    undo.addEventListener("click", () => {
      undo.disabled = true;
      unreview(log).then(() => toast.hide()).catch((err) => (text.textContent = err.message));
    });
    toast.show();
  }

  // body: {} or {plate: "..."} when the guard typed an unreadable plate.
  function review(log, body) {
    return S.postJSON(`/alerts/${log.id}/review`, body).then((data) => undoToast(data.log));
  }

  function unreview(log) {
    restored.add(log.id);
    return S.postJSON(`/alerts/${log.id}/unreview`, {}).catch((err) => {
      restored.delete(log.id);
      throw err;
    });
  }

  function markReviewed(log, button) {
    button.disabled = true;
    review(log, {}).catch((err) => {
      button.disabled = false;
      button.title = err.message;
    });
  }

  // ---- list -----------------------------------------------------------------

  function row(log, flash) {
    const worst = Object.keys(ICONS).find((r) => log.alert_reasons.includes(r));
    const [icon, tone] = ICONS[worst] || ["bi-bell", "info"];
    const title = titleOf(log);
    const source = S.plateSource(log);
    const vehicle = S.vehicleText(log) !== "—" ? S.vehicleText(log) : null;

    const times = el("div", { class: "notif-times" },
      el("span", { class: "notif-time", title: log.last_activity || "", "data-ago": "visit", "data-stamp": log.last_activity || "" },
        timeAgo(log.last_activity)),
      showingReviewed
        ? el("span", { class: "notif-reviewed", title: log.reviewed_at, "data-ago": "reviewed", "data-stamp": log.reviewed_at },
          reviewedAgo(log.reviewed_at))
        : null);
    const side = el("div", { class: "notif-side" }, times);
    if (!showingReviewed) {
      const button = el("button", {
        class: "btn notif-check", type: "button", title: "Mark as reviewed", "aria-label": `Mark ${title} for ${plateOf(log)} as reviewed`,
        onclick: () => markReviewed(log, button),
      }, el("i", { class: "bi bi-check2" }));
      side.append(button);
    }

    return el("li", { class: ["notif", fresh.has(log.id) && "is-new", flash && "flash"].filter(Boolean).join(" ") },
      el("span", { class: `notif-icon tone-${tone}`, "aria-hidden": "true" }, el("i", { class: `bi ${icon}` })),
      el("div", { class: "notif-body" },
        el("button", { class: "notif-open notif-title", type: "button", onclick: () => openModal(log) }, title),
        el("div", { class: "notif-meta" },
          el("strong", { class: "notif-plate" }, plateOf(log)),
          source ? ` (${source})` : null,
          [`${laneOf(log)} lane`, log.holder_name || S.ownerType(log).label, vehicle].filter(Boolean).map((part) => ` · ${part}`).join(""))),
      side,
    );
  }

  function render(flashId) {
    const list = [...items.values()].sort(newestFirst);
    document.getElementById("alerts").replaceChildren(...list.map((log) => row(log, log.id === flashId)));
    document.getElementById("alerts-empty").hidden = items.size > 0 || hasMore;
    document.getElementById("load-more-wrap").hidden = !hasMore;
    if (reviewAll) reviewAll.hidden = items.size === 0 && !hasMore;
  }

  // Refresh "5 min ago" without rebuilding the list, so keyboard focus stays put.
  function tickTimes() {
    document.querySelectorAll("#alerts [data-ago]").forEach((span) => {
      span.textContent = AGO[span.dataset.ago](span.dataset.stamp);
    });
  }

  function update(log) {
    const had = items.has(log.id);
    if (belongs(log)) items.set(log.id, log);
    else {
      items.delete(log.id);
      fresh.delete(log.id);
    }
    const added = !had && items.has(log.id);
    if (added && !showingReviewed && !restored.delete(log.id)) fresh.add(log.id);
    if (modalLog && modalLog.id === log.id) {
      modalLog = log;
      renderModal();
    }
    if (had || added) render(added ? log.id : null);
  }

  const loadMore = document.getElementById("load-more");
  loadMore.addEventListener("click", () => {
    loadMore.disabled = true;
    fetch(listUrl("/alerts/more", { offset: items.size }))
      .then((res) => res.json())
      .then((page) => {
        page.alerts.forEach((log) => items.has(log.id) || items.set(log.id, log));
        hasMore = page.has_more;
        render();
      })
      .catch(() => {})
      .finally(() => (loadMore.disabled = false));
  });

  // ---- filter counts --------------------------------------------------------

  function renderCounts() {
    document.querySelectorAll("[data-reason-count]").forEach((badge) => {
      const count = counts[badge.dataset.reasonCount] || 0;
      badge.textContent = count;
      badge.parentElement.classList.toggle("is-empty", count === 0);
    });
  }

  let countsTimer = null;
  function refreshCounts() {
    clearTimeout(countsTimer);
    countsTimer = setTimeout(() => {
      fetch(listUrl("/alerts/counts"))
        .then((res) => res.json())
        .then((data) => {
          counts = data;
          renderCounts();
        })
        .catch(() => {});
    }, 300);
  }

  // ---- details window -------------------------------------------------------

  const modalEl = document.getElementById("vehicle-modal");
  const modal = new bootstrap.Modal(modalEl);
  let modalLog = null;

  function openModal(log) {
    modalLog = log;
    renderModal();
    modal.show();
  }
  modalEl.addEventListener("hidden.bs.modal", () => (modalLog = null));

  function renderModal() {
    const log = modalLog;
    const body = modalEl.querySelector("[data-modal-body]");
    const actions = modalEl.querySelector("[data-modal-actions]");
    modalEl.querySelector(".modal-title").textContent = titleOf(log);

    const plateInput = !log.reviewed_at && log.flags.includes("plate_unreadable")
      ? el("input", {
        class: "form-control plate-input", id: "plate-fix", value: S.formatPlate(log.plate_read) || "",
        maxlength: 12, autocomplete: "off", spellcheck: "false", placeholder: "e.g. ABC 1234", "aria-describedby": "plate-fix-help",
      })
      : null;
    body.replaceChildren(S.vehicleDetails(log, {
      rows: [
        S.detail("Lane", `${laneOf(log)} lane`),
        S.detail("Decision", DECISIONS[log.access_result] || log.access_result),
        log.reviewed_at ? S.detail("Reviewed", log.reviewed_at) : null,
      ],
      extra: plateInput && el("div", { class: "mt-3" },
        el("label", { class: "detail-label mb-1", for: "plate-fix" }, "Plate number"),
        plateInput,
        el("div", { class: "form-text", id: "plate-fix-help" },
          "The camera couldn't read this plate. Check the photo and fix the plate if it's wrong or missing.")),
    }));

    const error = el("span", { class: "text-danger small me-auto", role: "alert" });
    const close = el("button", { class: "btn btn-light", type: "button", "data-bs-dismiss": "modal" }, "Close");

    if (log.reviewed_at) {
      const back = el("button", { class: "btn btn-outline-secondary", type: "button" },
        el("i", { class: "bi bi-arrow-counterclockwise" }), " Move back to To review");
      back.addEventListener("click", () => {
        back.disabled = true;
        unreview(log).then(() => modal.hide()).catch((err) => {
          error.textContent = err.message;
          back.disabled = false;
        });
      });
      actions.replaceChildren(error, close, back);
      return;
    }

    const done = el("button", { class: "btn btn-neu", type: "button" }, el("i", { class: "bi bi-check2" }), " Mark as reviewed");
    function submit() {
      const changes = {};
      if (plateInput) {
        const typed = plateInput.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
        if (plateInput.value.trim() && !typed) {
          error.textContent = "Type the plate as letters and numbers, e.g. ABC 1234.";
          return;
        }
        if (typed && typed !== (log.plate_read || "")) changes.plate = plateInput.value;
      }
      done.disabled = true;
      error.textContent = "";
      review(log, changes).then(() => modal.hide()).catch((err) => {
        error.textContent = err.message;
        done.disabled = false;
      });
    }
    done.addEventListener("click", submit);
    if (plateInput) plateInput.addEventListener("keydown", (e) => e.key === "Enter" && submit());
    actions.replaceChildren(error, close, done);
  }

  // ---- mark all -------------------------------------------------------------

  if (reviewAll) {
    const confirmEl = document.getElementById("review-all-modal");
    const confirmModal = new bootstrap.Modal(confirmEl);
    const text = confirmEl.querySelector("[data-review-all-text]");
    const error = confirmEl.querySelector("[data-review-all-error]");
    const go = document.getElementById("review-all-confirm");

    reviewAll.addEventListener("click", () => {
      const count = counts[reason || "all"];
      const what = reason ? `“${LABELS[reason]}” alert` : "alert";
      text.textContent = `${count} ${what}${count === 1 ? "" : "s"} will move to Reviewed. You can move one back from its details.`;
      error.textContent = "";
      go.disabled = false;
      confirmModal.show();
    });
    go.addEventListener("click", () => {
      go.disabled = true;
      S.postJSON("/alerts/review-all", reason ? { reason } : {})
        .then(() => confirmModal.hide())
        .catch((err) => {
          error.textContent = err.message;
          go.disabled = false;
        });
    });
  }

  // ---- live updates ---------------------------------------------------------

  let connectedBefore = false;
  S.socket.on("connect", () => {
    // After a reconnect the page may have missed alerts; reload to resync.
    if (connectedBefore) window.location.reload();
    connectedBefore = true;
  });

  S.socket.on("gate_event", (event) => {
    update(event.log);
    if (event.log.alert_reasons.length) refreshCounts();
  });
  S.socket.on("alert_update", (event) => {
    if (event.log) update(event.log);
    else if (showingReviewed) window.location.reload();  // fetch the newly reviewed items
    else {
      event.reviewed_ids.forEach((id) => {
        items.delete(id);
        fresh.delete(id);
      });
      render();
    }
    refreshCounts();
  });

  render();
  setInterval(tickTimes, 60000);  // keep "5 min ago" current
})();
