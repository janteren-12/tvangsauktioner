// Læser data/kommunale.json og viser kommunale salg med filtre.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtNum = (n) => (n == null ? "–" : n.toLocaleString("da-DK"));
const fmtDato = (s) => (s ? new Date(s).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" }) : "–");
const today = new Date().toISOString().slice(0, 10);

let all = [];
let lastVisit = null;
try { lastVisit = localStorage.getItem("lastVisitKommunale"); } catch (e) {}

const udloebet = (a) => a.frist && a.frist < today;
const nySidenSidst = (a) => lastVisit && a.foerst_set > lastVisit;

function fillSelect(id, values) {
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "da")).forEach((v) => {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    $(id).appendChild(o);
  });
}

function filtered() {
  const q = $("f-q").value.trim().toLowerCase();
  const kat = $("f-kat").value, ld = $("f-landsdel").value, km = $("f-kommune").value;
  return all.filter((a) => {
    if (!a.paa_sitet) return false;
    if ($("f-aktiv").checked && (a.status === "solgt" || udloebet(a))) return false;
    if (q && !`${a.titel} ${a.beskrivelse} ${a.kommune}`.toLowerCase().includes(q)) return false;
    if (kat && a.kategori !== kat) return false;
    if (ld && a.landsdel !== ld) return false;
    if (km && a.kommune !== km) return false;
    if ($("f-nye").checked && a.foerst_set !== today && a.aendret !== today) return false;
    if ($("f-sidst").checked && !nySidenSidst(a)) return false;
    return true;
  });
}

function sorted(list) {
  const by = {
    nyest: (a, b) => (b.foerst_set || "").localeCompare(a.foerst_set || "") || a.kommune.localeCompare(b.kommune, "da"),
    kommune: (a, b) => a.kommune.localeCompare(b.kommune, "da") || a.titel.localeCompare(b.titel, "da"),
    frist: (a, b) => (a.frist || "9").localeCompare(b.frist || "9"),
    pris: (a, b) => (a.pris ?? Infinity) - (b.pris ?? Infinity),
  }[$("sort").value];
  return list.sort(by);
}

function badges(a) {
  let h = "";
  if (a.foerst_set === today) h += '<span class="badge">NY I DAG</span>';
  else if (nySidenSidst(a)) h += '<span class="badge">NY</span>';
  if (a.samlet_side && a.aendret && (a.aendret === today || (lastVisit && a.aendret > lastVisit))) h += '<span class="badge blue">ÆNDRET</span>';
  if (a.samlet_side) h += '<span class="badge grey">SAMLET SIDE</span>';
  if (a.status === "solgt") h += '<span class="badge grey">SOLGT</span>';
  if (a.status === "reserveret") h += '<span class="badge grey">RESERVERET</span>';
  if (udloebet(a)) h += '<span class="badge grey">FRIST UDLØBET</span>';
  return h;
}

function pris(a) {
  if (a.pris != null) return a.pris.toLocaleString("da-DK") + " kr.";
  if (a.pris_m2 != null) return a.pris_m2.toLocaleString("da-DK") + " kr./m²";
  return "–";
}

function render() {
  const list = sorted(filtered());
  $("count").textContent = `${list.length} salg`;
  $("rows").innerHTML = list.length ? list.map((a) => `
    <tr>
      <td class="wrap"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.titel)}</a>${badges(a)}
        ${a.beskrivelse ? `<div class="muted">${esc(a.beskrivelse)}</div>` : ""}</td>
      <td>${esc(a.kategori)}</td>
      <td>${esc(a.kommune)}</td>
      <td class="r">${pris(a)}</td>
      <td class="r">${fmtNum(a.areal)}</td>
      <td>${fmtDato(a.frist)}</td>
      <td>${fmtDato(a.foerst_set)}</td>
    </tr>`).join("") : '<tr><td colspan="7" class="empty">Ingen salg matcher filtrene.</td></tr>';
}

async function init() {
  const [data, meta] = await Promise.all([
    fetch("data/kommunale.json").then((r) => r.json()),
    fetch("data/kommunale_meta.json").then((r) => r.json()).catch(() => null),
  ]);
  all = data;
  if (meta) {
    $("updated").textContent = "Senest opdateret " + new Date(meta.opdateret).toLocaleString("da-DK", { dateStyle: "medium", timeStyle: "short" }) + ".";
    $("coverage").textContent = `Dækker ${meta.kommuner.length} kommuner: ${meta.kommuner.join(", ")}.`;
  }
  const live = all.filter((a) => a.paa_sitet);
  fillSelect("f-landsdel", live.map((a) => a.landsdel));
  fillSelect("f-kommune", live.map((a) => a.kommune));
  document.querySelectorAll(".filters input, .filters select, #sort").forEach((el) => el.addEventListener("input", render));
  $("reset").onclick = () => {
    document.querySelectorAll(".filters input").forEach((i) => (i.type === "checkbox" ? (i.checked = i.id === "f-aktiv") : (i.value = "")));
    document.querySelectorAll(".filters select").forEach((s) => (s.value = ""));
    render();
  };
  render();
  try { localStorage.setItem("lastVisitKommunale", today); } catch (e) {}
}
init().catch((e) => { $("count").textContent = "Kunne ikke læse data: " + e.message; });
