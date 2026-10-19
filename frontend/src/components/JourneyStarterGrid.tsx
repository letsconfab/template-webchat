import type { JourneySummary } from '../services/api'

interface JourneyStarterGridProps {
  journeys: JourneySummary[]
  onSelect: (journey: JourneySummary) => void
  disabled?: boolean
}

/** Journeys offered as starter-question cards in the Librarian's empty state. */
export function JourneyStarterGrid({
  journeys,
  onSelect,
  disabled,
}: JourneyStarterGridProps) {
  if (journeys.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground">
        Type your question below to get started.
      </p>
    )
  }

  return (
    <div>
      <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Or start with a question
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {journeys.map((journey) => (
          <button
            key={journey.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(journey)}
            className="flex h-full flex-col rounded-lg border bg-card p-5 text-left text-card-foreground shadow-sm transition-colors hover:border-accent hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <span className="font-display text-lg font-semibold">
              {journey.icon ? `${journey.icon} ` : ''}
              {journey.title}
            </span>
            {journey.purpose && (
              <span className="mt-1 text-sm text-muted-foreground">{journey.purpose}</span>
            )}
            {journey.starter_prompt && (
              <span className="mt-3 text-sm italic text-foreground">
                “{journey.starter_prompt}”
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
