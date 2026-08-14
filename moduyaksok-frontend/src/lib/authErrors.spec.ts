import axios from 'axios'
import { describe, expect, it } from 'vitest'
import { googleLoginErrorMessage } from './authErrors'

function axiosError(status?: number, detail?: string) {
  return new axios.AxiosError(
    'failed',
    undefined,
    undefined,
    undefined,
    status ? { status, data: detail ? { detail } : {}, headers: {}, config: {} as any, statusText: '' } : undefined,
  )
}

describe('googleLoginErrorMessage', () => {
  it('distinguishes an invalid Google credential', () => {
    expect(googleLoginErrorMessage(axiosError(401))).toContain('만료되었거나 유효하지')
  })

  it('distinguishes a network failure', () => {
    expect(googleLoginErrorMessage(axiosError())).toContain('연결하지 못했어요')
  })

  it('shows safe backend details for client errors', () => {
    expect(googleLoginErrorMessage(axiosError(400, 'Google Client ID가 일치하지 않습니다.')))
      .toContain('Google Client ID가 일치하지 않습니다.')
  })

  it('does not expose backend details for server errors', () => {
    expect(googleLoginErrorMessage(axiosError(500, 'secret traceback'))).not.toContain('secret traceback')
  })
})
