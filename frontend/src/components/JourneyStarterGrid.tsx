import type { JourneySummary } from '../services/api'

interface JourneyStarterGridProps {
  journeys: JourneySummary[]
  onSelect: (journey: JourneySummary) => void
  disabled?: boolean
}

export function JourneyStarterGrid({
  journeys,
  onSelect,
  disabled,
}: JourneyStarterGridProps) {
  if (journeys.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        <p className="text-base font-medium text-foreground">Start a conversation</p>
        <p className="mt-1 text-sm">
          Type a message below, or ask an administrator to publish starter journeys.
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl py-6">
      <h2 className="text-center text-lg font-semibold text-foreground">
        Choose a starting point
      </h2>
      <p className="mt-1 text-center text-sm text-muted-foreground">
        Administrator-curated ALO journeys grounded in Knowledge Sources.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {journeys.map((journey) => (
          <button
            key={journey.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(journey)}
            className="rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-muted/40 disabled:opacity-50"
          >
            <div className="text-sm font-semibold">{journey.title}</div>
            {journey.purpose && (
              <p className="mt-1 text-xs text-muted-foreground">{journey.purpose}</p>
            )}
            {journey.knowledge_source_labels?.length > 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Sources: {journey.knowledge_source_labels.join(', ')}
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
