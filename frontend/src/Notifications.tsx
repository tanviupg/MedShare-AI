import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Check, CheckCheck, RefreshCw } from 'lucide-react'
import { API_BASE_URL } from './config'

type Notice = { id: string; title: string; message: string; type: string; is_read: boolean; created_at: string }
type NotificationPage = { items: Notice[]; total: number; limit: number; offset: number }

const INITIAL_LIMIT = 8
const PAGE_LIMIT = 50

export default function Notifications({ token }: { token: string }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notice[]>([])
  const [total, setTotal] = useState(0)
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const refreshRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const itemsRef = useRef(items)
  itemsRef.current = items

  const fetchPage = useCallback(async (limit: number, offset: number): Promise<NotificationPage> => {
    const response = await fetch(`${API_BASE_URL}/notifications?limit=${limit}&offset=${offset}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error('Could not load your notifications. Please try again.')
    return await response.json() as NotificationPage
  }, [token])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    setActionError('')
    try {
      const countResponse = await fetch(`${API_BASE_URL}/notifications/unread-count`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!countResponse.ok) throw new Error('Could not load your notifications. Please try again.')
      const unread = await countResponse.json() as { count: number }
      setCount(unread.count)

      const target = Math.max(INITIAL_LIMIT, itemsRef.current.length)
      const refreshed: Notice[] = []
      let nextTotal = 0
      while (refreshed.length < target) {
        const limit = Math.min(PAGE_LIMIT, target - refreshed.length)
        const page = await fetchPage(limit, refreshed.length)
        refreshed.push(...page.items)
        nextTotal = page.total
        if (page.items.length < limit) break
      }
      setItems(refreshed)
      setTotal(nextTotal)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load your notifications. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [fetchPage, token])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, 30000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [refresh])

  useEffect(() => {
    if (!open) return
    refreshRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [open])

  async function loadMore() {
    if (loadingMore || loading || items.length >= total) return
    setLoadingMore(true)
    setError('')
    try {
      const page = await fetchPage(PAGE_LIMIT, itemsRef.current.length)
      setItems((current) => [...current, ...page.items])
      setTotal(page.total)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load more notifications. Please try again.')
    } finally {
      setLoadingMore(false)
    }
  }

  async function markRead(id: string) {
    setActionBusy(true)
    setActionError('')
    try {
      const response = await fetch(`${API_BASE_URL}/notifications/${id}/read`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Could not mark this notification as read. Please try again.')
      const updated = await response.json() as Notice
      setItems((current) => current.map((item) => item.id === id ? { ...item, ...updated, is_read: true } : item))
      setCount((current) => Math.max(0, current - 1))
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Could not mark this notification as read. Please try again.')
    } finally {
      setActionBusy(false)
    }
  }

  async function markAll() {
    setActionBusy(true)
    setActionError('')
    try {
      const response = await fetch(`${API_BASE_URL}/notifications/read-all`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Could not mark notifications as read. Please try again.')
      setItems((current) => current.map((item) => ({ ...item, is_read: true })))
      setCount(0)
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Could not mark notifications as read. Please try again.')
    } finally {
      setActionBusy(false)
    }
  }

  return <div className="relative">
    <button ref={triggerRef} type="button" onClick={() => setOpen((value) => !value)} aria-label="Notifications" aria-haspopup="dialog" aria-expanded={open} aria-controls="notification-panel" className="relative grid size-10 place-items-center rounded-full border border-[#dce4d9] bg-white p-0 text-[#31574b] transition-colors hover:bg-[#f5f7f2] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#a85c45]"><Bell size={18} aria-hidden="true" /></button>
    {open && <section ref={panelRef} id="notification-panel" role="dialog" aria-modal="false" aria-labelledby="notification-title" className="absolute right-0 z-40 mt-2 flex max-h-[min(80vh,42rem)] w-[min(26rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-[#e4e9e0] bg-white text-left shadow-xl">
      <header className="flex items-center justify-between gap-3 border-b border-[#edf0ea] px-4 py-3">
        <h2 id="notification-title" className="font-semibold">Notifications</h2>
        <div className="flex items-center gap-3">
          <button ref={refreshRef} type="button" onClick={() => void refresh()} disabled={loading} aria-label="Refresh notifications" className="rounded p-1 text-[#54766a] hover:bg-[#f5f7f2] disabled:opacity-50"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /></button>
          <button type="button" onClick={() => void markAll()} disabled={actionBusy || count === 0} className="flex items-center gap-1 text-xs font-medium text-[#54766a] hover:text-[#174e3f] disabled:opacity-50"><CheckCheck size={14} /> Mark all as read</button>
        </div>
      </header>
      {count > 0 && <span className="sr-only">{count} unread notifications</span>}
      {loading && items.length > 0 && <p className="border-b border-[#edf0ea] px-4 py-2 text-xs text-[#718078]" role="status">Refreshing notifications…</p>}
      {actionError && <p role="alert" className="border-b border-red-100 bg-red-50 px-4 py-2 text-sm text-red-800">{actionError}</p>}
      {error ? <div className="px-4 py-8 text-center" role="alert"><p className="text-sm text-red-800">{error}</p><button type="button" onClick={() => void refresh()} className="mt-3 rounded-full border border-[#dce4d9] px-4 py-2 text-sm font-semibold text-[#174e3f] hover:bg-[#f5f7f2]">Retry</button></div>
        : loading && items.length === 0 ? <p className="px-4 py-8 text-center text-sm text-[#718078]" role="status">Loading notifications…</p>
          : items.length === 0 ? <p className="px-4 py-8 text-center text-sm text-[#718078]">You have no notifications.</p>
            : <div className="min-h-0 flex-1 overflow-y-auto" aria-busy={loadingMore}>
              {items.map((item) => <article key={item.id} className={`border-b border-[#f0f2ee] px-4 py-3 ${item.is_read ? 'bg-white' : 'bg-[#f4f8f4]'}`}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs leading-5 text-[#687870]">{item.message}</p><time className="mt-1 block text-[11px] text-[#87938a]">{new Date(item.created_at).toLocaleString()}</time></div>{!item.is_read && <button type="button" onClick={() => void markRead(item.id)} disabled={actionBusy} className="flex shrink-0 items-center gap-1 rounded px-1 py-1 text-xs font-medium text-[#54766a] hover:bg-white disabled:opacity-50"><Check size={14} /> Mark read</button>}</div></article>)}
              {items.length < total && <button type="button" onClick={() => void loadMore()} disabled={loadingMore} className="w-full px-4 py-3 text-sm font-semibold text-[#174e3f] hover:bg-[#f5f7f2] disabled:opacity-50">{loadingMore ? 'Loading more…' : `Load more (${items.length} of ${total})`}</button>}
              {items.length >= total && total > INITIAL_LIMIT && <p className="px-4 py-3 text-center text-xs text-[#718078]">All {total} notifications loaded</p>}
            </div>}
    </section>}
  </div>
}
