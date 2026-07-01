import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'

import { Badge } from '../components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { api } from '../services/api'

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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    if (!caseId) {
      api.get('/admin/feedback-cases')
        .then(response => setCases(response.data.cases || []))
        .finally(() => setLoading(false))
      return
    }

    const loadReplay = async () => {
      let cursor: number | null = null
      const replay: ReplayMessage[] = []
      do {
        const response = await api.get(`/admin/feedback-cases/${caseId}/replay`, {
          params: cursor ? { cursor } : {},
        })
        setSelectedCase(response.data.case)
        replay.push(...(response.data.messages || []))
        cursor = response.data.next_cursor
      } while (cursor)
      setMessages(replay)
      setLoading(false)
    }
    loadReplay()
  }, [caseId])

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            <h1 className="text-xl font-semibold">Feedback case review</h1>
          </div>
          <Link to="/admin/dashboard" className="text-sm text-primary hover:underline">Admin dashboard</Link>
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 px-4 py-8">
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
                    <p className="whitespace-pre-wrap text-sm">
                      {message.redaction_status === 'succeeded'
                        ? message.content
                        : 'Content unavailable pending privacy processing'}
                    </p>
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
          cases.map(feedbackCase => (
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
          ))
        )}
      </main>
    </div>
  )
}

