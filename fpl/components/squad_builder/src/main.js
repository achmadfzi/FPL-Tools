import Sortable from "sortablejs";
import { Streamlit } from "streamlit-component-lib";

const POSITIONS = ["GK", "DEF", "MID", "FWD"];
const NEED = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const MAX_CANDIDATES = 80;
const SQUAD_SIZE = 15;

const state = {
  players: [],
  byId: new Map(),
  selected: emptySelected(),
  budget: 1000,
  clubMax: 3,
  version: -1,
  search: "",
  posFilter: "ALL",
  ready: false,
  toastTimer: null,
  sortables: [],
  revision: 0,
};

let els = {};

function emptySelected() {
  return { GK: [], DEF: [], MID: [], FWD: [] };
}

function normalizeSelected(value) {
  const out = emptySelected();
  if (!value || typeof value !== "object") return out;
  for (const pos of POSITIONS) {
    const raw = value[pos];
    if (!Array.isArray(raw)) continue;
    for (const item of raw) {
      const id = Number(item);
      if (Number.isFinite(id) && !out[pos].includes(id)) out[pos].push(id);
    }
  }
  return out;
}

function cloneSelected(selected = state.selected) {
  return {
    GK: [...selected.GK],
    DEF: [...selected.DEF],
    MID: [...selected.MID],
    FWD: [...selected.FWD],
  };
}

function allSelectedIds(selected = state.selected) {
  return POSITIONS.flatMap((pos) => selected[pos] || []);
}

function selectedFromDom() {
  const out = emptySelected();
  for (const pos of POSITIONS) {
    const container = document.getElementById(`sb-drop-${pos}`);
    if (!container) continue;
    container.querySelectorAll(".sb-player").forEach((el) => {
      const id = Number(el.dataset.id);
      if (Number.isFinite(id)) out[pos].push(id);
    });
  }
  return out;
}

function playerById(id) {
  return state.byId.get(Number(id));
}

function playerCard(player, context) {
  const card = document.createElement("div");
  card.className = "sb-player";
  if (context === "pool") card.classList.add("sb-player-pool");
  const chance = player.chance;
  if (player.status !== "a" || (chance !== null && chance !== undefined && Number(chance) === 0)) {
    card.classList.add("sb-player-out");
  }
  card.dataset.id = String(player.id);
  card.dataset.pos = player.pos;
  card.dataset.team = String(player.team || "");
  card.dataset.price = String(player.price || 0);
  card.title = `${player.name} · ${player.team} · ${player.pos}`;

  const handle = document.createElement("span");
  handle.className = "sb-handle";
  handle.textContent = "⠿";
  handle.setAttribute("aria-hidden", "true");

  const photo = document.createElement("img");
  photo.className = "sb-photo";
  photo.alt = "";
  photo.loading = "lazy";
  if (player.photo) {
    const code = String(player.photo).split(".")[0];
    photo.src = `https://resources.premierleague.com/premierleague/photos/players/110x140/p${code}.png`;
    photo.addEventListener("error", () => {
      photo.style.visibility = "hidden";
    });
  } else {
    photo.style.visibility = "hidden";
  }

  const info = document.createElement("div");
  info.className = "sb-info";
  const name = document.createElement("div");
  name.className = "sb-name";
  name.textContent = player.name || "";
  const meta = document.createElement("div");
  meta.className = "sb-meta";
  const price = (Number(player.price || 0) / 10).toFixed(1);
  meta.textContent = `${player.team || "-"} · £${price}m · ${Number(player.proj || 0).toFixed(1)} pts`;
  info.append(name, meta);

  const badge = document.createElement("span");
  badge.className = `sb-pos sb-pos-${player.pos}`;
  badge.textContent = player.pos;

  const action = document.createElement("button");
  action.type = "button";
  action.className = "sb-action";
  action.dataset.action = context === "pool" ? "add" : "remove";
  action.textContent = context === "pool" ? "+" : "×";
  action.title = context === "pool" ? "Tambahkan ke skuad" : "Keluarkan dari skuad";

  card.append(handle, photo, info, badge, action);
  return card;
}

