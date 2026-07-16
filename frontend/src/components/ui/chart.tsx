import * as React from "react"
import * as RechartsPrimitive from "recharts"

import { cn } from "../../lib/utils"

const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config?: Record<string, { label?: string; color?: string }>
  }
>(({ className, children, config, ...props }, ref) => {
  const colorVars = config
    ? Object.entries(config).reduce<Record<string, string>>((acc, [key, value]) => {
        if (value.color) {
          acc[`--color-${key}`] = value.color
        }
        return acc
      }, {})
    : undefined

  return (
    <div
      ref={ref}
      className={cn("flex aspect-video justify-center text-xs", className)}
      style={colorVars}
      {...props}
    >
      <RechartsPrimitive.ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </RechartsPrimitive.ResponsiveContainer>
    </div>
  )
})
ChartContainer.displayName = "ChartContainer"

const ChartTooltip = RechartsPrimitive.Tooltip

const ChartTooltipContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    active?: boolean
    payload?: Array<{ name?: string; value?: number; color?: string; dataKey?: string }>
    label?: string
  }
>(({ className, active, payload, label }, ref) => {
  if (!active || !payload?.length) {
    return null
  }
  return (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border bg-background px-3 py-2 shadow-sm",
        className,
      )}
    >
      {label ? <div className="mb-1 font-medium">{label}</div> : null}
      <div className="grid gap-1">
        {payload.map((item) => (
          <div key={String(item.dataKey)} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-muted-foreground">{item.name}</span>
            <span className="font-mono font-medium tabular-nums">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
})
ChartTooltipContent.displayName = "ChartTooltipContent"

export { ChartContainer, ChartTooltip, ChartTooltipContent }
