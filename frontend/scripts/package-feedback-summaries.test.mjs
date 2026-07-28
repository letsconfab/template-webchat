import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  checkPrivacy,
  checkSvgSafety,
  packageFeedbackSummaries,
} from './package-feedback-summaries.mjs'

const FIXTURE_ROOT = path.join(os.tmpdir(), `feedback-summaries-tests-${process.pid}`)

function cleanRoot() {
  rmSync(FIXTURE_ROOT, { recursive: true, force: true })
}

/**
 * @param {string} name
 * @param {Partial<Record<string, unknown>>} [overrides]
 * @param {string} [extraBody]
 */
function validArtifact(name, overrides = {}, extraBody = '') {
  const meta = {
    schema_version: 1,
    artifact_id: name.replace(/\.md$/, ''),
    title: '30-Day Negative Feedback Summary',
    generated_at: '2026-07-28T00:00:00Z',
    window_start: '2026-06-27T00:00:00Z',
    window_end: '2026-07-27T00:00:00Z',
    authoring_workflow: 'Codex with ChatGPT 5.6 Sol',
    privacy_reviewed: true,
    ...overrides,
  }
  const body = `# ${meta.title}

## Executive summary

Aggregate themes only.

## Evidence snapshot

| Measure | Result |
|---|---:|
| Negative ratings | 11 |

## Major themes

Themes paraphrased.

## Limitations and caveats

Sample is small.

${extraBody}`

  return `---
schema_version: ${meta.schema_version}
artifact_id: ${meta.artifact_id}
title: ${JSON.stringify(meta.title)}
generated_at: "${meta.generated_at}"
window_start: "${meta.window_start}"
window_end: "${meta.window_end}"
authoring_workflow: ${JSON.stringify(meta.authoring_workflow)}
privacy_reviewed: ${meta.privacy_reviewed}
---

${body}`
}

