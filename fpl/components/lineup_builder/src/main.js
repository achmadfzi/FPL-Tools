import Sortable from "sortablejs";
import { Streamlit } from "streamlit-component-lib";

const POSITIONS = ["GK", "DEF", "MID", "FWD"];
const XI_MIN = { GK: 1, DEF: 3, MID: 2, FWD: 1 };
const XI_MAX = { GK: 1, DEF: 5, MID: 5, FWD: 3 };
const FDR_COLORS = {
  1: ["#01FC7A", "#064420"],
  2: ["#01FC7A", "#064420"],
  3: ["#e2e8f0", "#1e293b"],
  4: ["#FF1751", "#ffffff"],
  5: ["#80072D", "#ffffff"],
};

const state = {
  players: [],
  byId: new Map(),
  xi: [],
  benchOut: [],
  benchGk: null,
  version: -1,
  toastTimer: null,
  sortables: [],
  hoverTargetId: null,
  hoverTargetContainer: null,
  dropLock: false,
  revision: 0,
};

let els = {};

function playerById(id) {
  return state.byId.get(Number(id));
}

function allIds() {
  return [...state.xi, ...state.benchOut, ...(state.benchGk != null ? [state.benchGk] : [])];
}

function counts(ids) {
  const out = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const id of ids) {
    const p = playerById(id);
    if (p && out[p.pos] != null) out[p.pos] += 1;
  }
  return out;
}

function totalProj(ids) {
  return ids.reduce((sum, id) => sum + Number(playerById(id)?.proj || 0), 0);
}

function captainIds() {
  const ordered = state.xi
    .map((id) => playerById(id))
    .filter(Boolean)
    .sort((a, b) => Number(b.proj || 0) - Number(a.proj || 0));
  return {
    captain: ordered[0]?.id ?? null,
    vice: ordered[1]?.id ?? null,
  };
}

function photoUrl(code) {
  if (!code) return "";
  const clean = String(code).split(".")[0];
  return `https://resources.premierleague.com/premierleague/photos/players/110x140/p${clean}.png`;
}

function gwCells(player) {
  const wrap = document.createElement("div");
  wrap.className = "lb-gw";
  for (const cell of player.gw || []) {
    const fdr = Number(cell.fdr || 3);
    const [bg, fg] = FDR_COLORS[fdr] || ["#e2e8f0", "#1e293b"];
    const el = document.createElement("div");
    el.className = "lb-gw-cell";
    el.style.background = bg;
    el.style.color = fg;
    const pts = document.createElement("div");
    pts.className = "lb-gw-pts";
    pts.textContent = Number(cell.pts || 0).toFixed(1);
    const opp = document.createElement("div");
    opp.className = "lb-gw-opp";
    opp.textContent = `${cell.opp || "-"}${cell.ha || ""}`;
    el.append(pts, opp);
    wrap.append(el);
  }
  return wrap;
}

function playerCard(player, context = "pitch") {
  const card = document.createElement("div");
  card.className = "lb-card";
  if (context === "bench") card.classList.add("lb-bench-card");
  if (player.status && player.status !== "a") card.classList.add("lb-out");
  card.dataset.id = String(player.id);
  card.dataset.pos = player.pos;
  card.title = `${player.name} · ${player.team} · ${player.pos}`;

  const handle = document.createElement("span");
  handle.className = "lb-handle";
  handle.textContent = "⠿";
  handle.setAttribute("aria-hidden", "true");

  const photo = document.createElement("img");
  photo.className = "lb-photo";
  photo.alt = "";
  photo.loading = "lazy";
  if (player.photo) {
    photo.src = photoUrl(player.photo);
    photo.addEventListener("error", () => {
      photo.style.visibility = "hidden";
    });
  } else {
    photo.style.visibility = "hidden";
  }

  const name = document.createElement("div");
  name.className = "lb-name";
  name.textContent = player.name || "";

  const team = document.createElement("div");
  team.className = "lb-team";
  team.textContent = player.team || "-";

  const price = document.createElement("div");
  price.className = "lb-price";
  price.textContent = `£${(Number(player.price || 0) / 10).toFixed(1)}m`;

  const cap = captainIds();
  if (context === "pitch" && cap.captain === Number(player.id)) {
    const b = document.createElement("span");
    b.className = "lb-cap";
    b.textContent = "C";
    card.append(b);
  } else if (context === "pitch" && cap.vice === Number(player.id)) {
    const b = document.createElement("span");
    b.className = "lb-vice";
    b.textContent = "V";
    card.append(b);
  }

  card.append(handle, photo, name, team, price, gwCells(player));
  return card;
}

