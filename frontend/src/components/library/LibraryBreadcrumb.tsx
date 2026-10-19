import { Fragment } from 'react'
import { Link } from 'react-router-dom'

export interface BreadcrumbTrailItem {
  label: string
  to: string
}

/** "Resource Library › … › <current>" trail for the library pages. */
export default function LibraryBreadcrumb({ trail, current }: { trail: BreadcrumbTrailItem[]; current: string }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
      {trail.map((item) => (
        <Fragment key={item.to}>
          <Link to={item.to} className="text-link">
            {item.label}
          </Link>
          <span aria-hidden="true"> › </span>
        </Fragment>
      ))}
      <span aria-current="page">{current}</span>
    </nav>
  )
}
