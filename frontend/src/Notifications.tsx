import { useCallback, useEffect, useState } from 'react'
import { Bell, CheckCheck } from 'lucide-react'
import { API_BASE_URL } from './config'

type Notice = { id: string; title: string; message: string; type: string; is_read: boolean; created_at: string }

export default function Notifications({ token, standalone = false }: { token: string; standalone?: boolean }) {
  const [open, setOpen] = useState(standalone)
  const [all, setAll] = useState(standalone)
  const [items, setItems] = useState<Notice[]>([])
  const [count, setCount] = useState(0)

  const refresh = useCallback(async () => {
    const headers = { Authorization: `Bearer ${token}` }
    const [countResponse, listResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/notifications/unread-count`, { headers }),
      fetch(`${API_BASE_URL}/notifications?limit=${all ? 50 : 8}&offset=0`, { headers }),
    ])
    if (countResponse.ok) setCount((await countResponse.json() as { count: number }).count)
    if (listResponse.ok) setItems((await listResponse.json() as { items: Notice[] }).items)
  }, [token, all])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh() }, 30000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [refresh])

  async function markRead(id: string) {
    const response = await fetch(`${API_BASE_URL}/notifications/${id}/read`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    if (response.ok) await refresh()
  }

  async function markAll() {
    const response = await fetch(`${API_BASE_URL}/notifications/read-all`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    if (response.ok) await refresh()
  }

  return <div className={standalone ? 'w-full' : 'relative'}>
    <button onClick={() => setOpen((value) => !value)} aria-label="Notifications" aria-expanded={open} className={standalone ? 'relative rounded-full border border-[#dce4d9] bg-white px-4 py-2.5 text-sm font-semibold text-[#31574b] hover:bg-[#f5f7f2]' : 'relative rounded-full border border-[#dce4d9] bg-white p-2.5 text-[#31574b] hover:bg-[#f5f7f2]'}><Bell className={standalone ? 'mr-2 inline' : ''} size={18} />{standalone && 'Notifications'}{count > 0 && <span className={standalone ? 'ml-2 inline-grid min-w-5 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-bold leading-5 text-white' : 'absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-bold leading-5 text-white'}>{count > 99 ? '99+' : count}</span>}</button>
    {open && <section className={`${standalone ? 'mt-3 w-full' : 'absolute right-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))]'} overflow-hidden rounded-2xl border border-[#e4e9e0] bg-white text-left shadow-xl`}>
      <header className="flex items-center justify-between border-b border-[#edf0ea] px-4 py-3"><h2 className="font-semibold">Notifications</h2><button onClick={() => void markAll()} className="flex items-center gap-1 text-xs font-medium text-[#54766a] hover:text-[#174e3f]"><CheckCheck size={14} /> Mark all as read</button></header>
      <div className="max-h-96 overflow-y-auto">{items.length ? items.map((item) => <article key={item.id} className={`border-b border-[#f0f2ee] px-4 py-3 ${item.is_read ? 'bg-white' : 'bg-[#f4f8f4]'}`}><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs leading-5 text-[#687870]">{item.message}</p><time className="mt-1 block text-[11px] text-[#87938a]">{new Date(item.created_at).toLocaleString()}</time></div>{!item.is_read && <button onClick={() => void markRead(item.id)} className="shrink-0 text-xs font-medium text-[#54766a]">Mark read</button>}</div></article>) : <p className="px-4 py-8 text-center text-sm text-[#718078]">You have no notifications.</p>}</div>
      {!all && items.length === 8 && <button onClick={() => setAll(true)} className="w-full px-4 py-3 text-sm font-semibold text-[#174e3f] hover:bg-[#f5f7f2]">View all</button>}
      {all && <button onClick={() => setAll(false)} className="w-full px-4 py-3 text-sm font-semibold text-[#174e3f] hover:bg-[#f5f7f2]">Show recent</button>}
    </section>}
  </div>
}
