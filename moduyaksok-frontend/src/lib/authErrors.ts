import axios from 'axios'

export function googleLoginErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return '로그인 처리 중 예상하지 못한 오류가 발생했어요. 잠시 후 다시 시도해주세요.'
  }
  if (!error.response) {
    return '로그인 서버에 연결하지 못했어요. 네트워크 상태를 확인해주세요.'
  }
  if (error.response.status === 401) {
    return 'Google 로그인 정보가 만료되었거나 유효하지 않아요. 다시 로그인해주세요.'
  }
  const detail = error.response.data?.detail
  if (typeof detail === 'string' && detail.length > 0 && error.response.status < 500) {
    return `로그인에 실패했어요: ${detail}`
  }
  if (error.response.status >= 500) {
    return '로그인 서버에 일시적인 문제가 발생했어요. 잠시 후 다시 시도해주세요.'
  }
  return '로그인에 실패했어요. 다시 시도해주세요.'
}
