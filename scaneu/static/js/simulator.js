// Gate simulator: sends fake vehicles to the gate and draws each lane's barrier, LEDs and buzzer.
(() => {
  const { el, postJSON } = window.ScaNEU;
  const form = document.getElementById("sim-form");
  const result = document.getElementById("sim-result");
  const plateInput = document.getElementById("plate");
  const unreadable = document.getElementById("plate_unreadable");

  unreadable.addEventListener("change", () => (plateInput.disabled = unreadable.checked));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    try {
      const res = await postJSON("/dev/simulator/vehicle", {
        lane: data.get("lane"),
        rfid_uid: data.get("rfid_uid"),
        plate: plateInput.value,
        plate_unreadable: unreadable.checked,
      });
      const d = res.decision;
      result.replaceChildren(
        el("div", { class: `alert alert-${d.open_barrier ? "success" : "warning"} mb-0` },
          el("strong", {}, d.open_barrier ? "Barrier opens" : "Barrier stays closed"),
          ` - ${d.access_result} · ${d.owner_type}`,
          el("div", { class: "small mt-1" }, d.reason),
          d.flags.length ? el("div", { class: "small text-body-secondary" }, `Flags: ${d.flags.join(", ")}`) : null,
          el("div", { class: "small text-body-secondary" }, `Log #${res.log_id}`)));
    } catch (err) {
      result.replaceChildren(el("div", { class: "alert alert-danger mb-0" }, err.message));
    }
  });

  document.querySelectorAll("[data-lane]").forEach((card) => {
    const lane = card.dataset.lane;
    card.querySelector("[data-ir]").addEventListener("change", (e) =>
      postJSON("/dev/simulator/ir", { lane, present: e.target.checked }));
    card.querySelector("[data-button]").addEventListener("click", () =>
      postJSON("/dev/simulator/button", { lane }));
  });

  const buzzerTimers = {};

  function render(lane, b) {
    const card = document.querySelector(`[data-lane="${lane}"]`);
    card.querySelector("[data-arm]").classList.toggle("open", b.barrier === "open");
    card.querySelector("[data-led-green]").classList.toggle("led-green", b.led === "green");
    card.querySelector("[data-led-red]").classList.toggle("led-red", b.led === "red");
    card.querySelector("[data-ir]").checked = b.vehicle_present;
    if (b.buzzer) {
      const buzzer = card.querySelector("[data-buzzer]");
      buzzer.textContent = b.buzzer === "short" ? "🔊 short beep" : "🔊 long beep";
      clearTimeout(buzzerTimers[lane]);
      buzzerTimers[lane] = setTimeout(() => (buzzer.textContent = ""), 1500);
    }
  }

  const initial = JSON.parse(document.getElementById("initial-barriers").textContent);
  Object.entries(initial).forEach(([lane, b]) => render(lane, b));

  window.ScaNEU.socket.on("barrier", (b) => render(b.lane, b));
})();
