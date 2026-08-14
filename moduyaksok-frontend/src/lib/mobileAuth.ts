export const GOOGLE_LOGIN_REDIRECT_KEY = 'google_login_redirect'

export function needsGoogleRedirect(
  userAgent = navigator.userAgent,
  platform = navigator.platform,
  maxTouchPoints = navigator.maxTouchPoints,
): boolean {
  return /iPad|iPhone|iPod/i.test(userAgent) || (platform === 'MacIntel' && maxTouchPoints > 1)
}

export function googleRedirectLoginUri(apiBaseUrl: string, origin = window.location.origin): string {
  const base = apiBaseUrl.endsWith('/') ? apiBaseUrl : `${apiBaseUrl}/`
  return new URL('auth/google/redirect', new URL(base, `${origin}/`)).toString()
}
