const API = "https://api.frankfurter.dev/v2/rates";
const STORAGE_KEY = "cny-fx-settings-v1";
const CACHE_KEY = "cny-fx-last-payload-v1";

const CATALOG = [
  { code: "USD", name: "美元", unit: 1 },
  { code: "EUR", name: "欧元", unit: 1 },
  { code: "JPY", name: "日元", unit: 100 },
  { code: "GBP", name: "英镑", unit: 1 },
  { code: "HKD", name: "港币", unit: 1 },
  { code: "AUD", name: "澳元", unit: 1 },
  { code: "CAD", name: "加元", unit: 1 },
  { code: "CHF", name: "瑞郎", unit: 1 },
  { code: "SGD", name: "新加坡元", unit: 1 },
  { code: "KRW", name: "韩元", unit: 100 },
  { code: "NZD", name: "新西兰元", unit: 1 },
  { code: "THB", name: "泰铢", unit: 1 },
  { code: "MYR", name: "林吉特", unit: 1 },
  { code: "TWD", name: "新台币", unit: 1 },
  { code: "MOP", name: "澳门元", unit: 1 },
  { code: "INR", name: "印度卢比", unit: 1 },
  { code: "PHP", name: "菲律宾比索", unit: 1 },
  { code: "IDR", name: "印尼盾", unit: 10000 },
  { code: "VND", name: "越南盾", unit: 10000 },
  { code: "RUB", name: "卢布", unit: 1 },
  { code: "BRL", name: "巴西雷亚尔", unit: 1 },
  { code: "ZAR", name: "南非兰特", unit: 1 },
  { code: "DKK", name: "丹麦克朗", unit: 1 },
  { code: "NOK", name: "挪威克朗", unit: 1 },
  { code: "SEK", name: "瑞典克朗", unit: 1 },
  { code: "MXN", name: "墨西哥比索", unit: 1 },
  { code: "TRY", name: "土耳其里拉", unit: 1 },
  { code: "PLN", name: "波兰兹罗提", unit: 1 },
  { code: "AED", name: "阿联酋迪拉姆", unit: 1 },
  { code: "SAR", name: "沙特里亚尔", unit: 1 },
  { code: "CNH", name: "离岸人民币", unit: 1 },
];

const DEFAULT_CODES = [
  "USD",
  "EUR",
  "JPY",
  "GBP",
  "HKD",
  "AUD",
  "CAD",
  "CHF",
  "SGD",
  "KRW",
  "NZD",
  "THB",
];

const state = {
  settings: loadSettings(),
  rows: [],
  stale: false,
  loading: false,
};

const els = {
  grid: document.getElementById("grid"),
  empty: document.getElementById("empty"),
  meta: document.getElementById("meta"),
  refreshBtn: document.getElementById("refreshBtn"),
  settingsBtn: document.getElementById("settingsBtn"),
  sortSelect: document.getElementById("sortSelect"),
  sheet: document.getElementById("sheet"),
  currencyList: document.getElementById("currencyList"),
  detail: document.getElementById("detail"),
  detailTitle: document.getElementById("detailTitle"),
  detailBody: document.getElementById("detailBody"),
};

function uniqueCatalog() {
  const seen = new Set();
  return CATALOG.filter((item) => {
    if (seen.has(item.code)) return false;
    seen.add(item.code);
    return true;
  });
}

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && Array.isArray(saved.selected) && saved.selected.length) {
      return {
        selected: saved.selected,
        range: Number(saved.range) === 7 || Number(saved.range) === 90 ? Number(saved.range) : 30,
        sort: ["default", "up", "down"].includes(saved.sort) ? saved.sort : "default",
      };
    }
  } catch {
    /* keep defaults */
  }
  return { selected: DEFAULT_CODES.slice(), range: 30, sort: "default" };
}

function saveSettings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.settings));
}

