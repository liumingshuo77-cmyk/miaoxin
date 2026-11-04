"use strict";

// 2026 年放假调休：国务院办公厅国办发明电〔2025〕7号
const HOLIDAY_OFF = {
  "2026-01-01": "元旦", "2026-01-02": "元旦", "2026-01-03": "元旦",
  "2026-02-15": "春节", "2026-02-16": "春节", "2026-02-17": "春节", "2026-02-18": "春节",
  "2026-02-19": "春节", "2026-02-20": "春节", "2026-02-21": "春节", "2026-02-22": "春节", "2026-02-23": "春节",
  "2026-04-04": "清明", "2026-04-05": "清明", "2026-04-06": "清明",
  "2026-05-01": "劳动节", "2026-05-02": "劳动节", "2026-05-03": "劳动节", "2026-05-04": "劳动节", "2026-05-05": "劳动节",
  "2026-06-19": "端午", "2026-06-20": "端午", "2026-06-21": "端午",
  "2026-09-25": "中秋", "2026-09-26": "中秋", "2026-09-27": "中秋",
  "2026-10-01": "国庆", "2026-10-02": "国庆", "2026-10-03": "国庆", "2026-10-04": "国庆",
  "2026-10-05": "国庆", "2026-10-06": "国庆", "2026-10-07": "国庆",
};
const MAKEUP = {
  "2026-01-04": "调休", "2026-02-14": "调休", "2026-02-28": "调休",
  "2026-05-09": "调休", "2026-09-20": "调休", "2026-10-10": "调休",
};

const STATE_KEY = "miaoxin.state.v1";
const QUOTE_KEY = "miaoxin.quotes.v1";

