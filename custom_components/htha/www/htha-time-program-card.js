/*
 * Ht HA \u2013 weekly time program card
 *
 * type: custom:htha-time-program-card
 * entity: sensor.heliotherm_heat_pump_time_programs   # optional, auto-detected
 * programs: [0, 1]                                     # optional, default: all
 * title: Zeitprogramme                                 # optional
 * state_names:                                         # optional, per program index
 *   2: ["Absenkung", "Normal", "Komfort"]
 */

const HTHA_VERSION = "1.3.0";

const I18N = {
  de: {
    days: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    title: "Zeitprogramme",
    off: "Aus",
    on: "An",
    state: "Zustand",
    add: "Zeitraum hinzuf\u00fcgen",
    save: "Speichern",
    cancel: "Abbrechen",
    applyTo: "\u00dcbernehmen f\u00fcr",
    weekdays: "Mo\u2013Fr",
    weekend: "Sa\u2013So",
    all: "Alle",
    saving: "Speichere \u2026",
    saved: "Gespeichert",
    noData: "Keine Zeitprogramme verf\u00fcgbar",
    refresh: "Neu einlesen",
    hint: "Tag antippen zum Bearbeiten",
  },
  en: {
    days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    title: "Time programs",
    off: "Off",
    on: "On",
    state: "State",
    add: "Add period",
    save: "Save",
    cancel: "Cancel",
    applyTo: "Apply to",
    weekdays: "Mon\u2013Fri",
    weekend: "Sat\u2013Sun",
    all: "All",
    saving: "Saving \u2026",
    saved: "Saved",
    noData: "No time programs available",
    refresh: "Refresh",
    hint: "Tap a day to edit",
  },
};

const STATE_COLORS = [
  "var(--disabled-color, #bdbdbd)",
  "var(--state-active-color, var(--accent-color, #ff9800))",
  "var(--error-color, #db4437)",
];

