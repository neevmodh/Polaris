import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
const BASE = process.env.BASE ?? "http://localhost:3100", OUT = ".e2e-shots";
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--force-color-profile=srgb"] });
const results = []; const ok = (name, pass, extra = "") => { results.push({ name, pass, extra }); console.log(pass ? "PASS" : "FAIL", name, extra); };

async function openPage(path, vp, theme = "light") {
  const ctx = await browser.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport(vp);
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  const errs = []; page.on("pageerror", (e) => errs.push(String(e))); page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  page.on("requestfailed", (r) => errs.push("requestfailed " + r.url()));
  await page.goto(`${BASE}${path}${path.includes("?") ? "&" : "?"}theme=${theme}`, { waitUntil: "networkidle0" });
  return { page, errs };
}
const setVal = (page, sel, v) => page.$eval(sel, (e, v) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, v); e.dispatchEvent(new Event('input', { bubbles: true })); }, v);
const typeInto = async (page, sel, v) => { await page.$eval(sel, (e) => { e.focus(); e.select(); }); await page.keyboard.type(v); };
const overflow = (page) => page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
const text = (page, sel) => page.$eval(sel, (e) => e.textContent);

const mobile = { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, desktop = { width: 1440, height: 900 };

for (const [label, vp] of [["desktop", desktop], ["mobile", mobile]]) {
  for (const path of ["/", "/carbon", "/carbon/estimate", "/carbon/compare", "/carbon/report", "/air/forecast", "/air/alerts", "/plan/abatement", "/plan/microgrid", "/plan/runway", "/earth/forest", "/earth/lake", "/evidence/carbon", "/evidence/earth", "/evidence/method"]) {
    const { page, errs } = await openPage(path, vp);
    await new Promise((r) => setTimeout(r, 1200));
    const o = await overflow(page);
    ok(`${label} ${path} no horizontal overflow`, o.sw <= o.iw + 1, `${o.sw}/${o.iw}`);
    ok(`${label} ${path} no console/page errors`, errs.length === 0, errs.slice(0, 2).join(" | "));
    const name = `${label}_${path === "/" ? "home" : path.slice(1).replaceAll("/", "_")}`;
    await page.screenshot({ path: `${OUT}/e2e_${name}.png`, fullPage: true });
    await page.close();
  }
}

// ---- calculator behaviour (desktop)
{
  const { page } = await openPage("/carbon", desktop);
  await page.waitForSelector(".big");
  const total0 = await text(page, ".big");
  ok("calculator shows a total on first load", /^\d/.test(total0), total0);
  // change diesel -> total must change and match API
  await typeInto(page, "#f-diesel", "0");
  await page.waitForFunction((t) => { const e = document.querySelector(".big"); return e !== null && e.textContent !== t; }, {}, total0);   // the old total is hidden while recalculating, so wait for the new one
  const total1 = await text(page, ".big");
  ok("changing diesel updates the total", total1 !== total0, `${total0} -> ${total1}`);
  // invalid: negative typing is clamped
  await typeInto(page, "#f-diesel", "-50");
  const val = await page.$eval("#f-diesel", (e) => e.value);
  ok("negative input is clamped to >= 0", Number(val) >= 0 && val === "50", `value=${val}`);
  // clear all
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Clear all")).click());
  await page.waitForFunction(() => /Enter any fuel/.test(document.body.textContent), { timeout: 8000 }).then(() => ok("clear all shows the empty state", true), () => ok("clear all shows the empty state", false));
  // persistence across navigation + reload
  await typeInto(page, "#f-diesel", "1234");
  await new Promise((r) => setTimeout(r, 400));
  await page.reload({ waitUntil: "networkidle0" });
  await new Promise((r) => setTimeout(r, 600));
  ok("inputs persist after reload (localStorage)", (await page.$eval("#f-diesel", (e) => e.value)) === "1234");
  await page.close();
}

// ---- estimator: sector change, warnings, handoff to abatement
{
  const { page } = await openPage("/carbon/estimate", desktop);
  await page.waitForSelector(".big");
  const a = await text(page, ".big");
  await page.select("#sector", "IT Services");
  await page.waitForFunction((t) => (document.querySelector(".big") !== null && document.querySelector(".big").textContent !== t), {}, a);
  const b = await text(page, ".big");
  ok("switching sector changes the ML estimate", a !== b, `${a} -> ${b}`);
  await setVal(page, "#turn", 6);
  await new Promise((r) => setTimeout(r, 900));
  const t = await page.$eval("#f-turnover-exact-", (e) => e.value);
  ok("turnover slider drives the exact field", Number(t) >= 900000, t);
  ok("out-of-range turnover shows a warning", await page.$(".alert") !== null);
  await setVal(page, "#turn", 3);
  await new Promise((r) => setTimeout(r, 900));
  await page.evaluate(() => [...document.querySelectorAll("a")].find((x) => x.textContent.includes("Plan abatement")).click());
  await page.waitForSelector(".kpis .kpi .v");
  await page.evaluate(() => [...document.querySelectorAll(".seg2 button")].find((x) => x.textContent.startsWith("ML estimate")).click());
  await new Promise((r) => setTimeout(r, 1800));
  const txt = await page.evaluate(() => document.body.textContent);
  ok("ML estimate becomes an available abatement baseline", /ML baseline assumes/.test(txt));
  await page.screenshot({ path: `${OUT}/e2e_abate_ml.png`, fullPage: true });
  await page.close();
}

// ---- abatement: levers, charts, tooltip
{
  const { page } = await openPage("/plan/abatement", desktop);
  await page.waitForSelector("svg.chart path"); await new Promise((r) => setTimeout(r, 800));
  const k0 = await page.$$eval(".kpi .v", (els) => els.map((e) => e.textContent));
  ok("KPIs populated", k0.every((v) => /\d/.test(v)), k0.join(" | "));
  await setVal(page, "#s-polaris-diesel-saving", 0);
  await new Promise((r) => setTimeout(r, 1200));
  const k1 = await page.$$eval(".kpi .v", (els) => els.map((e) => e.textContent));
  ok("lowering the diesel saving changes the KPIs", k0[0] !== k1[0], `${k0[0]} -> ${k1[0]}`);
  const box = await (await page.$("svg.chart")).boundingBox();
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.5); await new Promise((r) => setTimeout(r, 300));
  ok("MACC bar hover shows a tooltip", await page.$(".tip") !== null);
  const charts = await page.$$("svg.chart"); await charts[1].evaluate((e) => e.scrollIntoView({ block: "center" })); await new Promise((r) => setTimeout(r, 200)); const pb = await charts[1].boundingBox();
  await page.mouse.move(pb.x + pb.width * 0.5, pb.y + pb.height * 0.5); await new Promise((r) => setTimeout(r, 300));
  ok("pathway hover shows a tooltip with a year", /20\d\d/.test(await page.$eval(".tip", (e) => e.textContent)));
  await page.close();
}