function pad(n) { return String(n).padStart(2, "0"); }
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
function parseISODate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function shiftDays(iso, delta) {
  const d = parseISODate(iso);
  d.setDate(d.getDate() + delta);
  return isoDate(d);
}
function prettyDate(iso) {
  const d = parseISODate(iso);
  return (d.getMonth() + 1) + "月" + d.getDate() + "日";
}
function daysInMonth(y, m) { return new Date(y, m, 0).getDate(); }
function monthKeys(y, m) {
  const n = daysInMonth(y, m);
  const keys = [];
  for (let d = 1; d <= n; d += 1) keys.push(y + "-" + pad(m) + "-" + pad(d));
  return keys;
}
function num(v) {
  if (typeof v === "number") return isFinite(v) ? v : 0;
  if (v == null) return 0;
  const n = parseFloat(String(v).replace(/,/g, ""));
  return isFinite(n) ? n : 0;
}
function timeToMin(hhmm) {
  const [h, m] = String(hhmm || "0:0").split(":").map(Number);
  if (!isFinite(h) || !isFinite(m)) return 0;
  return h * 60 + m;
}
function atMin(iso, minutes) {
  const d = parseISODate(iso);
  return d.getTime() + minutes * 60000;
}
function overlapMs(a1, a2, b1, b2) {
  return Math.max(0, Math.min(a2, b2) - Math.max(a1, b1));
}
function otMult(settings) {
  if (settings.ot === "" || settings.ot == null) return 1;
  const n = Number(settings.ot);
  if (!isFinite(n)) return 1;
  return Math.min(3, Math.max(0, n));
}
function defaultKind(iso, settings) {
  if (settings.useHoliday !== false && Object.prototype.hasOwnProperty.call(MAKEUP, iso)) return "work";
  if (settings.useHoliday !== false && Object.prototype.hasOwnProperty.call(HOLIDAY_OFF, iso)) return "off";
  const dow = parseISODate(iso).getDay();
  const days = (settings.weekdays || [1, 2, 3, 4, 5]).map(Number);
  return days.includes(dow) ? "work" : "off";
}
function kindOf(iso, settings) {
  const o = settings.leaves && settings.leaves[iso];
  if (o === "paid" || o === "unpaid" || o === "off" || o === "work") return o;
  return defaultKind(iso, settings);
}
function workdayCount(y, m, settings) {
  return monthKeys(y, m).filter((k) => defaultKind(k, settings) === "work").length;
}
function dayRate(y, m, settings) {
  const n = workdayCount(y, m, settings);
  if (n <= 0) return 0;
  return num(settings.salary) / n;
}
function standardSeconds(settings) {
  const start = timeToMin(settings.start);
  const end = timeToMin(settings.end);
  if (end <= start) return 0;
  let minutes = end - start;
  if (settings.deductLunch !== false) {
    const ls = Math.max(timeToMin(settings.lunchStart), start);
    const le = Math.min(timeToMin(settings.lunchEnd), end);
    if (le > ls) minutes -= le - ls;
  }
  return minutes * 60;
}
function payableWindows(iso, settings, kind) {
  const dayStart = parseISODate(iso).getTime();
  const dayEnd = dayStart + 86400000;
  const shiftStart = atMin(iso, timeToMin(settings.start));
  const shiftEnd = atMin(iso, timeToMin(settings.end));
  const mult = otMult(settings);
  if (kind === "off") return [{ start: dayStart, end: dayEnd, mult: mult, bucket: "extra" }];
  if (!(shiftEnd > shiftStart)) return [];
  const windows = [];
  const lunchS = atMin(iso, timeToMin(settings.lunchStart));
  const lunchE = atMin(iso, timeToMin(settings.lunchEnd));
  const deduct = settings.deductLunch !== false && lunchE > lunchS;
  if (!deduct) {
    windows.push({ start: shiftStart, end: shiftEnd, mult: 1, bucket: "shift" });
  } else {
    const ls = Math.max(lunchS, shiftStart);
    const le = Math.min(lunchE, shiftEnd);
    if (le <= ls) windows.push({ start: shiftStart, end: shiftEnd, mult: 1, bucket: "shift" });
    else {
      if (ls > shiftStart) windows.push({ start: shiftStart, end: ls, mult: 1, bucket: "shift" });
      if (shiftEnd > le) windows.push({ start: le, end: shiftEnd, mult: 1, bucket: "shift" });
    }
  }
  windows.push({ start: shiftEnd, end: dayEnd, mult: mult, bucket: "ot" });
  return windows.filter((w) => w.end > w.start);
}
function accumulate(iso, settings, sessions, nowMs) {
  const kind = kindOf(iso, settings);
  const dt = parseISODate(iso);
  const rateDay = dayRate(dt.getFullYear(), dt.getMonth() + 1, settings);
  const std = standardSeconds(settings);
  if (kind === "paid") return { pay: rateDay, shiftSec: std, otSec: 0, extraSec: 0, kind: kind };
  if (kind === "unpaid") return { pay: 0, shiftSec: 0, otSec: 0, extraSec: 0, kind: kind };
  const secRate = std > 0 ? rateDay / std : 0;
  const dayStart = dt.getTime();
  const dayEnd = dayStart + 86400000;
  let pay = 0, shiftSec = 0, otSec = 0, extraSec = 0;
  for (const seg of (sessions && sessions[iso]) || []) {
    const a = Math.max(seg.start, dayStart);
    let b = seg.end == null ? nowMs : seg.end;
    b = Math.min(b, nowMs, dayEnd);
    if (b <= a) continue;
    for (const w of payableWindows(iso, settings, kind)) {
      const sec = overlapMs(a, b, w.start, w.end) / 1000;
      if (sec <= 0) continue;
      pay += sec * secRate * w.mult;
      if (w.bucket === "shift") shiftSec += sec;
      else if (w.bucket === "ot") otSec += sec;
      else extraSec += sec;
    }
  }
  return { pay: pay, shiftSec: shiftSec, otSec: otSec, extraSec: extraSec, kind: kind };
}
function salaryForDay(iso, settings, sessions, nowMs) {
  return accumulate(iso, settings, sessions, nowMs).pay;
}
function remainingShiftPay(iso, settings, nowMs) {
  const dt = parseISODate(iso);
  const std = standardSeconds(settings);
  const rate = std > 0 ? dayRate(dt.getFullYear(), dt.getMonth() + 1, settings) / std : 0;
  let pay = 0;
  for (const w of payableWindows(iso, settings, "work")) {
    if (w.bucket !== "shift") continue;
    pay += overlapMs(nowMs, nowMs + 86400000, w.start, w.end) / 1000 * rate;
  }
  return pay;
}
function monthSalary(settings, sessions, now) {
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const today = isoDate(now);
  let sum = 0;
  for (const k of monthKeys(y, m)) {
    if (k > today) break;
    sum += salaryForDay(k, settings, sessions, now.getTime());
  }
  return sum;
}
function projectedSalary(settings, sessions, now) {
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const today = isoDate(now);
  const rate = dayRate(y, m, settings);
  const nowMs = now.getTime();
  let sum = 0;
  for (const k of monthKeys(y, m)) {
    const kind = kindOf(k, settings);
    if (k < today) sum += salaryForDay(k, settings, sessions, nowMs);
    else if (k > today) {
      if (kind === "work" || kind === "paid") sum += rate;
    } else if (kind === "paid") sum += rate;
    else if (kind === "unpaid" || kind === "off") sum += salaryForDay(k, settings, sessions, nowMs);
    else {
      const earned = salaryForDay(k, settings, sessions, nowMs);
      const segs = (sessions && sessions[k]) || [];
      const open = segs.some((s) => !s.end);
      if (open || segs.length === 0) sum += earned + remainingShiftPay(k, settings, nowMs);
      else sum += earned;
    }
  }
  return sum;
}
function spentThrough(expenses, y, m, todayIso) {
  let sum = 0;
  for (const k of monthKeys(y, m)) {
    if (k > todayIso) break;
    sum += num(expenses && expenses[k]);
  }
  return sum;
}
function rentMonth(settings) {
  return Math.max(0, num(settings && settings.rent));
}
function rentPerDay(y, m, settings) {
  const days = daysInMonth(y, m);
  if (!(days > 0)) return 0;
  return rentMonth(settings) / days;
}
function rentThrough(y, m, todayIso, settings) {
  const month = rentMonth(settings);
  if (!(month > 0)) return 0;
  const prefix = y + "-" + pad(m) + "-";
  if (!todayIso || todayIso < prefix + "01") return 0;
  if (!todayIso.startsWith(prefix)) return month;
  return rentPerDay(y, m, settings) * Number(todayIso.slice(8, 10));
}
function money(n, digits) {
  if (!isFinite(n)) return "—";
  const d = digits == null ? 2 : digits;
  const body = Math.abs(n).toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });
  return (n < 0 ? "-" : "") + "¥" + body;
}
function moneySigned(n, digits) {
  if (!isFinite(n)) return "—";
  if (n > 0) return "+" + money(n, digits);
  return money(n, digits);
}
function moneyRate(n) {
  if (!isFinite(n)) return "—";
  const digits = Math.abs(n) >= 0.01 || n === 0 ? 4 : 6;
  return money(n, digits);
}
function fmtDur(sec) {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return s + "秒";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return h + "小时" + m + "分钟";
  return m + "分钟";
}
function hm(ms) {
  const d = new Date(ms);
  return pad(d.getHours()) + ":" + pad(d.getMinutes());
}
function freshState() {
  return {
    salary: "",
    start: "09:00",
    end: "18:00",
    lunchStart: "12:00",
    lunchEnd: "13:30",
    deductLunch: true,
    weekdays: [1, 2, 3, 4, 5],
    useHoliday: true,
    ot: "1",
    holdings: [],
    leaves: {},
    sessions: {},
    expenses: {},
    rent: "",
  };
}
function hydrate(raw) {
  const base = freshState();
  if (!raw || typeof raw !== "object") return base;
  const s = Object.assign(base, raw);
  s.weekdays = Array.isArray(raw.weekdays) ? raw.weekdays.map(Number) : base.weekdays;
  s.holdings = Array.isArray(raw.holdings) ? raw.holdings : [];
  s.leaves = raw.leaves && typeof raw.leaves === "object" ? raw.leaves : {};
  s.sessions = raw.sessions && typeof raw.sessions === "object" ? raw.sessions : {};
  s.expenses = raw.expenses && typeof raw.expenses === "object" ? raw.expenses : {};
  return s;
}
function repairSessions(state, now) {
  const today = isoDate(now);
  let repaired = false;
  for (const [day, segs] of Object.entries(state.sessions)) {
    if (day >= today || !Array.isArray(segs)) continue;
    for (const seg of segs) {
      if (!seg || seg.end) continue;
      const shiftEnd = atMin(day, timeToMin(state.end));
      if (seg.start < shiftEnd) seg.end = shiftEnd;
      else seg.end = Math.min(seg.start + 3 * 3600 * 1000, parseISODate(day).getTime() + 86400000 - 1000);
      seg.autoClosed = true;
      repaired = true;
    }
  }
  return repaired;
}

