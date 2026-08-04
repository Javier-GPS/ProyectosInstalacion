import { useState, useRef, useEffect } from 'react'
import { Sparkles, X, Send } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { apiPost } from '../api'

/** Reads every project saved to localStorage by TopBar's "Guardar" (keys prefixed salvi_solar_). */
function readSavedProjects() {
  const saved = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (!key || !key.startsWith('salvi_solar_')) continue
    try {
      saved.push(JSON.parse(localStorage.getItem(key)))
    } catch { /* skip corrupt entry */ }
  }
  return saved
}

function buildContext(state) {
  return {
    current_project: {
      project: state.project,
      photometry: state.photometry,
      nightProfile: state.nightProfile,
      env: state.env,
      candidates: state.candidates,
      simulation: state.simulation,
    },
    saved_projects: readSavedProjects(),
  }
}

export default function AskAIWidget() {
  const { state } = useApp()
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, loading])

  const send = async () => {
    const q = question.trim()
    if (!q || loading) return
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: q }])
    setQuestion('')
    setLoading(true)
    try {
      const r = await apiPost('/ai/ask', { question: q, context: buildContext(state), history })
      setMessages(m => [...m, { role: 'assistant', content: r.answer }])
    } catch (e) {
      setMessages(m => [...m, { role: 'error', content: e.message || 'Error al contactar la IA' }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div style={{ position: 'fixed', bottom: 20, right: 20, zIndex: 2000, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 10 }}>
      {open && (
        <div style={{
          width: 340, height: 440, background: '#fff', borderRadius: 12,
          boxShadow: '0 8px 28px rgba(0,0,0,0.22)', border: '1px solid rgba(0,0,0,0.1)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--salvi-line, #eee)', display: 'flex', alignItems: 'center', gap: 8, background: '#1E1E1E', color: '#fff' }}>
            <Sparkles size={16} />
            <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>Ask IA · Proyectos SALVI Solar</span>
            <button onClick={() => setOpen(false)} style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex' }}>
              <X size={16} />
            </button>
          </div>

          <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {messages.length === 0 && (
              <div style={{ fontSize: 12, color: 'var(--salvi-muted, #999)', lineHeight: 1.5 }}>
                Pregunta sobre el proyecto actual o los proyectos guardados en este navegador:
                dimensionado, producción, batería, coste, sombras…
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '88%',
                background: m.role === 'user' ? '#1E1E1E' : m.role === 'error' ? '#fdecea' : '#f4f2ee',
                color: m.role === 'user' ? '#fff' : m.role === 'error' ? '#b3261e' : '#1E1E1E',
                borderRadius: 10, padding: '7px 10px', fontSize: 12.5, whiteSpace: 'pre-wrap', lineHeight: 1.45,
              }}>
                {m.content}
              </div>
            ))}
            {loading && (
              <div style={{ alignSelf: 'flex-start', color: 'var(--salvi-muted, #999)', fontSize: 12 }}>Pensando…</div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6, padding: 10, borderTop: '1px solid var(--salvi-line, #eee)' }}>
            <textarea
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu pregunta…"
              rows={1}
              style={{ flex: 1, resize: 'none', borderRadius: 8, border: '1px solid rgba(0,0,0,0.15)', padding: '7px 9px', fontSize: 12.5, fontFamily: 'inherit' }}
            />
            <button
              onClick={send}
              disabled={loading || !question.trim()}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 34, height: 34, borderRadius: 8, border: 'none',
                background: '#1E1E1E', color: '#fff', cursor: loading ? 'default' : 'pointer',
                opacity: loading || !question.trim() ? 0.5 : 1, flexShrink: 0,
              }}
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(o => !o)}
        title="Ask IA"
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', borderRadius: 24, border: 'none',
          background: '#1E1E1E', color: '#fff', cursor: 'pointer',
          boxShadow: '0 4px 14px rgba(0,0,0,0.28)', fontSize: 13, fontWeight: 600,
        }}
      >
        <Sparkles size={16} />
        Ask IA
      </button>
    </div>
  )
}