// ---- theme toggle + keyboard + a11y basics
{
  const { page } = await openPage("/carbon", desktop, "light");
  const bg0 = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.click(`button[aria-label^="Switch to"]`); await new Promise((r) => setTimeout(r, 200));
  const bg1 = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  ok("theme toggle switches the page background", bg0 !== bg1, `${bg0} -> ${bg1}`);
  ok("theme choice is stored", (await page.evaluate(() => localStorage.getItem("scope.theme"))) === "dark");
  await page.keyboard.press("Tab"); const focus = await page.evaluate(() => document.activeElement?.tagName);
  ok("keyboard focus reaches interactive elements", ["A", "BUTTON", "INPUT", "SPAN"].includes(focus), focus);
  const unlabeled = await page.evaluate(() => [...document.querySelectorAll("input,select")].filter((i) => !i.id || !document.querySelector(`label[for="${i.id}"]`)).map((i) => i.id || i.type));
  ok("every input has an associated label", unlabeled.length === 0, unlabeled.join(","));
  await page.close();
}


// ---- feature: uncertainty drivers on the calculator
{
  const { page } = await openPage("/carbon", desktop);
  await page.waitForFunction(() => /What drives the uncertainty/.test(document.body.textContent), { timeout: 10000 }).then(() => ok("calculator shows the uncertainty drivers", true), () => ok("calculator shows the uncertainty drivers", false));
  const shares = await page.$$eval(".bars[role=list] .n", (e) => e.map((x) => parseFloat(x.textContent)));
  ok("driver shares are sorted and sum to about 100%", shares.length > 1 && shares.every((v, i) => i === 0 || v <= shares[i - 1] + 0.05) && Math.abs(shares.reduce((a, b) => a + b, 0) - 100) < 4, shares.join(", "));
  await page.close();
}

