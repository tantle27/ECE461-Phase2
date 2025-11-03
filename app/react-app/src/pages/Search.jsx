import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ArtifactList from '../components/ArtifactList'
import ErrorBanner from '../components/ErrorBanner'

export default function Search() {
  const { client } = useAuth()
  const [type, setType] = useState('')
  const [name, setName] = useState('')
  const [regex, setRegex] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function listAll(e) {
    e && e.preventDefault()
    setLoading(true); setError(null)
    try {
      const body = [{ name: '*', artifact_type: type || undefined, page, page_size: pageSize }]
      const resp = await client.post('/artifacts', body)
      const arr = Array.isArray(resp.data) ? resp.data : []
      setItems(arr.map(m => ({ metadata: { id: m.id, name: m.name, type: m.type, version: '1.0.0' }, data: {} })))
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  async function searchByName(e) {
    e && e.preventDefault()
    if (!name) return
    setLoading(true); setError(null)
    try {
      const resp = await client.get(`/artifact/byName/${encodeURIComponent(name)}`)
      const arr = Array.isArray(resp.data) ? resp.data : []
      setItems(arr.map(m => ({ metadata: { id: m.id, name: m.name, type: m.type, version: '1.0.0' }, data: {} })))
    } catch (err) {
      setError(err)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  async function searchByRegex(e) {
    e && e.preventDefault()
    if (!regex) return
    setLoading(true); setError(null)
    try {
      const resp = await client.post('/artifact/byRegEx', { regex })
      const arr = Array.isArray(resp.data) ? resp.data : []
      setItems(arr.map(m => ({ metadata: { id: m.id, name: m.name, type: m.type, version: '1.0.0' }, data: {} })))
    } catch (err) {
      setError(err)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Search</h2>
      <div className="bg-white p-4 rounded shadow space-y-4">
        <div className="grid md:grid-cols-4 gap-3">
          <div>
            <label className="block text-sm text-gray-700">Type</label>
            <select value={type} onChange={e => setType(e.target.value)} className="mt-1 p-2 border rounded w-full">
              <option value="">Any</option>
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-700">Name (exact)</label>
            <input value={name} onChange={e => setName(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="artifact name" />
          </div>
          <div>
            <label className="block text-sm text-gray-700">Regex</label>
            <input value={regex} onChange={e => setRegex(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="e.g. ^resnet" />
          </div>
          <div className="grid grid-cols-2 gap-2 items-end">
            <div>
              <label className="block text-sm text-gray-700">Page</label>
              <input type="number" min={1} value={page} onChange={e => setPage(parseInt(e.target.value || '1'))} className="mt-1 p-2 border rounded w-full" />
            </div>
            <div>
              <label className="block text-sm text-gray-700">Page size</label>
              <input type="number" min={1} max={100} value={pageSize} onChange={e => setPageSize(parseInt(e.target.value || '10'))} className="mt-1 p-2 border rounded w-full" />
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <button onClick={listAll} className="px-3 py-2 bg-blue-700 text-white rounded">List</button>
          <button onClick={searchByName} className="px-3 py-2 bg-green-700 text-white rounded">Find by Name</button>
          <button onClick={searchByRegex} className="px-3 py-2 bg-purple-700 text-white rounded">Regex</button>
        </div>
      </div>

      <ErrorBanner error={error} />
      {loading ? <div className="mt-4">Loading…</div> : (
        <div className="mt-4">
          <ArtifactList items={items} />
        </div>
      )}
    </div>
  )
}