describe('packageFeedbackSummaries', () => {
  /** @type {string} */
  let sourceDir
  /** @type {string} */
  let outputDir

  beforeEach(() => {
    cleanRoot()
    sourceDir = path.join(FIXTURE_ROOT, 'source')
    outputDir = path.join(FIXTURE_ROOT, 'output')
    mkdirSync(sourceDir, { recursive: true })
  })

  afterEach(() => {
    cleanRoot()
  })

  it('writes a versioned empty index when the directory has no artifacts', async () => {
    const result = await packageFeedbackSummaries({ sourceDir, outputDir })
    expect(result.summaries).toEqual([])
    const index = JSON.parse(readFileSync(path.join(outputDir, 'index.json'), 'utf8'))
    expect(index).toEqual({ schema_version: 1, summaries: [] })
  })

  it('sorts multiple valid artifacts by window_end then generated_at descending', async () => {
    writeFileSync(
      path.join(sourceDir, '2026-06-30-negative-feedback-30d.md'),
      validArtifact('2026-06-30-negative-feedback-30d', {
        artifact_id: 'older-window',
        window_start: '2026-05-31T00:00:00Z',
        window_end: '2026-06-30T00:00:00Z',
        generated_at: '2026-07-01T00:00:00Z',
      }),
    )
    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact('2026-07-27-negative-feedback-30d', {
        artifact_id: 'newer-window-older-gen',
        window_start: '2026-06-27T00:00:00Z',
        window_end: '2026-07-27T00:00:00Z',
        generated_at: '2026-07-27T00:00:00Z',
      }),
    )
    writeFileSync(
      path.join(sourceDir, '2026-07-28-negative-feedback-30d.md'),
      validArtifact('2026-07-28-negative-feedback-30d', {
        artifact_id: 'newer-window-newer-gen',
        window_start: '2026-06-27T00:00:00Z',
        window_end: '2026-07-27T00:00:00Z',
        generated_at: '2026-07-28T12:00:00Z',
        title: 'Regenerated same window',
      }),
    )

    // Filename must match pattern — rewrite third with valid date name already done.
    // Wait: 2026-07-28 filename is fine. But we need unique filenames. Good.

    const result = await packageFeedbackSummaries({ sourceDir, outputDir })
    expect(result.summaries.map((s) => s.artifact_id)).toEqual([
      'newer-window-newer-gen',
      'newer-window-older-gen',
      'older-window',
    ])
  })

  it('rejects duplicate artifact IDs with file-specific errors', async () => {
    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact('2026-07-27-negative-feedback-30d', {
        artifact_id: 'same-id',
      }),
    )
    writeFileSync(
      path.join(sourceDir, '2026-07-26-negative-feedback-30d.md'),
      validArtifact('2026-07-26-negative-feedback-30d', {
        artifact_id: 'same-id',
        window_start: '2026-06-26T00:00:00Z',
        window_end: '2026-07-26T00:00:00Z',
      }),
    )

    await expect(
      packageFeedbackSummaries({ sourceDir, outputDir }),
    ).rejects.toThrow(/duplicate artifact_id/)
    expect(existsSync(outputDir)).toBe(false)
  })

  it('fails on malformed timestamps, windows, headings, and privacy_reviewed', async () => {
    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      `---
schema_version: 1
artifact_id: bad-meta
title: Bad
generated_at: "not-a-date"
window_start: "2026-07-01T00:00:00Z"
window_end: "2026-07-10T00:00:00Z"
authoring_workflow: test
privacy_reviewed: false
---

# Bad

## Executive summary

x
`,
    )

    try {
      await packageFeedbackSummaries({ sourceDir, outputDir })
      expect.unreachable('should have thrown')
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      expect(message).toMatch(/privacy_reviewed/)
      expect(message).toMatch(/timestamp|generated_at|ISO-8601/)
      expect(message).toMatch(/30 days|window/)
      expect(message).toMatch(/Evidence snapshot|Major themes|Limitations/)
    }
  })

  it('fails privacy checks for emails, UUIDs, and secrets', async () => {
    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact(
        '2026-07-27-negative-feedback-30d',
        { artifact_id: 'leaky' },
        [
          'Contact t***@example.com',
          'case 550e8400-e29b-41d4-a716-446655440000',
          'api_key sk-abcdefghijklmnopqrstuvwxyz',
        ].join('\n\n'),
      ),
    )

    await expect(
      packageFeedbackSummaries({ sourceDir, outputDir }),
    ).rejects.toThrow(/email|UUID|secret/i)
  })

  it('copies valid relative assets and rejects missing or unsafe ones', async () => {
    const assetsDir = path.join(sourceDir, 'assets', 'demo')
    mkdirSync(assetsDir, { recursive: true })
    writeFileSync(
      path.join(assetsDir, 'chart.svg'),
      '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="1" cy="1" r="1"/></svg>\n',
    )

    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact(
        '2026-07-27-negative-feedback-30d',
        { artifact_id: 'with-asset' },
        '![Chart](assets/demo/chart.svg)\n',
      ),
    )

    const result = await packageFeedbackSummaries({ sourceDir, outputDir })
    const entry = result.summaries[0]
    const packaged = path.join(
      outputDir,
      'artifacts',
      entry.artifact_id,
      entry.content_url.split('/').at(-2),
      'assets',
      'demo',
      'chart.svg',
    )
    expect(existsSync(packaged)).toBe(true)
    expect(existsSync(path.join(
      outputDir,
      'artifacts',
      entry.artifact_id,
      entry.content_url.split('/').at(-2),
      'summary.md',
    ))).toBe(true)

    writeFileSync(
      path.join(sourceDir, '2026-07-26-negative-feedback-30d.md'),
      validArtifact(
        '2026-07-26-negative-feedback-30d',
        {
          artifact_id: 'bad-asset',
          window_start: '2026-06-26T00:00:00Z',
          window_end: '2026-07-26T00:00:00Z',
        },
        '![Remote](https://example.com/x.png)\n',
      ),
    )

    const previousIndex = readFileSync(path.join(outputDir, 'index.json'), 'utf8')
    await expect(
      packageFeedbackSummaries({ sourceDir, outputDir }),
    ).rejects.toThrow(/relative artifact asset/)
    // Failed run must not leave a partially rewritten package.
    expect(readFileSync(path.join(outputDir, 'index.json'), 'utf8')).toBe(
      previousIndex,
    )
  })

  it('changes content hash when body or assets change', async () => {
    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact('2026-07-27-negative-feedback-30d', {
        artifact_id: 'hash-demo',
      }),
    )
    const first = await packageFeedbackSummaries({ sourceDir, outputDir })
    const firstHash = first.summaries[0].content_url

    writeFileSync(
      path.join(sourceDir, '2026-07-27-negative-feedback-30d.md'),
      validArtifact(
        '2026-07-27-negative-feedback-30d',
        { artifact_id: 'hash-demo' },
        'Updated analysis note.\n',
      ),
    )
    const second = await packageFeedbackSummaries({ sourceDir, outputDir })
    expect(second.summaries[0].content_url).not.toBe(firstHash)
  })

  it('requires the canonical source directory to exist', async () => {
    await expect(
      packageFeedbackSummaries({
        sourceDir: path.join(FIXTURE_ROOT, 'missing'),
        outputDir,
      }),
    ).rejects.toThrow(/required but missing/)
  })
})

describe('privacy and SVG helpers', () => {
  it('flags privacy patterns with line numbers', () => {
    const errors = checkPrivacy('hello\nuser@example.com\n', 'demo.md')
    expect(errors).toEqual([
      expect.objectContaining({
        file: 'demo.md',
        rule: 'email',
        line: 2,
      }),
    ])
  })

  it('rejects unsafe SVG constructs', () => {
    expect(
      checkSvgSafety('<svg><script>alert(1)</script></svg>', 'x.svg'),
    ).toEqual([expect.objectContaining({ rule: 'svg_script' })])
    expect(
      checkSvgSafety('<svg onclick="x()"></svg>', 'x.svg'),
    ).toEqual([expect.objectContaining({ rule: 'svg_event' })])
  })
})

describe('ordinary link validation', () => {
  it('allows HTTPS and anchors and rejects filesystem or http links', async () => {
    const { checkOrdinaryLinks } = await import('./package-feedback-summaries.mjs')
    expect(
      checkOrdinaryLinks(
        'See [ok](https://example.com/doc) and [here](#limitations).',
        'a.md',
      ),
    ).toEqual([])
    expect(
      checkOrdinaryLinks('See [bad](docs/local.md)', 'a.md'),
    ).toEqual([expect.objectContaining({ rule: 'link' })])
    expect(
      checkOrdinaryLinks('See [bad](http://example.com/doc)', 'a.md'),
    ).toEqual([expect.objectContaining({ rule: 'link' })])
  })
})