let state = freshState();
let quoteBook = {};
let quoteError = "";
let saveTimer = 0;
let latestSummary = "";
let spendShown = "";
let punchShown = "";
let pending = null;
let adding = false;
let loadingQuotes = false;
let viewYear = 0;
let viewMonth = 1;
let lastTitle = 0;

function byId(id) { return document.getElementById(id); }
function desktopApi() {
  return (typeof window !== "undefined" && window.pywebview && window.pywebview.api) || null;
}
function save(immediate) {
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
  clearTimeout(saveTimer);
  const send = () => {
    const api = desktopApi();
    if (!api) return;
    const payload = JSON.parse(JSON.stringify(state));
    Promise.resolve(api.save_state(payload)).catch(() => {});
  };
  if (immediate) send();
  else saveTimer = setTimeout(send, 400);
}
function costOf(h) {
  if (h.cost === "" || h.cost == null) return null;
  const n = parseFloat(String(h.cost).replace(/,/g, ""));
  return isFinite(n) ? n : null;
}
function stockFigures() {
  let day = 0;
  let month = 0;
  let total = 0;
  let monthOk = true;
  let missingCost = false;
  const rows = [];
  if (!state.holdings.length) monthOk = true;
  for (const h of state.holdings) {
    const q = quoteBook[h.symbol];
    const qty = num(h.qty);
    const cost = costOf(h);
    if (cost == null) missingCost = true;
    const row = { h: h, q: q, day: null, month: null, total: null, pct: null };
    if (!q || !(q.price > 0) || !q.fx) {
      monthOk = false;
      rows.push(row);
      continue;
    }
    if (q.prevClose > 0) {
      row.day = (q.price - q.prevClose) * qty * q.fx;
      row.pct = (q.price - q.prevClose) / q.prevClose * 100;
      day += row.day;
    } else monthOk = false;
    if (q.monthRef > 0) {
      row.month = (q.price - q.monthRef) * qty * q.fx;
      month += row.month;
    } else monthOk = false;
    if (cost != null) {
      row.total = (q.price - cost) * qty * q.fx;
      total += row.total;
    }
    rows.push(row);
  }
  return { day: day, month: month, total: total, monthOk: monthOk, missingCost: missingCost, rows: rows };
}
function yesterdayKey(now) { return shiftDays(isoDate(now), -1); }
function saveYesterdayFromInput(now) {
  const y = yesterdayKey(now || new Date());
  const v = byId("ySpend").value.trim();
  if (!v) delete state.expenses[y];
  else state.expenses[y] = v;
}
function openSegment(iso) {
  return ((state.sessions[iso] || [])).some((s) => !s.end);
}
function clockIn(now) {
  saveYesterdayFromInput(now);
  const iso = isoDate(now);
  const kind = kindOf(iso, state);
  if (kind === "paid" || kind === "unpaid") return;
  const segs = state.sessions[iso] || [];
  if (segs.some((s) => !s.end)) return;
  segs.push({ start: now.getTime() });
  state.sessions[iso] = segs;
  save(true);
}
function clockOut(now) {
  const iso = isoDate(now);
  const segs = state.sessions[iso] || [];
  for (let i = segs.length - 1; i >= 0; i -= 1) {
    if (!segs[i].end) {
      segs[i].end = now.getTime();
      break;
    }
  }
  save(true);
}
function accruing(now) {
  const iso = isoDate(now);
  const kind = kindOf(iso, state);
  if (!openSegment(iso)) return false;
  const t = now.getTime();
  return payableWindows(iso, state, kind).some((w) => t >= w.start && t < w.end);
}
function inLunch(now) {
  const iso = isoDate(now);
  if (kindOf(iso, state) !== "work" || state.deductLunch === false || !openSegment(iso)) return false;
  const t = now.getTime();
  const ls = atMin(iso, timeToMin(state.lunchStart));
  const le = atMin(iso, timeToMin(state.lunchEnd));
  return le > ls && t >= ls && t < le;
}

