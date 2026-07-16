import { useEffect, useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, XAxis, YAxis } from 'recharts'

import { api } from '../../services/api'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '../ui/chart'

type Days = 7 | 30 | 90

interface DailyBucket {
  date: string
  messages: number
  sessions: number
  is_partial: boolean
}

interface AnalyticsOverview {
  days: Days
  thumbs_up: number
  thumbs_down: number
  undated_messages: number
  undated_sessions: number
  undated_feedback: number
  daily: DailyBucket[]
}

const DAY_OPTIONS: Days[] = [7, 30, 90]

const chartConfig = {
  messages: { label: 'Messages (user + assistant)', color: 'hsl(var(--primary))' },
  sessions: { label: 'Sessions', color: 'hsl(var(--muted-foreground))' },
}

export function AnalyticsOverviewSection() {
  const [days, setDays] = useState<Days>(30)
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await api.get<AnalyticsOverview>('/admin/analytics/overview', {
          params: { days },
        })
        if (!cancelled) {
          setData(response.data)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError('Failed to load analytics')
          setData(null)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [days])

  const chartData =
    data?.daily.map((bucket) => ({
      ...bucket,
      label: bucket.is_partial ? `${bucket.date} (today)` : bucket.date,
    })) ?? []

  return (
    <div className="space-y-4 mb-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Analytics</h2>
        <div className="flex gap-2">
          {DAY_OPTIONS.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={days === option ? 'default' : 'outline'}
              onClick={() => setDays(option)}
            >
              {option}d
            </Button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Thumbs up</CardDescription>
            <CardTitle className="flex items-center gap-2 text-3xl">
              <ThumbsUp className="h-6 w-6 text-emerald-600" />
              {loading ? '—' : data?.thumbs_up ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Thumbs down</CardDescription>
            <CardTitle className="flex items-center gap-2 text-3xl">
              <ThumbsDown className="h-6 w-6 text-destructive" />
              {loading ? '—' : data?.thumbs_down ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Usage volume</CardTitle>
          <CardDescription>
            Daily message count (user + assistant) and new chat sessions. Today is a partial day.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              Loading…
            </div>
          ) : (
            <ChartContainer config={chartConfig} className="h-64 w-full aspect-auto">
              <LineChart data={chartData} margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
                <YAxis allowDecimals={false} width={36} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="messages"
                  name="Messages (user + assistant)"
                  stroke="var(--color-messages)"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="sessions"
                  name="Sessions"
                  stroke="var(--color-sessions)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ChartContainer>
          )}
          {data && (data.undated_messages > 0 || data.undated_sessions > 0) && (
            <p className="mt-3 text-xs text-muted-foreground">
              Undated rows excluded from the chart: {data.undated_messages} messages,{' '}
              {data.undated_sessions} sessions
              {data.undated_feedback > 0 ? `, ${data.undated_feedback} feedback` : ''}.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