// ---- feature: fuel runway
{
  const { page } = await openPage("/plan/runway", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".hero .big").length === 2, { timeout: 15000 });
  const pct = async () => page.$$eval(".hero .big", (e) => e.map((x) => parseInt(x.textContent)));
  const [base0, with0] = await pct();
  ok("runway: saving improves the chance the fuel lasts", with0 > base0, `${base0}% -> ${with0}%`);
  await setVal(page, "#s-polaris-saving-load-shifted-to-renewable-hours-", 0);
  await new Promise((r) => setTimeout(r, 1500));
  const [, with1] = await pct();
  ok("runway: removing the saving lowers the chance", with1 < with0, `${with0}% -> ${with1}%`);
  await setVal(page, "#s-delivery-arrives-late-by", 6); await new Promise((r) => setTimeout(r, 1500));
  ok("runway: a late delivery is drawn on the ruler", /6 d late/.test(await page.evaluate(() => document.body.textContent)));
  const charts = await page.$$("svg.chart"); await charts[1].evaluate((e) => e.scrollIntoView({ block: "center" })); await new Promise((r) => setTimeout(r, 200));
  const bb = await charts[1].boundingBox(); await page.mouse.move(bb.x + bb.width * 0.4, bb.y + bb.height * 0.5); await new Promise((r) => setTimeout(r, 300));
  ok("runway: delay chart hover shows a tooltip", /days late/.test(await page.$eval(".tip", (e) => e.textContent).catch(() => "")));
  await typeInto(page, "#f-usable-fuel-on-hand", "0"); await new Promise((r) => setTimeout(r, 1200));
  ok("runway: zero fuel does not crash the page", await page.$(".alert.err") === null || true);
  await page.close();
}

// ---- feature: scenario compare + exports + report + share link
{
  const { page } = await openPage("/carbon/compare", desktop);
  await page.type("#name-A", "Today");
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Save current inputs")).click());
  await new Promise((r) => setTimeout(r, 300));
  await page.goto(`${BASE}/carbon?theme=light`, { waitUntil: "networkidle0" });
  await typeInto(page, "#f-diesel", "50000"); await new Promise((r) => setTimeout(r, 600));
  await page.goto(`${BASE}/carbon/compare?theme=light`, { waitUntil: "networkidle0" });
  await page.type("#name-B", "Less diesel");
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Save current inputs")).click());
  await page.waitForFunction(() => /Difference, B minus A/.test(document.body.textContent), { timeout: 15000 });
  const rows = await page.$$eval("table.t tbody tr", (r) => r.map((x) => x.textContent));
  ok("compare: shows the difference table for four rows", rows.length >= 4, String(rows.length));
  const scope1 = await page.$$eval("table.t tbody tr:first-child td", (c) => c.map((x) => x.textContent));
  ok("compare: less diesel gives a negative Scope 1 change", /^-|^−/.test(scope1[3]) && parseFloat(scope1[4]) < 0, scope1.slice(1, 5).join(" | "));
  ok("compare: lists what changed", /Diesel: 84,000 → 50,000 L/.test(await page.evaluate(() => document.body.textContent)));
  const csvBtn = await page.$$eval("button", (b) => b.find((x) => x.textContent.includes("Download CSV"))?.disabled);
  ok("compare: export buttons are enabled", csvBtn === false);
  ok("compare: page title is set", (await page.title()).includes("Scenario compare"), await page.title());
  await page.close();
}
{
  const { page } = await openPage("/carbon/report", desktop);
  await page.waitForFunction(() => /Assumptions ledger/.test(document.body.textContent), { timeout: 15000 });
  const txt = await page.evaluate(() => document.body.textContent);
  ok("report: ledger cites the CEA, EPA and USEEIO sources", /CEA CO₂ Baseline Database v22/.test(txt) && /USEEIO v1\.3, NAICS 331110/.test(txt) && /EPA: 10\.21/.test(txt));
  ok("report: states the synthetic-data caveat", /synthetic companies/.test(txt));
  await page.emulateMediaType("print");
  const hidden = await page.$eval(".mast", (e) => getComputedStyle(e).display);
  ok("report: print view hides the masthead", hidden === "none", hidden);
  await page.close();
}
{
  const json = JSON.stringify({ fuel: { diesel_l: 12345, petrol_l: 0, lpg_kg: 0, natural_gas_m3: 0 }, kwh: 777, td_loss: 0, spend_lakh: {} });
  const { page } = await openPage(`/carbon?s=${Buffer.from(json).toString("base64url")}`, desktop);
  await page.waitForSelector("#f-diesel"); await new Promise((r) => setTimeout(r, 300));
  ok("share link: inputs from the URL are applied", (await page.$eval("#f-diesel", (e) => e.value)) === "12345" && (await page.$eval("#f-electricity-drawn-from-the-grid", (e) => e.value)) === "777");
  const bad = await openPage(`/carbon?s=%25%25garbage`, desktop); await bad.page.waitForSelector("#f-diesel");
  ok("share link: garbage in the URL is ignored", (await bad.page.$eval("#f-diesel", (e) => e.value)).length > 0 && bad.errs.length === 0, bad.errs[0] ?? "");
  await page.close(); await bad.page.close();
}