function tick() {
  const now = new Date();
  const iso = isoDate(now);
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const acc = accumulate(iso, state, state.sessions, now.getTime());
  const stock = stockFigures();
  const spent = spentThrough(state.expenses, y, m, iso);
  const yKey = yesterdayKey(now);
  const ySpent = num(state.expenses[yKey]);
  const rentDay = rentPerDay(y, m, state);
  const rentSoFar = rentThrough(y, m, iso, state);
  const payToday = acc.pay;
  const earnToday = payToday + stock.day - rentDay;
  const monthPay = monthSalary(state, state.sessions, now);
  const earnMonth = monthPay + stock.month - spent - rentSoFar;
  const std = standardSeconds(state);
  const perSec = std > 0 ? dayRate(y, m, state) / std : 0;
  const weeks = ["日", "一", "二", "三", "四", "五", "六"];
  const clockText = pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
  const clock = byId("clock");
  if (clock) clock.textContent = clockText;
  byId("todayLabel").textContent = (now.getMonth() + 1) + "月" + now.getDate() + "日 周" + weeks[now.getDay()];
  byId("dayState").textContent = dayStateText(iso);
  byId("hero").textContent = money(earnToday);
  byId("hero").className = "hero-num" + (earnToday < -0.005 ? " down" : "");
  paintFood(stock.day);
  byId("payToday").textContent = money(payToday);
  const stockNode = byId("stockToday");
  stockNode.textContent = moneySigned(stock.day);
  stockNode.className = stock.day > 0.005 ? "up" : stock.day < -0.005 ? "down" : "";
  byId("monthEarn").textContent = money(earnMonth);
  byId("monthPay").textContent = money(monthPay);
  const ms = byId("monthStock");
  ms.textContent = moneySigned(stock.month);
  ms.className = stock.month > 0.005 ? "up" : stock.month < -0.005 ? "down" : "";
  byId("monthSpend").textContent = money(spent + rentSoFar);
  const rentInfo = byId("rentInfo");
  if (rentInfo) rentInfo.textContent = rentDay > 0.005 ? "房租 " + money(-rentDay) : "";
  const rentNote = byId("rentNote");
  if (rentNote) rentNote.textContent = rentDay > 0.005 ? money(rentDay) + "/天" : "";

  const live = byId("live");
  if (accruing(now)) {
    live.hidden = false;
    live.className = "on";
  } else live.hidden = true;

  byId("secLine").textContent = num(state.salary) > 0
    ? money(perSec * 3600) + "/时 · " + moneyRate(perSec) + "/秒"
    : "";
  const otLabel = byId("otLabel");
  if (otLabel && document.activeElement !== byId("ot")) otLabel.textContent = otMult(state).toFixed(1) + " 倍";

  const n = workdayCount(y, m, state);
  byId("rateNote").textContent = num(state.salary) > 0 && n > 0
    ? n + " 天 · " + money(dayRate(y, m, state)) + "/天"
    : "";

  paintShift(now, acc, std);
  paintStockEq(stock.day, perSec);
  paintForecast(now, stock.month, spent);
  paintBook(stock);
  paintSessions(iso);
  syncSpend(now, yKey, ySpent);
  syncPunchInputs(now);

  latestSummary = [
    iso + " 秒薪",
    "今日所赚 " + money(earnToday),
    "今日工资 " + money(payToday),
    "今日股票 " + moneySigned(stock.day),
    "昨日开销 " + money(ySpent),
    "今日房租 " + money(rentDay),
    "本月所赚 " + money(earnMonth),
    "本月工资 " + money(monthPay),
    "本月股票 " + moneySigned(stock.month),
    "本月开销 " + money(spent + rentSoFar),
    "秒薪 " + moneyRate(perSec),
  ].join("\n");
  if (now.getTime() - lastTitle > 1000) {
    document.title = clockText + "  " + money(earnToday);
    lastTitle = now.getTime();
  }
}
function dayStateText(iso) {
  const kind = kindOf(iso, state);
  if (kind === "paid") return "带薪";
  if (kind === "unpaid") return "无薪";
  if (state.useHoliday !== false && MAKEUP[iso] && kind === "work") return "调休";
  if (kind === "work") return "工作日";
  if (state.useHoliday !== false && HOLIDAY_OFF[iso]) return HOLIDAY_OFF[iso];
  return "休息";
}
function paintFood(day) {
  const node = byId("food");
  if (!node) return;
  const up = state.holdings.length && day > 0.005;
  const down = state.holdings.length && day < -0.005;
  node.textContent = up ? "🍖" : down ? "🍜" : "";
  if (up) node.dataset.word = "吃肉";
  else if (down) node.dataset.word = "吃面";
  else node.removeAttribute("data-word");
  node.className = "food" + (up ? " up" : down ? " down" : "");
}
function paintShift(now, acc, std) {
  const iso = isoDate(now);
  const bar = byId("barFill");
  const line = byId("shiftLine");
  if (acc.kind === "paid") {
    bar.style.width = "100%";
    line.textContent = "带薪";
    return;
  }
  if (acc.kind === "unpaid") {
    bar.style.width = "0%";
    line.textContent = "无薪";
    return;
  }
  if (acc.kind === "off") {
    bar.style.width = acc.extraSec > 0 ? "100%" : "0%";
    line.textContent = acc.extraSec > 0 ? "加班 " + fmtDur(acc.extraSec) : "";
    return;
  }
  const pct = std > 0 ? Math.min(100, acc.shiftSec / std * 100) : 0;
  bar.style.width = pct + "%";
  const segs = state.sessions[iso] || [];
  const open = segs.some((s) => !s.end);
  if (!segs.length) {
    line.textContent = "";
    return;
  }
  const parts = [fmtDur(acc.shiftSec)];
  if (std > acc.shiftSec) parts.push("差 " + fmtDur(std - acc.shiftSec));
  if (acc.otSec > 0) parts.push("加班 " + fmtDur(acc.otSec));
  if (inLunch(now)) parts.push("午休");
  else if (!open) parts.push("下班");
  line.textContent = parts.join(" · ");
}
function paintStockEq(dayPnl, perSec) {
  const node = byId("stockEq");
  if (!(perSec > 0) || Math.abs(dayPnl) < 0.01) {
    node.textContent = "";
    return;
  }
  const minutes = Math.round(Math.abs(dayPnl) / perSec / 60);
  if (minutes < 1) {
    node.textContent = "";
    return;
  }
  node.textContent = (dayPnl < 0 ? "白上 " : "多上 ") + minutes + " 分钟";
}
function paintForecast(now, stockMonth, spent) {
  const projected = projectedSalary(state, state.sessions, now);
  const left = projected + stockMonth - spent - rentMonth(state);
  byId("forecast").textContent = num(state.salary) > 0 ? "月底 " + money(left) : "";
}
function paintBook(stock) {
  const node = byId("bookTotal");
  const explain = byId("bookExplain");
  if (explain) explain.hidden = true;
  if (!state.holdings.length || (stock.missingCost && Math.abs(stock.total) < 0.005)) {
    node.textContent = "";
    node.className = "";
    return;
  }
  node.textContent = "成本 " + moneySigned(stock.total);
  node.className = stock.total > 0.005 ? "up" : stock.total < -0.005 ? "down" : "";
}
function punchLabel(iso) {
  const kind = kindOf(iso, state);
  if (kind === "paid") return "带薪";
  if (kind === "unpaid") return "无薪";
  const segs = state.sessions[iso] || [];
  if (!segs.length) return "";
  return segs.map((s) => hm(s.start) + "–" + (s.end ? hm(s.end) : "")).join("  ");
}
function paintSessions(iso) {
  const text = punchLabel(iso);
  const node = byId("punchStatus");
  if (node) node.textContent = text;
  const line = byId("sessionLine");
  if (line) line.textContent = text;
}
function syncSpend(now, yKey, ySpent) {
  const node = byId("ySpend");
  if (node && spendShown !== yKey && document.activeElement !== node) {
    node.value = state.expenses[yKey] != null ? state.expenses[yKey] : "";
    spendShown = yKey;
  }
  const sameMonth = yKey.slice(0, 7) === isoDate(now).slice(0, 7);
  const hint = byId("ySpendHint");
  if (hint) {
    hint.textContent = sameMonth ? "" : "不进本月";
  }
  const info = byId("spendInfo");
  if (info) info.textContent = ySpent ? "昨日 " + money(ySpent) : "";
}
function syncPunchInputs(now) {
  const iso = isoDate(now);
  const inn = byId("punchIn");
  const out = byId("punchOut");
  if (!inn || !out || punchShown === iso) return;
  if (document.activeElement === inn || document.activeElement === out) return;
  const seg = (state.sessions[iso] || [])[0];
  inn.value = seg ? hm(seg.start) : "";
  out.value = seg && seg.end ? hm(seg.end) : "";
  punchShown = iso;
}
function applyPunch() {
  const now = new Date();
  const iso = isoDate(now);
  const inn = byId("punchIn").value;
  const out = byId("punchOut").value;
  if (!inn) delete state.sessions[iso];
  else {
    const start = atMin(iso, timeToMin(inn));
    const seg = { start: start };
    if (out) {
      const end = atMin(iso, timeToMin(out));
      if (end > start) seg.end = end;
    }
    state.sessions[iso] = [seg];
  }
  punchShown = iso;
  save();
}