function catalogByCode(code) {
  return uniqueCatalog().find((item) => item.code === code);
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function daysAgo(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return isoDate(date);
}

function formatPrice(value) {
  if (!Number.isFinite(value)) return "—";
  const digits = value >= 100 ? 2 : value >= 10 ? 3 : value >= 1 ? 4 : 5;
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPct(value) {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function deltaClass(value) {
  if (!Number.isFinite(value) || Math.abs(value) < 0.005) return "flat";
  return value > 0 ? "up" : "down";
}

function sparkline(values, width, height) {
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = values.length === 1 ? 0 : width / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - min) / span) * (height - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = values[values.length - 1];
  const first = values[0];
  const color = last >= first ? "#ff5a4f" : "#37d67a";
  return `<svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="${points.join(" ")}"></polyline></svg>`;
}

function invertSeries(rows, unit) {
  return rows
    .filter((row) => row.rate)
    .map((row) => ({
      date: row.date,
      value: unit / row.rate,
    }));
}

function changeVs(series, rangeDays) {
  if (series.length < 2) return { current: series.at(-1)?.value, change: NaN, window: series };
  const latest = series[series.length - 1];
  const cutoff = new Date(`${latest.date}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - rangeDays);
  const cutoffIso = isoDate(cutoff);
  let baseline = series[0];
  for (const point of series) {
    if (point.date <= cutoffIso) baseline = point;
    else break;
  }
  const window = series.filter((point) => point.date >= baseline.date);
  const change = ((latest.value - baseline.value) / baseline.value) * 100;
  return { current: latest.value, change, window, asOf: latest.date, start: baseline.date };
}

function sortRows(rows) {
  const copy = rows.slice();
  if (state.settings.sort === "up") copy.sort((a, b) => (b.change || -Infinity) - (a.change || -Infinity));
  if (state.settings.sort === "down") copy.sort((a, b) => (a.change || Infinity) - (b.change || Infinity));
  if (state.settings.sort === "default") {
    const order = new Map(state.settings.selected.map((code, index) => [code, index]));
    copy.sort((a, b) => (order.get(a.code) ?? 99) - (order.get(b.code) ?? 99));
  }
  return copy;
}

function renderMeta(asOf) {
  const stale = state.stale ? " · 当前是缓存" : "";
  els.meta.textContent = asOf
    ? `外币兑人民币 · 数据日期 ${asOf}${stale}`
    : `打开后一次加载全部货币对${stale}`;
}

function renderCards() {
  const selected = state.settings.selected
    .map(catalogByCode)
    .filter(Boolean);
  els.empty.classList.toggle("hidden", selected.length > 0);
  const visible = sortRows(state.rows.filter((row) => state.settings.selected.includes(row.code)));
  els.grid.innerHTML = visible
    .map((row) => {
      const unitLabel = row.unit === 1 ? `1 ${row.name}` : `${row.unit} ${row.name}`;
      return `<button class="card" type="button" data-code="${row.code}">
        <div class="card-top">
          <div>
            <p class="pair-name">${row.name}</p>
            <p class="pair-code">${row.code} / CNY</p>
          </div>
          <div class="delta ${deltaClass(row.change)}">${formatPct(row.change)}</div>
        </div>
        <p class="price">${formatPrice(row.current)}</p>
        <p class="unit">${unitLabel} = 人民币</p>
        ${sparkline(row.window.map((point) => point.value), 280, 44)}
      </button>`;
    })
    .join("");
}

function renderSettings() {
  els.currencyList.innerHTML = uniqueCatalog()
    .map((item) => {
      const checked = state.settings.selected.includes(item.code) ? "checked" : "";
      return `<label class="currency-item">
        <div>
          <strong>${item.name}</strong>
          <span>${item.code}${item.unit === 1 ? "" : ` · 按 ${item.unit} 计价`}</span>
        </div>
        <input type="checkbox" value="${item.code}" ${checked} />
      </label>`;
    })
    .join("");
}

function openSheet(id) {
  document.getElementById(id).classList.remove("hidden");
}

function closeSheet(id) {
  document.getElementById(id).classList.add("hidden");
}

function showDetail(code) {
  const row = state.rows.find((item) => item.code === code);
  if (!row) return;
  const ranges = [7, 30, 90].map((days) => {
    const stats = changeVs(row.series, days);
    const values = stats.window.map((point) => point.value);
    const high = values.length ? Math.max(...values) : NaN;
    const low = values.length ? Math.min(...values) : NaN;
    return { days, ...stats, high, low };
  });
  els.detailTitle.textContent = `${row.name} ${row.code}`;
  els.detailBody.innerHTML = `
    <p class="price">${formatPrice(row.current)}</p>
    <p class="unit">${row.unit === 1 ? `1 ${row.name}` : `${row.unit} ${row.name}`} = 人民币 · ${row.asOf || ""}</p>
    ${sparkline(row.series.map((point) => point.value), 480, 160).replace('class="spark"', 'class="spark big-spark"')}
    <div class="stats">
      ${ranges
        .map(
          (item) => `<div class="stat">
            <small>${item.days}日</small>
            <b class="delta ${deltaClass(item.change)}">${formatPct(item.change)}</b>
          </div>`
        )
        .join("")}
    </div>
    <p class="note">区间最高 ${formatPrice(ranges[1].high)}，最低 ${formatPrice(ranges[1].low)}。这是各国央行参考价拼出来的日频数据，适合每天看趋势，不是券商成交价。</p>
  `;
  openSheet("detail");
}

function applyRangeButtons() {
  document.querySelectorAll(".seg-btn").forEach((button) => {
    button.classList.toggle("is-on", Number(button.dataset.range) === state.settings.range);
  });
}

function deriveRows(payload) {
  const grouped = new Map();
  for (const row of payload) {
    if (!grouped.has(row.quote)) grouped.set(row.quote, []);
    grouped.get(row.quote).push(row);
  }
  return uniqueCatalog()
    .map((item) => {
      const series = invertSeries((grouped.get(item.code) || []).sort((a, b) => a.date.localeCompare(b.date)), item.unit);
      const stats = changeVs(series, state.settings.range);
      return {
        ...item,
        series,
        ...stats,
      };
    })
    .filter((item) => item.series.length);
}

async function fetchRates() {
  const quotes = uniqueCatalog().map((item) => item.code).join(",");
  const url = `${API}?from=${daysAgo(120)}&base=CNY&quotes=${quotes}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error("行情接口暂时不可用");
  return response.json();
}

function usePayload(payload, stale) {
  state.stale = stale;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ savedAt: Date.now(), payload }));
  } catch {
    /* ignore quota */
  }
  state.rows = deriveRows(payload);
  const asOf = state.rows.reduce((latest, row) => (row.asOf > latest ? row.asOf : latest), "");
  renderMeta(asOf);
  renderCards();
}

