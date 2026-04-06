import { useState, useRef, useEffect } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { ChatWebSocket, type Settings as ChatSettings } from '../services/api'

interface ChatInterfaceProps {
  settings: ChatSettings | null
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function ChatInterface({ settings }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentResponse, setCurrentResponse] = useState('')
  const currentResponseRef = useRef('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<ChatWebSocket | null>(null)

  useEffect(() => {
    if (settings) {
      connectWebSocket()
    }
    return () => {
      wsRef.current?.disconnect()
    }
  }, [settings])

  useEffect(() => {
    scrollToBottom()
  }, [messages, currentResponse])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const connectWebSocket = () => {
    if (!settings) return

    wsRef.current = new ChatWebSocket()
    wsRef.current.connect(settings)

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
        // Clear streaming state after message is added
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

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      {/* Messages */}
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
  )
}
