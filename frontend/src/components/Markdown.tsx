import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownProps {
  children: string | null | undefined
  className?: string
}

/**
 * Shared GFM Markdown renderer used by the tester chat and the admin replay so
 * assistant content (headings, bold, tables, lists) renders identically in both
 * places and can't drift apart. Raw HTML is intentionally not enabled
 * (no rehype-raw), so this introduces no HTML-injection surface.
 */
export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children ?? ''}</ReactMarkdown>
    </div>
  )
}
