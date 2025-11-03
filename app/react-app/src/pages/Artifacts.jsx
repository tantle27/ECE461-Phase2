import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ArtifactForm from '../components/ArtifactForm'
import ArtifactList from '../components/ArtifactList'
import ErrorBanner from '../components/ErrorBanner'
import Loading from '../components/Loading'
import LineageGraph from '../components/LineageGraph'
import AuditTrail from '../components/AuditTrail'

export default function ArtifactsPage() {
  const { client } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [lineage, setLineage] = useState({ nodes: [], links: [] })
  const [updateName, setUpdateName] = useState('')
  const [updateUrl, setUpdateUrl] = useState('')
  const [listType, setListType] = useState('')
  const [listPage, setListPage] = useState(1)
  const [listPageSize, setListPageSize] = useState(10)

  async function handleCreate({ type, url }) {
    setError(null)
    setLoading(true)
    try {
      const resp = await client.post(`/artifact/${type}`, { url })
      // backend returns full artifact { metadata, data }
      const art = resp.data
      setSelected(art)
      const md = art?.metadata || {}
      setItems(prev => [{ id: md.id, name: md.name, type: md.type, url: art?.data?.url }, ...prev])
      // fetch audit (ok for all types)
      try { const a = await client.get(`/artifact/${md.type}/${md.id}/audit`); setAudit(a.data) } catch (e) { /* ignore */ }
      // lineage only for models with a package present
      if (md.type === 'model' && art?.data && (art.data.path || art.data.s3_key)) {
        try {
          const l = await client.get(`/artifact/${md.type}/${md.id}/lineage`)
          const ln = l.data || {}
          const nodes = (ln.nodes || []).map(n => ({ id: n.artifact_id, name: n.name }))
          const links = (ln.edges || []).map(e => ({ source: e.from_node_artifact_id, target: e.to_node_artifact_id }))
          setLineage({ nodes, links })
        } catch (e) { /* ignore */ }
      } else {
        setLineage({ nodes: [], links: [] })
      }
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  async function fetchById(artifactType, artifactId) {
    setError(null)
    setLoading(true)
    try {
      const resp = await client.get(`/artifact/${artifactType}/${artifactId}`)
      setSelected(resp.data)
  setUpdateName(resp.data?.metadata?.name || '')
  setUpdateUrl(resp.data?.data?.url || '')
      // fetch audit (ok for all types)
      try { const a = await client.get(`/artifact/${artifactType}/${artifactId}/audit`); setAudit(a.data) } catch (e) { /* ignore */ }
      // lineage only for models with a package present
      const art = resp.data
      const hasPkg = art?.data && (art.data.path || art.data.s3_key)
      if (artifactType === 'model' && hasPkg) {
        try {
          const l = await client.get(`/artifact/${artifactType}/${artifactId}/lineage`)
          const ln = l.data || {}
          const nodes = (ln.nodes || []).map(n => ({ id: n.artifact_id, name: n.name }))
          const links = (ln.edges || []).map(e => ({ source: e.from_node_artifact_id, target: e.to_node_artifact_id }))
          setLineage({ nodes, links })
        } catch (e) { /* ignore */ }
      } else {
        setLineage({ nodes: [], links: [] })
      }
    } catch (err) {
      setError(err)
      setSelected(null)
    } finally {
      setLoading(false)
    }
  }

  async function listArtifacts(e) {
    e && e.preventDefault()
    setError(null); setLoading(true)
    try {
      const body = [{ name: '*', artifact_type: listType || undefined, page: listPage, page_size: listPageSize }]
      const resp = await client.post('/artifacts', body)
      const arr = Array.isArray(resp.data) ? resp.data : []
      setItems(arr.map(m => ({ metadata: { id: m.id, name: m.name, type: m.type, version: '1.0.0' }, data: {} })))
    } catch (err) { setError(err) } finally { setLoading(false) }
  }

  async function updateSelected(e) {
    e && e.preventDefault()
    if (!selected) return
    const md = selected.metadata || {}
    const dt = selected.data || {}
    const body = { metadata: { ...md, name: updateName }, data: { ...dt, url: updateUrl } }
    setError(null); setLoading(true)
    try {
      await client.put(`/artifacts/${md.type}/${md.id}`, body)
      // refresh selection
      await fetchById(md.type, md.id)
    } catch (err) { setError(err) } finally { setLoading(false) }
  }

  async function deleteSelected() {
    if (!selected) return
    const md = selected.metadata || {}
    setError(null); setLoading(true)
    try {
      await client.delete(`/artifacts/${md.type}/${md.id}`)
      setSelected(null)
      setAudit([])
      setLineage({ nodes: [], links: [] })
      // remove from local list
      setItems(prev => prev.filter(it => (it.metadata?.id || it.id) !== md.id))
    } catch (err) { setError(err) } finally { setLoading(false) }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-semibold">Artifacts</h2>

      <div className="grid md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium mb-2">Create Artifact</h3>
          <ArtifactForm onSubmit={handleCreate} />
        </div>

        <div>
          <h3 className="text-lg font-medium mb-2">Get Artifact by ID</h3>
          <GetByIdForm onFetch={fetchById} />
        </div>
      </div>

      <ErrorBanner error={error} />
      {loading && <Loading />}

      <section>
        <h3 className="text-lg font-medium mb-2">Selected Artifact</h3>
        {selected ? <ArtifactList items={[selected]} /> : <div className="text-sm text-gray-600">No artifact selected.</div>}
      </section>

      {selected && (
        <section>
          <h3 className="text-lg font-medium mb-2">Update / Delete</h3>
          <form onSubmit={updateSelected} className="bg-white p-4 rounded shadow grid md:grid-cols-3 gap-3">
            <div>
              <label className="block text-sm text-gray-700">Name</label>
              <input value={updateName} onChange={e => setUpdateName(e.target.value)} className="mt-1 p-2 border rounded w-full" />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm text-gray-700">URL</label>
              <input value={updateUrl} onChange={e => setUpdateUrl(e.target.value)} className="mt-1 p-2 border rounded w-full" />
            </div>
            <div className="flex gap-2 items-end">
              <button type="submit" className="px-3 py-2 bg-blue-700 text-white rounded">Save</button>
              <button type="button" onClick={deleteSelected} className="px-3 py-2 bg-red-700 text-white rounded">Delete</button>
            </div>
          </form>
        </section>
      )}

      <section>
        <h3 className="text-lg font-medium mb-2">Rate / Metrics</h3>
        {/* placeholder for metrics display; could use recharts */}
        {selected?.metrics ? <pre className="bg-gray-50 p-3 rounded">{JSON.stringify(selected.metrics, null, 2)}</pre> : <div className="text-sm text-gray-600">No metrics available</div>}
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Cost</h3>
        <div className="text-sm text-gray-700">Standalone: {selected?.cost?.standalone ?? '—'} • Total: {selected?.cost?.total ?? '—'}</div>
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Lineage</h3>
        {selected && selected.metadata?.type === 'model' && selected.data && (selected.data.path || selected.data.s3_key) ? (
          <LineageGraph nodes={lineage.nodes} links={lineage.links} />
        ) : (
          <div className="text-sm text-gray-600">No package available for lineage. Upload a model package to see the lineage graph.</div>
        )}
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Audit Trail</h3>
        <AuditTrail entries={audit} />
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">List Artifacts</h3>
        <form onSubmit={listArtifacts} className="bg-white p-4 rounded shadow grid md:grid-cols-5 gap-3">
          <div>
            <label className="block text-sm text-gray-700">Type</label>
            <select value={listType} onChange={e => setListType(e.target.value)} className="mt-1 p-2 border rounded w-full">
              <option value="">Any</option>
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-700">Page</label>
            <input type="number" min={1} value={listPage} onChange={e => setListPage(parseInt(e.target.value || '1'))} className="mt-1 p-2 border rounded w-full" />
          </div>
          <div>
            <label className="block text-sm text-gray-700">Page size</label>
            <input type="number" min={1} max={100} value={listPageSize} onChange={e => setListPageSize(parseInt(e.target.value || '10'))} className="mt-1 p-2 border rounded w-full" />
          </div>
          <div className="flex items-end">
            <button className="px-3 py-2 bg-gray-800 text-white rounded" type="submit">List</button>
          </div>
        </form>

        <div className="mt-3">
          <ArtifactList items={items} />
        </div>
      </section>
    </div>
  )
}

function GetByIdForm({ onFetch }) {
  const [type, setType] = useState('model')
  const [id, setId] = useState('')
  const [err, setErr] = useState(null)

  function submit(e) {
    e.preventDefault()
    setErr(null)
    if (!id) return setErr('ID required')
    onFetch(type, id)
  }

  return (
    <form onSubmit={submit} className="bg-white p-4 rounded shadow flex gap-2 items-end">
      <div>
        <label className="block text-sm text-gray-700">Type</label>
        <select value={type} onChange={e => setType(e.target.value)} className="mt-1 p-2 border rounded">
          <option value="model">Model</option>
          <option value="dataset">Dataset</option>
          <option value="code">Code</option>
        </select>
      </div>
      <div className="flex-1">
        <label className="block text-sm text-gray-700">ID</label>
        <input value={id} onChange={e => setId(e.target.value)} className="mt-1 p-2 border rounded w-full" />
      </div>
      <div>
        <button className="px-3 py-2 bg-blue-700 text-white rounded">Fetch</button>
      </div>
      {err && <div className="text-sm text-red-700">{err}</div>}
    </form>
  )
}