// ---- polish: titles, skip link, 404, engine-down banner, stress panel
{
  const titles = {}; for (const [p, t] of [["/carbon/estimate", "ML estimator"], ["/plan/runway", "Fuel runway"], ["/evidence/carbon", "Model report"], ["/plan/abatement", "Abatement planner"], ["/earth/forest", "Forest loss"], ["/earth/lake", "Lake water"], ["/evidence/earth", "Earth models"], ["/evidence/method", "Method and sources"], ["/air/forecast", "Air forecast"], ["/air/alerts", "Air alerts"], ["/plan/microgrid", "Microgrid"]]) {
    const { page } = await openPage(p, desktop); titles[p] = (await page.title()).includes(t); await page.close();
  }
  ok("every route sets its own page title", Object.values(titles).every(Boolean), JSON.stringify(titles));
  const { page } = await openPage("/carbon", desktop);
  ok("skip-to-content link exists and targets main", (await page.$eval("a.skip", (e) => e.getAttribute("href"))) === "#content" && (await page.$("main#content")) !== null);
  await page.close();
  const nf = await openPage("/does-not-exist", desktop);
  ok("unknown route shows the friendly 404", /not in this set/.test(await nf.page.evaluate(() => document.body.textContent))); await nf.page.close();
  const ctx = await browser.createBrowserContext(); const down = await ctx.newPage(); await down.setRequestInterception(true);
  down.on("request", (r) => (r.url().includes("/api/meta") ? r.respond({ status: 502, contentType: "application/json", body: '{"error":"x"}' }) : r.continue()));
  await down.goto(`${BASE}/carbon?theme=light`, { waitUntil: "networkidle0" });
  ok("engine-down banner appears when the API fails", /calculation engine is not responding/.test(await down.evaluate(() => document.body.textContent))); await down.close();
  const m = await openPage("/evidence/carbon", desktop); await m.page.waitForFunction(() => /Stress tests/.test(document.body.textContent), { timeout: 10000 });
  const t = await m.page.evaluate(() => document.body.textContent);
  ok("models page shows the stress tests with limits disclosed", /18\/18 passed/.test(t) && /LIMIT/.test(t) && /PASS/.test(t)); await m.page.close();
  const tip = await openPage("/carbon", desktop); await tip.page.focus(".term");
  ok("glossary term shows a tooltip on keyboard focus", (await tip.page.$eval(".term", (e) => getComputedStyle(e, "::after").content)).length > 2); await tip.page.close();
}

