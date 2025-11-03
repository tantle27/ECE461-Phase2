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
  const [metrics, setMetrics] = useState(null)
  const [cost, setCost] = useState(null)
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
      
      // Clear previous data
      setAudit([])
      setLineage({ nodes: [], links: [] })
      setMetrics(null)
      setCost(null)
      
      // Fetch audit (available for all types)
      try { 
        const a = await client.get(`/artifact/${artifactType}/${artifactId}/audit`)
        setAudit(a.data) 
      } catch (e) { /* ignore */ }
      
      // Fetch cost (available for all types)
      try {
        const c = await client.get(`/artifact/${artifactType}/${artifactId}/cost?dependency=true`)
        setCost(c.data)
      } catch (e) { /* ignore */ }
      
      // For models, fetch additional data
      if (artifactType === 'model') {
        const art = resp.data
        const hasPkg = art?.data && (art.data.path || art.data.s3_key)
        
        // Fetch metrics/rating
        try {
          const r = await client.get(`/artifact/model/${artifactId}/rate`)
          setMetrics(r.data)
        } catch (e) { /* ignore */ }
        
        // Fetch lineage only if package exists
        if (hasPkg) {
          try {
            const l = await client.get(`/artifact/model/${artifactId}/lineage`)
            const ln = l.data || {}
            const nodes = (ln.nodes || []).map(n => ({ id: n.artifact_id, name: n.name }))
            const links = (ln.edges || []).map(e => ({ source: e.from_node_artifact_id, target: e.to_node_artifact_id }))
            setLineage({ nodes, links })
          } catch (e) { /* ignore */ }
        }
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
      // Backend returns array of metadata: [{ id, name, type }]
      const arr = Array.isArray(resp.data) ? resp.data : []
      // Transform to full artifact shape for display
      setItems(arr.map(m => ({ 
        metadata: { id: m.id, name: m.name, type: m.type, version: '1.0.0' }, 
        data: {},
        // Add flat properties for easier access
        id: m.id,
        name: m.name,
        type: m.type
      })))
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
      setMetrics(null)
      setCost(null)
      // remove from local list
      setItems(prev => prev.filter(it => (it.metadata?.id || it.id) !== md.id))
    } catch (err) { setError(err) } finally { setLoading(false) }
  }

  async function downloadModel() {
    if (!selected || selected.metadata?.type !== 'model') return
    const md = selected.metadata || {}
    try {
      const resp = await client.get(`/artifact/model/${md.id}/download`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([resp.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${md.name || md.id}.zip`)
      document.body.appendChild(link)
      link.click()
      link.parentNode.removeChild(link)
    } catch (err) {
      setError(err)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">Artifacts</h2>
        <p className="text-gray-600 mt-1">Create, view, and manage your artifacts</p>
      </div>

      <ErrorBanner error={error} />
      {loading && <Loading />}

      {/* Create & Fetch Section */}
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold mb-4 text-gray-900">Create New Artifact</h3>
          <ArtifactForm onSubmit={handleCreate} />
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold mb-4 text-gray-900">Get Artifact by ID</h3>
          <GetByIdForm onFetch={fetchById} />
        </div>
      </div>

      {/* List Artifacts Section */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4 text-gray-900">Browse Artifacts</h3>
        <form onSubmit={listArtifacts} className="grid md:grid-cols-5 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
            <select value={listType} onChange={e => setListType(e.target.value)} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500">
              <option value="">All Types</option>
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Page</label>
            <input type="number" min={1} value={listPage} onChange={e => setListPage(parseInt(e.target.value || '1'))} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Per Page</label>
            <input type="number" min={1} max={100} value={listPageSize} onChange={e => setListPageSize(parseInt(e.target.value || '10'))} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" />
          </div>
          <div className="flex items-end">
            <button className="w-full px-4 py-2 bg-blue-700 text-white rounded hover:bg-blue-800" type="submit">
              List All
            </button>
          </div>
        </form>
        {items.length > 0 ? (
          <ArtifactList items={items} />
        ) : (
          <div className="text-center py-8 text-gray-500">No artifacts listed yet. Click "List All" to browse.</div>
        )}
      </div>

      {/* Selected Artifact Details */}
      {selected && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold mb-4 text-gray-900">Selected Artifact</h3>
            <ArtifactList items={[selected]} />
          </div>

          {/* Update & Delete */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold mb-4 text-gray-900">Update or Delete</h3>
            <form onSubmit={updateSelected} className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input value={updateName} onChange={e => setUpdateName(e.target.value)} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
                  <input value={updateUrl} onChange={e => setUpdateUrl(e.target.value)} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" />
                </div>
              </div>
              <div className="flex gap-3">
                <button type="submit" className="px-4 py-2 bg-blue-700 text-white rounded hover:bg-blue-800">
                  Save Changes
                </button>
                <button type="button" onClick={deleteSelected} className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700">
                  Delete Artifact
                </button>
                {selected.metadata?.type === 'model' && selected.data && (selected.data.path || selected.data.s3_key) && (
                  <button type="button" onClick={downloadModel} className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">
                    Download Package
                  </button>
                )}
              </div>
            </form>
          </div>

          {/* Metrics & Rating - Only for models */}
          {selected.metadata?.type === 'model' && metrics && (
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold mb-4 text-gray-900">Metrics & Rating</h3>
              <div className="space-y-2">
                {metrics.net_score !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Net Score:</span>
                    <span className="font-semibold">{metrics.net_score.toFixed(3)}</span>
                  </div>
                )}
                {metrics.ramp_up_time !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Ramp-Up Time:</span>
                    <span className="font-semibold">{metrics.ramp_up_time.toFixed(3)}</span>
                  </div>
                )}
                {metrics.bus_factor !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Bus Factor:</span>
                    <span className="font-semibold">{metrics.bus_factor.toFixed(3)}</span>
                  </div>
                )}
                {metrics.correctness !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Correctness:</span>
                    <span className="font-semibold">{metrics.correctness.toFixed(3)}</span>
                  </div>
                )}
                {metrics.responsive_maintainer !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Responsive Maintainer:</span>
                    <span className="font-semibold">{metrics.responsive_maintainer.toFixed(3)}</span>
                  </div>
                )}
                {metrics.license_score !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">License Score:</span>
                    <span className="font-semibold">{metrics.license_score.toFixed(3)}</span>
                  </div>
                )}
                {metrics.good_pinning_practice !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Good Pinning Practice:</span>
                    <span className="font-semibold">{metrics.good_pinning_practice.toFixed(3)}</span>
                  </div>
                )}
                {metrics.pull_request !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-700">Pull Request Score:</span>
                    <span className="font-semibold">{metrics.pull_request.toFixed(3)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Cost Analysis */}
          {cost && (
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold mb-4 text-gray-900">Cost Analysis</h3>
              {Object.keys(cost).length > 0 ? (
                <div className="space-y-3">
                  {Object.entries(cost).map(([id, costs]) => (
                    <div key={id} className="border-b pb-2">
                      <div className="font-mono text-sm text-gray-600 mb-1">{id}</div>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        {costs.standalone_cost !== undefined && (
                          <div>
                            <span className="text-gray-700">Standalone:</span>
                            <span className="ml-2 font-semibold">{costs.standalone_cost} MB</span>
                          </div>
                        )}
                        {costs.total_cost !== undefined && (
                          <div>
                            <span className="text-gray-700">Total:</span>
                            <span className="ml-2 font-semibold">{costs.total_cost} MB</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-gray-600">No cost data available</div>
              )}
            </div>
          )}

          {/* Audit Trail */}
          {audit.length > 0 && (
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold mb-4 text-gray-900">Audit Trail</h3>
              <AuditTrail entries={audit} />
            </div>
          )}

          {/* Lineage - Only for models with packages */}
          {selected.metadata?.type === 'model' && selected.data && (selected.data.path || selected.data.s3_key) && (
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-semibold mb-4 text-gray-900">Lineage Graph</h3>
              <LineageGraph nodes={lineage.nodes} links={lineage.links} />
            </div>
          )}
        </div>
      )}
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
