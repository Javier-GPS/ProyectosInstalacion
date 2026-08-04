import { useState } from 'react'

let _addToast = null

export function showToast(msg, type = 'info') {
  _addToast?.(msg, type)
}

export default function Toast() {
  const [toasts, setToasts] = useState([])

  _addToast = (msg, type) => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, msg, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3500)
  }

  return (
    <div id="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>{t.msg}</div>
      ))}
    </div>
  )
}
