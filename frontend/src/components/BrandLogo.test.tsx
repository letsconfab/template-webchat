import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import BrandLogo from './BrandLogo'

describe('BrandLogo', () => {
  it('shows the long logo image when the brand file is present', () => {
    render(<BrandLogo />)
    const img = screen.getByRole('img', { name: 'A Loving Organization' })
    expect(img).toHaveAttribute('src', '/brand/alo-logo-long.svg')
  })

  it('falls back to a text wordmark when the logo image fails to load', () => {
    render(<BrandLogo />)
    fireEvent.error(screen.getByRole('img', { name: 'A Loving Organization' }))

    expect(screen.queryByRole('img', { name: 'A Loving Organization' })).not.toBeInTheDocument()
    const wordmark = screen.getByText('A Loving Organization')
    expect(wordmark).toHaveClass('font-display')
  })

  it('uses the heart mark for the mark variant and falls back to the heart icon alone', () => {
    const { container } = render(<BrandLogo variant="mark" />)
    const img = screen.getByRole('img', { name: 'A Loving Organization' })
    expect(img).toHaveAttribute('src', '/brand/alo-heart.svg')

    fireEvent.error(img)

    expect(screen.queryByText('A Loving Organization')).not.toBeInTheDocument()
    expect(container.querySelector('svg')).toHaveClass('text-brand-heart')
    expect(screen.getByRole('img', { name: 'A Loving Organization' })).not.toHaveAttribute('src')
  })
})
