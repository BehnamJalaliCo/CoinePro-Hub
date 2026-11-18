// Lighthouse through a pipe (the studio user reaches no loopback port, so chrome-launcher's
// debugging port cannot work): node lh.mjs URL OUT.json. Lighthouse and puppeteer-core live in
// /home/studio/kits/seo-node (npm, outside git).
import { createRequire } from "node:module";
import fs from "node:fs";
const req = createRequire("/home/studio/kits/seo-node/package.json");
const puppeteer = (await import(req.resolve("puppeteer-core"))).default;
const lighthouse = (await import(req.resolve("lighthouse"))).default;
const [url, out] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH, pipe: true, headless: true,
  args: ["--no-sandbox", "--disable-gpu"] });
try {
  const page = await browser.newPage();
  const r = await lighthouse(url, { output: "json", logLevel: "error",
    onlyCategories: ["performance", "seo", "accessibility", "best-practices"] }, undefined, page);
  fs.writeFileSync(out, r.report);
} finally {
  await browser.close();
}
