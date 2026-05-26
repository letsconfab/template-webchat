import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  LogOut,
  RefreshCw,
  Send,
  Upload,
  FileUp,
  GitBranch,
  CircleCheck,
  AlertTriangle,
  X,
  PencilLine,
  Save,
  Trash2,
  Settings,
} from 'lucide-react'
import { api } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Textarea } from '../components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'

type SourceStatus = 'uploaded' | 'processing' | 'draft_ready' | 'committed' | 'failed'

interface SourceItem {
  id: number
  original_filename: string
  title: string | null
  file_type: string
  status: SourceStatus
  error_message: string | null
  created_at: string
  updated_at: string
  job?: {
    id: number
    status: string
    progress: number
    message: string | null
    started_at: string | null
    finished_at: string | null
  } | null
  patch?: PatchItem | null
}

interface PatchItem {
  id: number
  source_id: number
  status: 'draft' | 'committed'
  draft_title: string
  draft_json: BookTree
  draft_markdown: string
  redaction_report?: Record<string, number>
  created_at: string
  updated_at: string
  committed_at: string | null
}

interface TreeNode {
  id: number
  title: string
  node_type: 'chapter' | 'topic' | 'page'
  level: number
  content_md?: string | null
  children: TreeNode[]
  updated_at: string
}

interface BookTree {
  book_title: string
  summary?: string
  chapters: Array<{
    title: string
    summary?: string
    topics: Array<{
      title: string
      summary?: string
      pages: Array<{
        title: string
        content_md: string
      }>
    }>
  }>
}

interface DraftTreeNode {
  path: string
  title: string
  node_type: 'chapter' | 'topic' | 'page'
  level: number
  content_md?: string | null
  children: DraftTreeNode[]
}

interface KnowledgeStatus {
  source_counts: Record<SourceStatus, number>
  patch_counts: { draft: number; committed: number }
  active_nodes: number
  rag_initialized: boolean
  rag_healthy: boolean
  chat_ready: boolean
  storage_root: string
}

type ContentNode = TreeNode

const statusBadge = (status: string) => {
  if (status === 'committed') {
    return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">Committed</Badge>
  }
  if (status === 'draft') {
    return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Draft</Badge>
  }
  if (status === 'draft_ready') {
    return <Badge className="bg-blue-100 text-blue-800 border-blue-200">Ready</Badge>
  }
  if (status === 'processing') {
    return <Badge className="bg-indigo-100 text-indigo-800 border-indigo-200">Processing</Badge>
  }
  if (status === 'failed') {
    return <Badge className="bg-red-100 text-red-800 border-red-200">Failed</Badge>
  }
  return <Badge variant="secondary">{status}</Badge>
}

const ragStatusBadge = (status: KnowledgeStatus | null) => {
  if (!status) {
    return <Badge variant="secondary">RAG status unavailable</Badge>
  }

  if (status.chat_ready) {
    return <Badge className="border-emerald-200 bg-emerald-100 text-emerald-800">RAG ready</Badge>
  }

  if (status.rag_healthy) {
    return <Badge className="border-amber-200 bg-amber-100 text-amber-800">RAG healthy, indexing</Badge>
  }

  if (status.rag_initialized) {
    return <Badge className="border-red-200 bg-red-100 text-red-800">RAG init only</Badge>
  }

  return <Badge className="border-slate-200 bg-slate-100 text-slate-700">RAG offline</Badge>
}

