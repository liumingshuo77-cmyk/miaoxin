"use strict";

const {
  defaultKind,
  salaryForDay,
  standardSeconds,
  dayRate,
  workdayCount,
  remainingShiftPay,
  projectedSalary,
  spentThrough,
  rentPerDay,
  rentThrough,
  salePnl,
  realizedOn,
  realizedThrough,
} = require("./app.js");

let failed = 0;
function assertClose(actual, expected, name) {
  const delta = Math.abs(actual - expected);
  if (delta > 0.001) {
    failed += 1;
    console.error("FAIL", name, actual, "expected", expected, "delta", delta);
  }
}
function assertEqual(actual, expected, name) {
  if (actual !== expected) {
    failed += 1;
    console.error("FAIL", name, actual, "expected", expected);
  }
}

const settings = {
  salary: 21000,
  start: "09:00",
  end: "18:00",
  lunchStart: "12:00",
  lunchEnd: "13:30",
  deductLunch: true,
  weekdays: [1, 2, 3, 4, 5],
  useHoliday: true,
  ot: 1.5,
  leaves: {},
};

const weekdays = {
  "2026-01-01": 4,
  "2026-01-04": 0,
  "2026-02-14": 6,
  "2026-02-15": 0,
  "2026-02-23": 1,
  "2026-02-28": 6,
  "2026-04-04": 6,
  "2026-04-06": 1,
  "2026-05-01": 5,
  "2026-05-05": 2,
  "2026-05-09": 6,
  "2026-06-19": 5,
  "2026-09-20": 0,
  "2026-09-25": 5,
  "2026-10-01": 4,
  "2026-10-07": 3,
  "2026-10-10": 6,
  "2026-11-04": 3,
};
for (const [iso, day] of Object.entries(weekdays)) {
  const [y, m, d] = iso.split("-").map(Number);
  assertEqual(new Date(y, m - 1, d).getDay(), day, iso + " weekday");
}

assertEqual(defaultKind("2026-01-02", settings), "off", "jan 2 holiday");
assertEqual(defaultKind("2026-01-04", settings), "work", "jan 4 makeup");
assertEqual(defaultKind("2026-02-14", settings), "work", "feb 14 makeup");
assertEqual(defaultKind("2026-02-16", settings), "off", "feb 16 spring");
assertEqual(defaultKind("2026-10-01", settings), "off", "oct 1");
assertEqual(defaultKind("2026-10-10", settings), "work", "oct 10 makeup");
assertEqual(defaultKind("2026-01-02", { ...settings, useHoliday: false }), "work", "holiday off switch");
assertEqual(workdayCount(2026, 11, settings), 21, "nov workdays");
assertEqual(standardSeconds(settings), 27000, "standard seconds");
assertClose(dayRate(2026, 11, settings), 1000, "day rate");

function at(h, min) {
  return new Date(2026, 10, 4, h, min, 0, 0).getTime();
}
const day = "2026-11-04";

assertClose(salaryForDay(day, settings, { [day]: [{ start: at(9, 0), end: at(12, 0) }] }, at(12, 0)), 400, "morning");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(9, 0), end: at(13, 30) }] }, at(13, 30)), 400, "through lunch");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(12, 0), end: at(13, 30) }] }, at(13, 30)), 0, "lunch only");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(9, 0), end: at(18, 0) }] }, at(18, 0)), 1000, "full shift");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(8, 30), end: at(18, 0) }] }, at(18, 0)), 1000, "early does not add");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(9, 30), end: at(18, 0) }] }, at(18, 0)), 1000 * 7 / 7.5, "late 30");
assertClose(salaryForDay(day, settings, { [day]: [{ start: at(9, 0), end: at(19, 0) }] }, at(19, 0)), 1200, "one hour ot");

const paid = { ...settings, leaves: { [day]: "paid" } };
assertClose(salaryForDay(day, paid, { [day]: [{ start: at(9, 0), end: at(12, 0) }] }, at(12, 0)), 1000, "paid leave");
const unpaid = { ...settings, leaves: { [day]: "unpaid" } };
assertClose(salaryForDay(day, unpaid, { [day]: [{ start: at(9, 0), end: at(18, 0) }] }, at(18, 0)), 0, "unpaid leave");

const sunday = "2026-11-08";
const sunStart = new Date(2026, 10, 8, 10, 0, 0, 0).getTime();
const sunEnd = new Date(2026, 10, 8, 12, 0, 0, 0).getTime();
assertClose(salaryForDay(sunday, settings, { [sunday]: [{ start: sunStart, end: sunEnd }] }, sunEnd), 400, "sunday ot");

assertClose(remainingShiftPay(day, settings, at(8, 0)), 1000, "remain before shift");
assertClose(remainingShiftPay(day, settings, at(12, 30)), 600, "remain at lunch");
assertClose(remainingShiftPay(day, settings, at(19, 0)), 0, "remain after shift");

let restOfMonth = 0;
for (let d = 4; d <= 30; d += 1) {
  const iso = `2026-11-${String(d).padStart(2, "0")}`;
  if (defaultKind(iso, settings) === "work") restOfMonth += 1000;
}
assertEqual(restOfMonth, 19000, "remaining workday paydays");
assertClose(projectedSalary(settings, {}, new Date(2026, 10, 4, 8, 0, 0)), 19000, "forecast at 8:00");

let afterToday = 0;
for (let d = 5; d <= 30; d += 1) {
  const iso = `2026-11-${String(d).padStart(2, "0")}`;
  if (defaultKind(iso, settings) === "work") afterToday += 1000;
}
assertClose(projectedSalary(settings, {}, new Date(2026, 10, 4, 20, 0, 0)), afterToday, "forecast after shift");

assertClose(rentPerDay(2026, 11, { rent: "3000" }), 100, "nov rent per day");
assertClose(rentThrough(2026, 11, "2026-11-04", { rent: "3000" }), 400, "rent through the 4th");
assertClose(rentThrough(2026, 11, "2026-11-30", { rent: "3000" }), 3000, "full month rent");
assertClose(rentPerDay(2026, 2, { rent: "2800" }), 100, "february rent per day");
assertClose(rentThrough(2026, 11, "2026-10-31", { rent: "3000" }), 0, "rent before month");

const sold = { qty: "100", cost: "10", sell: "12.5", fx: 1, date: "2026-11-04" };
assertClose(salePnl(sold), 250, "sale profit");
assertClose(realizedOn([sold, { qty: "10", cost: "1", sell: "2", fx: 1, date: "2026-11-03" }], "2026-11-04"), 250, "realized today");
assertClose(realizedThrough([
  sold,
  { qty: "10", cost: "1", sell: "3", fx: 1, date: "2026-11-01" },
  { qty: "10", cost: "1", sell: "9", fx: 1, date: "2026-11-05" },
  { qty: "10", cost: "1", sell: "9", fx: 1, date: "2026-10-31" },
], 2026, 11, "2026-11-04"), 270, "realized through the 4th");

assertClose(spentThrough({
  "2026-11-03": "40",
  "2026-11-04": "10.5",
  "2026-11-05": "99",
  "2026-10-31": "100",
}, 2026, 11, "2026-11-04"), 50.5, "spent through today");

if (failed) {
  console.error(failed + " failed");
  process.exit(1);
}
console.log("ok");
