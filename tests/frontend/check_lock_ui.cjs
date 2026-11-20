// The locked-history controls on a static site built with ARCHIVE_PASSPHRASE (tests/test_history_lock.py).
// argv: base URL, passphrase. Prints "ok" or what failed.
const { chromium } = require("playwright");
const [base, pass] = process.argv.slice(2);
(async () => {
  const fail = [];
  const browser = await chromium.launch();
  for (const width of [320, 1280]) {
    const ctx = await browser.newContext({ viewport: { width, height: 800 }, serviceWorkers: "block" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => fail.push(`${width}: page error ${e.message}`));
    const state = () => page.evaluate(() => ({
      long: [...document.querySelectorAll("[data-preset]")].filter((b) => !b.hidden && ["30d", "90d", "1y"].includes(b.dataset.preset)).length,
      min: document.querySelector('[name="from"]').min,
      span: document.querySelector("[data-span]").textContent,
      overflow: document.documentElement.scrollWidth - innerWidth,
      bad: /\b(NaN|undefined|Infinity)\b/.test(document.querySelector("main").innerText),
    }));
    await page.goto(`${base}#/generation?range=90d`); await page.waitForSelector("[data-lock]:not([hidden])", { timeout: 20000 }).catch(() => fail.push(`${width}: no lock controls on the Generation page`));
    let s = await state();
    if (s.long) fail.push(`${width}: 30/90-day buttons shown while locked`);
    if (!s.min) fail.push(`${width}: older dates can be picked while locked`);
    if (!/^Public: last/.test(s.span)) fail.push(`${width}: date bar says "${s.span}" while locked`);
    if (!(await page.$("[data-unlock]"))) fail.push(`${width}: no unlock button`);
    else {
      await page.click("[data-unlock]");
      await page.fill('[data-lock] input[name="pw"]', "not it"); await page.click('[data-lock] button[type="submit"]');
      await page.waitForFunction(() => /Wrong/.test(document.querySelector("[data-msg]")?.textContent || ""), null, { timeout: 15000 }).catch(() => fail.push(`${width}: wrong password not refused`));
      if ((await state()).overflow > 0) fail.push(`${width}: password form widens the page`);
      await page.fill('[data-lock] input[name="pw"]', pass); await page.click('[data-lock] button[type="submit"]');
      await page.waitForSelector("[data-relock]", { timeout: 20000 }).catch(() => fail.push(`${width}: right password did not unlock`));
      s = await state();
      if (!s.long) fail.push(`${width}: long ranges still hidden after unlocking`);
      if (s.min) fail.push(`${width}: dates still limited after unlocking`);
      if (await page.$("[data-relock]")) {
        await page.click("[data-relock]"); await page.waitForSelector("[data-unlock]", { timeout: 20000 }).catch(() => fail.push(`${width}: Lock did not lock`));
      }
    }
    if (s.bad) fail.push(`${width}: NaN/undefined on screen`);
    await ctx.close();
  }
  await browser.close();
  console.log(fail.length ? fail.join("\n") : "ok");
})();
