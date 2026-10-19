import { useState } from 'react'
import { Heart } from 'lucide-react'

import { cn } from '../lib/utils'

const BRAND_NAME = 'A Loving Organization'

const heart = <Heart aria-hidden="true" className="h-6 w-6 fill-current text-brand-heart" />

const BRAND_SOURCES = {
  full: '/brand/alo-logo-long.svg',
  mark: '/brand/alo-heart.svg',
} as const

interface BrandLogoProps {
  className?: string
  /** `full` is the long logo; `mark` is the heart alone. */
  variant?: keyof typeof BRAND_SOURCES
}

/**
 * The brand logo. The image files live in the gitignored `public/brand/`
 * folder, so environments without them fall back to a text wordmark.
 */
export default function BrandLogo({ className, variant = 'full' }: BrandLogoProps) {
  const [failed, setFailed] = useState(false)

  if (!failed) {
    return (
      <img
        src={BRAND_SOURCES[variant]}
        alt={BRAND_NAME}
        className={cn(variant === 'full' ? 'h-8 w-auto' : 'h-8 w-8', className)}
        onError={() => setFailed(true)}
      />
    )
  }

  if (variant === 'mark') {
    return (
      <span role="img" aria-label={BRAND_NAME} className={cn('inline-flex', className)}>
        {heart}
      </span>
    )
  }

  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      {heart}
      <span className="font-display text-lg font-semibold text-foreground">{BRAND_NAME}</span>
    </span>
  )
}
