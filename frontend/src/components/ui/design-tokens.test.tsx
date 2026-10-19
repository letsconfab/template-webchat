import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert } from './alert'
import { Button } from './button'

const indexCss = readFileSync(resolve(__dirname, '../../index.css'), 'utf8')
const tailwindConfig = readFileSync(
  resolve(__dirname, '../../../tailwind.config.js'),
  'utf8',
)

describe('design token variants', () => {
  // ALO brand palette (#26). Expected values are the HSL triplets from the
  // ticket's token table; the app is light-only.
  const brandTokens: Record<string, string> = {
    '--background': '0.0 0.0% 100.0%',
    '--foreground': '194.3 25.9% 15.9%',
    '--card': '0.0 0.0% 100.0%',
    '--card-foreground': '194.3 25.9% 15.9%',
    '--popover': '0.0 0.0% 100.0%',
    '--popover-foreground': '194.3 25.9% 15.9%',
    '--primary': '4.5 85.5% 48.8%',
    '--primary-foreground': '0.0 0.0% 100.0%',
    '--secondary': '190.9 28.2% 92.4%',
    '--secondary-foreground': '194.3 25.9% 15.9%',
    '--muted': '190.0 27.3% 95.7%',
    '--muted-foreground': '193.3 15.3% 34.7%',
    '--accent': '190.8 35.0% 40.4%',
    '--accent-foreground': '0.0 0.0% 100.0%',
    '--destructive': '343.4 79.7% 34.7%',
    '--destructive-foreground': '0.0 0.0% 100.0%',
    '--border': '190.4 24.7% 81.8%',
    '--input': '190.4 24.7% 81.8%',
    '--ring': '190.8 35.0% 40.4%',
    '--surface-hero': '190.4 24.7% 81.8%',
    '--brand-heart': '4.5 85.6% 53.7%',
    '--brand-heart-soft': '17.4 80.3% 72.2%',
    '--link': '190.7 31.8% 17.3%',
  }

  it('defines every ALO brand token in :root', () => {
    const root = indexCss.match(/:root\s*{([^}]*)}/)
    expect(root, ':root block').not.toBeNull()
    for (const [token, value] of Object.entries(brandTokens)) {
      expect(root![1], token).toMatch(new RegExp(`${token}:\\s*${value.replace(/[.%]/g, '\\$&')};`))
    }
  })

  it('is light-only: no .dark block and no class-based dark mode', () => {
    expect(indexCss).not.toMatch(/\.dark\s*{/)
    expect(tailwindConfig).not.toMatch(/darkMode/)
  })

  it('maps the new brand colors and fonts in tailwind.config.js', () => {
    for (const key of ['surface-hero', 'brand-heart', 'brand-heart-soft', 'link']) {
      expect(tailwindConfig).toContain(`"${key}": "hsl(var(--${key}))"`)
    }
    expect(tailwindConfig).toMatch(/sans:\s*\[\s*["']Metrophobic["']/)
    expect(tailwindConfig).toMatch(/display:\s*\[\s*['"]"Playfair Display"['"]/)
  })

  it('styles links with the link token, underlined', () => {
    expect(indexCss).toMatch(/\ba\s*{[^}]*text-link[^}]*underline|\ba\s*{[^}]*underline[^}]*text-link/)
  })

  it('maps repaired tokens in tailwind.config.js', () => {
    for (const key of ['destructive', 'secondary', 'accent', 'card', 'popover', 'input', 'ring']) {
      expect(tailwindConfig).toContain(key)
    }
  })

  it('destructive button uses bg-destructive token class', () => {
    const { getByRole } = render(<Button variant="destructive">Delete</Button>)
    expect(getByRole('button').className).toMatch(/bg-destructive/)
    expect(getByRole('button').className).toMatch(/text-destructive-foreground/)
  })

  it('secondary button uses bg-secondary token class', () => {
    const { getByRole } = render(<Button variant="secondary">Secondary</Button>)
    expect(getByRole('button').className).toMatch(/bg-secondary/)
  })

  it('outline and ghost use accent/input hover tokens', () => {
    const { getByRole, rerender } = render(<Button variant="outline">Outline</Button>)
    expect(getByRole('button').className).toMatch(/border-input/)
    expect(getByRole('button').className).toMatch(/hover:bg-accent/)

    rerender(<Button variant="ghost">Ghost</Button>)
    expect(getByRole('button').className).toMatch(/hover:bg-accent/)
  })

  it('default button declares a focus-visible ring using ring token', () => {
    const { getByRole } = render(<Button>Focus</Button>)
    expect(getByRole('button').className).toMatch(/focus-visible:ring-ring/)
    expect(getByRole('button').className).toMatch(/focus-visible:ring-2/)
  })

  it('destructive alert uses destructive token classes', () => {
    const { getByRole } = render(<Alert variant="destructive">Something broke</Alert>)
    expect(getByRole('alert').className).toMatch(/text-destructive|border-destructive/)
  })
})
