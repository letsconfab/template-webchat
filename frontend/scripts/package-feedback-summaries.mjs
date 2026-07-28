#!/usr/bin/env node
/**
 * Build-time packager for docs/feedback-summaries/*.md artifacts.
 * Discovers, validates, and packages public-safe Markdown summaries into
 * frontend/public/static/feedback-summaries/ for the Vite build.
 */
import { createHash } from 'node:crypto'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import matter from 'gray-matter'
import { z } from 'zod'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const FRONTEND_ROOT = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..')
const DEFAULT_SOURCE_DIR = path.join(REPO_ROOT, 'docs', 'feedback-summaries')
const DEFAULT_OUTPUT_DIR = path.join(
  FRONTEND_ROOT,
  'public',
  'static',
  'feedback-summaries',
)

const FILENAME_RE = /^\d{4}-\d{2}-\d{2}-negative-feedback-30d\.md$/
const ARTIFACT_ID_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000
const MAX_TITLE_LEN = 200
const MAX_WORKFLOW_LEN = 500

const REQUIRED_HEADINGS = [
  '## Executive summary',
  '## Evidence snapshot',
  '## Major themes',
  '## Limitations and caveats',
]

const frontMatterSchema = z.object({
  schema_version: z.literal(1),
  artifact_id: z
    .string()
    .min(1)
    .max(120)
    .regex(ARTIFACT_ID_RE, 'artifact_id must be kebab-case'),
  title: z.string().min(1).max(MAX_TITLE_LEN),
  generated_at: z.string().min(1),
  window_start: z.string().min(1),
  window_end: z.string().min(1),
  authoring_workflow: z.string().min(1).max(MAX_WORKFLOW_LEN),
  privacy_reviewed: z.literal(true),
})

const PRIVACY_RULES = [
  {
    id: 'email',
    re: /\b[A-Za-z0-9._%+*-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
    message: 'possible email or masked email address',
  },
  {
    id: 'uuid',
    re: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    message: 'UUID identifier',
  },
  {
    id: 'ipv4',
    re: /\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b/g,
    message: 'IPv4 address',
  },
  {
    id: 'secret',
    re: /\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|bearer\s+[A-Za-z0-9._~+/=-]{8,}|sk-[A-Za-z0-9]{16,})\b/gi,
    message: 'secret or token pattern',
  },
  {
    id: 'private_ops_url',
    re: /\/admin\/feedback\/[0-9a-f-]{8,}/gi,
    message: 'private Feedback Case operational URL',
  },
]

/**
 * @typedef {{ file: string, rule: string, line: number, message: string }} ValidationError
 */

/**
 * @param {string} iso
 * @param {string} field
 * @param {string} file
 * @returns {{ ok: true, date: Date } | { ok: false, error: ValidationError }}
 */
function parseUtcIso(iso, field, file) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(iso)) {
    return {
      ok: false,
      error: {
        file,
        rule: 'timestamp',
        line: 1,
        message: `${field} must be an ISO-8601 UTC timestamp ending in Z`,
      },
    }
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return {
      ok: false,
      error: {
        file,
        rule: 'timestamp',
        line: 1,
        message: `${field} is not a valid date`,
      },
    }
  }
  return { ok: true, date }
}

/**
 * @param {string} text
 * @param {string} file
 * @returns {ValidationError[]}
 */
export function checkPrivacy(text, file) {
  /** @type {ValidationError[]} */
  const errors = []
  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    for (const rule of PRIVACY_RULES) {
      rule.re.lastIndex = 0
      if (rule.re.test(line)) {
        errors.push({
          file,
          rule: rule.id,
          line: i + 1,
          message: rule.message,
        })
      }
    }
  }
  return errors
}

/**
 * @param {string} body
 * @param {string} file
 * @returns {ValidationError[]}
 */
function checkRequiredHeadings(body, file) {
  /** @type {ValidationError[]} */
  const errors = []
  for (const heading of REQUIRED_HEADINGS) {
    const matches = body.match(new RegExp(`^${escapeRegExp(heading)}\\s*$`, 'gm'))
    const count = matches?.length ?? 0
    if (count !== 1) {
      errors.push({
        file,
        rule: 'heading',
        line: 1,
        message: `required heading "${heading}" must occur exactly once (found ${count})`,
      })
    }
  }
  return errors
}