function selectionStats(selected = state.selected) {
  const ids = allSelectedIds(selected);
  const players = ids.map((id) => playerById(id)).filter(Boolean);
  const cost = players.reduce((sum, p) => sum + Number(p.price || 0), 0);
  const clubs = {};
  for (const p of players) {
    const team = String(p.team || "-");
    clubs[team] = (clubs[team] || 0) + 1;
  }
  return {
    count: players.length,
    cost,
    bank: state.budget - cost,
    clubs,
    maxClub: Math.max(0, ...Object.values(clubs)),
  };
}

function validateSelection(selected) {
  for (const pos of POSITIONS) {
    if ((selected[pos] || []).length > NEED[pos]) {
      return `Posisi ${pos} maksimal ${NEED[pos]} pemain`;
    }
  }
  const ids = allSelectedIds(selected);
  if (ids.length > SQUAD_SIZE) return `Skuad maksimal ${SQUAD_SIZE} pemain`;

  const stats = selectionStats(selected);
  if (stats.maxClub > state.clubMax) {
    return `Maksimal ${state.clubMax} pemain per klub`;
  }
  if (stats.cost > state.budget) {
    return `Budget terlampaui (£${(stats.cost / 10).toFixed(1)}m > £${(state.budget / 10).toFixed(1)}m)`;
  }
  return null;
}

function toast(message) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2800);
}

function commit() {
  const payload = {};
  for (const pos of POSITIONS) payload[pos] = [...state.selected[pos]];
  // Revision distinguishes a fresh user action from the same value being
  // re-sent by Streamlit on a rerun.
  payload._revision = `${Date.now()}-${++state.revision}`;
  Streamlit.setComponentValue(payload);
}

function setHeight() {
  window.requestAnimationFrame(() => Streamlit.setFrameHeight());
}

function renderSummary() {
  const stats = selectionStats();
  els.count.textContent = `${stats.count}/${SQUAD_SIZE} pemain`;
  els.bank.textContent = `£${(stats.bank / 10).toFixed(1)}m tersisa`;
  els.bank.classList.toggle("sb-warn", stats.bank < 0);
  els.clubs.textContent = `Klub maks ${stats.maxClub}/${state.clubMax}`;
  els.clubs.classList.toggle("sb-warn", stats.maxClub > state.clubMax);
  els.clubs.title = `Maksimal ${state.clubMax} pemain dari satu klub`;
  els.cost.textContent = `£${(stats.cost / 10).toFixed(1)}m terpakai`;
}

function renderFilters() {
  els.filters.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pos === state.posFilter);
  });
}

function renderPool() {
  const selected = new Set(allSelectedIds());
  const query = state.search.trim().toLowerCase();
  let players = state.players.filter((p) => !selected.has(Number(p.id)));
  if (state.posFilter !== "ALL") {
    players = players.filter((p) => p.pos === state.posFilter);
  }
  if (query) {
    players = players.filter(
      (p) =>
        String(p.name || "").toLowerCase().includes(query) ||
        String(p.team || "").toLowerCase().includes(query)
    );
  }
  players.sort((a, b) => {
    const proj = Number(b.proj || 0) - Number(a.proj || 0);
    if (proj !== 0) return proj;
    return Number(a.price || 0) - Number(b.price || 0);
  });

  const visible = players.slice(0, MAX_CANDIDATES);
  els.pool.innerHTML = "";
  if (!visible.length) {
    const alreadySelected = state.players.some((p) => {
      const id = Number(p.id);
      if (!selected.has(id)) return false;
      const matchesQuery = !query ||
        String(p.name || "").toLowerCase().includes(query) ||
        String(p.team || "").toLowerCase().includes(query);
      return matchesQuery && (state.posFilter === "ALL" || p.pos === state.posFilter);
    });
    const empty = document.createElement("div");
    empty.className = "sb-empty";
    if (alreadySelected) {
      empty.textContent = "Pemain tersebut sudah ada di skuad.";
    } else if (query || state.posFilter !== "ALL") {
      empty.textContent = "Tidak ada pemain yang cocok.";
    } else {
      empty.textContent = "Semua pemain sudah masuk skuad.";
    }
    els.pool.append(empty);
  } else {
    for (const player of visible) els.pool.append(playerCard(player, "pool"));
  }
  els.poolCount.textContent = players.length > visible.length
    ? `${visible.length} dari ${players.length}`
    : `${players.length} tersedia`;
}

