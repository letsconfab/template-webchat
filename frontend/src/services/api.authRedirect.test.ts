import { describe, expect, it } from 'vitest'

import { loginRedirectForUnauthorized, rememberPostLoginReturnTo } from './api'

const caseId = 'a7b7c2df-a857-42fc-880c-a771328dc5a8'
const feedbackPath = `/feedback/${caseId}`

describe('loginRedirectForUnauthorized', () => {
  it('preserves the current path as returnTo when leaving a protected page', () => {
    expect(loginRedirectForUnauthorized(feedbackPath)).toBe(
      `/login?returnTo=${encodeURIComponent(feedbackPath)}`,
    )
  })

  it('includes the current search string in returnTo', () => {
    expect(loginRedirectForUnauthorized('/chat', '?tab=history')).toBe(
      `/login?returnTo=${encodeURIComponent('/chat?tab=history')}`,
    )
  })

  it('does not redirect when already on /login so an existing returnTo is not wiped', () => {
    expect(loginRedirectForUnauthorized('/login', `?returnTo=${encodeURIComponent(feedbackPath)}`)).toBeNull()
  })

  it('does not redirect on other auth pages', () => {
    expect(loginRedirectForUnauthorized('/register')).toBeNull()
    expect(loginRedirectForUnauthorized('/setup')).toBeNull()
  })

  it('rejects open redirects that use a protocol-relative path', () => {
    expect(loginRedirectForUnauthorized('//evil.example')).toBe('/login')
  })
})

describe('rememberPostLoginReturnTo', () => {
  it('stores a protected Feedback Case path for post-login recovery', () => {
    rememberPostLoginReturnTo(feedbackPath)
    expect(sessionStorage.getItem('postLoginReturnTo')).toBe(feedbackPath)
  })

  it('does not store protocol-relative open redirects', () => {
    rememberPostLoginReturnTo('//evil.example')
    expect(sessionStorage.getItem('postLoginReturnTo')).toBeNull()
  })
})
