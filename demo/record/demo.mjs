// Records the SurfaceX demo with Polish on-screen captions.
// Usage: ./demo/record/run.sh   (resets data, records, converts to MP4)
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const REPO = process.env.REPO;
const OUT = process.env.OUT || `${REPO}/demo/out`;
const APP = "http://localhost:8080";
const DOJO = "http://127.0.0.1:8081"; // different host than the app, so session cookies do not collide
const W = 1920, H = 1080;
const PHP_KEY = "tech:http://10.77.0.11:80:php:7.4.33";
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
        "background:rgba(17,20,28,.92);color:#fff;font:500 30px/1.4 \"IBM Plex Sans\",-apple-system,Helvetica,Arial,sans-serif;" +
        "padding:16px 28px;border-radius:6px;border-left:6px solid #ffcc00;pointer-events:none";
      document.documentElement.appendChild(el);
    }
    el.innerHTML = (step ? `<span style="color:#ffcc00;margin-right:14px">${step}</span>` : "") + text;
    el.style.display = text ? "block" : "none";
  };
});
const p = await ctx.newPage();
const T0 = Date.now();
const ffMarks = []; // [start, end] seconds of scan waits, sped up in post (run.sh)
const ff = () => ffMarks.push((Date.now() - T0) / 1000);
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
await cap("To SurfaceX na naszym laboratorium: siedem kontenerów udaje kawałek sieci uczelni w 10.77.0.0/24. Logujemy się jako admin.", "", 4500);
await login("admin", "changeme");
await shot("dashboard");

// ---------- 1b. allowlist: scanner touches only approved ranges ----------
await go("Allowlist");
await cap("Najpierw zakres. Skaner ruszy tylko adresy z allowlisty, więc wpisujemy podsieć labu.", "", 3200);
await p.locator("#allowlist-value").locator("xpath=preceding-sibling::select").selectOption("cidr");
await slowType(p.locator("#allowlist-value"), "10.77.0.0/24");
await p.getByRole("button", { name: /^Add$/ }).click(); await sleep(1800);
await shot("allowlist");
await go("Dashboard");

// ---------- 2. modules + safe scanning ----------
await cap("Wybieramy moduły. Hosty i porty bada nmap, strony WWW i certyfikaty httpx. Każdy moduł ma limit tempa, a skaner tylko odpytuje usługi.", "", 5000);
for (const m of ["Service detection", "TLS certificate", "Custom signatures"]) {
  const cb = p.getByRole("checkbox", { name: new RegExp(m) });
  if (!(await cb.isChecked())) { await cb.scrollIntoViewIfNeeded(); await cb.check(); await sleep(500); }
}
await p.mouse.wheel(0, -3000); await sleep(400);
await shot("filters");

// ---------- 3. import ----------
await go("Targets");
await cap("Cele wczytujemy z pliku CSV. Ten sam import przyjmuje JSON i zwykłą listę adresów.", "", 2800);
await p.setInputFiles('input[type="file"]', `${REPO}/demo/lab/targets.csv`);
await sleep(1200);
const auto = p.getByRole("checkbox", { name: /After import, queue discovery/ });
if (await auto.isChecked()) { await auto.uncheck(); await sleep(600); }
await shot("import");
await p.getByRole("button", { name: /^Import/ }).click();
await sleep(2500);
await p.mouse.wheel(0, 900); await sleep(1500);
await cap("Siedem hostów od razu trafiło do grupy „Lab demo”, każdy z komentarzem, czym jest.", "", 3000);
await p.mouse.wheel(0, -3000); await sleep(500);

// ---------- 4. group + schedule ----------
await go("Groups");
await p.getByRole("button", { name: /^Schedule$|Edit schedule/ }).first().click(); await sleep(1000);
await p.locator("#schedule-frequency").selectOption("daily"); await sleep(700);
await p.locator("#schedule-time").fill("02:00"); await sleep(700);
const active = p.locator("#schedule-enabled");
if (!(await active.isChecked())) await active.check();
await shot("schedule");
await p.getByRole("button", { name: "Save schedule" }).click(); await sleep(1500);
await cap("Grupa „Lab demo” skanuje się teraz codziennie o 02:00 UTC. Na potrzeby nagrania odpalamy skan od razu.", "", 4000);
await p.getByRole("button", { name: "Scan now" }).first().click(); await sleep(1500);

// ---------- 5. scan 1 live ----------
await go("Scans");
await cap("Każdy host to osobna porcja pracy w kolejce. W konsoli widać dokładnie, jakie komendy uruchamia worker.", "", 1000);
await p.locator("text=Activity console").last().scrollIntoViewIfNeeded(); await sleep(4000);
await shot("scan1-running");
ff();
const s1 = await waitScanDone();
ff();
await sleep(1500);
await shot("scan1-console");
await cap(`Skan trwał ${Math.round(s1)} sekund. Wyniki same poszły też do DefectDojo.`, "", 3800);