function renderSquad() {
  let total = 0;
  for (const pos of POSITIONS) {
    const ids = state.selected[pos] || [];
    total += ids.length;
    const container = document.getElementById(`sb-drop-${pos}`);
    container.innerHTML = "";
    if (!ids.length) {
      const empty = document.createElement("div");
      empty.className = "sb-empty";
      empty.textContent = "Tarik pemain ke sini";
      container.append(empty);
    } else {
      for (const id of ids) {
        const player = playerById(id);
        if (player) container.append(playerCard(player, "squad"));
      }
    }
    const need = document.getElementById(`sb-need-${pos}`);
    need.textContent = `${ids.length}/${NEED[pos]}`;
    need.classList.toggle("sb-full", ids.length >= NEED[pos]);
  }
  els.squadCount.textContent = `${total}/${SQUAD_SIZE} dipilih`;
}

function renderAll() {
  renderSummary();
  renderFilters();
  renderPool();
  renderSquad();
  setHeight();
}

function addPlayer(id) {
  const player = playerById(id);
  if (!player) return;
  const next = cloneSelected();
  if (next[player.pos].includes(Number(id))) return;
  if (next[player.pos].length >= NEED[player.pos]) {
    toast(`Posisi ${player.pos} sudah penuh (${NEED[player.pos]})`);
    return;
  }
  next[player.pos].push(Number(id));
  const error = validateSelection(next);
  if (error) {
    toast(error);
    return;
  }
  state.selected = next;
  renderAll();
  commit();
}

function removePlayer(id) {
  const pid = Number(id);
  const next = cloneSelected();
  for (const pos of POSITIONS) {
    next[pos] = next[pos].filter((x) => x !== pid);
  }
  state.selected = next;
  renderAll();
  commit();
}

function canMove(evt) {
  const from = evt.from.dataset.target;
  const to = evt.to.dataset.target;
  const id = Number(evt.dragged.dataset.id);
  const player = playerById(id);
  if (!player) return false;

  // Reordering the candidate list itself is not useful; squad order is
  // maintained by Python/roster order.
  if (from === to) return false;
  if (to === "POOL") return true;
  if (player.pos !== to) {
    toast(`${player.name} adalah ${player.pos}, bukan ${to}`);
    return false;
  }

  const next = selectedFromDom();
  if (from !== "POOL") {
    next[from] = next[from].filter((x) => x !== id);
  }
  if (!next[to].includes(id)) next[to].push(id);

  const error = validateSelection(next);
  if (error) {
    toast(error);
    return false;
  }
  return true;
}

function afterDrop(evt) {
  const from = evt.from.dataset.target;
  const to = evt.to.dataset.target;
  if (from === to) return;

  const next = selectedFromDom();
  const error = validateSelection(next);
  if (error) {
    toast(error);
    renderAll();
    return;
  }
  state.selected = next;
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
    document.getElementById("sb-pool"),
    ...POSITIONS.map((pos) => document.getElementById(`sb-drop-${pos}`)),
  ];
  for (const container of containers) {
    if (!container) continue;
    state.sortables.push(
      new Sortable(container, {
        group: { name: "sb-players", pull: true, put: true },
        animation: 150,
        draggable: ".sb-player",
        filter: ".sb-action, .sb-empty",
        preventOnFilter: true,
        ghostClass: "sb-ghost",
        chosenClass: "sb-chosen",
        dragClass: "sb-drag",
        onMove: canMove,
        onEnd: afterDrop,
      })
    );
  }
}

