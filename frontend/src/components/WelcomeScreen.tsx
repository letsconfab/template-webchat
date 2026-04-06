import { Settings } from 'lucide-react'

interface WelcomeScreenProps {
  onOpenSettings: () => void
}

export default function WelcomeScreen({ onOpenSettings }: WelcomeScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="text-6xl mb-6">❤️</div>
      <h1 className="text-3xl font-bold mb-4">Welcome to AI Copilot</h1>
      <p className="text-muted-foreground mb-8 max-w-md">
        Configure your LLM provider to get started with AI-powered assistance powered by your knowledge base.
      </p>
      
      <div className="bg-muted rounded-lg p-6 max-w-md mb-8 text-left">
        <h2 className="font-semibold mb-4">Supported Providers:</h2>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li>• <strong>OpenAI</strong> - gpt-4o-mini, gpt-4o</li>
          <li>• <strong>Groq</strong> - llama3-70b-8192, mixtral-8x7b-32768</li>
          <li>• <strong>Ollama</strong> - llama3:latest, mistral:latest (local, no API key needed)</li>
          <li>• <strong>Sarvam</strong> - sarvam-1</li>
        </ul>
      </div>

      <button
        onClick={onOpenSettings}
        className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-3 rounded-lg hover:bg-primary/90 transition-colors"
      >
        <Settings className="w-5 h-5" />
        Configure Settings
      </button>
    </div>
  )
}
