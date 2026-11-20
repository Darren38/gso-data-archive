// Locked history (gso_archive/sealing.py): the public sees the newest few days; the owner's passphrase opens the rest.
// The browser derives the same key once (PBKDF2-SHA256, salt and rounds from meta.json "lock") and opens each
// NAME.json.enc (b"GSO1" + 12-byte nonce + AES-256-GCM) with it. Only the derived key is kept, never the passphrase:
// for this tab (sessionStorage), or on this device when the visitor ticks "Remember" (localStorage).
const STORE = "gso-history-key";
const MAGIC = [71, 83, 79, 49]; // "GSO1"
const b64ToBytes = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const bytesToB64 = (u) => btoa(String.fromCharCode(...u));
const stores = () => [globalThis.sessionStorage, globalThis.localStorage].filter(Boolean);

/** The stored key (raw bytes), or null. Anything unreadable counts as no key (lesson 23). */
export function storedKey() {
  for (const s of stores()) {
    try {
      const v = s.getItem(STORE);
      if (v && /^[A-Za-z0-9+/]{43}=$/.test(v)) return b64ToBytes(v);
    } catch { /* storage blocked */ }
  }
  return null;
}

export function forget() {
  for (const s of stores()) { try { s.removeItem(STORE); } catch { /* storage blocked */ } }
}

export async function deriveKey(passphrase, lock) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: b64ToBytes(lock.salt), iterations: lock.iterations }, base, 256);
  return new Uint8Array(bits);
}

/** Open one locked file's bytes with a raw key; throws for a wrong key or a damaged file. */
export async function openBytes(raw, buf) {
  const u = new Uint8Array(buf);
  if (u.length < 32 || MAGIC.some((b, i) => u[i] !== b)) throw new Error("not a locked file");
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: u.slice(4, 16) }, key, u.slice(16)));
}

/** Check a passphrase against the published check value; keep the key when it is right. */
export async function tryUnlock(passphrase, lock, remember = false) {
  if (!passphrase || !lock?.salt || !lock?.check) return false;
  try {
    const raw = await deriveKey(passphrase, lock);
    const text = new TextDecoder().decode(await openBytes(raw, b64ToBytes(lock.check)));
    if (text !== "gso-data-archive unlocked") return false;
    forget();
    (remember ? globalThis.localStorage : globalThis.sessionStorage)?.setItem(STORE, bytesToB64(raw));
    return true;
  } catch {
    return false;
  }
}