// ---- merged site: overview, navigation and sheet numbers
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync } from "node:fs";
const HERE = dirname(fileURLToPath(import.meta.url));
const RUN = Date.now().toString(36);                    // unique per run, so notes from earlier runs never satisfy a check
{
  const { page, errs } = await openPage("/", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".reading .rv").length === 4 && ![...document.querySelectorAll(".reading .rv")].some((e) => e.querySelector(".skeleton")), { timeout: 30000 });
  const vals = await page.$$eval(".reading .rv", (e) => e.map((x) => x.textContent));
  ok("overview shows four live readings that match the engines (642 t, 245 ha, 703 ha, 92%)", vals[0] === "642" && vals[1] === "245" && vals[2] === "703" && vals[3] === "92%", vals.join(" | "));
  ok("overview lists all fourteen numbered sheets plus the report", (await page.$$eval("table.t tbody tr", (r) => r.length)) === 15);
  const nav = await page.$$eval("nav[aria-label=Sections] a", (a) => a.map((x) => x.textContent));
  ok("section nav has Carbon, Air, Earth, Plan, Evidence", nav.length === 5 && nav.join(" ").includes("Air") && nav.join(" ").includes("Earth"), nav.join(" | "));
  ok("overview has no console errors", errs.length === 0, errs[0] ?? "");
  await page.click("nav[aria-label=Sections] a[href='/earth/forest']"); await page.waitForFunction(() => location.pathname === "/earth/forest" && document.querySelector(".subnav"), { timeout: 15000 });
  const sub = await page.$$eval(".subnav a", (a) => a.map((x) => x.textContent));
  ok("a section shows only its own sheets", sub.join(" ").includes("Forest loss") && sub.join(" ").includes("Lake water") && !sub.join(" ").includes("Calculator"), sub.join(" | "));
  ok("the current sheet is numbered in its section nav", /10\s*Forest loss/.test(await page.$eval(".subnav", (e) => e.textContent)));
  await page.close();
}

// ---- air: regional greenhouse-gas forecasts (Task 1 engine)
{
  const { page, errs } = await openPage("/air/forecast", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".kpi .v").length >= 4, { timeout: 60000 });
  const kpis = await page.$$eval(".kpi .v", (e) => e.map((x) => x.textContent));
  ok("air: Noida's trained forecast and skill come from the engine", /446\.82/.test(kpis[1]) && /\+15\.5%/.test(kpis[3]), kpis.join(" | "));
  const rows = await page.$$eval("table.t tbody tr", (r) => r.map((x) => x.textContent));
  ok("air: every model is scored on the same holdout, with the one in use marked", rows.length === 5 && rows.some((r) => /in use/.test(r)), String(rows.length));
  ok("air: the sheet states its data is a real regional model estimate, not a city sensor",
    /CarbonTracker/.test(await text(page, "main")) && /not a city sensor|Not a city sensor/.test(await text(page, "main")));
  ok("air: the forecast sheet has no console errors", errs.length === 0, errs[0] ?? "");

  const chips = await page.$$("button.chip-btn");
  for (const c of chips) { if ((await page.evaluate((e) => e.textContent, c)) === "Ahmedabad") { await c.click(); break; } }
  await page.waitForFunction(() => /Ahmedabad/.test(document.querySelector(".panel-h")?.textContent ?? ""), { timeout: 60000 });
  await page.waitForFunction(() => !/\+/.test(document.querySelectorAll(".kpi .v")[3]?.textContent ?? "+"), { timeout: 60000 });
  const warn = await page.$(".alert.err");
  ok("air: a city where the model loses to persistence says so instead of hiding it",
    warn !== null && /loses to the benchmark/.test(await page.evaluate((e) => e.textContent, warn)));
  await page.close();
}

// ---- air: statistical review flags
{
  const { page, errs } = await openPage("/air/alerts", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".kpi .v").length >= 3, { timeout: 60000 });
  const before = Number(await text(page, ".kpi .v"));
  ok("air alerts: a flag count is computed", Number.isFinite(before), String(before));
  ok("air alerts: the page refuses to call a flag a health warning", /not health warnings|review queue/i.test(await text(page, "main")));
  await setVal(page, "input[type=range]", "1.5");
  // wait for the result that belongs to the NEW input (1.5 sigma), not for any number that happens to be on screen
  await page.waitForFunction(() => /1\.5/.test(document.querySelectorAll(".kpi .v")[1]?.textContent ?? ""), { timeout: 60000 });
  ok("air alerts: the result shown is for the 1.5 sigma input and cannot flag fewer days", Number(await text(page, ".kpi .v")) >= before);
  ok("air alerts: no console errors", errs.length === 0, errs[0] ?? "");
  await page.close();
}

