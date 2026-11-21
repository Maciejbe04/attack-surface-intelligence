// Records the SurfaceX demo with Polish on-screen captions.
// Usage: ./demo/record/run.sh   (resets data, records, converts to MP4)
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

const REPO = process.env.REPO;
const OUT = process.env.OUT || `${REPO}/demo/out`;
const APP = "http://localhost:8080";
const DOJO = "http://127.0.0.1:8081"; // different host than the app, so session cookies do not collide
const W = 1920, H = 1080;
mkdirSync(`${OUT}/shots`, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: `${OUT}/raw`, size: { width: W, height: H } },
  acceptDownloads: true,
});
// Caption overlay survives SPA re-renders and full navigations.
await ctx.addInitScript(() => {
  window.__cap = (text, step) => {
    let el = document.getElementById("__cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "__cap";
      el.style.cssText = "position:fixed;left:50%;bottom:36px;transform:translateX(-50%);z-index:2147483647;max-width:1500px;" +
        "background:rgba(17,20,28,.92);color:#fff;font:600 30px/1.35 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;" +
        "padding:18px 30px;border-radius:12px;border-left:8px solid #ffcc00;box-shadow:0 10px 40px rgba(0,0,0,.35);pointer-events:none";
      document.documentElement.appendChild(el);
    }
    el.innerHTML = (step ? `<span style="color:#ffcc00;margin-right:14px">${step}</span>` : "") + text;
    el.style.display = text ? "block" : "none";
  };
});
const p = await ctx.newPage();
const sleep = (ms) => p.waitForTimeout(ms);
let shotN = 0;
async function cap(text, step = "", ms = 3500) {
  await p.evaluate(([t, s]) => window.__cap?.(t, s), [text, step]);
  await sleep(ms);
}
// Slide screenshots are taken without the caption overlay.
// clip (optional): crop to the relevant region so text stays legible on slides.
async function shot(name, clip) {
  await p.evaluate(() => { const el = document.getElementById("__cap"); if (el) el.style.visibility = "hidden"; });
  await p.screenshot({ path: `${OUT}/shots/${String(++shotN).padStart(2, "0")}-${name}.png`, ...(clip ? { clip } : {}) });
  await p.evaluate(() => { const el = document.getElementById("__cap"); if (el) el.style.visibility = "visible"; });
}
const nav = (name) => p.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}$`) })
  .or(p.locator("aside").getByRole("button", { name: new RegExp(`^${name}$`) })).first();
async function go(name) { await p.evaluate(() => window.__cap?.("")); await nav(name).click(); await sleep(1200); }
async function slowType(locator, text) { await locator.fill(""); await locator.pressSequentially(text, { delay: 60 }); }
async function login(user, pass) {
  await p.goto(APP);
  await slowType(p.getByLabel("Username"), user);
  await slowType(p.getByLabel("Password"), pass);
  await p.getByRole("button", { name: "Sign in" }).click();
  await sleep(2000);
}
async function waitScanDone(maxMs = 240000) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    const row = await p.locator("table").first().locator("tbody tr").first().innerText().catch(() => "");
    if (/Completed|Failed|Partial|Paused/i.test(row)) return (Date.now() - t0) / 1000;
    await sleep(2000);
  }
  throw new Error("scan did not finish");
}
async function scrollFindings(px = 900, steps = 3) {
  for (let i = 0; i < steps; i++) { await p.mouse.wheel(0, px); await sleep(1600); }
}
async function centerOn(text) {
  await p.getByText(text, { exact: true }).first().evaluate((el) => el.scrollIntoView({ block: "center", behavior: "smooth" }));
  await sleep(1500);
}
async function filterLifecycle(value) {
  await p.locator("#findings-lifecycle").selectOption(value);
  await sleep(1800);
}

// ---------- 1. intro + login ----------
await p.goto(APP);
await cap("<b>SurfaceX</b> — Attack Surface Intelligence. Demo na lokalnym labie: 7 usług Docker w sieci 10.77.0.0/24", "", 5000);
await cap("Logowanie kontem administratora. System ma 4 role: admin · operator · analyst · viewer", "1/9", 2500);
await login("admin", "changeme");
await shot("dashboard");

// ---------- 2. modules + safe scanning ----------
await cap("Dashboard: moduły discovery — nmap (hosty, porty, usługi), httpx (HTTP, TLS), własne sygnatury YAML", "2/9", 4500);
for (const m of ["Service detection", "TLS certificate", "Custom signatures"]) {
  const cb = p.getByRole("checkbox", { name: new RegExp(m) });
  if (!(await cb.isChecked())) { await cb.scrollIntoViewIfNeeded(); await cb.check(); await sleep(700); }
}
await p.mouse.wheel(0, -3000); await sleep(600);
const portFilters = p.getByRole("button", { name: "Filters" }).nth(1);
await portFilters.click(); await sleep(800);
await cap("Bezpieczny skan: tylko sondy, bez logowania i exploitów. Limit tempa (maxRate) i timing ustawiane per moduł", "", 5000);
await shot("filters");
await portFilters.click(); await sleep(500);
await cap("Okno czasowe skanu: po przekroczeniu niedokończone batche są wstrzymywane i można je wznowić", "", 4000);

// ---------- 3. import ----------
await go("Targets");
await cap("Import listy hostów z pliku CSV (obsługiwane też JSON i TXT, do 10 000 hostów) — z przypisaniem do grupy", "3/9", 4000);
await p.setInputFiles('input[type="file"]', `${REPO}/demo/lab/targets.csv`);
await sleep(1200);
const auto = p.getByRole("checkbox", { name: /After import, queue discovery/ });
if (await auto.isChecked()) { await auto.uncheck(); await sleep(600); }
await shot("import");
await p.getByRole("button", { name: /^Import/ }).click();
await sleep(2500);
await p.mouse.wheel(0, 900); await sleep(1500);
await cap("7 hostów zaimportowanych do grupy „Lab demo” (kolumna group w CSV). Komentarze opisują właściciela i przeznaczenie", "", 4500);
await p.mouse.wheel(0, -3000); await sleep(500);

// ---------- 4. group + schedule ----------
await go("Groups");
await cap("Grupy = podział adresów na podgrupy skanowane razem. Harmonogram: co N godzin, codziennie lub co tydzień", "4/9", 4000);
await p.getByRole("button", { name: /^Schedule$|Edit schedule/ }).first().click(); await sleep(1000);
await p.locator("#schedule-frequency").selectOption("daily"); await sleep(700);
await p.locator("#schedule-time").fill("02:00"); await sleep(700);
const active = p.locator("#schedule-enabled");
if (!(await active.isChecked())) await active.check();
await shot("schedule");
await p.getByRole("button", { name: "Save schedule" }).click(); await sleep(1500);
await cap("Grupa „Lab demo” skanowana codziennie o 02:00 UTC — cyklicznie, bez udziału operatora. Teraz uruchamiamy skan ręcznie", "", 4500);
await p.getByRole("button", { name: "Scan now" }).first().click(); await sleep(1500);

// ---------- 5. scan 1 live ----------
await go("Scans");
await cap("Skan #1: cele dzielone na batche, worker uruchamia prawdziwe komendy nmap i httpx z limitem tempa — log na żywo", "5/9", 1000);
await p.locator("text=Activity console").last().scrollIntoViewIfNeeded(); await sleep(4000);
await shot("scan1-running");
const s1 = await waitScanDone();
await sleep(1500);
await shot("scan1-console");
await cap(`Skan #1 zakończony w ~${Math.round(s1)} s: liczba hostów i portów, czas, automatyczny eksport do DefectDojo`, "", 5000);