function renderSummary() {
  const c = counts(state.xi);
  const formation = `${c.DEF}-${c.MID}-${c.FWD}`;
  const total = totalProj(state.xi);
  const cap = captainIds();
  const capName = playerById(cap.captain)?.name || "-";
  const viceName = playerById(cap.vice)?.name || "-";
  els.form.textContent = formation;
  els.pts.textContent = `${total.toFixed(1)} pts`;
  els.cap.textContent = `C ${capName}`;
  els.vice.textContent = `V ${viceName}`;
}

function renderPitch() {
  for (const pos of POSITIONS) {
    const container = document.getElementById(`lb-row-${pos}`);
    container.innerHTML = "";
    const ids = state.xi
      .map((id) => playerById(id))
      .filter((p) => p && p.pos === pos)
      .sort((a, b) => Number(b.proj || 0) - Number(a.proj || 0));
    if (!ids.length) {
      const empty = document.createElement("div");
      empty.className = "lb-empty";
      empty.textContent = "Tarik pemain ke sini";
      container.append(empty);
    } else {
      for (const player of ids) container.append(playerCard(player, "pitch"));
    }
  }
}

function renderBench() {
  const out = document.getElementById("lb-bench-out");
  out.innerHTML = "";
  state.benchOut.forEach((id, index) => {
    const player = playerById(id);
    if (!player) return;
    const card = playerCard(player, "bench");
    card.dataset.slot = String(index + 1);
    out.append(card);
  });
  if (!state.benchOut.length) {
    const empty = document.createElement("div");
    empty.className = "lb-empty";
    empty.textContent = "Bench outfield";
    out.append(empty);
  }

  const gk = document.getElementById("lb-bench-gk");
  gk.innerHTML = "";
  const keeper = playerById(state.benchGk);
  if (keeper) {
    gk.append(playerCard(keeper, "bench"));
  } else {
    const empty = document.createElement("div");
    empty.className = "lb-empty";
    empty.textContent = "GK";
    gk.append(empty);
  }
}

function setHeight() {
  window.requestAnimationFrame(() => Streamlit.setFrameHeight());
}

function renderAll() {
  renderSummary();
  renderPitch();
  renderBench();
  setHeight();
}

function toast(message) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2800);
}

function readDom() {
  const xi = [];
  for (const pos of POSITIONS) {
    document.querySelectorAll(`#lb-row-${pos} .lb-card`).forEach((el) => {
      xi.push(Number(el.dataset.id));
    });
  }
  const benchOut = [...document.querySelectorAll("#lb-bench-out .lb-card")].map((el) =>
    Number(el.dataset.id)
  );
  const gkEl = document.querySelector("#lb-bench-gk .lb-card");
  const benchGk = gkEl ? Number(gkEl.dataset.id) : null;
  return { xi, benchOut, benchGk };
}

function validateLineup(next) {
  if (next.xi.length !== 11) return "XI harus berisi 11 pemain";
  if (next.benchOut.length !== 3) return "Bench outfield harus berisi 3 pemain";
  if (next.benchGk == null) return "Bench harus punya kiper";

  const ids = [...next.xi, ...next.benchOut, next.benchGk];
  if (new Set(ids).size !== 15) return "Lineup harus berisi 15 pemain unik";

  const c = counts(next.xi);
  if (c.GK !== 1) return "XI harus punya tepat 1 kiper";
  for (const pos of POSITIONS) {
    if (c[pos] < XI_MIN[pos] || c[pos] > XI_MAX[pos]) {
      return `Formasi tidak valid: ${pos} ${c[pos]} (${XI_MIN[pos]}-${XI_MAX[pos]})`;
    }
  }

  const keeper = playerById(next.benchGk);
  if (!keeper || keeper.pos !== "GK") return "Slot bench GK harus diisi kiper";
  for (const id of next.benchOut) {
    if (playerById(id)?.pos === "GK") return "Kiper tidak boleh di bench outfield";
  }
  return null;
}