// ---------- 6. findings ----------
await p.mouse.wheel(0, -20000); await sleep(800);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(800);
await cap("Teraz wyniki: hosty, porty, strony WWW, certyfikat i technologie. Kolumna Curiosity podpowiada, od czego zacząć.", "", 4200);
await shot("findings-1");
await centerOn("http:http://10.77.0.10:80");
await cap("Same tytuły stron zdradzają sporo: staging portalu studenta, kamerę IP i przekierowanie do panelu /admin.", "", 5000);
await shot("findings-http", { x: 240, y: 200, width: 1680, height: 680 });
await centerOn(PHP_KEY);
await cap("httpx rozpoznał WordPressa 6.4.2 i PHP 7.4.33, które od 2022 roku nie dostaje poprawek bezpieczeństwa.", "", 5000);
await shot("findings-tech", { x: 240, y: 200, width: 1680, height: 680 });
// Manual override (req. 14): tags + note survive later scans.
await p.locator("tr", { hasText: PHP_KEY }).first().getByRole("button", { name: /Add override|Edit override/ }).click(); await sleep(900);
await p.locator("#override-notes").scrollIntoViewIfNeeded();
await slowType(p.locator("#override-tags"), "eol, do-zgloszenia");
await slowType(p.locator("#override-notes"), "PHP bez wsparcia. Zgłoszone do IT.");
await shot("override-form");
await p.getByRole("button", { name: "Save override" }).click(); await sleep(1200);
await cap("Do każdego wyniku można dopisać tagi i notatkę. Dane ze skanera zostają nietknięte.", "", 3800);
await p.mouse.wheel(0, -20000); await sleep(600);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(600);
await cap("Wszystko można pobrać jako JSON albo CSV.", "", 600);
await p.getByRole("button", { name: "Export JSON" }).click(); await sleep(1000);
await p.getByRole("button", { name: "Export CSV" }).click(); await sleep(1000);

// ---------- 7. change the lab, scan 2 ----------
await cap("Zmieniamy sieć: wyłączamy serwer pomiarowy, aktualizujemy staging i stawiamy nową aplikację.", "", 1000);
execFileSync(`${REPO}/demo/lab/lab.sh`, ["mutate"], { stdio: "ignore" });
await sleep(4500);
await go("Groups");
await p.getByRole("button", { name: "Scan now" }).first().click(); await sleep(1500);
await go("Scans");
await cap("Drugi skan tej samej grupy. SurfaceX porówna go z poprzednim.", "", 1000);
ff();
const s2 = await waitScanDone();
ff();
await sleep(1500);
await p.locator("text=Findings / Changes").first().scrollIntoViewIfNeeded(); await sleep(800);
await shot("diff-summary");
await cap(`Gotowe po ${Math.round(s2)} sekundach. Każda obserwacja ma teraz status względem poprzedniego skanu.`, "", 4200);
for (const lc of ["NEW", "CHANGED", "MISSING"]) {
  await filterLifecycle(lc);
  const rows = await p.locator("table").nth(1).locator("tbody tr").count().catch(() => 0);
  const msg = { NEW: `Nowe od poprzedniego skanu: ${rows}. Jest wśród nich aplikacja pod 10.77.0.16.`, CHANGED: "Zmienił się staging: tytuł mówi teraz o wersji 2.4.0-rc1 i trybie DEBUG.", MISSING: "Serwer pomiarowy nie odpowiedział. Jeśli zamilknie w trzech skanach z rzędu, dostanie status GONE." }[lc];
  if (rows > 0) { await cap(msg, "", 4300); await shot(`diff-${lc}`, { x: 240, y: 0, width: 1680, height: 620 }); }
}
await filterLifecycle("");
await centerOn(PHP_KEY);
await cap("Notatka przy PHP przetrwała drugi skan.", "", 3200);
await shot("override-kept", { x: 240, y: 200, width: 1680, height: 680 });

// ---------- 8. RBAC ----------
await p.mouse.wheel(0, -20000); await sleep(500);
await p.getByRole("button", { name: "Sign out" }).first().click(); await sleep(1500);
await cap("Teraz to samo oczami audytora, który ma rolę viewer.", "", 3000);
await login("audytor", "Demo-2026!");
await go("Targets");
await shot("viewer");
await cap("Audytor nie ma formularzy ani przycisków skanu. Gdyby spróbował zapisać coś przez API, też dostanie odmowę.", "", 4300);

// ---------- 9. DefectDojo ----------
await cap("Na koniec DefectDojo, do którego SurfaceX wysyła wyniki po każdym skanie.", "", 2600);
await p.goto(`${DOJO}/login`);
await slowType(p.locator("#id_username"), "admin");
await slowType(p.locator("#id_password"), "changeme");
await p.keyboard.press("Enter");
await sleep(2500);
await p.goto(`${DOJO}/finding/open`);
await sleep(2500);
await shot("defectdojo");
await cap("Każdy host, usługa i technologia jest tu osobnym findingiem informacyjnym, gotowym do przejrzenia przez zespół.", "", 4500);
await cap("Dzięki za obejrzenie. Kod i ten lab są w repozytorium, a całość startuje przez docker compose up.", "", 3500);

const video = p.video();
await ctx.close();
await browser.close();
writeFileSync(`${OUT}/ff.json`, JSON.stringify(ffMarks));
console.log("VIDEO", await video.path());
