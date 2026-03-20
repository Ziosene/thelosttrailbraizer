import mitt from 'mitt'

type Events = Record<string, unknown>

export const bus = mitt<Events>()

let ws: WebSocket | null = null

export function connectSocket(gameCode: string): WebSocket {
  const token = localStorage.getItem('token') ?? ''
  const url = `/ws/${gameCode}?token=${token}`
  ws = new WebSocket(url)

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type) bus.emit(msg.type, msg)
    } catch { /* ignore */ }
  }

  ws.onclose = () => bus.emit('ws_closed', {})
  ws.onerror = () => bus.emit('ws_error', {})

  return ws
}

export function sendAction(action: string, data: Record<string, unknown> = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action, ...data }))
  }
}

export function disconnectSocket() {
  ws?.close()
  ws = null
}