const ProgressBar: React.FC<{ value: number }> = ({ value }) => {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
      <div
        className="h-full rounded-full bg-gradient-to-r from-sky-500 via-cyan-500 to-emerald-500 transition-all duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

const flattenPages = (nodes: ContentNode[]): ContentNode[] => {
  const pages: ContentNode[] = []
  const walk = (items: ContentNode[]) => {
    items.forEach((item) => {
      if (item.node_type === 'page') {
        pages.push(item)
      }
      if (item.children.length > 0) {
        walk(item.children)
      }
    })
  }
  walk(nodes)
  return pages
}

const getFirstPage = (nodes: ContentNode[]): ContentNode | null => flattenPages(nodes)[0] || null

const buildDraftTree = (book: BookTree): DraftTreeNode[] =>
  (book.chapters || []).map((chapter, chapterIndex) => ({
    path: `${chapterIndex}`,
    title: chapter.title,
    node_type: 'chapter',
    level: 1,
    content_md: chapter.summary || null,
    children: (chapter.topics || []).map((topic, topicIndex) => ({
      path: `${chapterIndex}.${topicIndex}`,
      title: topic.title,
      node_type: 'topic',
      level: 2,
      content_md: topic.summary || null,
      children: (topic.pages || []).map((page, pageIndex) => ({
        path: `${chapterIndex}.${topicIndex}.${pageIndex}`,
        title: page.title,
        node_type: 'page',
        level: 3,
        content_md: page.content_md,
        children: [],
      })),
    })),
  }))

const flattenDraftPages = (nodes: DraftTreeNode[]): DraftTreeNode[] => {
  const pages: DraftTreeNode[] = []
  const walk = (items: DraftTreeNode[]) => {
    items.forEach((item) => {
      if (item.node_type === 'page') {
        pages.push(item)
      }
      if (item.children.length > 0) {
        walk(item.children)
      }
    })
  }
  walk(nodes)
  return pages
}

const findDraftNodeByPath = (nodes: DraftTreeNode[], path: string | null): DraftTreeNode | null => {
  if (!path) return null
  const walk = (items: DraftTreeNode[]): DraftTreeNode | null => {
    for (const item of items) {
      if (item.path === path) return item
      const child = walk(item.children)
      if (child) return child
    }
    return null
  }
  return walk(nodes)
}

const updateDraftBookPage = (book: BookTree, path: string, content_md: string): BookTree => {
  const [chapterIndex, topicIndex, pageIndex] = path.split('.').map((value) => Number(value))
  if ([chapterIndex, topicIndex, pageIndex].some((value) => Number.isNaN(value))) {
    return book
  }

  const nextBook: BookTree = {
    ...book,
    chapters: (book.chapters || []).map((chapter, cIndex) => {
      if (cIndex !== chapterIndex) return chapter
      return {
        ...chapter,
        topics: (chapter.topics || []).map((topic, tIndex) => {
          if (tIndex !== topicIndex) return topic
          return {
            ...topic,
            pages: (topic.pages || []).map((page, pIndex) =>
              pIndex === pageIndex ? { ...page, content_md } : page,
            ),
          }
        }),
      }
    }),
  }

  return nextBook
}

const renderBookTreeMarkdown = (book: BookTree): string => {
  const lines: string[] = []
  const title = book.book_title || 'Knowledge Book'
  lines.push(`# ${title}`)
  if (book.summary) {
    lines.push('', book.summary, '')
  }

  ;(book.chapters || []).forEach((chapter) => {
    lines.push(`## ${chapter.title}`)
    if (chapter.summary) {
      lines.push('', chapter.summary, '')
    }
    ;(chapter.topics || []).forEach((topic) => {
      lines.push(`### ${topic.title}`)
      if (topic.summary) {
        lines.push('', topic.summary, '')
      }
      ;(topic.pages || []).forEach((page) => {
        lines.push(`#### ${page.title}`)
        if (page.content_md) {
          lines.push('', page.content_md.trim(), '')
        }
      })
    })
  })

  return lines.join('\n').trim() + '\n'
}

const TreeView: React.FC<{
  node: TreeNode
  depth?: number
  number: string
  selectedPageId: number | null
  onSelectPage: (node: TreeNode) => void
}> = ({ node, depth = 0, number, selectedPageId, onSelectPage }) => {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children.length > 0
  const isSelected = node.node_type === 'page' && selectedPageId === node.id

  return (
    <div>
      <div
        className={`flex min-w-max items-center gap-2 rounded-lg px-2 py-1.5 transition-colors ${
          isSelected ? 'bg-sky-100 text-sky-950' : 'hover:bg-muted/60'
        }`}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        <button
          className="flex items-center justify-center w-5 h-5 text-muted-foreground"
          onClick={() => {
            if (hasChildren) {
              setOpen((value) => !value)
            } else if (node.node_type === 'page') {
              onSelectPage(node)
            }
          }}
          type="button"
        >
          {hasChildren ? (open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />) : <span className="w-4 h-4" />}
        </button>
        {node.node_type === 'chapter' && <BookOpen className="w-4 h-4 text-blue-600" />}
        {node.node_type === 'topic' && <GitBranch className="w-4 h-4 text-cyan-600" />}
        {node.node_type === 'page' && <FileText className="w-4 h-4 text-slate-600" />}
        <span className="w-10 shrink-0 text-right font-mono text-[10px] font-semibold leading-none tabular-nums text-slate-500">
          {number}
        </span>
        <button
          type="button"
          onClick={() => {
            if (node.node_type === 'page') {
              onSelectPage(node)
            } else if (hasChildren) {
              setOpen((value) => !value)
            }
          }}
          className="min-w-[180px] flex-1 text-left"
        >
          <div className="text-sm font-medium text-slate-900 truncate">{node.title}</div>
        </button>
      </div>
      {hasChildren && open && (
        <div className="space-y-0.5">
          {node.children.map((child, childIndex) => (
            <TreeView
              key={child.id}
              node={child}
              depth={depth + 1}
              number={`${number}.${childIndex + 1}`}
              selectedPageId={selectedPageId}
              onSelectPage={onSelectPage}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const DraftTreeView: React.FC<{
  node: DraftTreeNode
  depth?: number
  number: string
  selectedPagePath: string | null
  onSelectPage: (node: DraftTreeNode) => void
  onEditPage: (node: DraftTreeNode) => void
  onCommitPatch: () => void
}> = ({ node, depth = 0, number, selectedPagePath, onSelectPage, onEditPage, onCommitPatch }) => {
  const [open, setOpen] = useState(true)
  const hasChildren = node.children.length > 0
  const isSelected = node.node_type === 'page' && selectedPagePath === node.path

  return (
    <div>
      <div
        className={`group flex min-w-max items-center gap-2 rounded-lg px-2 py-1.5 transition-colors ${
          isSelected ? 'bg-amber-100 text-amber-950' : 'hover:bg-amber-50'
        }`}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        {node.node_type === 'page' && (
          <div className="flex items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
            <button
              type="button"
              className="rounded-md p-1.5 text-slate-500 hover:bg-white hover:text-slate-900"
              onClick={() => onEditPage(node)}
              title="Edit page"
            >
              <PencilLine className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="rounded-md p-1.5 text-slate-500 hover:bg-white hover:text-slate-900"
              onClick={onCommitPatch}
              title="Commit draft"
            >
              <CircleCheck className="h-4 w-4" />
            </button>
          </div>
        )}
        <button
          className="flex h-5 w-4 items-center justify-center text-amber-700"
          onClick={() => {
            if (hasChildren) {
              setOpen((value) => !value)
            } else {
              onSelectPage(node)
            }
          }}
          type="button"
        >
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400 shadow-sm shadow-amber-300" />
        </button>
        <span className="w-10 shrink-0 text-right font-mono text-[10px] font-semibold leading-none tabular-nums text-amber-700">
          {number}
        </span>
        <button
          type="button"
          onClick={() => {
            if (node.node_type === 'page') {
              onSelectPage(node)
            } else if (hasChildren) {
              setOpen((value) => !value)
            }
          }}
          className="min-w-[180px] flex-1 text-left"
        >
          <div className="truncate text-sm font-medium text-slate-900">{node.title}</div>
        </button>
      </div>
      {hasChildren && open && (
        <div className="space-y-0.5">
          {node.children.map((child, childIndex) => (
            <DraftTreeView
              key={child.path}
              node={child}
              depth={depth + 1}
              number={`${number}.${childIndex + 1}`}
              selectedPagePath={selectedPagePath}
              onSelectPage={onSelectPage}
              onEditPage={onEditPage}
              onCommitPatch={onCommitPatch}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const markdownToHtml = (markdown: string) => {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let inCode = false
  let codeLang = ''
  let codeLines: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let listItems: string[] = []
  let paragraph: string[] = []

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push(`<p>${paragraph.join(' ').trim()}</p>`)
      paragraph = []
    }
  }

  const flushList = () => {
    if (listType && listItems.length > 0) {
      const tag = listType
      blocks.push(`<${tag}>${listItems.map((item) => `<li>${item}</li>`).join('')}</${tag}>`)
    }
    listType = null
    listItems = []
  }

  const flushCode = () => {
    if (codeLines.length > 0) {
      const langClass = codeLang ? ` class="language-${escapeHtml(codeLang)}"` : ''
      blocks.push(`<pre><code${langClass}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
    }
    codeLines = []
    codeLang = ''
  }

  const inline = (text: string) =>
    escapeHtml(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/^\s*-\s+/, '')

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd()
    const codeFence = line.match(/^```(\w+)?\s*$/)

    if (codeFence) {
      if (inCode) {
        flushCode()
        inCode = false
      } else {
        flushParagraph()
        flushList()
        inCode = true
        codeLang = codeFence[1] || ''
      }
      return
    }

    if (inCode) {
      codeLines.push(rawLine)
      return
    }

    if (!line.trim()) {
      flushParagraph()
      flushList()
      return
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/)
    if (heading) {
      flushParagraph()
      flushList()
      const level = heading[1].length
      blocks.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      return
    }

    const unordered = line.match(/^-\s+(.*)$/)
    const ordered = line.match(/^\d+\.\s+(.*)$/)
    if (unordered || ordered) {
      flushParagraph()
      if (!listType) {
        listType = unordered ? 'ul' : 'ol'
      }
      listItems.push(`<span>${inline((unordered || ordered)?.[1] || '')}</span>`)
      return
    }

    if (listType) {
      flushList()
    }

    paragraph.push(inline(line))
  })

  flushParagraph()
  flushList()
  if (inCode) {
    flushCode()
  }

  return blocks.join('\n')
}

export default function KnowledgeBook() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [sources, setSources] = useState<SourceItem[]>([])
  const [patches, setPatches] = useState<PatchItem[]>([])
  const [tree, setTree] = useState<{ book_title: string; chapters: TreeNode[] }>({
    book_title: 'Knowledge Book',
    chapters: [],
  })
  const [audit, setAudit] = useState<Array<{ id: number; action: string; created_at: string; details?: any; patch_id: number }>>([])
  const [selectedPatchId, setSelectedPatchId] = useState<number | null>(null)
  const [draftJson, setDraftJson] = useState('')
  const [draftMarkdown, setDraftMarkdown] = useState('')
  const [noteTitle, setNoteTitle] = useState('')
  const [noteContent, setNoteContent] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedPageId, setSelectedPageId] = useState<number | null>(null)
  const [selectedDraftPagePath, setSelectedDraftPagePath] = useState<string | null>(null)
  const [draftViewMode, setDraftViewMode] = useState<'markdown' | 'raw'>('markdown')
  const [draftTreeState, setDraftTreeState] = useState<BookTree | null>(null)
  const [draftPageMarkdown, setDraftPageMarkdown] = useState('')
  const [showInputsModal, setShowInputsModal] = useState(false)
  const [showQueueModal, setShowQueueModal] = useState(false)
  const [showSettingsModal, setShowSettingsModal] = useState(false)
  const [contentsTab, setContentsTab] = useState<'published' | 'draft'>('published')
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const draftSelectionInitializedForPatchRef = useRef<number | null>(null)

  const selectedPatch = useMemo(
    () => patches.find((patch) => patch.id === selectedPatchId) || null,
    [patches, selectedPatchId],
  )

  const contentsPages = useMemo(() => flattenPages(tree.chapters), [tree])
  const draftTreeNodes = useMemo(() => (draftTreeState ? buildDraftTree(draftTreeState) : []), [draftTreeState])
  const draftPages = useMemo(() => flattenDraftPages(draftTreeNodes), [draftTreeNodes])
  const selectedPage = useMemo(() => {
    if (!selectedPageId) {
      return contentsPages[0] || null
    }
    return contentsPages.find((page) => page.id === selectedPageId) || contentsPages[0] || null
  }, [contentsPages, selectedPageId])
  const selectedDraftPage = useMemo(
    () => findDraftNodeByPath(draftTreeNodes, selectedDraftPagePath),
    [draftTreeNodes, selectedDraftPagePath],
  )
  const activeProcessingSources = useMemo(
    () => sources.filter((source) => source.status === 'processing' && source.job),
    [sources],
  )

  const loadAll = async () => {
    try {
      const [statusRes, sourcesRes, patchesRes, treeRes, auditRes] = await Promise.all([
        api.get('/knowledge/status'),
        api.get('/knowledge/sources'),
        api.get('/knowledge/patches'),
        api.get('/knowledge/tree'),
        api.get('/knowledge/audit'),
      ])

      setStatus(statusRes.data)
      setSources(sourcesRes.data.sources || [])
      const allPatches: PatchItem[] = patchesRes.data.patches || []
      setPatches(allPatches)
      setTree(treeRes.data)
      setAudit(auditRes.data.audit || [])
      const nextPages = flattenPages(treeRes.data.chapters || [])

      const latestCommitted = allPatches.find((patch) => patch.status === 'committed') || null
      const latestDraft = allPatches.find((patch) => patch.status === 'draft') || null
      const fallbackPatch = latestCommitted || latestDraft || allPatches[0] || null
      if (fallbackPatch) {
        setSelectedPatchId((current) => current ?? fallbackPatch.id)
      }

      setSelectedPageId((current) => {
        if (current && nextPages.some((page) => page.id === current)) {
          return current
        }
        return nextPages[0]?.id ?? null
      })
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load knowledge book')
    }
  }

  useEffect(() => {
    if (!user || user.role !== 'admin') {
      navigate('/login')
      return
    }

    loadAll()
    const timer = window.setInterval(loadAll, 5000)
    return () => window.clearInterval(timer)
  }, [user, navigate])

  useEffect(() => {
    if (!selectedPatch || selectedPatch.status !== 'draft') {
      setDraftJson('')
      setDraftMarkdown('')
      setDraftTreeState(null)
      setSelectedDraftPagePath(null)
      setDraftPageMarkdown('')
      draftSelectionInitializedForPatchRef.current = null
      return
    }

    setDraftJson(JSON.stringify(selectedPatch.draft_json, null, 2))
    setDraftMarkdown(selectedPatch.draft_markdown)
    setDraftTreeState(selectedPatch.draft_json)
    const draftNodes = buildDraftTree(selectedPatch.draft_json)
    const currentDraftPage = selectedDraftPagePath ? findDraftNodeByPath(draftNodes, selectedDraftPagePath) : null
    const firstDraftPage = flattenDraftPages(draftNodes)[0] || null

    if (draftSelectionInitializedForPatchRef.current !== selectedPatch.id) {
      const nextSelectedPage = currentDraftPage || firstDraftPage
      setSelectedDraftPagePath(nextSelectedPage?.path || null)
      setDraftPageMarkdown(nextSelectedPage?.content_md || '')
      draftSelectionInitializedForPatchRef.current = selectedPatch.id
      return
    }

    if (currentDraftPage) {
      setDraftPageMarkdown(currentDraftPage.content_md || '')
    } else if (!selectedDraftPagePath && firstDraftPage) {
      setSelectedDraftPagePath(firstDraftPage.path)
      setDraftPageMarkdown(firstDraftPage.content_md || '')
    }
  }, [selectedPatch, selectedDraftPagePath])

  useEffect(() => {
    if (!selectedDraftPage) {
      return
    }
    setDraftPageMarkdown(selectedDraftPage.content_md || '')
  }, [selectedDraftPage])

  const refresh = async () => {
    setError(null)
    await loadAll()
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    setIsBusy(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      await api.post('/knowledge/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSelectedFile(null)
      setSuccess(`Queued ${selectedFile.name} for knowledge book generation`)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Upload failed')
    } finally {
      setIsBusy(false)
    }
  }

  const handleCreateNote = async () => {
    if (!noteContent.trim()) return

    setIsBusy(true)
    setError(null)
    setSuccess(null)

    try {
      await api.post('/knowledge/note', {
        title: noteTitle || 'Quick Note',
        content: noteContent,
      })
      setNoteTitle('')
      setNoteContent('')
      setSuccess('Queued note for knowledge book generation')
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Note creation failed')
    } finally {
      setIsBusy(false)
    }
  }

  const handleSaveDraft = async () => {
    if (!selectedPatch || !draftTreeState) return false

    const updatedMarkdown = renderBookTreeMarkdown(draftTreeState)
    if (!updatedMarkdown.trim()) {
      setError('Draft markdown is empty')
      return false
    }

    setIsBusy(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await api.put(`/knowledge/patches/${selectedPatch.id}`, {
        draft_json: draftTreeState,
        draft_markdown: updatedMarkdown,
      })
      setDraftMarkdown(updatedMarkdown)
      setSuccess(`Saved draft patch #${response.data.id}`)
      await refresh()
      return true
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to save draft')
      return false
    } finally {
      setIsBusy(false)
    }
  }

  const handleCommit = async () => {
    if (!selectedPatch) return

    setIsBusy(true)
    setError(null)
    setSuccess(null)

    try {
      const saved = await handleSaveDraft()
      if (!saved) return
      await api.post(`/knowledge/patches/${selectedPatch.id}/commit`)
      setSuccess(`Committed patch #${selectedPatch.id}`)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to commit patch')
    } finally {
      setIsBusy(false)
    }
  }

  const handleDeleteQueueItem = async (sourceId: number, sourceLabel: string) => {
    const confirmed = window.confirm(`Delete queue item "${sourceLabel}"?`)
    if (!confirmed) return

    setIsBusy(true)
    setError(null)
    setSuccess(null)

    try {
      await api.delete(`/knowledge/sources/${sourceId}`)
      setSuccess(`Deleted queue item "${sourceLabel}"`)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to delete queue item')
    } finally {
      setIsBusy(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const pageTitle = selectedDraftPage?.title || selectedPage?.title || selectedPatch?.draft_title || tree.book_title || 'Knowledge Book'
  const pageMarkdown = selectedDraftPage
    ? draftPageMarkdown
    : selectedPage?.content_md || '# No page selected\n\nOpen a page from the contents tree to preview it here.'
  const showingDraftPreview = Boolean(selectedDraftPage)

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.16),_transparent_35%),linear-gradient(180deg,_#f8fafc_0%,_#eef6ff_100%)] text-slate-900">
      <header className="sticky top-0 z-10 border-b border-white/60 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-gradient-to-br from-sky-500 to-cyan-600 p-2 text-white shadow-lg">
              <BookOpen className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">Knowledge Book</h1>
                <button
                  type="button"
                  onClick={() => setShowSettingsModal(true)}
                  className="rounded-full p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
                  title="Settings"
                >
                  <Settings className="h-4 w-4" />
                </button>
                {ragStatusBadge(status)}
              </div>
              <p className="text-sm text-slate-500">Contents on the left, markdown page on the right</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/admin/dashboard">
              <Button variant="outline" className="border-slate-200 bg-white/70">
                Back to Dashboard
              </Button>
            </Link>
            <Button onClick={() => setShowInputsModal(true)} className="bg-sky-600 text-white hover:bg-sky-700">
              <FileUp className="mr-2 h-4 w-4" />
              Inputs
            </Button>
            <Button onClick={() => setShowQueueModal(true)} className="bg-cyan-600 text-white hover:bg-cyan-700">
              <FileText className="mr-2 h-4 w-4" />
              Queue
            </Button>
            <Button variant="outline" onClick={refresh} className="border-slate-200 bg-white/70">
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
            <Button onClick={handleLogout} className="bg-slate-900 text-white hover:bg-slate-800">
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <AlertTriangle className="mr-2 inline-block h-4 w-4" />
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <CircleCheck className="mr-2 inline-block h-4 w-4" />
            {success}
          </div>
        )}

        {activeProcessingSources.length > 0 && (
          <div className="mb-4 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-4 text-sky-900 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">Document processing in progress</div>
                <div className="text-xs text-sky-700">
                  {activeProcessingSources.length} source{activeProcessingSources.length === 1 ? '' : 's'} are currently being processed.
                </div>
              </div>
              <Badge className="border-sky-200 bg-white text-sky-800">
                {Math.max(...activeProcessingSources.map((source) => source.job?.progress ?? 0))}% max
              </Badge>
            </div>
            <div className="mt-3 space-y-3">
              {activeProcessingSources.map((source) => (
                <div key={source.id} className="rounded-xl bg-white/80 p-3">
                  <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium">{source.title || source.original_filename}</span>
                    <span className="text-sky-700">{source.job?.progress ?? 0}%</span>
                  </div>
                  <ProgressBar value={source.job?.progress ?? 0} />
                  {source.job?.message && (
                    <div className="mt-2 text-xs text-slate-600">{source.job.message}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="min-h-[calc(100vh-220px)] border-white/70 bg-white/85 shadow-xl backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-sky-600" />
                Contents
              </CardTitle>
              <CardDescription>Select a page to render its markdown.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="max-h-[calc(100vh-300px)] space-y-4 overflow-y-auto pr-1">
                <Tabs value={contentsTab} onValueChange={(value) => setContentsTab(value as 'published' | 'draft')} className="w-full">
                  <TabsList className="grid w-full grid-cols-2 bg-slate-100">
                    <TabsTrigger value="published">Published</TabsTrigger>
                    <TabsTrigger value="draft">Draft</TabsTrigger>
                  </TabsList>

                  <TabsContent value="published" className="mt-3">
                    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-2">
                      <div className="mb-2 flex items-center justify-between px-2 pt-1">
                        <div className="text-sm font-semibold text-slate-900">Published contents</div>
                        <div className="text-xs text-slate-500">{tree.chapters.length} chapters</div>
                      </div>
                      {tree.chapters.length === 0 ? (
                        <div className="p-4 text-sm text-slate-500">No committed knowledge book yet.</div>
                      ) : (
                        tree.chapters.map((chapter, chapterIndex) => (
                          <TreeView
                            key={chapter.id}
                            node={chapter}
                            number={`${chapterIndex + 1}`}
                            selectedPageId={selectedPageId}
                            onSelectPage={(node) => {
                              setSelectedPageId(node.id)
                              setSelectedDraftPagePath(null)
                              setDraftViewMode('markdown')
                            }}
                          />
                        ))
                      )}
                    </div>
                  </TabsContent>

                  <TabsContent value="draft" className="mt-3">
                    {draftTreeNodes.length > 0 && selectedPatch?.status === 'draft' ? (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-3">
                        <div className="mb-3 flex items-center justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2 text-sm font-semibold text-amber-950">
                              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                              Draft hierarchy
                            </div>
                            <div className="text-xs text-amber-800">{selectedPatch.draft_title}</div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              className="h-8 w-8 border-amber-300 bg-white p-0 text-amber-900 hover:bg-amber-100"
                              title="Edit draft page"
                              aria-label="Edit draft page"
                              onClick={() => {
                                if (selectedDraftPage) {
                                  setDraftViewMode('raw')
                                } else if (draftPages[0]) {
                                  setSelectedDraftPagePath(draftPages[0].path)
                                  setDraftViewMode('raw')
                                }
                              }}
                            >
                              <PencilLine className="h-4 w-4" />
                            </Button>
                            <Button
                              type="button"
                              className="h-8 w-8 bg-amber-500 p-0 text-white hover:bg-amber-600"
                              title="Commit draft"
                              aria-label="Commit draft"
                              onClick={handleCommit}
                            >
                              <CircleCheck className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                        <div className="overflow-x-auto rounded-2xl border border-amber-200 bg-white p-2">
                          {draftTreeNodes.map((chapter, chapterIndex) => (
                            <DraftTreeView
                              key={chapter.path}
                              node={chapter}
                              number={`${chapterIndex + 1}`}
                              selectedPagePath={selectedDraftPagePath}
                              onSelectPage={(node) => {
                                setSelectedDraftPagePath(node.path)
                                setSelectedPageId(null)
                                setDraftViewMode('markdown')
                              }}
                              onEditPage={(node) => {
                                setSelectedDraftPagePath(node.path)
                                setSelectedPageId(null)
                                setDraftViewMode('raw')
                              }}
                              onCommitPatch={handleCommit}
                            />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                        No draft hierarchy available yet.
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </div>
            </CardContent>
          </Card>

          <Card className="min-h-[calc(100vh-220px)] border-white/70 bg-white/85 shadow-xl backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-cyan-600" />
                Page
              </CardTitle>
              <CardDescription>
                {selectedDraftPage ? 'Draft page editor' : pageTitle}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedDraftPage ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <div>
                      <div className="text-sm font-semibold text-amber-950">{selectedDraftPage.title}</div>
                      <div className="text-xs text-amber-800">Editing the draft page before commit</div>
                    </div>
                      <div className="flex items-center gap-2">
                        <div className="rounded-full border border-amber-200 bg-white p-1">
                          <button
                            type="button"
                            className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            draftViewMode === 'markdown'
                              ? 'bg-amber-500 text-white'
                              : 'text-amber-800 hover:bg-amber-100'
                          }`}
                          onClick={() => setDraftViewMode('markdown')}
                        >
                          Markdown
                        </button>
                        <button
                          type="button"
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            draftViewMode === 'raw'
                              ? 'bg-amber-500 text-white'
                              : 'text-amber-800 hover:bg-amber-100'
                          }`}
                          onClick={() => setDraftViewMode('raw')}
                        >
                          Raw
                        </button>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-8 w-8 border-amber-300 bg-white p-0 text-amber-900 hover:bg-amber-100"
                        title="Toggle edit mode"
                        aria-label="Toggle edit mode"
                        onClick={() => setDraftViewMode((mode) => (mode === 'raw' ? 'markdown' : 'raw'))}
                      >
                        <PencilLine className="h-4 w-4" />
                      </Button>
                      <Button
                        onClick={handleSaveDraft}
                        disabled={isBusy}
                        className="h-8 w-8 bg-slate-900 p-0 text-white hover:bg-slate-800"
                        title="Save draft"
                        aria-label="Save draft"
                      >
                        <Save className="h-4 w-4" />
                      </Button>
                      <Button
                        onClick={handleCommit}
                        disabled={isBusy}
                        className="bg-amber-500 text-white hover:bg-amber-600"
                        title="Commit draft"
                        aria-label="Commit draft"
                      >
                        <CircleCheck className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {draftViewMode === 'raw' ? (
                    <Textarea
                      value={draftPageMarkdown}
                      onChange={(event) => {
                        const next = event.target.value
                        setDraftPageMarkdown(next)
                        if (selectedDraftPagePath && draftTreeState) {
                          setDraftTreeState(updateDraftBookPage(draftTreeState, selectedDraftPagePath, next))
                        }
                      }}
                      rows={22}
                      className="min-h-[60vh] font-mono text-sm"
                    />
                  ) : (
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div
                        className="knowledge-markdown prose prose-slate max-w-none"
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(pageMarkdown) }}
                      />
                    </div>
                  )}
                </>
              ) : (
                <>
                  {showingDraftPreview && (
                    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                      Draft preview. Commit this patch to publish it into Contents.
                    </div>
                  )}
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div
                      className="knowledge-markdown prose prose-slate max-w-none"
                      dangerouslySetInnerHTML={{ __html: markdownToHtml(pageMarkdown) }}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      {showInputsModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={() => setShowInputsModal(false)} />
            <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/40 bg-white shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-lg font-semibold">Inputs</h2>
                  <p className="text-sm text-slate-500">Upload files or add a markdown note.</p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  onClick={() => setShowInputsModal(false)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="grid gap-4 px-6 py-5">
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/70 p-4">
                  <Input
                    type="file"
                    accept=".pdf,.docx,.md"
                    onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                    className="mb-3"
                  />
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{selectedFile ? selectedFile.name : 'No file selected'}</p>
                      <p className="text-xs text-slate-500">PDF, DOCX, or MD only</p>
                    </div>
                    <Button onClick={handleUpload} disabled={!selectedFile || isBusy} className="bg-sky-600 hover:bg-sky-700">
                      {isBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                      Queue
                    </Button>
                  </div>
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Quick Note</h3>
                    <Badge variant="secondary">Markdown</Badge>
                  </div>
                  <Input
                    value={noteTitle}
                    onChange={(e) => setNoteTitle(e.target.value)}
                    placeholder="Optional title"
                  />
                  <Textarea
                    value={noteContent}
                    onChange={(e) => setNoteContent(e.target.value)}
                    rows={7}
                    placeholder="Write a markdown note that should become part of the knowledge book..."
                    className="font-mono text-sm"
                  />
                  <Button onClick={handleCreateNote} disabled={!noteContent.trim() || isBusy} className="w-full bg-emerald-600 hover:bg-emerald-700">
                    {isBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                    Create Draft
                  </Button>
                </div>
              </div>
</div>
            </div>
          </div>
        )}

      {showQueueModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={() => setShowQueueModal(false)} />
            <div className="relative z-10 w-full max-w-5xl overflow-hidden rounded-3xl border border-white/40 bg-white shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-lg font-semibold">Upload history and queue</h2>
                  <p className="text-sm text-slate-500">All uploaded sources, their job state, and the latest patch status.</p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  onClick={() => setShowQueueModal(false)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="max-h-[75vh] overflow-y-auto px-6 py-5">
                {sources.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No uploads yet.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {sources.map((source) => {
                      const progress = source.job?.progress ?? 0
                      const sourceLabel = source.title || source.original_filename
                      const canDelete = source.status !== 'committed' && source.status !== 'processing'
                      return (
                        <div key={source.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-slate-900">{sourceLabel}</div>
                              <div className="text-xs text-slate-500">
                                {source.file_type.toUpperCase()} · {source.original_filename}
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-2">
                              <Badge className="border-slate-200 bg-white text-slate-700">
                                {source.status === 'processing' && source.job ? 'Processing' : 
                                 source.status === 'draft_ready' ? 'Draft Ready' :
                                 source.status === 'committed' ? 'Committed' :
                                 source.status === 'uploaded' ? 'Uploaded' : source.status}
                              </Badge>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 border-red-300 bg-white px-3 text-red-700 hover:bg-red-50"
                                disabled={!canDelete || isBusy}
                                onClick={() => handleDeleteQueueItem(source.id, sourceLabel)}
                              >
                                Delete
                              </Button>
                            </div>
                          </div>
                          <div className="mt-3">
                            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                              <div className="h-full bg-sky-600 transition-all duration-300" style={{ width: `${progress}%` }} />
                            </div>
                          </div>
                          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                            <span className="rounded-full bg-white px-2 py-1 font-medium text-slate-700">
                              Source: {source.status}
                            </span>
                            <span className="rounded-full bg-white px-2 py-1 font-medium text-slate-700">
                              Job: {source.job?.status || 'n/a'}
                            </span>
                            <span className="rounded-full bg-white px-2 py-1 font-medium text-slate-700">
                              Progress: {progress}%
                            </span>
                            {source.patch && (
                              <span className="rounded-full bg-white px-2 py-1 font-medium text-slate-700">
                                Patch: {source.patch.status}
                              </span>
                            )}
                          </div>
                          {source.job?.message && (
                            <div className="mt-2 text-xs text-slate-500">{source.job.message}</div>
                          )}
                          {source.error_message && (
                            <div className="mt-2 text-xs text-red-700">{source.error_message}</div>
                          )}
                          <div className="mt-3 flex items-center gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              className="h-8 border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100"
                              disabled={!source.patch || source.patch.status !== 'draft'}
                            >
                              Ready draft
                            </Button>
                            {source.patch?.status === 'draft' && (
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 border-amber-300 bg-white px-3 text-amber-900 hover:bg-amber-100"
                                onClick={() => {
                                  setSelectedPatchId(source.patch!.id)
                                  setContentsTab('draft')
                                  setSelectedDraftPagePath(null)
                                  setDraftViewMode('raw')
                                  setShowQueueModal(false)
                                }}
                              >
                                Edit draft
                              </Button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {showSettingsModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={() => setShowSettingsModal(false)} />
            <div className="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-white/40 bg-white shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-lg font-semibold">Knowledge Book Settings</h2>
                  <p className="text-sm text-slate-500">Hard reset and cleanup options.</p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  onClick={() => setShowSettingsModal(false)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-4 px-6 py-5">
                <div className="rounded-2xl border border-red-200 bg-red-50 p-4">
                  <h3 className="font-semibold text-red-900">Danger Zone</h3>
                  <p className="mt-1 text-sm text-red-700">These actions cannot be undone.</p>

                  <div className="mt-4 space-y-3">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full border-red-300 bg-white text-red-700 hover:bg-red-100"
                      disabled={isBusy}
                      onClick={async () => {
                        if (!confirm('Delete all sources? This cannot be undone.')) return
                        setIsBusy(true)
                        try {
                          for (const source of sources) {
                            if (source.status !== 'committed' && source.status !== 'processing') {
                              await api.delete(`/knowledge/sources/${source.id}`)
                            }
                          }
                          setSuccess('All sources deleted')
                          await refresh()
                        } catch (err: any) {
                          setError(err?.response?.data?.detail || err?.message || 'Failed to delete sources')
                        } finally {
                          setIsBusy(false)
                        }
                      }}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete All Sources
                    </Button>

                    <Button
                      type="button"
                      variant="outline"
                      className="w-full border-red-300 bg-white text-red-700 hover:bg-red-100"
                      disabled={isBusy}
                      onClick={async () => {
                        if (!confirm('Hard reset - delete all sources, patches, and contents? This cannot be undone.')) return
                        setIsBusy(true)
                        try {
                          await api.post('/knowledge/hard-reset')
                          setSuccess('Knowledge book hard reset complete')
                          await refresh()
                          setShowSettingsModal(false)
                        } catch (err: any) {
                          setError(err?.response?.data?.detail || err?.message || 'Failed to hard reset')
                        } finally {
                          setIsBusy(false)
                        }
                      }}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Hard Reset All
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
