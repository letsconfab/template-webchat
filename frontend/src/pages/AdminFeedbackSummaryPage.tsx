import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { AdminLayout } from '../components/admin/AdminLayout'
import { Markdown } from '../components/Markdown'
import {
  formatEvidenceWindow,
  formatSummaryDate,
  loadFeedbackSummary,
  type FeedbackSummaryContentState,
} from '../services/feedbackSummaries'

export default function AdminFeedbackSummaryPage() {
  const { artifactId } = useParams()
  const [state, setState] = useState<FeedbackSummaryContentState>({
    status: 'loading',
  })

  useEffect(() => {
    if (!artifactId) {
      setState({ status: 'not_found' })
      return
    }
    let cancelled = false
    setState({ status: 'loading' })
    loadFeedbackSummary(artifactId).then((next) => {
      if (!cancelled) setState(next)
    })
    return () => {
      cancelled = true
    }
  }, [artifactId])

  return (
    <AdminLayout title="Feedback summary">
      <div className="mx-auto max-w-4xl space-y-4 p-4">
        <nav className="text-sm text-muted-foreground">
          <Link to="/admin/feedback" className="hover:text-foreground">
            Feedback cases
          </Link>
          <span className="mx-2">/</span>
          <span className="text-foreground">Summary</span>
        </nav>

        {state.status === 'loading' && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading summary…
          </div>
        )}

        {state.status === 'unavailable' && (
          <p className="text-sm text-muted-foreground">
            Feedback summaries unavailable.
          </p>
        )}

        {state.status === 'not_found' && (
          <div className="space-y-3">
            <h1 className="text-2xl font-semibold">Summary not found</h1>
            <p className="text-sm text-muted-foreground">
              No packaged summary matches this identifier.
            </p>
            <Link
              to="/admin/feedback"
              className="text-sm font-medium text-primary underline-offset-2 hover:underline"
            >
              Return to feedback cases
            </Link>
          </div>
        )}

        {state.status === 'found' && (
          <article className="space-y-4">
            <header className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight">
                {state.entry.title}
              </h1>
              <p className="text-sm text-muted-foreground">
                Evidence window:{' '}
                {formatEvidenceWindow(
                  state.entry.window_start,
                  state.entry.window_end,
                )}
              </p>
              <p className="text-sm text-muted-foreground">
                Generated {formatSummaryDate(state.entry.generated_at)}
              </p>
            </header>
            <Markdown
              className="prose prose-sm max-w-none dark:prose-invert"
              assetBaseUrl={state.entry.asset_base_url}
            >
              {state.markdown}
            </Markdown>
          </article>
        )}
      </div>
    </AdminLayout>
  )
}
