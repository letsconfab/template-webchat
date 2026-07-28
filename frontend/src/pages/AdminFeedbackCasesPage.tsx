import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { Alert, AlertDescription } from '../components/ui/alert'
import { Badge } from '../components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Markdown } from '../components/Markdown'
import { api } from '../services/api'
import { AdminLayout } from '../components/admin/AdminLayout'
import { FeedbackSummaryLibrary } from '../components/admin/FeedbackSummaryLibrary'

interface AdminCase {
  case_id: string
  status: string
  categories: string[]
  comment: string | null
  comment_redaction_status: string
  account_email: string
  created_at: string
}

interface ReplayMessage {
  id: number
  role: string
  content: string | null
  redaction_status: string
  created_at: string
  is_rated: boolean
  is_post_feedback: boolean
  execution_trace: {
    status: string
    events?: Array<Record<string, unknown>>
    truncated?: boolean
  } | null
}

export default function AdminFeedbackCasesPage() {
  const { caseId } = useParams()
  const [cases, setCases] = useState<AdminCase[]>([])
  const [selectedCase, setSelectedCase] = useState<AdminCase | null>(null)
  const [messages, setMessages] = useState<ReplayMessage[]>([])
  const [replies, setReplies] = useState<Array<{
    id: number
    author_role: string
    text: string | null
    redaction_status: string
    created_at: string
    notification: {
      id: number
      state: string
      safe_error_category: string | null
    } | null
  }>>([])
  const [reply, setReply] = useState('')
  const [correspondenceEnabled, setCorrespondenceEnabled] = useState(false)
  const [actionError, setActionError] = useState('')
  const [actionSuccess, setActionSuccess] = useState('')
  const [submittingAction, setSubmittingAction] = useState<'reply' | 'resolve' | null>(null)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    setLoading(true)
    if (!caseId) {
      api.get('/admin/feedback-cases', {
        params: {
          ...(statusFilter ? { status: statusFilter } : {}),
          ...(categoryFilter ? { category: categoryFilter } : {}),
          ...(emailFilter ? { email: emailFilter } : {}),
          ...(dateFrom ? { date_from: `${dateFrom}T00:00:00` } : {}),
          ...(dateTo ? { date_to: `${dateTo}T23:59:59` } : {}),
        },
      })
        .then(response => setCases(response.data.cases || []))
        .finally(() => setLoading(false))
      return
    }

    const loadReplay = async () => {
      const features = await api.get('/settings/features')
      setCorrespondenceEnabled(
        Boolean(features.data.tester_correspondence_enabled),
      )
      let cursor: number | null = null
      const replay: ReplayMessage[] = []
      do {
        const response = await api.get(`/admin/feedback-cases/${caseId}/replay`, {
          params: cursor ? { cursor } : {},
        })
        setSelectedCase(response.data.case)
        setReplies(response.data.replies || [])
        replay.push(...(response.data.messages || []))
        cursor = response.data.next_cursor
      } while (cursor)
      setMessages(replay)
      setLoading(false)
    }
    loadReplay()
  }, [caseId, statusFilter, categoryFilter, emailFilter, dateFrom, dateTo])

  const sendReply = async () => {
    if (
      !caseId
      || !correspondenceEnabled
      || !reply.trim()
      || submittingAction
    ) return
    const text = reply.trim()
    setActionError('')
    setActionSuccess('')
    setSubmittingAction('reply')
    try {
      const response = await api.post(
        `/admin/feedback-cases/${caseId}/replies`,
        { text },
      )
      setReplies(current => [
        ...current,
        {
          id: response.data.id,
          author_role: 'admin',
          text,
          redaction_status: 'succeeded',
          created_at: response.data.created_at,
          notification: response.data.notification,
        },
      ])
      setSelectedCase(current => (
        current ? { ...current, status: response.data.status } : current
      ))
      setReply('')
      setActionSuccess('Reply sent.')
    } catch {
      setActionError(
        'Reply could not be sent. Your draft has been preserved. Please try again.',
      )
    } finally {
      setSubmittingAction(null)
    }
  }

  const resolveCase = async () => {
    if (!caseId || !correspondenceEnabled || submittingAction) return
    setActionError('')
    setActionSuccess('')
    setSubmittingAction('resolve')
    try {
      const response = await api.post(
        `/admin/feedback-cases/${caseId}/resolve`,
      )
      setSelectedCase(current => (
        current ? { ...current, status: response.data.status } : current
      ))
      setActionSuccess('Case resolved.')
    } catch {
      setActionError('Case could not be resolved. Please try again.')
    } finally {
      setSubmittingAction(null)
    }
  }

  const retryNotification = async (notificationId: number) => {
    await api.post(`/admin/case-notifications/${notificationId}/retry`)
    window.location.reload()
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>
  }

  return (
    <AdminLayout title="Feedback case review">
      <div className="space-y-4">
        {caseId && selectedCase ? (
          <>
            <Link to="/admin/feedback" className="text-sm text-primary hover:underline">← All cases</Link>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>{selectedCase.account_email}</span>
                  <Badge>{selectedCase.status.replace('_', ' ')}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">
                  {selectedCase.comment_redaction_status === 'succeeded'
                    ? selectedCase.comment || 'No comment'
                    : 'Content unavailable pending privacy processing'}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Correspondence</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {!correspondenceEnabled && (
                  <Alert>
                    <AlertDescription>
                      Correspondence is not enabled. Replies and case resolution
                      are unavailable until the production rollout is completed.
                    </AlertDescription>
                  </Alert>
                )}
                {actionError && (
                  <Alert variant="destructive">
                    <AlertDescription>{actionError}</AlertDescription>
                  </Alert>
                )}
                {actionSuccess && (
                  <p role="status" className="text-sm text-green-700">
                    {actionSuccess}
                  </p>
                )}
                {replies.map(caseReply => (
                  <div key={caseReply.id} className="rounded-lg border p-3 text-sm">
                    <p className="mb-1 text-xs font-semibold">
                      {caseReply.author_role === 'admin' ? 'Admin' : 'Tester'}
                    </p>
                    <p className="whitespace-pre-wrap">
                      {caseReply.redaction_status === 'succeeded'
                        ? caseReply.text
                        : 'Content unavailable'}
                    </p>
                    {caseReply.notification?.state === 'failed' && (
                      <button
                        onClick={() => retryNotification(caseReply.notification!.id)}
                        className="mt-2 rounded border px-2 py-1 text-xs"
                      >
                        Retry email ({caseReply.notification.safe_error_category})
                      </button>
                    )}
                  </div>
                ))}
                <textarea
                  value={reply}
                  onChange={event => setReply(event.target.value)}
                  maxLength={4000}
                  placeholder="Reply to tester"
                  disabled={!correspondenceEnabled}
                  className="min-h-24 w-full rounded-md border bg-background p-3 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    onClick={sendReply}
                    disabled={
                      !correspondenceEnabled
                      || !reply.trim()
                      || submittingAction !== null
                    }
                    className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
                  >
                    {submittingAction === 'reply' ? 'Sending reply…' : 'Send reply'}
                  </button>
                  <button
                    onClick={resolveCase}
                    disabled={
                      !correspondenceEnabled || submittingAction !== null
                    }
                    className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
                  >
                    {submittingAction === 'resolve' ? 'Resolving…' : 'Resolve'}
                  </button>
                </div>
              </CardContent>
            </Card>
            <div className="space-y-3">
              {messages.map(message => (
                <Card
                  key={message.id}
                  className={`${message.is_rated ? 'ring-2 ring-amber-500' : ''} ${message.is_post_feedback ? 'border-dashed' : ''}`}
                >
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{message.role}</span>
                      {message.is_rated && <Badge>Rated answer</Badge>}
                      {message.is_post_feedback && <Badge variant="secondary">After rated answer</Badge>}
                    </div>
                    {message.redaction_status === 'succeeded' ? (
                      <Markdown className="prose prose-sm max-w-none text-sm dark:prose-invert">
                        {message.content}
                      </Markdown>
                    ) : (
                      <p className="text-sm">
                        Content unavailable pending privacy processing
                      </p>
                    )}
                    {message.role === 'assistant' && message.execution_trace && (
                      <details className="text-xs">
                        <summary className="cursor-pointer font-medium">
                          {message.execution_trace.status === 'not_captured'
                            ? 'Trace not captured'
                            : `Execution trace${message.execution_trace.truncated ? ' (truncated)' : ''}`}
                        </summary>
                        {message.execution_trace.events?.map((event, index) => (
                          <pre key={index} className="mt-2 overflow-x-auto rounded bg-muted p-2">
                            {JSON.stringify(event, null, 2)}
                          </pre>
                        ))}
                      </details>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        ) : (
          <>
            <FeedbackSummaryLibrary />
            <div className="mb-4 flex flex-wrap gap-2">
              <select
                value={statusFilter}
                onChange={event => setStatusFilter(event.target.value)}
                className="rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">All statuses</option>
                <option value="awaiting_admin">Awaiting admin</option>
                <option value="awaiting_user">Awaiting user</option>
                <option value="resolved">Resolved</option>
              </select>
              <input value={categoryFilter} onChange={event => setCategoryFilter(event.target.value)} placeholder="Category" className="rounded-md border bg-background px-3 py-2 text-sm" />
              <input value={emailFilter} onChange={event => setEmailFilter(event.target.value)} placeholder="Masked email" className="rounded-md border bg-background px-3 py-2 text-sm" />
              <input type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm" />
              <input type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} className="rounded-md border bg-background px-3 py-2 text-sm" />
            </div>
          {cases.map(feedbackCase => (
            <Link key={feedbackCase.case_id} to={`/admin/feedback/${feedbackCase.case_id}`}>
              <Card className="mb-3 hover:bg-muted/50">
                <CardContent className="flex items-start justify-between p-5">
                  <div>
                    <p className="font-medium">{feedbackCase.account_email}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {feedbackCase.comment_redaction_status === 'succeeded'
                        ? feedbackCase.comment || 'No comment'
                        : 'Content unavailable'}
                    </p>
                  </div>
                  <Badge>{feedbackCase.status.replace('_', ' ')}</Badge>
                </CardContent>
              </Card>
            </Link>
          ))}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