const toMin = (t) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};
const toHHMM = (min) =>
  `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

class HthaTimeProgramCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._editing = null; // {prog, day, periods, days:Set}
    this._status = "";
    this._sig = "";
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes.time_programs
    );
    return { entity: entity || "sensor.heliotherm_heat_pump_time_programs" };
  }

  setConfig(config) {
    this._config = config || {};
    this._sig = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const progs = this._programs();
    const sig = JSON.stringify(progs) + (hass.language || "");
    if (sig !== this._sig && !this._editing) {
      this._sig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 3 + this._programs().length * 4;
  }

  get _t() {
    const lang = (this._hass && this._hass.language) || "en";
    return I18N[lang.split("-")[0]] || I18N.en;
  }

  _entityId() {
    if (this._config.entity) return this._config.entity;
    return Object.keys(this._hass.states).find(
      (e) => e.startsWith("sensor.") && this._hass.states[e].attributes.time_programs
    );
  }

  _programs() {
    if (!this._hass) return [];
    const st = this._hass.states[this._entityId()];
    let progs = (st && st.attributes.time_programs) || [];
    if (Array.isArray(this._config.programs)) {
      progs = progs.filter(
        (p) => this._config.programs.includes(p.index) || this._config.programs.includes(p.name)
      );
    }
    return progs;
  }

  _stateNames(prog) {
    const custom = this._config.state_names && this._config.state_names[prog.index];
    if (custom) return custom;
    if (prog.nos === 2) return [this._t.off, this._t.on];
    return Array.from({ length: prog.nos }, (_, i) => `${this._t.state} ${i}`);
  }

  _periods(prog, day) {
    return ((prog.entries && prog.entries[day]) || [])
      .filter((e) => e && e.start !== e.end)
      .map((e) => ({ state: e.state, start: e.start, end: e.end }));
  }

  _bar(prog, periods) {
    const names = this._stateNames(prog);
    return periods
      .map((p) => {
        const left = (toMin(p.start) / 1440) * 100;
        const width = ((toMin(p.end) - toMin(p.start)) / 1440) * 100;
        const label = width > 12 ? `${p.start}\u2013${p.end}` : "";
        return `<div class="seg s${p.state}" style="left:${left}%;width:${width}%;background:${
          STATE_COLORS[p.state] || STATE_COLORS[1]
        }" title="${names[p.state] || p.state}: ${p.start}\u2013${p.end}">${p.state ? label : ""}</div>`;
      })
      .join("");
  }

  _render() {
    const t = this._t;
    const progs = this._programs();
    const today = (new Date().getDay() + 6) % 7;
    const title = this._config.title || t.title;

    let body = "";
    if (!progs.length) {
      body = `<div class="empty">${t.noData}</div>`;
    }
    for (const prog of progs) {
      const names = this._stateNames(prog);
      const legend = names
        .map(
          (n, i) =>
            `<span class="lg"><i style="background:${STATE_COLORS[i] || STATE_COLORS[1]}"></i>${n}</span>`
        )
        .join("");
      let rows = "";
      for (let d = 0; d < prog.nod; d++) {
        const isEdit = this._editing && this._editing.prog === prog.index && this._editing.day === d;
        rows += `<div class="row ${d === today ? "today" : ""} ${isEdit ? "sel" : ""}" data-prog="${
          prog.index
        }" data-day="${d}">
          <div class="day">${t.days[d] || d}</div>
          <div class="bar">${this._bar(prog, this._periods(prog, d))}</div>
        </div>`;
        if (isEdit) rows += this._editor(prog);
      }
      body += `<div class="prog">
        <div class="ph"><span class="pn">${prog.name}</span><span class="legend">${legend}</span></div>
        <div class="scale"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
        ${rows}
      </div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 16px; }
        .hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
        .hdr h2 { font-size: 1.15em; font-weight: 500; margin: 0; }
        .hdr button { background:none; border:none; color: var(--primary-color); cursor:pointer; font: inherit; }
        .hint { color: var(--secondary-text-color); font-size: .8em; margin-bottom: 8px; }
        .prog { margin-top: 12px; }
        .ph { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px; margin-bottom:4px; }
        .pn { font-weight: 500; }
        .legend { font-size:.75em; color: var(--secondary-text-color); display:flex; gap:8px; }
        .lg i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:3px; vertical-align:-1px; }
        .scale { display:flex; justify-content:space-between; margin-left: 36px; font-size:.7em; color: var(--secondary-text-color); }
        .row { display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; border-radius:4px; }
        .row:hover .bar { outline: 1px solid var(--divider-color); }
        .row.today .day { font-weight: 700; color: var(--primary-color); }
        .row.sel .bar { outline: 2px solid var(--primary-color); }
        .day { width: 30px; font-size: .85em; }
        .bar { position:relative; flex:1; height: 20px; background: var(--secondary-background-color); border-radius:4px; overflow:hidden; }
        .seg { position:absolute; top:0; bottom:0; font-size:.68em; color: var(--text-primary-color, #fff); display:flex; align-items:center; justify-content:center; overflow:hidden; white-space:nowrap; }
        .seg.s0 { opacity: .35; }
        .ed { margin: 6px 0 10px 0; padding: 10px; border:1px solid var(--divider-color); border-radius: 8px; }
        .pr { display:flex; gap:4px; align-items:center; margin-bottom:6px; flex-wrap:nowrap; }
        .pr select, .pr input { font: inherit; padding: 4px; border-radius:4px; border:1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
        .pr input[type=time] { width: 6.6em; min-width:0; } .pr select { max-width: 7em; }
        .del { background:none; border:none; color: var(--error-color); cursor:pointer; font-size: 1.1em; }
        .days { display:flex; gap:4px; flex-wrap:wrap; align-items:center; margin: 8px 0; font-size:.85em; }
        .days label { display:flex; align-items:center; gap:2px; }
        .days button, .acts button { font: inherit; font-size:.85em; padding: 3px 8px; border-radius: 12px; border:1px solid var(--divider-color); background:none; color: var(--primary-text-color); cursor:pointer; }
        .acts { display:flex; gap:8px; justify-content:flex-end; align-items:center; }
        .acts .primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
        .status { font-size:.8em; color: var(--secondary-text-color); margin-right:auto; }
        .status.err { color: var(--error-color); }
        .empty { color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="hdr"><h2>${title}</h2><button class="refresh">${t.refresh}</button></div>
        <div class="hint">${t.hint}</div>
        ${body}
      </ha-card>`;
    this._bind();
  }

  _editor(prog) {
    const t = this._t;
    const ed = this._editing;
    const names = this._stateNames(prog);
    const step = (prog.ste || 15) * 60;
    const rows = ed.periods
      .map(
        (p, i) => `<div class="pr" data-i="${i}">
          <select class="st">${names
            .map((n, s) => `<option value="${s}" ${s === p.state ? "selected" : ""}>${n}</option>`)
            .join("")}</select>
          <input class="start" type="time" step="${step}" value="${p.start === "24:00" ? "23:59" : p.start}">
          \u2013
          <input class="end" type="time" step="${step}" value="${p.end === "24:00" ? "00:00" : p.end}">
          <button class="del" title="\u2715">\u2715</button>
        </div>`
      )
      .join("");
    const dayBoxes = t.days
      .slice(0, prog.nod)
      .map(
        (n, d) =>
          `<label><input type="checkbox" class="dbox" data-d="${d}" ${ed.days.has(d) ? "checked" : ""}>${n}</label>`
      )
      .join("");
    const disabled = ed.periods.length >= prog.ead ? "disabled" : "";
    return `<div class="ed">
      ${rows}
      <div class="acts" style="justify-content:flex-start"><button class="add" ${disabled}>+ ${t.add}</button></div>
      <div class="days">${t.applyTo}: ${dayBoxes}
        <button class="grp" data-g="weekdays">${t.weekdays}</button>
        <button class="grp" data-g="weekend">${t.weekend}</button>
        <button class="grp" data-g="all">${t.all}</button>
      </div>
      <div class="acts">
        <span class="status ${this._status.startsWith("!") ? "err" : ""}">${this._status.replace(/^!/, "")}</span>
        <button class="cancel">${t.cancel}</button>
        <button class="save primary">${t.save}</button>
      </div>
    </div>`;
  }

  _readEditor() {
    const root = this.shadowRoot;
    this._editing.periods = Array.from(root.querySelectorAll(".pr")).map((el) => {
      let end = el.querySelector(".end").value.slice(0, 5) || "00:00";
      if (end === "00:00") end = "24:00";
      return {
        state: Number(el.querySelector(".st").value),
        start: el.querySelector(".start").value.slice(0, 5) || "00:00",
        end,
      };
    });
    this._editing.days = new Set(
      Array.from(root.querySelectorAll(".dbox"))
        .filter((b) => b.checked)
        .map((b) => Number(b.dataset.d))
    );
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelector(".refresh").addEventListener("click", () =>
      this._hass.callService("htha", "refresh_time_programs", {})
    );
    root.querySelectorAll(".row").forEach((row) =>
      row.addEventListener("click", () => {
        const progIdx = Number(row.dataset.prog);
        const day = Number(row.dataset.day);
        const prog = this._programs().find((p) => p.index === progIdx);
        if (this._editing && this._editing.prog === progIdx && this._editing.day === day) {
          this._editing = null;
        } else {
          this._editing = { prog: progIdx, day, periods: this._periods(prog, day), days: new Set([day]) };
        }
        this._status = "";
        this._render();
      })
    );
    const ed = root.querySelector(".ed");
    if (!ed) return;
    const prog = this._programs().find((p) => p.index === this._editing.prog);
    ed.querySelectorAll(".del").forEach((b) =>
      b.addEventListener("click", (ev) => {
        this._readEditor();
        this._editing.periods.splice(Number(ev.target.closest(".pr").dataset.i), 1);
        this._render();
      })
    );
    ed.querySelector(".add").addEventListener("click", () => {
      this._readEditor();
      const last = this._editing.periods[this._editing.periods.length - 1];
      const start = last ? last.end : "00:00";
      const startMin = Math.min(toMin(start === "24:00" ? "23:45" : start), 1440 - (prog.ste || 15));
      this._editing.periods.push({ state: 0, start: toHHMM(startMin), end: "24:00" });
      this._render();
    });
    ed.querySelectorAll(".grp").forEach((b) =>
      b.addEventListener("click", () => {
        this._readEditor();
        const g = b.dataset.g;
        const set = g === "weekdays" ? [0, 1, 2, 3, 4] : g === "weekend" ? [5, 6] : [0, 1, 2, 3, 4, 5, 6];
        const allOn = set.every((d) => this._editing.days.has(d));
        set.forEach((d) => (allOn ? this._editing.days.delete(d) : this._editing.days.add(d)));
        this._render();
      })
    );
    ed.querySelector(".cancel").addEventListener("click", () => {
      this._editing = null;
      this._status = "";
      this._sig = "";
      this.hass = this._hass;
    });
    ed.querySelector(".save").addEventListener("click", () => this._save());
  }

  async _save() {
    this._readEditor();
    const ed = this._editing;
    if (!ed.days.size) ed.days.add(ed.day);
    this._status = this._t.saving;
    this._render();
    try {
      await this._hass.callWS({
        type: "call_service",
        domain: "htha",
        service: "set_time_program_day",
        service_data: {
          time_program: ed.prog,
          days: Array.from(ed.days).sort(),
          entries: ed.periods,
        },
      });
      this._editing = null;
      this._status = "";
      this._sig = "";
      this.hass = this._hass;
    } catch (err) {
      this._status = "!" + ((err && err.message) || String(err));
      this._render();
    }
  }
}

if (!customElements.get("htha-time-program-card")) {
  customElements.define("htha-time-program-card", HthaTimeProgramCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "htha-time-program-card",
    name: "Heliotherm Time Programs",
    description: "Weekly time programs of a Heliotherm heat pump (Ht HA)",
  });
  console.info(`%c HTHA-TIME-PROGRAM-CARD %c ${HTHA_VERSION} `, "background:#ff9800;color:#fff", "");
}
