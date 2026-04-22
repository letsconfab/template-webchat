import { useState, useRef, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Send, Loader2, Settings, LogOut, MessageSquare } from 'lucide-react'
import { ChatWebSocket, type Settings as ChatSettings, getSessionId } from '../services/api'
import { useAuth } from '../contexts/AuthContext'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function ChatPage() {
  const navigate = useNavigate()
  const { user, logout, isAdmin } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentResponse, setCurrentResponse] = useState('')
  const [settings, setSettings] = useState<ChatSettings | null>(null)
  
  const currentResponseRef = useRef('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<ChatWebSocket | null>(null)

  useEffect(() => {
    if (!user) {
      navigate('/login')
      return
    }
    loadSettingsAndConnect()
    return () => {
      wsRef.current?.disconnect()
    }
  }, [user])

  useEffect(() => {
    scrollToBottom()
  }, [messages, currentResponse])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadSettingsAndConnect = async () => {
    // Get LLM settings from backend
    try {
      const response = await fetch('/api/settings/current', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })
      if (response.ok) {
        const data = await response.json()
        const chatSettings: ChatSettings = {
          provider: data.llm_provider || 'openai',
          model: data.llm_model || 'gpt-4o-mini',
          apiKey: data.llm_api_key || ''
        }
        setSettings(chatSettings)
        connectWebSocket(chatSettings)
      }
    } catch (error) {
      console.error('Failed to load settings:', error)
      // Use defaults
      const defaultSettings: ChatSettings = {
        provider: 'openai',
        model: 'gpt-4o-mini',
        apiKey: ''
      }
      setSettings(defaultSettings)
      connectWebSocket(defaultSettings)
    }
  }

  const connectWebSocket = (chatSettings: ChatSettings) => {
    wsRef.current = new ChatWebSocket()
    wsRef.current.connect(chatSettings)

    wsRef.current.onMessage((data) => {
      if (data.type === 'status') {
        setMessages(prev => [...prev, { role: 'assistant', content: data.message }])
      } else if (data.type === 'history') {
        setMessages(data.messages || [])
      } else if (data.type === 'start') {
        setIsStreaming(true)
        setCurrentResponse('')
        currentResponseRef.current = ''
      } else if (data.type === 'chunk') {
        const newResponse = currentResponseRef.current + data.content
        currentResponseRef.current = newResponse
        setCurrentResponse(newResponse)
      } else if (data.type === 'end') {
        const finalResponse = currentResponseRef.current
        setMessages(prev => [...prev, { role: 'assistant', content: finalResponse }])
        setTimeout(() => {
          setCurrentResponse('')
          currentResponseRef.current = ''
          setIsStreaming(false)
        }, 0)
      } else if (data.type === 'error') {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.message}` }])
        setIsStreaming(false)
        setCurrentResponse('')
        currentResponseRef.current = ''
      }
    })

    wsRef.current.onError((error) => {
      console.error('WebSocket error:', error)
    })

    wsRef.current.onConnection((connected) => {
      setIsConnected(connected)
    })
  }

  const handleSend = () => {
    if (!input.trim() || !settings) return

    setMessages(prev => [...prev, { role: 'user', content: input }])
    wsRef.current?.sendMessage(input)
    setInput('')
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      
      {/* Header */}
      <header className="border-b border-border bg-card px-4 py-3">
        <div className="flex items-center justify-between max-w-4xl mx-auto">
          <div className="flex items-center gap-2">
            <span className="text-2xl">💬</span>
            <h1 className="text-xl font-semibold">AI Chat</h1>
            <span className="text-sm text-muted-foreground ml-2">
              ({user.email})
            </span>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <Link to="/admin/settings">
                <button className="p-2 hover:bg-muted rounded-lg transition-colors">
                  <Settings className="w-5 h-5" />
                </button>
              </Link>
            )}
            <Link to="/dashboard">
              <button className="p-2 hover:bg-muted rounded-lg transition-colors">
                <MessageSquare className="w-5 h-5" />
              </button>
            </Link>
            <button onClick={handleLogout} className="p-2 hover:bg-muted rounded-lg transition-colors">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Chat Messages */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-4">
        <div className="h-[calc(100vh-180px)] flex flex-col">
          <div className="flex-1 overflow-y-auto space-y-4 pb-4">
            {messages.length === 0 && !isStreaming && (
              <div className="text-center text-muted-foreground py-8">
                <p>Start a conversation by typing a message below.</p>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-4 ${
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted'
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}

            {isStreaming && currentResponse && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-lg p-4 bg-muted">
                  <div className="whitespace-pre-wrap">{currentResponse}</div>
                  <Loader2 className="w-4 h-4 animate-spin mt-2" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border pt-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message..."
                disabled={isStreaming || !isConnected}
                className="flex-1 p-3 border border-border rounded-lg bg-background disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming || !isConnected}
                className="p-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            {!isConnected && (
              <p className="text-sm text-muted-foreground mt-2">
                {isStreaming ? 'Connecting...' : 'Disconnected. Please refresh to reconnect.'}
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}