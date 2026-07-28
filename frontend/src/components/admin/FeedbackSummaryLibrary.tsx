import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import {
  formatSummaryDate,
  loadFeedbackSummariesIndex,
  type FeedbackSummariesIndexState,
} from '../../services/feedbackSummaries'

export function FeedbackSummaryLibrary() {
  const [state, setState] = useState<FeedbackSummariesIndexState>({
    status: 'loading',
  })

  useEffect(() => {
    let cancelled = false
    loadFeedbackSummariesIndex().then((next) => {
      if (!cancelled) setState(next)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Card className="mb-6">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Feedback summaries</CardTitle>
      </CardHeader>
      <CardContent>
        {state.status === 'loading' && (
          <p className="text-sm text-muted-foreground">Loading summaries…</p>
        )}
        {state.status === 'unavailable' && (
          <p className="text-sm text-muted-foreground">
            Feedback summaries unavailable.
          </p>
        )}
        {state.status === 'empty' && (
          <p className="text-sm text-muted-foreground">
            No feedback summaries available.
          </p>
        )}
        {state.status === 'ready' && (
          <ul className="space-y-3">
            {state.summaries.map((summary) => (
              <li key={summary.artifact_id}>
                <Link
                  to={`/admin/feedback/summaries/${summary.artifact_id}`}
                  className="block rounded-md border border-transparent px-2 py-2 hover:border-border hover:bg-muted/40"
                >
                  <p className="font-medium text-foreground">{summary.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Evidence window:{' '}
                    {formatSummaryDate(summary.window_start)} –{' '}
                    {formatSummaryDate(summary.window_end)}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Generated {formatSummaryDate(summary.generated_at)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