function priceFmt(n) {
  const d = n >= 100 ? 2 : 3;
  return n.toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function cls(n) {
  if (n > 0.005) return "up";
  if (n < -0.005) return "down";
  return "";
}
function renderPositions() {
  const box = byId("positions");
  box.replaceChildren();
  if (!state.holdings.length) return;
  const head = document.createElement("div");
  head.className = "pos head";
  ["持仓", "现价", "今日", "本月", "相对成本", ""].forEach((t) => {
    const s = document.createElement("span");
    s.textContent = t;
    head.append(s);
  });
  box.append(head);
  state.holdings.forEach((h) => {
    const row = document.createElement("div");
    row.className = "pos";
    row.dataset.id = h.id;
    const name = document.createElement("div");
    const nm = document.createElement("div");
    nm.className = "nm";
    nm.textContent = h.name || h.symbol;
    const code = document.createElement("div");
    code.className = "muted";
    code.textContent = h.symbol;
    const mini = document.createElement("div");
    mini.className = "mini";
    mini.append(miniField("股数", h.qty, (v) => { h.qty = v; save(); }));
    mini.append(miniField("成本", h.cost, (v) => { h.cost = v; save(); }));
    name.append(nm, code, mini);
    const px = span("px");
    const day = span("day");
    const mon = span("mon");
    const all = span("all");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "link";
    del.textContent = "移除";
    del.addEventListener("click", () => {
      state.holdings = state.holdings.filter((x) => x.id !== h.id);
      save(true);
      renderPositions();
      refreshQuotes();
    });
    row.append(name, px, day, mon, all, del);
    box.append(row);
  });
  fillQuoteCells();
}
function span(clsName) {
  const s = document.createElement("div");
  s.className = clsName;
  return s;
}
function miniField(label, value, oninput) {
  const lab = document.createElement("label");
  lab.textContent = label + " ";
  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "decimal";
  input.value = value == null ? "" : value;
  input.addEventListener("input", () => oninput(input.value));
  lab.append(input);
  return lab;
}
function fillQuoteCells() {
  const stock = stockFigures();
  for (const row of stock.rows) {
    const el = document.querySelector('[data-id="' + row.h.id + '"]');
    if (!el) {
      renderPositions();
      return;
    }
    const q = row.q;
    const nm = el.querySelector(".nm");
    if (q && q.name) {
      nm.textContent = q.name;
      if (row.h.name !== q.name) row.h.name = q.name;
    }
    const px = el.querySelector(".px");
    const day = el.querySelector(".day");
    const mon = el.querySelector(".mon");
    const all = el.querySelector(".all");
    if (!q) {
      px.textContent = "…";
      day.textContent = "—";
      mon.textContent = "—";
      all.textContent = "—";
      continue;
    }
    if (!(q.price > 0)) {
      px.textContent = "停牌";
    } else {
      const pct = row.pct == null ? "" : "  " + (row.pct > 0 ? "+" : "") + row.pct.toFixed(2) + "%";
      px.textContent = priceFmt(q.price) + " " + (q.currency || "") + pct;
    }
    px.className = "px " + cls(row.day);
    day.textContent = row.day == null ? "—" : moneySigned(row.day);
    day.className = "day " + cls(row.day);
    mon.textContent = row.month == null ? "—" : moneySigned(row.month);
    mon.className = "mon " + cls(row.month);
    all.textContent = row.total == null ? "—" : moneySigned(row.total);
    all.className = "all " + cls(row.total);
  }
  const times = state.holdings.map((h) => quoteBook[h.symbol] && quoteBook[h.symbol].time).filter(Boolean);
  let status = times.length ? "行情 " + times.slice().sort().pop() : "";
  if (quoteError) status = (status ? status + "。" : "") + quoteError;
  else if (state.holdings.length && !stock.monthOk) status += (status ? " · " : "") + "月初价未齐";
  byId("quoteStatus").textContent = status;
}
async function refreshQuotes() {
  if (loadingQuotes) return;
  if (!state.holdings.length) {
    quoteBook = {};
    quoteError = "";
    fillQuoteCells();
    return;
  }
  loadingQuotes = true;
  const symbols = state.holdings.map((h) => h.symbol).join(",");
  const month = isoDate(new Date()).slice(0, 7);
  try {
    const api = desktopApi();
    if (!api) throw new Error("no api");
    const data = await api.get_quotes(symbols, month);
    if (data.error && !(data.quotes || []).length) throw new Error(data.error);
    const next = {};
    for (const q of data.quotes || []) next[q.symbol] = q;
    quoteBook = next;
    quoteError = data.error || "";
    localStorage.setItem(QUOTE_KEY, JSON.stringify(quoteBook));
    let renamed = false;
    for (const h of state.holdings) {
      const q = quoteBook[h.symbol];
      if (q && q.name && h.name !== q.name) {
        h.name = q.name;
        renamed = true;
      }
    }
    if (renamed) save();
    if (!document.querySelector("#positions .pos")) renderPositions();
    else fillQuoteCells();
  } catch (e) {
    quoteError = "行情未连接";
    fillQuoteCells();
  } finally {
    loadingQuotes = false;
  }
}
function hideSuggest() {
  const box = byId("suggest");
  box.hidden = true;
  box.replaceChildren();
}
async function loadSuggest(q) {
  try {
    const api = desktopApi();
    if (!api) return;
    const data = await api.search(q);
    if (byId("stockQ").value.trim() !== q) return;
    const matches = data.matches || [];
    const box = byId("suggest");
    box.replaceChildren();
    if (!matches.length) {
      box.hidden = true;
      return;
    }
    matches.forEach((match) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = match.name + "  " + match.code;
      b.addEventListener("mousedown", (e) => {
        e.preventDefault();
        chooseMatch(match);
      });
      box.append(b);
    });
    box.hidden = false;
  } catch (e) {
    hideSuggest();
  }
}
function chooseMatch(match) {
  byId("stockQ").value = match.name + " " + match.code;
  pending = { q: byId("stockQ").value.trim(), symbol: match.symbol, name: match.name };
  hideSuggest();
}
async function addHolding() {
  if (adding) return;
  const q = byId("stockQ").value.trim();
  const qty = num(byId("stockQty").value);
  const costRaw = byId("stockCost").value.trim();
  if (!q || !(qty > 0)) {
    byId("quoteStatus").textContent = "填写代码和股数";
    return;
  }
  let symbol = pending && pending.q === q ? pending.symbol : "";
  let name = pending && pending.q === q ? pending.name : "";
  if (!symbol) {
    adding = true;
    try {
      const api = desktopApi();
      if (!api) throw new Error("no api");
      const data = await api.search(q);
      const matches = data.matches || [];
      if (matches.length === 1) {
        symbol = matches[0].symbol;
        name = matches[0].name;
      } else if (matches.length > 1) {
        byId("stockQ").value = q;
        await loadSuggest(q);
        byId("quoteStatus").textContent = "点选一只";
        return;
      } else {
        byId("quoteStatus").textContent = "没找到";
        return;
      }
    } catch (e) {
      byId("quoteStatus").textContent = "查找失败。";
      return;
    } finally {
      adding = false;
    }
  }
  if (state.holdings.some((h) => h.symbol === symbol)) {
    byId("quoteStatus").textContent = "已在列表";
    return;
  }
  state.holdings.push({
    id: Math.random().toString(36).slice(2, 10),
    symbol: symbol,
    name: name,
    qty: byId("stockQty").value.trim(),
    cost: costRaw,
  });
  byId("stockQ").value = "";
  byId("stockQty").value = "";
  byId("stockCost").value = "";
  pending = null;
  hideSuggest();
  save(true);
  renderPositions();
  refreshQuotes();
}

