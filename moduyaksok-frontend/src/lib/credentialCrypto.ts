// PBKDF2(패스프레이즈 → 키 유도) + AES-GCM(암호화)로 BYOK API 키를 브라우저에서만
// 암호화한다. 서버는 ciphertext/salt/iv/kdf_iterations만 보고 평문은 절대 못 본다
// (docs/superpowers/specs/2026-08-17-byok-client-side-encryption-design.md).
const PBKDF2_ITERATIONS = 600_000

export interface EncryptedBundle {
  ciphertext: string // base64
  salt: string // base64
  iv: string // base64
  kdfIterations: number
}

function toBase64(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
}

function fromBase64(value: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(value), (c) => c.charCodeAt(0)) as Uint8Array<ArrayBuffer>
}

async function deriveKey(
  passphrase: string,
  salt: Uint8Array<ArrayBuffer>,
  iterations: number,
  extractable = false,
): Promise<CryptoKey> {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    extractable,
    ['encrypt', 'decrypt'],
  )
}

// 세션 캐시(sessionStorage)에 넣으려면 export가 가능해야 하므로 extractable: true로
// 유도한다 — devtools 덤프 방어보다 새로고침 생존 UX를 우선한 트레이드오프
// (docs/superpowers/specs/2026-08-17-byok-client-side-encryption-design.md §4.1).
export function deriveKeyFromBundle(
  passphrase: string,
  bundle: Pick<EncryptedBundle, 'salt' | 'kdfIterations'>,
): Promise<CryptoKey> {
  return deriveKey(passphrase, fromBase64(bundle.salt), bundle.kdfIterations, true)
}

export async function exportDerivedKey(key: CryptoKey): Promise<string> {
  const raw = await crypto.subtle.exportKey('raw', key)
  return toBase64(raw)
}

export function importDerivedKey(base64Key: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', fromBase64(base64Key), { name: 'AES-GCM' }, false, [
    'decrypt',
  ])
}

export async function encryptApiKey(passphrase: string, apiKey: string): Promise<EncryptedBundle> {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt, PBKDF2_ITERATIONS)
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(apiKey),
  )
  return {
    ciphertext: toBase64(encrypted),
    salt: toBase64(salt.buffer as ArrayBuffer),
    iv: toBase64(iv.buffer as ArrayBuffer),
    kdfIterations: PBKDF2_ITERATIONS,
  }
}

export async function decryptApiKey(
  derivedKey: CryptoKey,
  bundle: Pick<EncryptedBundle, 'ciphertext' | 'iv'>,
): Promise<string> {
  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: fromBase64(bundle.iv) },
    derivedKey,
    fromBase64(bundle.ciphertext),
  )
  return new TextDecoder().decode(decrypted)
}

export function maskKey(rawKey: string): string {
  return rawKey.slice(0, 7) + '••••••••' + rawKey.slice(-4)
}
