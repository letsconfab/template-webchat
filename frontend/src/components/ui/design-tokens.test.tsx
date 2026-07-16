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
  it('defines all required CSS variables in light and dark themes', () => {
    const required = [
      '--destructive',
      '--destructive-foreground',
      '--secondary',
      '--secondary-foreground',
      '--accent',
      '--accent-foreground',
      '--card',
      '--card-foreground',
      '--popover',
      '--popover-foreground',
      '--input',
      '--ring',
    ]
    for (const token of required) {
      const occurrences = indexCss.split(token).length - 1
      // light + dark blocks
      expect(occurrences, `${token} should appear in light and dark`).toBeGreaterThanOrEqual(2)
    }
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