function renderCalendar() {
  const grid = byId("calGrid");
  grid.replaceChildren();
  ["一", "二", "三", "四", "五", "六", "日"].forEach((label) => {
    const d = document.createElement("div");
    d.className = "dow";
    d.textContent = label;
    grid.append(d);
  });
  const first = new Date(viewYear, viewMonth - 1, 1);
  const padCount = (first.getDay() + 6) % 7;
  for (let i = 0; i < padCount; i += 1) grid.append(document.createElement("div"));
  const today = isoDate(new Date());
  const n = daysInMonth(viewYear, viewMonth);
  for (let day = 1; day <= n; day += 1) {
    const iso = viewYear + "-" + pad(viewMonth) + "-" + pad(day);
    const btn = document.createElement("button");
    btn.type = "button";
    if (iso === today) btn.classList.add("today");
    const numEl = document.createElement("span");
    numEl.className = "d";
    numEl.textContent = String(day);
    const tag = document.createElement("span");
    tag.className = "k " + tagClass(iso);
    tag.textContent = dayTag(iso);
    btn.append(numEl, tag);
    btn.title = "默认 / 带薪 / 无薪 / 休息 / 加班";
    btn.addEventListener("click", () => cycleLeave(iso));
    grid.append(btn);
  }
  byId("calTitle").textContent = viewYear + "年" + viewMonth + "月";
  const note = byId("calNote");
  if (note) note.textContent = "";
}
function dayTag(iso) {
  const o = state.leaves[iso];
  if (o === "paid") return "带薪";
  if (o === "unpaid") return "无薪";
  if (o === "off") return "休假";
  if (o === "work") return "加班";
  if (state.useHoliday !== false && MAKEUP[iso]) return "调休";
  if (state.useHoliday !== false && HOLIDAY_OFF[iso]) return HOLIDAY_OFF[iso];
  return defaultKind(iso, state) === "work" ? "上班" : "休息";
}
function tagClass(iso) {
  const kind = kindOf(iso, state);
  if (kind === "paid") return "tag-paid";
  if (kind === "unpaid") return "tag-unpaid";
  if (kind === "off") return "tag-off";
  return "tag-work";
}
function cycleLeave(iso) {
  const order = ["", "paid", "unpaid", "off", "work"];
  const cur = state.leaves[iso] || "";
  let i = order.indexOf(cur);
  if (i < 0) i = 0;
  const next = order[(i + 1) % order.length];
  if (!next) delete state.leaves[iso];
  else {
    const def = defaultKind(iso, state);
    if ((next === "work" && def === "work") || (next === "off" && def === "off")) delete state.leaves[iso];
    else state.leaves[iso] = next;
  }
  save();
  renderCalendar();
}