function locatePlayer(id) {
  const xiIndex = state.xi.indexOf(id);
  if (xiIndex >= 0) return ["xi", xiIndex];
  const benchIndex = state.benchOut.indexOf(id);
  if (benchIndex >= 0) return ["benchOut", benchIndex];
  if (state.benchGk === id) return ["benchGk", null];
  return null;
}

function swapPlayers(idA, idB) {
  const a = locatePlayer(idA);
  const b = locatePlayer(idB);
  if (!a || !b) return null;
  const next = {
    xi: [...state.xi],
    benchOut: [...state.benchOut],
    benchGk: state.benchGk,
  };
  const put = (slot, id) => {
    if (slot[0] === "benchGk") next.benchGk = id;
    else next[slot[0]][slot[1]] = id;
  };
  put(a, idB);
  put(b, idA);
  return next;
}

function commit() {
  Streamlit.setComponentValue({
    xi: [...state.xi],
    bench_out: [...state.benchOut],
    bench_gk: state.benchGk,
    _revision: `${Date.now()}-${++state.revision}`,
  });
}

function canMove(evt) {
  if (!evt || !evt.from || !evt.to || !evt.dragged) return true;
  const from = evt.from.dataset.target;
  const to = evt.to.dataset.target;

  // Let the pointer travel across other pitch rows while dragging toward
  // the bench. Validation happens on drop, so crossing rows never blocks
  // the gesture.
  if (from !== to) {
    const related = evt.related;
    if (related && related.classList && related.classList.contains("lb-card")) {
      state.hoverTargetId = Number(related.dataset.id);
      state.hoverTargetContainer = to;
    } else {
      state.hoverTargetId = null;
      state.hoverTargetContainer = null;
    }
  }
  return true;
}

function swapError(dragId, targetId, targetContainer) {
  const dragged = playerById(dragId);
  const target = playerById(targetId);
  if (!dragged || !target) return "Pemain tidak ditemukan";
  if (POSITIONS.includes(targetContainer)) {
    if (dragged.pos !== targetContainer || target.pos !== targetContainer) {
      return `${dragged.name} (${dragged.pos}) tidak bisa menggantikan ${target.name} (${target.pos})`;
    }
    return null;
  }
  if (targetContainer === "BENCH_OUT") {
    if (dragged.pos === "GK" || target.pos === "GK") {
      return "Kiper punya slot bench sendiri";
    }
    return null;
  }
  if (targetContainer === "BENCH_GK") {
    if (dragged.pos !== "GK" || target.pos !== "GK") {
      return "Slot bench GK hanya untuk kiper";
    }
    return null;
  }
  return "Target tidak valid";
}

function afterDrop(evt) {
  if (!evt || !evt.from || !evt.to) return;
  const dragged = evt.dragged || evt.item;
  if (!dragged) return;
  if (state.dropLock) return;
  state.dropLock = true;
  setTimeout(() => {
    state.dropLock = false;
  }, 120);

  const from = evt.from.dataset.target;
  const to = evt.to.dataset.target;
  const dragId = Number(dragged.dataset.id);

  if (from !== to) {
    const targetId = state.hoverTargetId;
    const targetContainer = state.hoverTargetContainer;
    state.hoverTargetId = null;
    state.hoverTargetContainer = null;
    if (targetId == null || targetContainer !== to) {
      toast("Tarik ke kartu pemain untuk menukar posisi");
      renderAll();
      return;
    }
    const swapErrorMsg = swapError(dragId, targetId, targetContainer);
    if (swapErrorMsg) {
      toast(swapErrorMsg);
      renderAll();
      return;
    }
    const next = swapPlayers(dragId, targetId);
    const error = next ? validateLineup(next) : "Tidak bisa menukar pemain";
    if (error) {
      toast(error);
      renderAll();
      return;
    }
    state.xi = next.xi;
    state.benchOut = next.benchOut;
    state.benchGk = next.benchGk;
    renderAll();
    commit();
    return;
  }

  // Same container: bench order can be reordered; pitch rows do not change
  // the XI membership.
  const next = readDom();
  const error = validateLineup(next);
  if (error) {
    toast(error);
    renderAll();
    return;
  }
  state.xi = next.xi;
  state.benchOut = next.benchOut;
  state.benchGk = next.benchGk;
  renderAll();
  commit();
}

