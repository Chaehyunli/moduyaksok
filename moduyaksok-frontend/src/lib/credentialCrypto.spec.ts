import { describe, expect, it } from 'vitest'
import {
  decryptApiKey,
  deriveKeyFromBundle,
  encryptApiKey,
  exportDerivedKey,
  importDerivedKey,
  maskKey,
} from './credentialCrypto'

describe('credentialCrypto', () => {
  it('암호화한 값을 같은 패스프레이즈로 그대로 복호화한다', async () => {
    const bundle = await encryptApiKey('correct horse battery staple', 'sk-ant-abc123')
    const key = await deriveKeyFromBundle('correct horse battery staple', bundle)

    const decrypted = await decryptApiKey(key, bundle)

    expect(decrypted).toBe('sk-ant-abc123')
  })

  it('틀린 패스프레이즈로 복호화하면 예외를 던진다', async () => {
    const bundle = await encryptApiKey('correct horse battery staple', 'sk-ant-abc123')
    const wrongKey = await deriveKeyFromBundle('wrong passphrase', bundle)

    await expect(decryptApiKey(wrongKey, bundle)).rejects.toThrow()
  })

  it('유도키를 export/import해도 같은 값으로 복호화한다 (sessionStorage 캐시 라운드트립)', async () => {
    const bundle = await encryptApiKey('correct horse battery staple', 'sk-ant-abc123')
    const key = await deriveKeyFromBundle('correct horse battery staple', bundle)

    const exported = await exportDerivedKey(key)
    const reimported = await importDerivedKey(exported)

    expect(await decryptApiKey(reimported, bundle)).toBe('sk-ant-abc123')
  })

  it('앞 7자/뒤 4자만 남기고 마스킹한다', () => {
    expect(maskKey('sk-ant-abcdefghijklmnopqrstuvwx')).toBe('sk-ant-••••••••uvwx')
  })
})