// ---------- 6. findings ----------
await p.mouse.wheel(0, -20000); await sleep(800);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(800);
await cap("Obserwacje: hosty, porty, usługi HTTP (kod, tytuł, serwer), certyfikat TLS i wykryte technologie", "6/9", 4500);
await shot("findings-1");
await centerOn("http:http://10.77.0.10:80");
await cap("Fingerprint HTTP: tytuł, kod odpowiedzi i serwer — staging, kamera IP (IoT), przekierowanie 302 do panelu /admin", "", 5500);
await shot("findings-http", { x: 240, y: 200, width: 1680, height: 680 });
await centerOn("tech:http://10.77.0.11:80:php:7.4.33");
await cap("Technologie (httpx tech-detect): WordPress 6.4.2, PHP 7.4.33 (EOL), Nginx 1.27.5, HSTS na intranecie HTTPS", "", 5500);
await shot("findings-tech", { x: 240, y: 200, width: 1680, height: 680 });
await p.mouse.wheel(0, -20000); await sleep(600);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(600);
await p.getByRole("button", { name: "Export JSON" }).click(); await sleep(1200);
await p.getByRole("button", { name: "Export CSV" }).click(); await sleep(1200);
await cap("Eksport wyników do JSON i CSV (schemat surfacex.export.v1)", "", 3500);