/**
 * @param {string} body
 * @param {string} file
 * @returns {ValidationError[]}
 */
function checkRawHtml(body, file) {
  /** @type {ValidationError[]} */
  const errors = []
  const lines = body.split('\n')
  let inFence = false
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (/^```/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    if (/<\/?[a-zA-Z][\w:-]*\b[^>]*>/.test(line)) {
      errors.push({
        file,
        rule: 'raw_html',
        line: i + 1,
        message: 'raw HTML is not allowed in canonical artifacts',
      })
    }
  }
  return errors
}

/**
 * @param {string} body
 * @returns {string[]}
 */
export function extractRelativeImagePaths(body) {
  const paths = []
  const re = /!\[[^\]]*]\(([^)]+)\)/g
  let match
  while ((match = re.exec(body)) !== null) {
    paths.push(match[1].trim())
  }
  return paths
}

/**
 * @param {string} svgText
 * @param {string} file
 * @returns {ValidationError[]}
 */
export function checkSvgSafety(svgText, file) {
  /** @type {ValidationError[]} */
  const errors = []
  if (/<script[\s>]/i.test(svgText)) {
    errors.push({
      file,
      rule: 'svg_script',
      line: 1,
      message: 'SVG must not contain <script>',
    })
  }
  if (/<foreignObject[\s>]/i.test(svgText)) {
    errors.push({
      file,
      rule: 'svg_foreignObject',
      line: 1,
      message: 'SVG must not contain <foreignObject>',
    })
  }
  if (/\son[a-z]+\s*=/i.test(svgText)) {
    errors.push({
      file,
      rule: 'svg_event',
      line: 1,
      message: 'SVG must not contain event-handler attributes',
    })
  }
  if (/(?:xlink:)?href\s*=\s*["']https?:/i.test(svgText)) {
    errors.push({
      file,
      rule: 'svg_external',
      line: 1,
      message: 'SVG must not contain external references',
    })
  }
  return errors
}

/**
 * @param {string} value
 */
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Drop a leading ATX H1 that repeats the front-matter title so the admin detail
 * page can own the document title without a duplicate heading.
 * @param {string} body
 * @param {string | undefined} title
 */
export function stripLeadingTitleHeading(body, title) {
  if (!title) return body
  const lines = body.split('\n')
  let index = 0
  while (index < lines.length && lines[index].trim() === '') index += 1
  if (index >= lines.length) return body
  const heading = lines[index].match(/^#\s+(.+)$/)
  if (!heading) return body
  if (heading[1].trim() !== title.trim()) return body
  lines.splice(index, 1)
  if (lines[index]?.trim() === '') lines.splice(index, 1)
  return lines.join('\n')
}

/**
 * @param {ValidationError[]} errors
 */
export function formatValidationErrors(errors) {
  return errors
    .map(
      (e) =>
        `${e.file}:${e.line} [${e.rule}] ${e.message}`,
    )
    .join('\n')
}

/**
 * @param {{
 *   sourceDir?: string,
 *   outputDir?: string,
 * }} [options]
 */
export async function packageFeedbackSummaries(options = {}) {
  const sourceDir = path.resolve(options.sourceDir ?? DEFAULT_SOURCE_DIR)
  const outputDir = path.resolve(options.outputDir ?? DEFAULT_OUTPUT_DIR)

  if (!existsSync(sourceDir) || !statSync(sourceDir).isDirectory()) {
    throw new Error(
      `Feedback summaries source directory is required but missing: ${sourceDir}`,
    )
  }

  const entries = readdirSync(sourceDir)
    .filter((name) => FILENAME_RE.test(name))
    .sort()

  /** @type {ValidationError[]} */
  const errors = []
  /** @type {Array<{
   *   meta: z.infer<typeof frontMatterSchema>,
   *   body: string,
   *   fileName: string,
   *   sourcePath: string,
   *   assets: Array<{ relativePath: string, absolutePath: string }>,
   *   contentHash: string,
   * }>} */
  const prepared = []
  const seenIds = new Map()

  for (const fileName of entries) {
    const sourcePath = path.join(sourceDir, fileName)
    const raw = readFileSync(sourcePath, 'utf8')
    let parsed
    try {
      parsed = matter(raw)
    } catch (err) {
      errors.push({
        file: fileName,
        rule: 'yaml',
        line: 1,
        message: `malformed YAML front matter: ${err instanceof Error ? err.message : String(err)}`,
      })
      continue
    }

    const fmResult = frontMatterSchema.safeParse(parsed.data)
    if (!fmResult.success) {
      for (const issue of fmResult.error.issues) {
        errors.push({
          file: fileName,
          rule: 'front_matter',
          line: 1,
          message: `${issue.path.join('.') || 'front_matter'}: ${issue.message}`,
        })
      }
    }

    const data = /** @type {Record<string, unknown>} */ (parsed.data)
    const artifactId =
      typeof data.artifact_id === 'string' ? data.artifact_id : null

    if (artifactId) {
      if (seenIds.has(artifactId)) {
        errors.push({
          file: fileName,
          rule: 'duplicate_id',
          line: 1,
          message: `duplicate artifact_id "${artifactId}" (also in ${seenIds.get(artifactId)})`,
        })
      } else {
        seenIds.set(artifactId, fileName)
      }
    }

    const windowStart =
      typeof data.window_start === 'string' ? data.window_start : null
    const windowEnd =
      typeof data.window_end === 'string' ? data.window_end : null
    const generatedAt =
      typeof data.generated_at === 'string' ? data.generated_at : null

    const start = windowStart
      ? parseUtcIso(windowStart, 'window_start', fileName)
      : null
    const end = windowEnd
      ? parseUtcIso(windowEnd, 'window_end', fileName)
      : null
    const generated = generatedAt
      ? parseUtcIso(generatedAt, 'generated_at', fileName)
      : null
    if (start && !start.ok) errors.push(start.error)
    if (end && !end.ok) errors.push(end.error)
    if (generated && !generated.ok) errors.push(generated.error)

    if (start?.ok && end?.ok) {
      if (start.date.getTime() >= end.date.getTime()) {
        errors.push({
          file: fileName,
          rule: 'window',
          line: 1,
          message: 'window_start must precede window_end',
        })
      } else if (end.date.getTime() - start.date.getTime() !== THIRTY_DAYS_MS) {
        errors.push({
          file: fileName,
          rule: 'window',
          line: 1,
          message: 'evidence window must span exactly 30 days',
        })
      }
    }

    const body = stripLeadingTitleHeading(
      parsed.content.replace(/^\n+/, ''),
      typeof data.title === 'string' ? data.title : undefined,
    )
    errors.push(...checkRequiredHeadings(body, fileName))
    errors.push(...checkRawHtml(body, fileName))
    errors.push(
      ...checkPrivacy(`${JSON.stringify(parsed.data)}\n${body}`, fileName),
    )

    /** @type {Array<{ relativePath: string, absolutePath: string }>} */
    const assets = []
    const imagePaths = extractRelativeImagePaths(body)
    for (const imagePath of imagePaths) {
      if (/^(https?:|file:|\/\/|\/)/i.test(imagePath) || path.isAbsolute(imagePath)) {
        errors.push({
          file: fileName,
          rule: 'asset',
          line: 1,
          message: `image path must be a relative artifact asset: ${imagePath}`,
        })
        continue
      }
      if (imagePath.includes('\\') || imagePath.split('/').includes('..')) {
        errors.push({
          file: fileName,
          rule: 'asset',
          line: 1,
          message: `path traversal is not allowed: ${imagePath}`,
        })
        continue
      }
      const ext = path.extname(imagePath).toLowerCase()
      if (ext !== '.svg' && ext !== '.png') {
        errors.push({
          file: fileName,
          rule: 'asset',
          line: 1,
          message: `only .svg and .png assets are allowed: ${imagePath}`,
        })
        continue
      }

      const absolutePath = path.resolve(path.dirname(sourcePath), imagePath)
      const relToSource = path.relative(sourceDir, absolutePath)
      if (relToSource.startsWith('..') || path.isAbsolute(relToSource)) {
        errors.push({
          file: fileName,
          rule: 'asset',
          line: 1,
          message: `asset must remain within docs/feedback-summaries/: ${imagePath}`,
        })
        continue
      }
      if (!existsSync(absolutePath)) {
        errors.push({
          file: fileName,
          rule: 'asset',
          line: 1,
          message: `missing referenced asset: ${imagePath}`,
        })
        continue
      }

      if (ext === '.svg') {
        const svgText = readFileSync(absolutePath, 'utf8')
        errors.push(...checkSvgSafety(svgText, `${fileName} → ${imagePath}`))
        errors.push(...checkPrivacy(svgText, `${fileName} → ${imagePath}`))
      }

      assets.push({ relativePath: imagePath, absolutePath })
    }

    if (!fmResult.success) {
      continue
    }

    const meta = fmResult.data
    const hash = createHash('sha256')
    hash.update(body)
    for (const asset of assets.sort((a, b) =>
      a.relativePath.localeCompare(b.relativePath),
    )) {
      hash.update(asset.relativePath)
      hash.update(readFileSync(asset.absolutePath))
    }
    const contentHash = hash.digest('hex').slice(0, 16)

    prepared.push({
      meta,
      body,
      fileName,
      sourcePath,
      assets,
      contentHash,
    })
  }

  if (errors.length > 0) {
    const message = formatValidationErrors(errors)
    const err = new Error(`Feedback summary packaging failed:\n${message}`)
    // @ts-expect-error attach structured errors for tests
    err.validationErrors = errors
    throw err
  }

  prepared.sort((a, b) => {
    const endCmp = b.meta.window_end.localeCompare(a.meta.window_end)
    if (endCmp !== 0) return endCmp
    return b.meta.generated_at.localeCompare(a.meta.generated_at)
  })

  const stagingParent = mkdtempSync(path.join(tmpdir(), 'feedback-summaries-'))
  const stagingDir = path.join(stagingParent, 'feedback-summaries')
  mkdirSync(path.join(stagingDir, 'artifacts'), { recursive: true })

  /** @type {Array<Record<string, string>>} */
  const summaries = []

  try {
    for (const item of prepared) {
      const artifactDir = path.join(
        stagingDir,
        'artifacts',
        item.meta.artifact_id,
        item.contentHash,
      )
      const assetsOutDir = path.join(artifactDir, 'assets')
      mkdirSync(artifactDir, { recursive: true })
      writeFileSync(path.join(artifactDir, 'summary.md'), item.body, 'utf8')

      for (const asset of item.assets) {
        const dest = path.join(artifactDir, asset.relativePath)
        mkdirSync(path.dirname(dest), { recursive: true })
        copyFileSync(asset.absolutePath, dest)
        // Ensure assets live under the artifact hash directory (also create
        // assets/ when the markdown uses assets/... paths).
        if (!existsSync(assetsOutDir) && asset.relativePath.startsWith('assets/')) {
          mkdirSync(assetsOutDir, { recursive: true })
        }
      }

      const contentUrl = `/static/feedback-summaries/artifacts/${item.meta.artifact_id}/${item.contentHash}/summary.md`
      const assetBaseUrl = `/static/feedback-summaries/artifacts/${item.meta.artifact_id}/${item.contentHash}/`
      summaries.push({
        artifact_id: item.meta.artifact_id,
        title: item.meta.title,
        generated_at: item.meta.generated_at,
        window_start: item.meta.window_start,
        window_end: item.meta.window_end,
        content_url: contentUrl,
        asset_base_url: assetBaseUrl,
      })
    }

    writeFileSync(
      path.join(stagingDir, 'index.json'),
      `${JSON.stringify({ schema_version: 1, summaries }, null, 2)}\n`,
      'utf8',
    )

    mkdirSync(path.dirname(outputDir), { recursive: true })
    if (existsSync(outputDir)) {
      rmSync(outputDir, { recursive: true, force: true })
    }
    renameSync(stagingDir, outputDir)
  } finally {
    rmSync(stagingParent, { recursive: true, force: true })
  }

  return {
    sourceDir,
    outputDir,
    summaries,
  }
}

function isMain() {
  const entry = process.argv[1]
  if (!entry) return false
  return import.meta.url === pathToFileURL(path.resolve(entry)).href
}

if (isMain()) {
  packageFeedbackSummaries()
    .then((result) => {
      console.log(
        `Packaged ${result.summaries.length} feedback summar${result.summaries.length === 1 ? 'y' : 'ies'} → ${result.outputDir}`,
      )
    })
    .catch((err) => {
      console.error(err instanceof Error ? err.message : err)
      process.exit(1)
    })
}
