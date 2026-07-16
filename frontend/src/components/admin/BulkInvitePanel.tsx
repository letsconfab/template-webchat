import React, { useCallback, useEffect, useState } from 'react'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Alert, AlertDescription, AlertTitle } from '../ui/alert'
import { toast } from 'sonner'
import { api } from '../../services/api'

interface PreviewResult {
  filename: string
  role: string
  total_rows: number
  will_invite: number
  already_registered: number
  pending_invite: number
  invalid: number
  duplicate_rows: number
  invalid_rows: { line_number: number; raw: string; reason: string }[]
  sample_will_invite: string[]
}

interface BatchStatus {
  id: number
  filename: string
  role: string
  state: string
  total_count: number
  pending_count: number
  sent_count: number
  failed_count: number
  skipped_count: number
  cancelled_count: number
  unknown_delivery_count: number
  retry_wait_count: number
  cancel_note?: string | null
  recipients?: {
    id: number
    email: string
    state: string
    line_number: number
    safe_error_category?: string | null
  }[]
}

type Step = 'upload' | 'preview' | 'status'

export const BulkInvitePanel: React.FC = () => {
  const [step, setStep] = useState<Step>('upload')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [batch, setBatch] = useState<BatchStatus | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshBatch = useCallback(async (batchId: number) => {
    const response = await api.get(`/admin/bulk-invites/${batchId}`)
    setBatch(response.data)
    return response.data as BatchStatus
  }, [])

  useEffect(() => {
    if (step !== 'status' || !batch?.id) return
    if (batch.state === 'completed' || batch.state === 'cancelled') return
    const timer = setInterval(() => {
      refreshBatch(batch.id).catch(() => undefined)
    }, 3000)
    return () => clearInterval(timer)
  }, [step, batch?.id, batch?.state, refreshBatch])

  const runPreview = async () => {
    if (!file) {
      toast.error('Choose a CSV file first')
      return
    }
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('role', role)
      const response = await api.post('/admin/bulk-invites/preview', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setPreview(response.data)
      setStep('preview')
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Preview failed')
    } finally {
      setBusy(false)
    }
  }

  const confirmSend = async () => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('role', role)
      const response = await api.post('/admin/bulk-invites/confirm', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const batchId = response.data.batch_id as number
      toast.success(`Batch ${batchId} queued (worker sends asynchronously)`)
      const status = await refreshBatch(batchId)
      setBatch(status)
      setStep('status')
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to enqueue batch')
    } finally {
      setBusy(false)
    }
  }

  const cancelBatch = async () => {
    if (!batch) return
    setBusy(true)
    try {
      const response = await api.post(`/admin/bulk-invites/${batch.id}/cancel`)
      setBatch(response.data)
      toast.success('Cancellation committed')
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Cancel failed')
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setStep('upload')
    setFile(null)
    setPreview(null)
    setBatch(null)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bulk invite (CSV)</CardTitle>
        <CardDescription>
          Upload a CSV, preview the breakdown, then enqueue. Sending is handled by
          a separate worker — never inline with this request.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {step === 'upload' && (
          <div className="space-y-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Role for invitees</span>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={role}
                onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">CSV file</span>
              <input
                type="file"
                accept=".csv,text/csv"
                className="text-sm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <Button onClick={runPreview} disabled={busy || !file}>
              {busy ? 'Parsing…' : 'Preview'}
            </Button>
          </div>
        )}

        {step === 'preview' && preview && (
          <div className="space-y-4">
            <p className="text-sm text-foreground">
              {preview.total_rows} rows →{' '}
              <strong>{preview.will_invite}</strong> will be invited ·{' '}
              {preview.already_registered} already registered ·{' '}
              {preview.pending_invite} pending invite · {preview.invalid} invalid ·{' '}
              {preview.duplicate_rows} duplicate rows
              {preview.role ? ` · role ${preview.role}` : null}
            </p>
            {preview.invalid_rows.length > 0 && (
              <div className="rounded-md border border-border p-3 text-sm">
                <p className="mb-2 font-medium">Invalid rows</p>
                <ul className="max-h-40 space-y-1 overflow-y-auto text-muted-foreground">
                  {preview.invalid_rows.map((row) => (
                    <li key={`${row.line_number}-${row.raw}`}>
                      Line {row.line_number}: {row.reason}
                      {row.raw ? ` (${row.raw})` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={confirmSend} disabled={busy || preview.will_invite === 0}>
                {busy ? 'Enqueueing…' : 'Confirm & enqueue'}
              </Button>
              <Button variant="outline" onClick={reset} disabled={busy}>
                Start over
              </Button>
            </div>
          </div>
        )}

        {step === 'status' && batch && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">Batch #{batch.id}</span>
              <Badge variant="secondary">{batch.state}</Badge>
              <span className="text-sm text-muted-foreground">{batch.filename}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div>Pending: {batch.pending_count}</div>
              <div>Sent: {batch.sent_count}</div>
              <div>Failed: {batch.failed_count}</div>
              <div>Skipped: {batch.skipped_count}</div>
              <div>Cancelled: {batch.cancelled_count}</div>
              <div>Retry wait: {batch.retry_wait_count}</div>
              <div>Unknown delivery: {batch.unknown_delivery_count}</div>
              <div>Total: {batch.total_count}</div>
            </div>

            {batch.unknown_delivery_count > 0 && (
              <Alert variant="destructive">
                <AlertTitle>Operator decision required</AlertTitle>
                <AlertDescription>
                  {batch.unknown_delivery_count} recipient(s) are in{' '}
                  <strong>unknown_delivery</strong> — the lease expired while
                  sending, so email may or may not have been delivered. These are
                  never auto-retried.
                </AlertDescription>
              </Alert>
            )}

            {batch.cancel_note && batch.state === 'cancelled' && (
              <Alert>
                <AlertTitle>Cancellation note</AlertTitle>
                <AlertDescription>{batch.cancel_note}</AlertDescription>
              </Alert>
            )}

            {batch.recipients && batch.recipients.length > 0 && (
              <div className="max-h-56 overflow-y-auto rounded-md border border-border">
                <table className="w-full text-left text-sm">
                  <thead className="border-b bg-muted/40">
                    <tr>
                      <th className="px-3 py-2">Line</th>
                      <th className="px-3 py-2">Email</th>
                      <th className="px-3 py-2">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batch.recipients.map((r) => (
                      <tr key={r.id} className="border-b border-border/60">
                        <td className="px-3 py-1.5">{r.line_number}</td>
                        <td className="px-3 py-1.5">{r.email}</td>
                        <td className="px-3 py-1.5">{r.state}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {(batch.state === 'queued' || batch.state === 'processing') && (
                <Button variant="destructive" onClick={cancelBatch} disabled={busy}>
                  Cancel remaining
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => refreshBatch(batch.id)}
                disabled={busy}
              >
                Refresh
              </Button>
              <Button variant="outline" onClick={reset} disabled={busy}>
                New upload
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
