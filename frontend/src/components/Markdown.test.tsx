import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Markdown } from './Markdown'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, chart: string) => ({
      svg: `<svg data-testid="mermaid-svg"><title>${chart}</title></svg>`,
    })),
  },
}))

describe('Markdown', () => {
  it('renders GFM and knowledge-source citation links', () => {
    render(
      <Markdown>
        {`See [ALO Policy](https://drive.google.com/file/d/abc/view) for details.`}
      </Markdown>,
    )
    const link = screen.getByRole('link', { name: 'ALO Policy' })
    expect(link).toHaveAttribute('href', 'https://drive.google.com/file/d/abc/view')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('renders mermaid fences with accessible text equivalent', async () => {
    render(
      <Markdown>
        {['```mermaid', 'flowchart LR', '  A --> B', '```'].join('\n')}
      </Markdown>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('mermaid-svg')).toBeInTheDocument()
    })
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('A --> B'),
    )
  })

  it('renders mermaid diagrams outside the dark code-block wrapper', async () => {
    render(
      <Markdown>
        {['```mermaid', 'flowchart LR', '  A --> B', '```'].join('\n')}
      </Markdown>,
    )
    const svg = await screen.findByTestId('mermaid-svg')
    expect(svg.closest('pre')).toBeNull()
  })

  it('never runs two mermaid renders at once', async () => {
    const mermaid = await import('mermaid')
    let inFlight = 0
    vi.mocked(mermaid.default.render).mockImplementation(async (_id: string, chart: string) => {
      inFlight += 1
      try {
        if (inFlight > 1) throw new Error('mermaid render is not reentrant')
        await new Promise((resolve) => setTimeout(resolve, 10))
        return { svg: `<svg data-testid="mermaid-svg"><title>${chart}</title></svg>` } as never
      } finally {
        inFlight -= 1
      }
    })

    render(
      <Markdown>
        {[
          '```mermaid', 'flowchart LR', '  A --> B', '```',
          '',
          '```mermaid', 'flowchart LR', '  C --> D', '```',
        ].join('\n')}
      </Markdown>,
    )
    await waitFor(() => {
      expect(screen.getAllByTestId('mermaid-svg')).toHaveLength(2)
    })
    expect(screen.queryByLabelText(/could not be rendered/i)).toBeNull()
  })

  it('falls back to a code block when mermaid render fails', async () => {
    const mermaid = await import('mermaid')
    vi.mocked(mermaid.default.render).mockRejectedValueOnce(new Error('boom'))

    render(
      <Markdown>
        {['```mermaid', 'not valid', '```'].join('\n')}
      </Markdown>,
    )
    await waitFor(() => {
      expect(
        screen.getByLabelText(/could not be rendered/i),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('not valid')).toBeInTheDocument()
  })

  it('resolves relative images when assetBaseUrl is provided', () => {
    render(
      <Markdown assetBaseUrl="/static/feedback-summaries/artifacts/demo/hash/">
        {'![Theme chart](assets/theme.svg)'}
      </Markdown>,
    )
    expect(screen.getByRole('img', { name: 'Theme chart' })).toHaveAttribute(
      'src',
      '/static/feedback-summaries/artifacts/demo/hash/assets/theme.svg',
    )
  })

  it('leaves relative images unchanged when assetBaseUrl is absent', () => {
    render(<Markdown>{'![Theme chart](assets/theme.svg)'}</Markdown>)
    expect(screen.getByRole('img', { name: 'Theme chart' })).toHaveAttribute(
      'src',
      'assets/theme.svg',
    )
  })
})
