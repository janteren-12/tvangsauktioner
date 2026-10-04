// Læser data/auctions.json og viser tabel + kort med filtre.
const $ = (id) => document.getElementById(id);
const GRUPPER = {
  huse: ["villa", "rækkehus", "fritidshus", "helårsgrund"],
  lejligheder: ["ejerlejlighed", "andelslejlighed"],
  ejendomme: ["beboelsesejendom", "beboelses- og erhvervsejendom", "udlejningsejendom"],
  erhverv: ["erhverv", "landbrug", "butikslokale", "ideel anpart"],
};
const fmtKr = (n) => (n == null ? "–" : n.toLocaleString("da-DK") + " kr.");
const fmtNum = (n) => (n == null ? "–" : n.toLocaleString("da-DK"));
const fmtDato = (s) => {
  if (!s) return "–";
  const d = new Date(s);
  return d.toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" }) +
    " kl. " + d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const today = new Date().toISOString().slice(0, 10);

let all = [];
let map, layer;
let lastVisit = null;
try { lastVisit = localStorage.getItem("lastVisit"); } catch (e) {}

function gruppeOf(a) {
  const k = (a.kategori || "").toLowerCase();
  return Object.keys(GRUPPER).find((g) => GRUPPER[g].some((x) => k.includes(x))) || "erhverv";
}

function fillSelect(id, values) {
  const el = $(id);
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "da")).forEach((v) => {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    el.appendChild(o);
  });
}

function isNewSinceVisit(a) { return lastVisit && a.foerst_set > lastVisit; }

function filtered() {
  const q = $("f-q").value.trim().toLowerCase();
  const g = $("f-gruppe").value, ld = $("f-landsdel").value, rk = $("f-retskreds").value, km = $("f-kommune").value;
  const fra = $("f-fra").value, til = $("f-til").value;
  const amin = parseInt($("f-amin").value), amax = parseInt($("f-amax").value);
  const kun2 = $("f-2").checked, nye = $("f-nye").checked, sidst = $("f-sidst").checked, aflyst = $("f-aflyst").checked;
  return all.filter((a) => {
    if (!a.paa_sitet) return false;
    if (!aflyst && a.status !== "active") return false;
    if (q && !`${a.adresse} ${a.by} ${a.postnr}`.toLowerCase().includes(q)) return false;
    if (g && gruppeOf(a) !== g) return false;
    if (ld && a.landsdel !== ld) return false;
    if (rk && a.retskreds !== rk) return false;
    if (km && a.kommune !== km) return false;
    const d = (a.auktionsdato || "").slice(0, 10);
    if (fra && d < fra) return false;
    if (til && d > til) return false;
    if (!isNaN(amin) && (a.areal_bolig ?? 0) < amin) return false;
    if (!isNaN(amax) && (a.areal_bolig ?? 0) > amax) return false;
    if (kun2 && a.auktion_nr !== 2) return false;
    if (nye && a.foerst_set !== today) return false;
    if (sidst && !isNewSinceVisit(a)) return false;
    return true;
  });
}

function sorted(list) {
  const s = $("sort").value;
  const by = {
    dato: (a, b) => (a.auktionsdato || "9").localeCompare(b.auktionsdato || "9"),
    areal: (a, b) => (b.areal_bolig ?? -1) - (a.areal_bolig ?? -1),
    beloeb: (a, b) => (b.stoerstebeloeb ?? -1) - (a.stoerstebeloeb ?? -1),
    nyest: (a, b) => (b.foerst_set || "").localeCompare(a.foerst_set || "") || b.id - a.id,
  }[s];
  return list.sort(by);
}

function badges(a) {
  let h = "";
  if (a.foerst_set === today) h += '<span class="badge">NY I DAG</span>';
  else if (isNewSinceVisit(a)) h += '<span class="badge">NY</span>';
  if (a.status === "canceled") h += '<span class="badge grey">AFLYST</span>';
  if (a.status === "rescheduled") h += '<span class="badge grey">FLYTTET</span>';
  return h;
}