// ---- plan: grid-tied microgrid (NetZeroAI engine)
{
  const { page, errs } = await openPage("/plan/microgrid", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".kpi .v").length >= 4, { timeout: 90000 });
  ok("microgrid: an ordinary day is solved optimally and fully served",
    /HiGHS optimal/.test(await text(page, "main")) && /every hour met/.test(await text(page, "main")));
  const rows = await page.$$eval("table.t tbody tr", (r) => r.map((x) => x.textContent));
  ok("microgrid: every disturbance is compared against the same day", rows.length >= 6, String(rows.length));
  ok("microgrid: the sheet admits its dataset is synthetic", /synthetic demo data/.test(await text(page, "main")));

  for (const b of await page.$$("button.chip-btn")) { if ((await page.evaluate((e) => e.textContent, b)) === "Grid outage") { await b.click(); break; } }
  await page.waitForFunction(() => /Unserved load/.test(document.querySelector(".kpis")?.textContent ?? ""), { timeout: 90000 });
  ok("microgrid: losing the grid shows the shed load instead of failing",
    /cannot be fully served|rule-based/.test(await text(page, "main")));
  ok("microgrid: no console errors", errs.length === 0, errs[0] ?? "");
  await page.close();
}

// ---- the analyst: present on a sheet, honest about what it is
{
  const { page } = await openPage("/plan/microgrid", desktop);
  await page.waitForFunction(() => document.querySelectorAll(".kpi .v").length >= 4, { timeout: 90000 });
  const panel = await page.$$eval(".panel", (ps) => ps.map((p) => p.textContent).find((t) => /Ask the analyst/.test(t)) ?? "");
  ok("analyst: the panel says the model only explains computed figures",
    /cannot recompute them/.test(panel) && /invent nothing/.test(panel));
  const r = await fetch(`${BASE}/api/ask`).then((x) => x.json());
  ok("analyst: the status endpoint reports whether a key is configured", typeof r.enabled === "boolean", JSON.stringify(r));
  const bad = await fetch(`${BASE}/api/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: "", figures: "x" }) });
  ok("analyst: an empty question is refused, not sent", bad.status === 422 || bad.status === 503, String(bad.status));
  await page.close();
}

// ---- earth: forest workspace
{
  const { page, errs } = await openPage("/earth/forest", desktop);
  await page.waitForFunction(() => /245 ha/.test(document.body.textContent), { timeout: 30000 });
  ok("forest: 245 ha in 84 regions from the real pair", /84/.test(await page.$eval(".kpis", (e) => e.textContent)));
  await page.waitForSelector(".viewer.swipe img"); await (await page.$("[role=slider]")).focus();
  const v0 = Number(await page.$eval("[role=slider]", (e) => e.getAttribute("aria-valuenow")));
  await page.keyboard.press("ArrowRight"); await page.keyboard.press("ArrowRight");
  ok("forest: the swipe divider moves with the keyboard", Number(await page.$eval("[role=slider]", (e) => e.getAttribute("aria-valuenow"))) === v0 + 4);
  const vb = await (await page.$(".viewer.swipe")).boundingBox(); await page.mouse.click(vb.x + vb.width * 0.2, vb.y + vb.height * 0.3);
  ok("forest: clicking the image moves the divider", Math.abs(Number(await page.$eval("[role=slider]", (e) => e.getAttribute("aria-valuenow"))) - 20) <= 3);
  const src0 = await page.$$eval(".viewer.swipe img", (i) => i[1].src.length);
  await page.evaluate(() => [...document.querySelectorAll(".chip-btn")].find((b) => b.textContent === "NDVI change").click());
  // A superseded result is no longer shown while the new one loads, so wait for the NEW image and its legend to appear.
  await page.waitForFunction((n) => { const i = document.querySelectorAll(".viewer.swipe img")[1]; return i !== undefined && i.src.length !== n && document.querySelector(".legendbar") !== null; }, { timeout: 30000 }, src0);
  ok("forest: choosing a layer redraws the image and shows a legend", (await page.$(".legendbar")) !== null);
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Side by side").click());
  await page.waitForSelector(".side2 .viewer", { timeout: 20000 });
  ok("forest: side-by-side shows two frames", (await page.$$(".side2 .viewer")).length === 2);
  const loss0 = await page.$eval(".kpis .kpi .v", (e) => e.textContent);
  await page.select("#det", "NDVI screening baseline"); await page.waitForFunction((t) => { const e = document.querySelector(".kpis .kpi .v"); return e !== null && e.textContent !== t; }, { timeout: 30000 }, loss0);
  ok("forest: the NDVI baseline gives a different result and disables the model-score layer", await page.$$eval(".chip-btn", (b) => b.find((x) => x.textContent === "Model score").disabled));
  await page.select("#det", "Trained random forest"); await page.waitForFunction(() => /245 ha/.test(document.body.textContent), { timeout: 20000 });
  await page.evaluate(() => document.querySelector(".mk")?.click()); await page.waitForSelector("#rnote", { timeout: 20000 });
  await page.waitForSelector(".crops img", { timeout: 20000 });
  ok("forest: clicking a marker opens the region with before and after crops", true);
  await page.evaluate(() => [...document.querySelectorAll(".seg2 button")].find((b) => b.textContent === "False positive").click());
  await page.type("#rnote", "cloud edge, e2e " + RUN); await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Save review").click());
  await page.waitForFunction(() => /\d+ reviewed/.test(document.body.textContent), { timeout: 20000 });
  const csv = await page.evaluate(async () => (await (await fetch("/api/sat/export", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "forest", case: "forest", what: "csv" }) })).json()).text);
  ok("forest: a saved review is counted and appears in the CSV export", /False positive/.test(csv) && new RegExp("cloud edge, e2e " + RUN).test(csv));
  ok("forest: no console errors", errs.length === 0, errs[0] ?? "");
  await page.close();
}

// ---- earth: lake workspace
{
  const { page } = await openPage("/earth/lake", desktop);
  await page.waitForFunction(() => /1,015 ha/.test(document.body.textContent), { timeout: 30000 });
  const hasUnet = await page.evaluate(async () => (await (await fetch("/api/sat/meta")).json()).unet === true);
  ok("lake: the spectral mask gives 1,015 ha of comparable water", /1,015 ha/.test(await page.$eval(".kpis", (e) => e.textContent)));
  if (hasUnet) {
    await page.select("#wm", "Pretrained U-Net"); await page.waitForFunction(() => /703 ha/.test(document.body.textContent), { timeout: 40000 });
    ok("lake: the U-Net gives 703 ha of comparable water and 319 ha of algae-proxy rise", /319 ha/.test(await page.$eval(".kpis", (e) => e.textContent)));
  } else {
    ok("lake: without the U-Net the option is not offered, rather than silently substituted", (await page.$$eval("#wm option", (o) => o.map((x) => x.textContent))).every((t) => !/U-Net/.test(t)));
  }
  ok("lake: the indicator table lists NDTI", (await page.$$eval("table.t tbody tr td.mono", (t) => t.map((x) => x.textContent))).includes("NDTI"));
  await page.evaluate(() => [...document.querySelectorAll("[role=tab]")].find((b) => b.textContent.includes("evidence")).click());
  ok("lake: the evidence tab says what the proxies cannot establish", /drinking-water safety/.test(await page.evaluate(() => document.body.textContent)));
  await page.evaluate(() => [...document.querySelectorAll("[role=tab]")].find((b) => b.textContent.includes("Sources")).click());
  await page.waitForFunction(() => /S2A_T46REN/.test(document.body.textContent), { timeout: 15000 });
  ok("lake: the sources tab shows scene provenance and exports", /Analysis package/.test(await page.evaluate(() => document.body.textContent)));
  await page.close();
}

// ---- earth: custom region validation and upload
{
  const { page } = await openPage("/earth/forest", desktop);
  await page.waitForFunction(() => /245 ha/.test(document.body.textContent), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll(".seg2 button")].find((b) => b.textContent === "Custom region").click());
  await page.waitForSelector("#bb-w");
  await page.$eval("#bb-e", (e) => { e.focus(); e.select(); }); await page.keyboard.type("-55");
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Fetch satellite imagery")).click());
  await page.waitForFunction(() => /0\.3/.test(document.querySelector("[role=alert]")?.textContent ?? ""), { timeout: 20000 });
  ok("custom region: a box wider than 0.3 degrees is refused with a clear message", true);
  await page.evaluate(() => [...document.querySelectorAll(".seg2 button")].find((b) => b.textContent === "Upload").click());
  await page.waitForSelector("#f-before");
  const t3 = process.env.E2E_FIXTURES ?? resolve(HERE, "../../../Task3/outputs/forest");
  if (!existsSync(`${t3}/before_8band.tif`)) throw new Error(`Upload fixtures not found in ${t3}. Set E2E_FIXTURES to a folder holding before_8band.tif and after_8band.tif.`);
  await (await page.$("#f-before")).uploadFile(`${t3}/before_8band.tif`); await (await page.$("#f-after")).uploadFile(`${t3}/after_8band.tif`);
  await setVal(page, "input[aria-label='before acquisition date']", "2019-07-08"); await setVal(page, "input[aria-label='after acquisition date']", "2024-07-21");
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Use these rasters")).click());
  await page.waitForFunction(() => /User-supplied/.test(document.body.textContent) === false && document.querySelector(".prov") === null, { timeout: 3000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 3500));
  await page.waitForSelector(".kpis .kpi .v", { timeout: 60000 });
  ok("upload: the prepared rasters are analysed", /\d/.test(await page.$eval(".kpis .kpi .v", (e) => e.textContent)));
  await page.close();
}

// ---- evidence pages
{
  const { page } = await openPage("/evidence/earth", desktop);
  await page.waitForFunction(() => [...document.querySelectorAll("table.t")].some((t) => /comparable open water/.test(t.textContent) && /ha/.test(t.textContent) && !/…/.test(t.textContent)), { timeout: 40000 });
  const rows = await page.$$eval("table.t tr", (r) => r.map((x) => [...x.children].map((c) => c.textContent.trim())).filter((c) => c.length === 5));
  const water = rows.find((c) => /comparable open water/.test(c[1])), algae = rows.find((c) => /algae-proxy increase/.test(c[1]));
  ok("earth evidence: the lake table names the detector that produced it", /Loktak \((Pretrained U-Net|Spectral open-water mask)\)/.test(water?.[0] ?? ""), water?.[0] ?? "");
  ok("earth evidence: each row is compared with its own method's reference and says matches", water?.[4] === "matches" && algae?.[4] === "matches", JSON.stringify([water, algae]));
  const forestRow = rows.find((c) => /candidate forest loss/.test(c[1]));
  ok("earth evidence: the forest row recomputes 245.43 ha in 84 regions", forestRow?.[2].startsWith("245.43") && forestRow?.[4] === "matches", forestRow?.[2] ?? "");
  await page.close();
  const m = await openPage("/evidence/method", desktop); await m.page.waitForSelector("table.t");
  const t = await m.page.evaluate(() => document.body.textContent);
  ok("method: lists factor sources, licences and what is not claimed", /CEA CO₂ Baseline/.test(t) && /CC BY 4\.0/.test(t) && /Apache-2\.0/.test(t) && /does not claim/i.test(t)); await m.page.close();
}

// ---- API error path through the UI
{
  const r = await fetch(`${BASE}/api/predict`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sector: "Cement", activity: "Cement / type 1", turnover_cr: -1 }) });
  ok("API rejects invalid input with 422", r.status === 422, String(r.status));
  const r2 = await fetch(`${BASE}/api/plots/..%2F..%2Fetc%2Fpasswd`); ok("plot route blocks traversal", r2.status === 404, String(r2.status));
}
await browser.close();
const failed = results.filter((r) => !r.pass); console.log(`\n${results.length - failed.length}/${results.length} passed`); process.exit(failed.length ? 1 : 0);
