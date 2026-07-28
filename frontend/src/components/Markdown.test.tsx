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
