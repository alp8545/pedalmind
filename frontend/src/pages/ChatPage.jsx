import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { G } from '../components/ui'

const QUICK_REPLIES = ['Analizza uscita', 'Piano settimana', 'Come sto?']

export default function ChatPage() {
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    api('/api/chat/conversations').then(convs => {
      setConversations(convs)
      // Auto-select most recent conversation
      if (convs.length > 0 && !activeId) {
        setActiveId(convs[0].id)
      }
    }).catch(err => console.error('Failed to load conversations:', err))
  }, [])
  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    api(`/api/chat/conversations/${activeId}/messages`).then(setMessages).catch(() => {})
  }, [activeId])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function createConversation() {
    const conv = await api('/api/chat/conversations', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) })
    setConversations(prev => [conv, ...prev]); setActiveId(conv.id); setSidebarOpen(false)
  }

  async function sendMessage(e) {
    e?.preventDefault()
    if (!input.trim() || sending) return
    let convId = activeId
    if (!convId) {
      const conv = await api('/api/chat/conversations', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) })
      setConversations(prev => [conv, ...prev]); convId = conv.id; setActiveId(conv.id)
    }
    const text = input.trim(); setInput(''); setSending(true)
    const tempUserMsg = { id: 'temp-u', role: 'user', content: text, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, tempUserMsg])
    try {
      const data = await api(`/api/chat/conversations/${convId}/messages`, { method: 'POST', body: JSON.stringify({ content: text }) })
      setMessages(prev => [...prev.filter(m => m.id !== 'temp-u'), data.user_message, data.assistant_message])
      setConversations(prev => prev.map(c => c.id === convId ? { ...c, title: data.user_message.content.slice(0, 80) } : c))
    } catch (err) {
      setMessages(prev => [...prev, { id: 'err', role: 'assistant', content: `Errore: ${err.message}`, created_at: new Date().toISOString() }])
    }
    setSending(false)
  }

  async function handleQuickReply(text) {
    if (sending) return
    let convId = activeId
    if (!convId) {
      const conv = await api('/api/chat/conversations', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) })
      setConversations(prev => [conv, ...prev]); convId = conv.id; setActiveId(conv.id)
    }
    setSending(true)
    const tempMsg = { id: 'temp-u', role: 'user', content: text, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, tempMsg])
    try {
      const data = await api(`/api/chat/conversations/${convId}/messages`, { method: 'POST', body: JSON.stringify({ content: text }) })
      setMessages(prev => [...prev.filter(m => m.id !== 'temp-u'), data.user_message, data.assistant_message])
      setConversations(prev => prev.map(c => c.id === convId ? { ...c, title: text.slice(0, 80) } : c))
    } catch (err) {
      setMessages(prev => [...prev, { id: 'err', role: 'assistant', content: `Errore: ${err.message}`, created_at: new Date().toISOString() }])
    }
    setSending(false)
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] max-w-2xl mx-auto flex-col px-4">
      {/* Coach header */}
      <div className="flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-full flex items-center justify-center text-base"
          style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}>
          {'\uD83D\uDEB2'}
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-50">PedalMind Coach</div>
          <div className="flex items-center gap-1 font-mono text-green-500" style={{ fontSize: 9 }}>
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />online
          </div>
        </div>
        {/* Sidebar toggle */}
        <button onClick={() => setSidebarOpen(!sidebarOpen)}
          className="ml-auto font-mono text-slate-400 hover:text-white" style={{ fontSize: 10 }}>
          {sidebarOpen ? 'Chiudi' : 'Chat'}
        </button>
      </div>

      {/* Sidebar overlay */}
      {sidebarOpen && (
        <div className="mb-3">
          <G className="!p-2 flex flex-col gap-0.5">
            <button onClick={createConversation}
              className="text-xs font-mono text-amber-400 px-3 py-2 rounded-lg hover:bg-amber-500/10 text-left">
              + Nuova Chat
            </button>
            {conversations.map(conv => (
              <button key={conv.id} onClick={() => { setActiveId(conv.id); setSidebarOpen(false) }}
                className={`text-xs px-3 py-2 rounded-lg text-left truncate transition-colors ${
                  conv.id === activeId ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/50'
                }`}>
                {conv.title}
              </button>
            ))}
          </G>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-3 pb-2">
        {messages.length === 0 && (
          <div className="text-center mt-20">
            <p className="text-slate-400 text-sm mb-1">Chiedi al tuo coach</p>
            <p className="text-slate-400 font-mono" style={{ fontSize: 10 }}>Allenamento, analisi, consigli...</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className="flex flex-col" style={{ alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '88%', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div className="px-3.5 py-2.5 text-sm leading-relaxed" style={{
              background: msg.role === 'user'
                ? 'linear-gradient(135deg, #f59e0b, #d97706)'
                : 'linear-gradient(135deg, rgba(15,23,42,0.9), rgba(15,23,42,0.6))',
              border: msg.role === 'user' ? 'none' : '1px solid rgba(148,163,184,0.1)',
              borderRadius: msg.role === 'user' ? '14px 14px 3px 14px' : '14px 14px 14px 3px',
              color: msg.role === 'user' ? '#0a0e1a' : '#e2e8f0',
              whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
            </div>
            <span className="font-mono text-slate-400 mt-1" style={{ fontSize: 9 }}>
              {new Date(msg.created_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
        {sending && (
          <div className="flex" style={{ alignSelf: 'flex-start' }}>
            <div className="px-3.5 py-2.5 text-sm text-slate-400 rounded-[14px]"
              style={{ background: 'linear-gradient(135deg, rgba(15,23,42,0.9), rgba(15,23,42,0.6))', border: '1px solid rgba(148,163,184,0.1)' }}>
              Sto pensando...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick replies */}
      <div className="flex gap-1.5 mb-2 flex-wrap">
        {QUICK_REPLIES.map(q => (
          <button key={q} onClick={() => handleQuickReply(q)}
            className="rounded-full px-2.5 py-1 font-mono text-amber-500 border border-amber-500/20 hover:bg-amber-500/10 transition-colors"
            style={{ fontSize: 10, background: 'rgba(245,158,11,0.08)' }}>
            {q}
          </button>
        ))}
      </div>

      {/* Input bar */}
      <form onSubmit={sendMessage} className="flex gap-1.5 items-center rounded-full px-4 py-1"
        style={{ background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(148,163,184,0.1)' }}>
        <input type="text" value={input} onChange={e => setInput(e.target.value)} disabled={sending}
          placeholder="Chiedi al tuo coach..."
          className="flex-1 bg-transparent border-none outline-none text-slate-200 text-sm placeholder-slate-600" />
        <button type="submit" disabled={!input.trim() || sending}
          className="w-8 h-8 rounded-full flex items-center justify-center border-none transition-colors"
          style={{ background: input.trim() ? 'linear-gradient(135deg, #f59e0b, #d97706)' : 'rgba(148,163,184,0.1)' }}>
          <span style={{ fontSize: 14, color: input.trim() ? '#0a0e1a' : '#475569' }}>{'\u2191'}</span>
        </button>
      </form>
    </div>
  )
}