// ---------- 7. change the lab, scan 2 ----------
await cap("Symulujemy zmianę infrastruktury: serwer pomiarowy znika, staging dostaje nową wersję i port 8443, pojawia się nowa aplikacja", "7/9", 1000);
execFileSync(`${REPO}/demo/lab/lab.sh`, ["mutate"], { stdio: "ignore" });
await sleep(4500);
await go("Groups");
await p.getByRole("button", { name: "Scan now" }).first().click(); await sleep(1500);
await go("Scans");
await cap("Skan #2 tej samej grupy — automatyczne porównanie z poprzednim przebiegiem", "", 1000);
const s2 = await waitScanDone();
await sleep(1500);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(800);
await shot("diff-summary");
await cap(`Skan #2 (~${Math.round(s2)} s): NEW = nowe, CHANGED = zmienione, MISSING → FLAKY → GONE = znikające (po 3 przebiegach bez odpowiedzi)`, "", 6000);
for (const lc of ["NEW", "CHANGED", "MISSING"]) {
  await filterLifecycle(lc);
  const rows = await p.locator("table").nth(1).locator("tbody tr").count().catch(() => 0);
  if (rows > 0) { await cap(`Filtr ${lc}: ${rows} obserwacji`, "", 4000); await shot(`diff-${lc}`, { x: 240, y: 0, width: 1680, height: 620 }); }
}
await filterLifecycle("");

// ---------- 8. RBAC ----------
await p.mouse.wheel(0, -20000); await sleep(500);
await p.getByRole("button", { name: "Sign out" }).first().click(); await sleep(1500);
await cap("RBAC: logujemy się jako „audytor” z rolą viewer (tylko odczyt)", "8/9", 2000);
await login("audytor", "Demo-2026!");
await go("Targets");
await shot("viewer");
await cap("Rola viewer: tryb tylko do odczytu — brak formularzy dodawania i importu oraz przycisków skanu; zapis blokuje też API", "", 5500);

// ---------- 9. DefectDojo ----------
await cap("Integracja z DefectDojo: obserwacje trafiają tam jako findingi informacyjne", "9/9", 2500);
await p.goto(`${DOJO}/login`);
await slowType(p.locator("#id_username"), "admin");
await slowType(p.locator("#id_password"), "changeme");
await p.keyboard.press("Enter");
await sleep(2500);
await p.goto(`${DOJO}/finding/open`);
await sleep(2500);
await shot("defectdojo");
await cap("DefectDojo: findingi z SurfaceX (live host, open service, technologia) — gotowe do triage przez zespół bezpieczeństwa", "", 5500);
await cap("<b>SurfaceX</b> · discovery · fingerprinting · zmiany w czasie · DefectDojo · RBAC — dziękujemy!", "", 5000);

const video = p.video();
await ctx.close();
await browser.close();
console.log("VIDEO", await video.path());