function buildShell() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="sb-root">
      <div class="sb-top">
        <div>
          <div class="sb-kicker">Team Builder</div>
          <div class="sb-title">Susun Skuad</div>
        </div>
        <div class="sb-stats">
          <span class="sb-stat" id="sb-count"></span>
          <span class="sb-stat" id="sb-bank"></span>
          <span class="sb-stat" id="sb-cost"></span>
          <span class="sb-stat" id="sb-clubs"></span>
        </div>
      </div>
      <div class="sb-toolbar">
        <input id="sb-search" class="sb-search" type="search" placeholder="Cari nama atau tim..." autocomplete="off" />
        <div id="sb-filters" class="sb-filters"></div>
      </div>
      <div class="sb-layout">
        <section class="sb-panel">
          <div class="sb-panel-head">
            <span>Kandidat</span>
            <span id="sb-pool-count" class="sb-muted"></span>
          </div>
          <div id="sb-pool" class="sb-list sb-pool" data-target="POOL"></div>
        </section>
        <section class="sb-panel">
          <div class="sb-panel-head">
            <span>Skuad Anda</span>
            <span id="sb-squad-count" class="sb-muted"></span>
          </div>
          <div class="sb-squad-grid">
            ${POSITIONS.map(
              (pos) => `
              <div class="sb-slot">
                <div class="sb-slot-head">
                  <span class="sb-pos sb-pos-${pos}">${pos}</span>
                  <span id="sb-need-${pos}" class="sb-muted">0/${NEED[pos]}</span>
                </div>
                <div id="sb-drop-${pos}" class="sb-list sb-drop" data-target="${pos}"></div>
              </div>`
            ).join("")}
          </div>
        </section>
      </div>
      <div id="sb-toast" class="sb-toast" role="status"></div>
    </div>
  `;

  els = {
    count: document.getElementById("sb-count"),
    bank: document.getElementById("sb-bank"),
    cost: document.getElementById("sb-cost"),
    clubs: document.getElementById("sb-clubs"),
    search: document.getElementById("sb-search"),
    filters: document.getElementById("sb-filters"),
    pool: document.getElementById("sb-pool"),
    poolCount: document.getElementById("sb-pool-count"),
    squadCount: document.getElementById("sb-squad-count"),
    toast: document.getElementById("sb-toast"),
  };

  for (const [pos, label] of [["ALL", "Semua"], ...POSITIONS.map((p) => [p, p])]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.dataset.pos = pos;
    btn.className = "sb-filter";
    btn.addEventListener("click", () => {
      state.posFilter = pos;
      renderFilters();
      renderPool();
      setHeight();
    });
    els.filters.append(btn);
  }

  els.search.addEventListener("input", () => {
    state.search = els.search.value || "";
    renderPool();
    setHeight();
  });

  app.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]");
    if (!action) return;
    const card = action.closest(".sb-player");
    if (!card) return;
    const id = Number(card.dataset.id);
    if (action.dataset.action === "add") addPlayer(id);
    else if (action.dataset.action === "remove") removePlayer(id);
  });

  initSortables();
}

function onRender(event) {
  const args = event.detail && event.detail.args ? event.detail.args : {};
  const players = Array.isArray(args.players) ? args.players : [];
  state.players = players;
  state.byId = new Map(players.map((p) => [Number(p.id), p]));
  state.budget = Number.isFinite(Number(args.budget)) ? Number(args.budget) : 1000;
  state.clubMax = Number.isFinite(Number(args.club_max)) ? Number(args.club_max) : 3;
  state.version = Number.isFinite(Number(args.version)) ? Number(args.version) : 0;
  state.selected = normalizeSelected(args.selected);
  state.ready = true;
  renderAll();
}

buildShell();
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();

if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => Streamlit.setFrameHeight()).observe(document.body);
}
