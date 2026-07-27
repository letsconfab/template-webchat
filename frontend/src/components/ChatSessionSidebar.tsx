import { Pencil, Plus, Trash2 } from 'lucide-react'
import type { ChatSessionSummary } from '../services/api'

interface ChatSessionSidebarProps {
  sessions: ChatSessionSummary[]
  activeUuid: string | null
  onSelect: (uuid: string) => void
  onNew: () => void
  onRename: (uuid: string, title: string) => void
  onDelete: (uuid: string) => void
}

function formatUpdated(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function ChatSessionSidebar({
  sessions,
  activeUuid,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: ChatSessionSidebarProps) {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border bg-card">
      <div className="border-b border-border p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-xs text-muted-foreground">
            No conversations yet.
          </p>
        )}
        <ul className="space-y-1">
          {sessions.map((session) => {
            const active = session.client_uuid === activeUuid
            return (
              <li key={session.client_uuid}>
                <div
                  className={`group flex items-start gap-1 rounded-md px-2 py-2 ${
                    active ? 'bg-muted' : 'hover:bg-muted/60'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(session.client_uuid)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="truncate text-sm font-medium">
                      {session.title || 'New chat'}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {formatUpdated(session.updated_at)}
                    </div>
                  </button>
                  <button
                    type="button"
                    title="Rename"
                    className="rounded p-1 opacity-0 hover:bg-background group-hover:opacity-100"
                    onClick={() => {
                      const next = window.prompt(
                        'Rename conversation',
                        session.title || 'New chat',
                      )
                      if (next && next.trim()) {
                        onRename(session.client_uuid, next.trim())
                      }
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                  <button
                    type="button"
                    title="Delete"
                    className="rounded p-1 opacity-0 hover:bg-background group-hover:opacity-100"
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete “${session.title || 'New chat'}”? This cannot be undone.`,
                        )
                      ) {
                        onDelete(session.client_uuid)
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </aside>
  )
}