function bindText(id, key) {
  const node = byId(id);
  node.addEventListener("input", () => {
    state[key] = node.value;
    save();
  });
}
function fill() {
  byId("salary").value = state.salary || "";
  byId("rent").value = state.rent || "";
  byId("start").value = state.start || "09:00";
  byId("end").value = state.end || "18:00";
  byId("lunchStart").value = state.lunchStart || "12:00";
  byId("lunchEnd").value = state.lunchEnd || "13:30";
  let ot = Number(state.ot);
  if (!isFinite(ot)) ot = 1;
  ot = Math.min(3, Math.max(0, Math.round(ot * 10) / 10));
  state.ot = String(ot);
  byId("ot").value = state.ot;
  const otLabel = byId("otLabel");
  if (otLabel) otLabel.textContent = ot.toFixed(1) + " 倍";
  byId("useHoliday").checked = state.useHoliday !== false;
  byId("deductLunch").checked = state.deductLunch !== false;
  document.querySelectorAll("#weekdays input[data-dow]").forEach((el) => {
    el.checked = state.weekdays.map(Number).includes(Number(el.dataset.dow));
  });
}
function bind() {
  ["salary", "rent", "start", "end", "lunchStart", "lunchEnd", "ot"].forEach((key) => bindText(key, key));
  byId("useHoliday").addEventListener("change", (e) => {
    state.useHoliday = e.target.checked;
    save();
    renderCalendar();
  });
  byId("deductLunch").addEventListener("change", (e) => {
    state.deductLunch = e.target.checked;
    save();
  });
  document.querySelectorAll("#weekdays input[data-dow]").forEach((el) => {
    el.addEventListener("change", () => {
      state.weekdays = Array.from(document.querySelectorAll("#weekdays input[data-dow]:checked")).map((n) => Number(n.dataset.dow));
      save();
      renderCalendar();
    });
  });
  byId("ySpend").addEventListener("input", () => {
    saveYesterdayFromInput(new Date());
    save();
  });
  byId("punchIn").addEventListener("input", applyPunch);
  byId("punchOut").addEventListener("input", applyPunch);
  byId("useShiftStart").addEventListener("click", () => {
    byId("punchIn").value = state.start || "09:00";
    byId("punchOut").value = "";
    applyPunch();
  });
  byId("ot").addEventListener("input", () => {
    const otLabel = byId("otLabel");
    if (otLabel) otLabel.textContent = otMult(state).toFixed(1) + " 倍";
  });
  byId("openBack").addEventListener("click", () => byId("flip").classList.add("is-back"));
  byId("openFront").addEventListener("click", () => byId("flip").classList.remove("is-back"));
  byId("prevMonth").addEventListener("click", () => {
    viewMonth -= 1;
    if (viewMonth < 1) { viewMonth = 12; viewYear -= 1; }
    renderCalendar();
  });
  byId("nextMonth").addEventListener("click", () => {
    viewMonth += 1;
    if (viewMonth > 12) { viewMonth = 1; viewYear += 1; }
    renderCalendar();
  });
  byId("copyBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(latestSummary);
      byId("copyBtn").textContent = "已复制";
      setTimeout(() => { byId("copyBtn").textContent = "复制"; }, 1500);
    } catch (e) {
      byId("copyBtn").textContent = "复制失败";
    }
  });
  const stockQ = byId("stockQ");
  let searchTimer = 0;
  stockQ.addEventListener("input", () => {
    pending = null;
    clearTimeout(searchTimer);
    const q = stockQ.value.trim();
    if (!q) { hideSuggest(); return; }
    searchTimer = setTimeout(() => loadSuggest(q), 250);
  });
  stockQ.addEventListener("keydown", (e) => { if (e.key === "Enter") addHolding(); });
  stockQ.addEventListener("blur", () => setTimeout(hideSuggest, 200));
  byId("addStock").addEventListener("click", addHolding);
  ["stockQty", "stockCost"].forEach((id) => {
    byId(id).addEventListener("keydown", (e) => { if (e.key === "Enter") addHolding(); });
  });
}

