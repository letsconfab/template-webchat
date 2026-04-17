import * as React from "react"

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive'
}

const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className = "", variant = 'default', children, ...props }, ref) => {
    const baseClasses = "relative w-full rounded-lg border p-4"
    const variantClasses = variant === 'destructive' 
      ? "border-red-200 bg-red-50 text-red-800"
      : "border-gray-200 bg-gray-50 text-gray-800"
    
    return (
      <div
        ref={ref}
        role="alert"
        className={`${baseClasses} ${variantClasses} ${className}`}
        {...props}
      >
        {children}
      </div>
    )
  }
)
Alert.displayName = "Alert"

const AlertDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className = "", children, ...props }, ref) => (
  <div
    ref={ref}
    className={`text-sm ${className}`}
    {...props}
  >
    {children}
  </div>
))
AlertDescription.displayName = "AlertDescription"

export { Alert, AlertDescription }
