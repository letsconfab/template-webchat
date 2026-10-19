/**
 * The nine INTEGRATE Systems: the single frontend source for their slugs,
 * names, areas, and taglines. Library Documents are filed under one of these,
 * and Browse folders live at `/library/browse/<slug>`.
 */
export interface IntegrateSystem {
  slug: string
  name: string
  area: string
  tagline: string
}

export const INTEGRATE_SYSTEMS: readonly IntegrateSystem[] = [
  { slug: 'inspire', name: 'Inspire', area: 'Leadership', tagline: 'from command to connection' },
  { slug: 'nurture', name: 'Nurture', area: 'Teams', tagline: 'from silos to safe, healing units' },
  { slug: 'trust', name: 'Trust', area: 'Information systems', tagline: 'from secrecy to transparency' },
  { slug: 'embody', name: 'Embody', area: 'Culture', tagline: 'from slogans to lived values' },
  { slug: 'guide', name: 'Guide', area: 'Management', tagline: 'from control to compassionate accountability' },
  { slug: 'regulate', name: 'Regulate', area: 'Policies', tagline: 'from restriction to justice and care' },
  { slug: 'align', name: 'Align', area: 'Workflows', tagline: 'from burnout cycles to humane rhythms' },
  { slug: 'transcend', name: 'Transcend', area: 'Community & patients', tagline: 'from outreach to shared healing' },
  { slug: 'engage', name: 'Engage', area: 'People systems', tagline: 'from tokenism to belonging and agency' },
]

export function integrateSystemPath(system: IntegrateSystem): string {
  return `/library/browse/${system.slug}`
}
