// Alerts: a notification feed of finished records the guard should check.
// Open / Deny lives on Live Log only.
(() => {
  const S = window.ScaNEU;
  const { el } = S;
  const state = JSON.parse(document.getElementById("initial-state").textContent);
  const LABELS = JSON.parse(document.getElementById("alert-labels").textContent);
  const showingReviewed = state.reviewed;
  const items = new Map(state.alerts.map((log) => [log.id, log]));  // newest first
  const reviewAll = document.getElementById("review-all");

  // Icon and color per alert reason; the first reason decides the row's icon.
  const ICONS = {
    plate_unreadable: ["bi-eye-slash", "warn"],
    exit_only: ["bi-box-arrow-right", "info"],
    card_expired: ["bi-calendar-x", "warn"],
    card_blocked: ["bi-slash-circle", "bad"],
    denied: ["bi-x-octagon", "bad"],
  };

  const belongs = (log) => log.alert_reasons.length > 0 && Boolean(log.reviewed_at) === showingReviewed;

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

  function markReviewed(log, button) {
    button.disabled = true;
    S.postJSON(`/alerts/${log.id}/review`, {}).catch((err) => {
      button.disabled = false;
      button.title = err.message;
    });
  }

  function row(log, flash) {
    const [icon, tone] = ICONS[log.alert_reasons[0]] || ["bi-bell", "info"];
    const lane = log.flags.includes("exit_only") ? "Exit" : "Entrance";
    const title = log.alert_reasons.map((r) => LABELS[r] || r).join(" · ");
    const vehicle = S.vehicleText(log) !== "—" ? S.vehicleText(log) : null;

    const side = el("div", { class: "notif-side" },
      el("span", { class: "notif-time", title: log.last_activity || "" }, timeAgo(log.last_activity)));
    if (!showingReviewed) {
      const button = el("button", {
        class: "btn notif-check", type: "button", title: "Mark as reviewed", "aria-label": `Mark ${title} for ${log.plate_read || "vehicle"} as reviewed`,
        onclick: () => markReviewed(log, button),
      }, el("i", { class: "bi bi-check2" }));
      side.append(button);
    }

    return el("li", { class: `notif${showingReviewed ? "" : " is-unread"}${flash ? " flash" : ""}` },
      el("span", { class: `notif-icon tone-${tone}`, "aria-hidden": "true" }, el("i", { class: `bi ${icon}` })),
      el("div", { class: "notif-body" },
        el("div", { class: "notif-title" }, title),
        el("div", { class: "notif-meta" },
          el("strong", { class: "notif-plate" }, S.formatPlate(log.plate_read) || "Unreadable plate"),
          [`${lane} lane`, S.ownerType(log).label, vehicle].filter(Boolean).map((part) => ` · ${part}`).join(""))),
      side,
    );
  }

  function render(flashId) {
    document.getElementById("alerts").replaceChildren(...[...items.values()].map((log) => row(log, log.id === flashId)));
    document.getElementById("alerts-empty").hidden = items.size > 0;
    if (reviewAll) reviewAll.hidden = items.size === 0;
  }

  function update(log) {
    const had = items.has(log.id);
    items.delete(log.id);
    if (belongs(log)) {
      const rest = [...items];
      items.clear();
      items.set(log.id, log);
      rest.forEach(([id, other]) => items.set(id, other));
    }
    if (had || items.has(log.id)) render(had ? null : log.id);
  }

  if (reviewAll) {
    reviewAll.addEventListener("click", () => {
      reviewAll.disabled = true;
      S.postJSON("/alerts/review-all", {}).finally(() => (reviewAll.disabled = false));
    });
  }

  S.socket.on("gate_event", (event) => update(event.log));
  S.socket.on("alert_update", (event) => {
    if (event.log) update(event.log);
    else if (event.all_reviewed) {
      if (showingReviewed) window.location.reload();  // fetch the newly reviewed items
      else { items.clear(); render(); }
    }
  });

  render();
  setInterval(render, 60000);  // keep "5 min ago" current
})();