function initSortables() {
  for (const instance of state.sortables) {
    try {
      instance.destroy();
    } catch (_) {
      // ignore stale instances
    }
  }
  state.sortables = [];
  const containers = [
    ...POSITIONS.map((pos) => document.getElementById(`lb-row-${pos}`)),
    document.getElementById("lb-bench-out"),
    document.getElementById("lb-bench-gk"),
  ];
  for (const container of containers) {
    if (!container) continue;
    state.sortables.push(
      new Sortable(container, {
        group: { name: "lb-lineup", pull: true, put: true },
        animation: 150,
        draggable: ".lb-card",
        filter: ".lb-empty",
        preventOnFilter: true,
        ghostClass: "lb-ghost",
        chosenClass: "lb-chosen",
        dragClass: "lb-drag",
        onStart: () => {
          state.hoverTargetId = null;
          state.hoverTargetContainer = null;
        },
        onMove: canMove,
        onEnd: afterDrop,
        onAdd: afterDrop,
      })
    );
  }
}

function buildShell() {
  document.getElementById("app").innerHTML = `
    <div class="lb-root">
      <div class="lb-top">
        <div>
          <div class="lb-kicker">Lineup</div>
          <div class="lb-title">Susun XI & Bench</div>
        </div>
        <div class="lb-stats">
          <span class="lb-stat" id="lb-form"></span>
          <span class="lb-stat" id="lb-pts"></span>
          <span class="lb-stat lb-cap-stat" id="lb-cap"></span>
          <span class="lb-stat lb-vice-stat" id="lb-vice"></span>
        </div>
      </div>
      <div class="lb-hint">
        Drag pemain ke pemain lain untuk menukar starter ↔ bench.
        Posisi harus sama; kiper punya slot bench sendiri.
      </div>
      <div class="lb-pitch">
        ${POSITIONS.map(
          (pos) => `
          <div class="lb-row-wrap">
            <span class="lb-row-label lb-label-${pos}">${pos}</span>
            <div id="lb-row-${pos}" class="lb-row" data-target="${pos}"></div>
          </div>`
        ).join("")}
      </div>
      <div class="lb-bench-panel">
        <div class="lb-bench-head">
          <span>Bench</span>
          <span class="lb-muted">Sub 1–3 + GK cadangan</span>
        </div>
        <div class="lb-bench-row">
          <div class="lb-bench-block">
            <div class="lb-bench-label">Urutan sub</div>
            <div id="lb-bench-out" class="lb-bench-list" data-target="BENCH_OUT"></div>
          </div>
          <div class="lb-bench-block lb-bench-gk-block">
            <div class="lb-bench-label">GK cadangan</div>
            <div id="lb-bench-gk" class="lb-bench-list" data-target="BENCH_GK"></div>
          </div>
        </div>
      </div>
      <div id="lb-toast" class="lb-toast" role="status"></div>
    </div>
  `;

  els = {
    form: document.getElementById("lb-form"),
    pts: document.getElementById("lb-pts"),
    cap: document.getElementById("lb-cap"),
    vice: document.getElementById("lb-vice"),
    toast: document.getElementById("lb-toast"),
  };
  initSortables();
}

function onRender(event) {
  const args = event.detail && event.detail.args ? event.detail.args : {};
  const players = Array.isArray(args.players) ? args.players : [];
  state.players = players;
  state.byId = new Map(players.map((p) => [Number(p.id), p]));
  state.xi = Array.isArray(args.xi) ? args.xi.map(Number).filter((id) => state.byId.has(id)) : [];
  state.benchOut = Array.isArray(args.bench_out)
    ? args.bench_out.map(Number).filter((id) => state.byId.has(id))
    : [];
  state.benchGk = args.bench_gk != null && state.byId.has(Number(args.bench_gk))
    ? Number(args.bench_gk)
    : null;
  state.version = Number.isFinite(Number(args.version)) ? Number(args.version) : 0;
  renderAll();
}

buildShell();
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();

if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => Streamlit.setFrameHeight()).observe(document.body);
}
