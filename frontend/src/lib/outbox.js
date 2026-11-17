import api from '../api/client'

// A tiny persistent outbox for writes that must not be lost when the connection drops or the page is
// refreshed. Every entry carries a client_request_id and the server de-duplicates on it, so re-sending is always
// safe: if the first attempt actually reached the server, the retry returns the same record.
const KEY = 'ats-outbox-v1'

const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
const write = (items) => { try { localStorage.setItem(KEY, JSON.stringify(items)) } catch { /* private mode */ } }

export const newRequestId = () =>
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random().toString(16).slice(2)}`).replace(/-/g, '')

// "No answer from the server" (offline, dropped connection, timeout): worth retrying. Any HTTP error is final.
const isNetworkError = (err) => !err.response

export function pending() {
  return read()
}

export function drop(id) {
  write(read().filter((e) => e.id !== id))
}

/** Send now; if the network fails, keep it and report { queued: true }. HTTP errors (422, 402...) are thrown. */
export async function sendOrQueue(entry) {
  const items = read()
  if (!items.some((e) => e.id === entry.id)) write([...items, { ...entry, queuedAt: Date.now() }])
  try {
    const res = await api.post(entry.path, entry.body, { timeout: 30000 })
    drop(entry.id)
    return { queued: false, data: res.data }
  } catch (err) {
    if (isNetworkError(err)) return { queued: true }
    drop(entry.id)
    throw err
  }
}

/** Re-send everything waiting. Returns the successfully delivered responses. */
export async function flush(onDelivered) {
  const sent = []
  for (const entry of read()) {
    try {
      const res = await api.post(entry.path, entry.body, { timeout: 30000 })
      drop(entry.id)
      sent.push({ entry, data: res.data })
      onDelivered?.(entry, res.data)
    } catch (err) {
      if (isNetworkError(err)) break            // still offline: keep the rest for next time
      drop(entry.id)                            // the server refused it: retrying cannot help
    }
  }
  return sent
}