function render() {
  const list = sorted(filtered());
  $("count").textContent = `${list.length} auktioner`;
  $("rows").innerHTML = list.length ? list.map((a) => `
    <tr class="${a.status !== "active" ? "cancelled" : ""}">
      <td><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.adresse)}, ${esc(a.postnr)} ${esc(a.by)}</a>${badges(a)}</td>
      <td>${esc(a.kategori)}</td>
      <td>${fmtDato(a.auktionsdato)}</td>
      <td>${a.auktion_nr ?? "–"}.</td>
      <td class="r">${fmtNum(a.areal_bolig)}</td>
      <td class="r">${fmtNum(a.areal_grund)}</td>
      <td class="r">${fmtKr(a.stoerstebeloeb)}</td>
      <td>${esc(a.retskreds ?? "–")}</td>
      <td>${esc(a.landsdel ?? "–")}</td>
      <td><a href="${esc(a.url)}" target="_blank" rel="noopener">Original ↗</a></td>
    </tr>`).join("") : '<tr><td colspan="10" class="empty">Ingen auktioner matcher filtrene.</td></tr>';
  renderMap(list);
}

function renderMap(list) {
  if (!map) return;
  layer.clearLayers();
  const pts = [];
  list.filter((a) => a.lat && a.lng).forEach((a) => {
    const m = L.marker([a.lat, a.lng]).bindPopup(
      `<strong>${esc(a.adresse)}, ${esc(a.postnr)} ${esc(a.by)}</strong><br>${esc(a.kategori)}<br>` +
      `Auktion: ${fmtDato(a.auktionsdato)} (${a.auktion_nr ?? "?"}.)<br>Bolig: ${fmtNum(a.areal_bolig)} m²<br>` +
      `Størstebeløb: ${fmtKr(a.stoerstebeloeb)}<br><a href="${esc(a.url)}" target="_blank" rel="noopener">Se original ↗</a>`);
    layer.addLayer(m);
    pts.push([a.lat, a.lng]);
  });
  if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 12 });
}

function showTab(kort) {
  $("view-tabel").hidden = kort;
  $("view-kort").hidden = !kort;
  $("tab-tabel").classList.toggle("on", !kort);
  $("tab-kort").classList.toggle("on", kort);
  if (kort) {
    if (!map) {
      map = L.map("map").setView([56, 10.5], 7);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap-bidragydere" }).addTo(map);
      layer = L.layerGroup().addTo(map);
    }
    render();
    setTimeout(() => map.invalidateSize(), 50);
  }
}

async function init() {
  const [data, meta] = await Promise.all([
    fetch("data/auctions.json").then((r) => r.json()),
    fetch("data/meta.json").then((r) => r.json()).catch(() => null),
  ]);
  all = data;
  if (meta) $("updated").textContent = "Senest opdateret " + new Date(meta.opdateret).toLocaleString("da-DK", { dateStyle: "medium", timeStyle: "short" }) + ".";
  const live = all.filter((a) => a.paa_sitet);
  fillSelect("f-landsdel", live.map((a) => a.landsdel));
  fillSelect("f-retskreds", live.map((a) => a.retskreds));
  fillSelect("f-kommune", live.map((a) => a.kommune));
  document.querySelectorAll(".filters input, .filters select, #sort").forEach((el) => el.addEventListener("input", render));
  $("reset").onclick = () => { document.querySelectorAll(".filters input").forEach((i) => (i.type === "checkbox" ? (i.checked = false) : (i.value = ""))); document.querySelectorAll(".filters select").forEach((s) => (s.value = "")); render(); };
  $("tab-tabel").onclick = () => showTab(false);
  $("tab-kort").onclick = () => showTab(true);
  render();
  // husk besøget (efter visning, så "nye siden sidst" bruger forrige besøg)
  try { localStorage.setItem("lastVisit", today); } catch (e) {}
}
init().catch((e) => { $("count").textContent = "Kunne ikke læse data: " + e.message; });