async function boot() {
  let remote = null;
  const api = desktopApi();
  if (api) {
    try {
      const data = await api.get_state();
      remote = data && data.state;
    } catch (e) { remote = null; }
  }
  let local = null;
  try { local = JSON.parse(localStorage.getItem(STATE_KEY) || "null"); } catch (e) { local = null; }
  try { quoteBook = JSON.parse(localStorage.getItem(QUOTE_KEY) || "{}"); } catch (e) { quoteBook = {}; }
  state = hydrate(remote || local);
  const now = new Date();
  if (repairSessions(state, now) || (!remote && local)) save(true);
  viewYear = now.getFullYear();
  viewMonth = now.getMonth() + 1;
  bind();
  fill();
  renderPositions();
  renderCalendar();
  tick();
  setInterval(tick, 100);
  refreshQuotes();
  setInterval(() => { if (!document.hidden) refreshQuotes(); }, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshQuotes(); });
}

if (typeof window !== "undefined") {
  window.addEventListener("error", (e) => {
    const n = document.getElementById("fatal");
    if (n) n.textContent = "页面出错了：" + (e.message || "");
  });
}
if (typeof document !== "undefined") {
  let booted = false;
  const start = () => {
    if (booted || !desktopApi() || document.readyState === "loading") return;
    booted = true;
    boot();
  };
  window.addEventListener("pywebviewready", start);
  document.addEventListener("DOMContentLoaded", start);
  if (document.readyState !== "loading") start();
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    defaultKind: defaultKind,
    kindOf: kindOf,
    salaryForDay: salaryForDay,
    standardSeconds: standardSeconds,
    dayRate: dayRate,
    workdayCount: workdayCount,
    remainingShiftPay: remainingShiftPay,
    projectedSalary: projectedSalary,
    spentThrough: spentThrough,
    rentPerDay: rentPerDay,
    rentThrough: rentThrough,
    HOLIDAY_OFF: HOLIDAY_OFF,
    MAKEUP: MAKEUP,
  };
}
