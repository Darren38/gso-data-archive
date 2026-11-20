// Opens files locked by gso_archive/sealing.py with web/js/lock.js (the browser's own code), in Node's WebCrypto.
// argv: site data folder, passphrase. Prints "ok" or what failed.
import { readdirSync, readFileSync } from "node:fs";

const store = new Map();
globalThis.sessionStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
const { tryUnlock, storedKey, openBytes, forget } = await import(new URL("../../web/js/lock.js", import.meta.url));
const [dir, pass] = process.argv.slice(2);
const meta = JSON.parse(readFileSync(`${dir}/meta.json`, "utf8"));
const open = async (key, file) => JSON.parse(new TextDecoder().decode(await openBytes(key, readFileSync(file))));
const fail = [];
if (await tryUnlock("wrong password", meta.lock)) fail.push("a wrong password unlocked");
if (storedKey()) fail.push("a key was kept after a wrong password");
if (!(await tryUnlock(pass, meta.lock))) fail.push("the right password did not unlock");
const key = storedKey();
if (!key) fail.push("no key kept after unlocking");
else {
  if (!(await open(key, `${dir}/farms/index.json.enc`)).days) fail.push("locked farms index unreadable");
  const months = readdirSync(`${dir}/points`).flatMap((k) => readdirSync(`${dir}/points/${k}`)
    .filter((f) => /^\d{4}-\d{2}\.json\.enc$/.test(f)).map((f) => `${dir}/points/${k}/${f}`));
  if (!months.length) fail.push("no locked month files");
  for (const f of months.slice(0, 20)) if (!(await open(key, f)).points) fail.push(`no points in ${f}`);
  try { await openBytes(new Uint8Array(32), readFileSync(months[0])); fail.push("a wrong key opened a file"); } catch { /* expected */ }
}
forget();
if (storedKey()) fail.push("forget kept the key");
console.log(fail.length ? fail.join("; ") : "ok");
