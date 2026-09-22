import { useEffect, useId, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownProps {
  children: string | null | undefined
  className?: string
  /** When set, relative image sources resolve under this packaged asset base. */
  assetBaseUrl?: string
}

/**
 * Shared GFM Markdown renderer used by the tester chat and the admin replay so
 * assistant content (headings, bold, tables, lists) renders identically in both
 * places and can't drift apart. Raw HTML is intentionally not enabled
 * (no rehype-raw), so this introduces no HTML-injection surface.
 *
 * Mermaid fenced blocks are rendered safely client-side with an accessible text
 * equivalent and a readable code-block fallback if rendering fails.
 */
export function Markdown({ children, className, assetBaseUrl }: MarkdownProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: MarkdownCode,
          a: CitationLink,
          img: (props) => <MarkdownImage {...props} assetBaseUrl={assetBaseUrl} />,
        }}
      >
        {children ?? ''}
      </ReactMarkdown>
    </div>
  )
}

/**
 * Resolve a Markdown image `src` against an optional packaged asset base.
 * Absolute http(s) URLs and protocol-relative URLs are left alone. Relative
 * paths are joined to the base when provided; otherwise they stay unchanged so
 * chat/replay behavior is preserved.
 */
export function resolveMarkdownImageSrc(
  src: string | undefined,
  assetBaseUrl?: string,
): string | undefined {
  if (!src) return src
  if (/^(https?:|data:|blob:)/i.test(src) || src.startsWith('//')) {
    return src
  }
  if (!assetBaseUrl) return src
  if (src.startsWith('/')) return src
  if (src.includes('..')) return undefined

  const base = assetBaseUrl.endsWith('/') ? assetBaseUrl : `${assetBaseUrl}/`
  const relative = src.replace(/^\.\//, '')
  return `${base}${relative}`
}

function MarkdownImage({
  src,
  alt,
  assetBaseUrl,
  node: _node,
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement> & {
  assetBaseUrl?: string
  node?: unknown
}) {
  const resolved = resolveMarkdownImageSrc(
    typeof src === 'string' ? src : undefined,
    assetBaseUrl,
  )
  if (!resolved) {
    return (
      <span className="text-sm text-muted-foreground">
        {alt ? `[image: ${alt}]` : '[image unavailable]'}
      </span>
    )
  }
  return <img {...props} src={resolved} alt={alt ?? ''} />
}

function CitationLink({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: ReactNode }) {
  const isKnowledgeSource =
    typeof href === 'string' &&
    (href.includes('drive.google.com') || href.includes('docs.google.com'))

  return (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={
        isKnowledgeSource
          ? 'font-medium text-primary underline decoration-dotted underline-offset-2'
          : undefined
      }
      title={isKnowledgeSource ? 'Open Knowledge Source' : undefined}
    >
      {children}
    </a>
  )
}

function MarkdownCode({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & { children?: ReactNode }) {
  const match = /language-(\w+)/.exec(className || '')
  const language = match?.[1]
  const code = String(children ?? '').replace(/\n$/, '')

  if (language === 'mermaid') {
    return <MermaidBlock chart={code} />
  }

  const isInline = !className && !String(children ?? '').includes('\n')
  if (isInline) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    )
  }

  return (
    <pre className="overflow-x-auto rounded-md bg-black/5 p-3 text-xs">
      <code className={className} {...props}>
        {children}
      </code>
    </pre>
  )
}

function MermaidBlock({ chart }: { chart: string }) {
  const reactId = useId().replace(/:/g, '')
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'neutral',
        })
        const id = `mermaid-${reactId}-${Math.random().toString(36).slice(2, 8)}`
        const { svg: rendered } = await mermaid.render(id, chart)
        if (!cancelled) {
          setSvg(rendered)
          setFailed(false)
        }
      } catch {
        if (!cancelled) {
          setSvg(null)
          setFailed(true)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [chart, reactId])

  if (failed || (!svg && failed)) {
    return (
      <figure className="my-3">
        <figcaption className="sr-only">Diagram (text equivalent)</figcaption>
        <pre
          className="overflow-x-auto rounded-md border border-border bg-background p-3 text-xs"
          role="img"
          aria-label="Mermaid diagram could not be rendered; showing source"
        >
          <code>{chart}</code>
        </pre>
      </figure>
    )
  }

  if (!svg) {
    return (
      <pre className="overflow-x-auto rounded-md bg-black/5 p-3 text-xs text-muted-foreground">
        Rendering diagram…
      </pre>
    )
  }

  return (
    <figure className="my-3">
      <figcaption className="sr-only">Diagram: {chart.slice(0, 120)}</figcaption>
      <div
        className="overflow-x-auto"
        role="img"
        aria-label={`Diagram. Text equivalent: ${chart}`}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      {failed && (
        <pre className="mt-2 overflow-x-auto rounded-md border border-border p-3 text-xs">
          <code>{chart}</code>
        </pre>
      )}
    </figure>
  )
}
