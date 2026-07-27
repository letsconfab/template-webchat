import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { AdminLayout } from '../components/admin/AdminLayout'
import { api } from '../services/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Textarea } from '../components/ui/textarea'
import { Switch } from '../components/ui/switch'

interface Journey {
  id: number
  title: string
  purpose: string
  starter_prompt: string
  icon: string | null
  display_order: number
  is_active: boolean
  knowledge_source_labels: string[]
}

const emptyForm = {
  title: '',
  purpose: '',
  starter_prompt: '',
  icon: '',
  display_order: 0,
  is_active: true,
  knowledge_source_labels: '',
}

export default function AdminJourneysPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [journeys, setJourneys] = useState<Journey[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)

  useEffect(() => {
    if (!user || user.role !== 'admin') {
      navigate('/login')
      return
    }
    void loadJourneys()
  }, [user, navigate])

  const loadJourneys = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get<Journey[]>('/admin/journeys')
      setJourneys(response.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load journeys')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.post('/admin/journeys', {
        title: form.title.trim(),
        purpose: form.purpose.trim(),
        starter_prompt: form.starter_prompt.trim(),
        icon: form.icon.trim() || null,
        display_order: Number(form.display_order) || 0,
        is_active: form.is_active,
        knowledge_source_labels: form.knowledge_source_labels
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      })
      setForm(emptyForm)
      await loadJourneys()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to create journey')
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (journey: Journey) => {
    await api.patch(`/admin/journeys/${journey.id}`, {
      is_active: !journey.is_active,
    })
    await loadJourneys()
  }

  const remove = async (journey: Journey) => {
    if (!window.confirm(`Delete journey “${journey.title}”?`)) return
    await api.delete(`/admin/journeys/${journey.id}`)
    await loadJourneys()
  }

  return (
    <AdminLayout title="Starter journeys">
      <div className="mx-auto max-w-3xl space-y-8 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Starter journeys</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Curate the ALO journeys shown on the chat start screen. Knowledge
            Sources support content but do not auto-publish journeys.
          </p>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleCreate} className="space-y-4 rounded-xl border border-border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Plus className="h-4 w-4" />
            New journey
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
              />
            </div>
            <div>
              <Label htmlFor="display_order">Display order</Label>
              <Input
                id="display_order"
                type="number"
                value={form.display_order}
                onChange={(e) =>
                  setForm({ ...form, display_order: Number(e.target.value) })
                }
              />
            </div>
          </div>
          <div>
            <Label htmlFor="purpose">Purpose</Label>
            <Input
              id="purpose"
              value={form.purpose}
              onChange={(e) => setForm({ ...form, purpose: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="starter_prompt">Starter prompt</Label>
            <Textarea
              id="starter_prompt"
              value={form.starter_prompt}
              onChange={(e) =>
                setForm({ ...form, starter_prompt: e.target.value })
              }
              required
              className="min-h-[80px]"
            />
          </div>
          <div>
            <Label htmlFor="sources">Knowledge source labels (comma-separated)</Label>
            <Input
              id="sources"
              value={form.knowledge_source_labels}
              onChange={(e) =>
                setForm({ ...form, knowledge_source_labels: e.target.value })
              }
              placeholder="ALO Licensing Policy, Governance Handbook"
            />
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={form.is_active}
              onCheckedChange={(checked) =>
                setForm({ ...form, is_active: checked })
              }
            />
            <Label>Active</Label>
          </div>
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Create journey'}
          </Button>
        </form>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <ul className="space-y-3">
            {journeys.map((journey) => (
              <li
                key={journey.id}
                className="rounded-xl border border-border p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">
                      {journey.display_order}. {journey.title}
                      {!journey.is_active && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          (inactive)
                        </span>
                      )}
                    </div>
                    {journey.purpose && (
                      <p className="mt-1 text-sm text-muted-foreground">
                        {journey.purpose}
                      </p>
                    )}
                    <p className="mt-2 text-xs text-muted-foreground">
                      Prompt: {journey.starter_prompt}
                    </p>
                    {journey.knowledge_source_labels?.length > 0 && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Sources: {journey.knowledge_source_labels.join(', ')}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void toggleActive(journey)}
                    >
                      {journey.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void remove(journey)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </li>
            ))}
            {journeys.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No journeys yet. Create the first curated starter above.
              </p>
            )}
          </ul>
        )}
      </div>
    </AdminLayout>
  )
}
