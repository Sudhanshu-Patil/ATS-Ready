import api from '../api/client'

// Authenticated file download. A plain <a href> would break when the access cookie has just
// expired; going through the axios client refreshes the session first.
export async function downloadFile(path, fallbackName) {
  const res = await api.get(path.replace(/^\/api/, ''), { responseType: 'blob' })
  const disposition = res.headers['content-disposition'] || ''
  const name = (disposition.match(/filename="?([^";]+)"?/) || [])[1] || fallbackName
  const url = URL.createObjectURL(res.data)
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