async function refresh(forceNetwork = true) {
  if (state.loading) return;
  state.loading = true;
  els.refreshBtn.classList.add("is-busy");
  els.refreshBtn.textContent = "更新中";
  try {
    if (!forceNetwork) {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (cached?.payload) usePayload(cached.payload, true);
    }
    const payload = await fetchRates();
    usePayload(payload, false);
  } catch (error) {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    if (cached?.payload) {
      usePayload(cached.payload, true);
      els.meta.textContent = `无法刷新，先看上次数据。${error.message}`;
    } else {
      els.meta.textContent = `加载失败：${error.message}`;
    }
  } finally {
    state.loading = false;
    els.refreshBtn.classList.remove("is-busy");
    els.refreshBtn.textContent = "刷新";
  }
}

function bindEvents() {
  els.refreshBtn.addEventListener("click", () => refresh(true));
  els.settingsBtn.addEventListener("click", () => {
    renderSettings();
    openSheet("sheet");
  });
  els.sortSelect.value = state.settings.sort;
  els.sortSelect.addEventListener("change", (event) => {
    state.settings.sort = event.target.value;
    saveSettings();
    renderCards();
  });
  document.querySelectorAll(".seg-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.settings.range = Number(button.dataset.range);
      saveSettings();
      applyRangeButtons();
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (cached?.payload) usePayload(cached.payload, state.stale);
    });
  });
  els.grid.addEventListener("click", (event) => {
    const card = event.target.closest("[data-code]");
    if (card) showDetail(card.dataset.code);
  });
  els.currencyList.addEventListener("change", (event) => {
    const box = event.target;
    if (box.type !== "checkbox") return;
    const selected = new Set(state.settings.selected);
    if (box.checked) selected.add(box.value);
    else selected.delete(box.value);
    state.settings.selected = uniqueCatalog()
      .map((item) => item.code)
      .filter((code) => selected.has(code));
    saveSettings();
    renderCards();
    els.empty.classList.toggle("hidden", state.settings.selected.length > 0);
  });
  document.querySelectorAll("[data-close]").forEach((node) => {
    node.addEventListener("click", () => closeSheet(node.dataset.close));
  });

  let startY = 0;
  window.addEventListener(
    "touchstart",
    (event) => {
      startY = event.touches[0].clientY;
    },
    { passive: true }
  );
  window.addEventListener(
    "touchend",
    (event) => {
      const endY = event.changedTouches[0].clientY;
      if (window.scrollY <= 0 && endY - startY > 72) refresh(true);
    },
    { passive: true }
  );
}

applyRangeButtons();
bindEvents();
renderSettings();
refresh(false);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
