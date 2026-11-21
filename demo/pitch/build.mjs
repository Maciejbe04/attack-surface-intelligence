// Renders demo/pitch/index.html to PDF (1920x1080 pages). Env: TEAM, VIDEO_URL, OUT_PDF.
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
const dir = process.env.PITCH_DIR;
const b = await chromium.launch({ channel: "chrome", headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto(pathToFileURL(`${dir}/index.html`).href, { waitUntil: "load" });
await p.evaluate(([team, video]) => {
  document.body.innerHTML = document.body.innerHTML.replaceAll("{{TEAM}}", team).replaceAll("{{VIDEO_URL}}", video);
}, [process.env.TEAM || "—", process.env.VIDEO_URL || "link w polu „dodatkowe materiały” HackTribe"]);
await p.waitForLoadState("load");
await p.evaluate(() => Promise.all([...document.images].map((i) => i.complete ? 0 : new Promise((r) => (i.onload = i.onerror = r)))));
await p.pdf({ path: process.env.OUT_PDF, width: "1920px", height: "1080px", printBackground: true, preferCSSPageSize: true });
await b.close();
console.log("PDF", process.env.OUT_PDF);
