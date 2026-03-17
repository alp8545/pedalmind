import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

export default function ChatPage() {
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottomRef = useRef(null)

  // Load conversations
  useEffect(() => {
    api('/api/chat/conversations').then(setConversations).catch(() => {})
  }, [])

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    api(`/api/chat/conversations/${activeId}/messages`).then(setMessages).catch(() => {})
  }, [activeId])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function createConversation() {
    const conv = await api('/api/chat/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: 'New Chat' }),
    })
    setConversations(prev => [conv, ...prev])
    setActiveId(conv.id)
    setSidebarOpen(false)
  }

  async function sendMessage(e) {
    e.preventDefault()
    if (!input.trim() || sending) return

    let convId = activeId
    // Auto-create conversation if none selected
    if (!convId) {
      const conv = await api('/api/chat/conversations', {
        method: 'POST',
        body: JSON.stringify({ title: 'New Chat' }),
      })
      setConversations(prev => [conv, ...prev])
      convId = conv.id
      setActiveId(conv.id)
    }

    const text = input.trim()
    setInput('')
    setSending(true)

    // Optimistic user message
    const tempUserMsg = { id: 'temp-u', role: 'user', content: text, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, tempUserMsg])

    try {
      const data = await api(`/api/chat/conversations/${convId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: text }),
      })
      // Replace temp with real messages
      setMessages(prev => [
        ...prev.filter(m => m.id !== 'temp-u'),
        data.user_message,
        data.assistant_message,
      ])
      // Update conversation title
      setConversations(prev =>
        prev.map(c => c.id === convId ? { ...c, title: data.user_message.content.slice(0, 80) } : c)
      )
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { id: 'err', role: 'assistant', content: `Error: ${err.message}`, created_at: new Date().toISOString() },
      ])
    }
    setSending(false)
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Sidebar - desktop always visible, mobile toggle */}
      <div className={`${sidebarOpen ? 'block' : 'hidden'} md:block w-64 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col absolute md:relative z-10 h-full`}>
        <div className="p-3 border-b border-slate-800">
          <button
            onClick={createConversation}
            className="w-full bg-sky-600 hover:bg-sky-500 text-white text-sm py-2 rounded-lg transition-colors"
          >
            New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.map(conv => (
            <button
              key={conv.id}
              onClick={() => { setActiveId(conv.id); setSidebarOpen(false) }}
              className={`w-full text-left px-3 py-2.5 text-sm border-b border-slate-800/50 transition-colors truncate ${
                conv.id === activeId ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300'
              }`}
            >
              {conv.title}
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile sidebar toggle */}
        <div className="md:hidden p-2 border-b border-slate-800">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-sm text-slate-400 hover:text-white"
          >
            {sidebarOpen ? 'Close' : 'Conversations'}
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-slate-600 mt-20">
              <p className="text-lg text-slate-500 mb-1">Ask PedalMind anything</p>
              <p className="text-sm">Questions about your training, ride analysis, coaching advice...</p>
            </div>
          )}
          {messages.map(msg => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] sm:max-w-[70%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-800 text-slate-300 border border-slate-700'
              }`}>
                {msg.content}
                {msg.tokens_used && (
                  <div className="text-xs mt-1 opacity-50">{msg.tokens_used} tokens</div>
                )}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-500">
                Thinking...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <form onSubmit={sendMessage} className="p-3 border-t border-slate-800 bg-slate-900/50">
          <div className="flex gap-2 max-w-3xl mx-auto">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask about your training..."
              disabled={sending}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-30 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
