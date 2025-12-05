import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ArtifactList from '../components/ArtifactList'
import ErrorBanner from '../components/ErrorBanner'

export default function Search() {
  const { client } = useAuth()
  const [searchType, setSearchType] = useState('name')
  const [name, setName] = useState('')
  const [regex, setRegex] = useState('')
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function searchByName(e) {
    e && e.preventDefault()
    if (!name) return
    setLoading(true); setError(null); setItems([])
    try {
      const resp = await client.get(`/artifact/byName/${encodeURIComponent(name)}`)
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
    setLoading(true); setError(null); setItems([])
    try {
      const resp = await client.post('/artifact/byRegEx', { regex })
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
    } catch (err) {
      setError(err)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-semibold">Search Artifacts</h2>
      
      <div className="bg-white p-6 rounded shadow">
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">Search Method</label>
          <div className="flex gap-4">
            <label className="flex items-center">
              <input 
                type="radio" 
                name="searchType" 
                value="name" 
                checked={searchType === 'name'} 
                onChange={e => setSearchType(e.target.value)}
                className="mr-2"
              />
              <span className="text-sm">By Exact Name</span>
            </label>
            <label className="flex items-center">
              <input 
                type="radio" 
                name="searchType" 
                value="regex" 
                checked={searchType === 'regex'} 
                onChange={e => setSearchType(e.target.value)}
                className="mr-2"
              />
              <span className="text-sm">By Regex Pattern</span>
            </label>
          </div>
        </div>

        {searchType === 'name' && (
          <form onSubmit={searchByName} className="space-y-4">
            <div>
              <label htmlFor="searchNameInput" className="block text-sm font-medium text-gray-700 mb-2">
                Artifact Name (exact match, case-insensitive)
              </label>
              <input 
                id="searchNameInput"
                value={name} 
                onChange={e => setName(e.target.value)} 
                className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g., my-model-v1"
              />
            </div>
            <button 
              type="submit"
              disabled={!name || loading}
              className="px-4 py-2 bg-blue-700 text-white rounded hover:bg-blue-800 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Searching...' : 'Search by Name'}
            </button>
          </form>
        )}

        {searchType === 'regex' && (
          <form onSubmit={searchByRegex} className="space-y-4">
            <div>
              <label htmlFor="searchRegexInput" className="block text-sm font-medium text-gray-700 mb-2">
                Regex Pattern (searches name and readme fields)
              </label>
              <input 
                id="searchRegexInput"
                value={regex} 
                onChange={e => setRegex(e.target.value)} 
                className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                placeholder="e.g., ^resnet|vgg.*16$"
              />
              <p className="text-xs text-gray-600 mt-1">
                Examples: <code className="bg-gray-100 px-1">^model</code> (starts with "model"), 
                <code className="bg-gray-100 px-1 ml-1">.*v[0-9]+</code> (contains version number)
              </p>
            </div>
            <button 
              type="submit"
              disabled={!regex || loading}
              className="px-4 py-2 bg-purple-700 text-white rounded hover:bg-purple-800 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Searching...' : 'Search by Regex'}
            </button>
          </form>
        )}
      </div>

      <ErrorBanner error={error} />
      
      {loading && <div className="text-center py-4">Loading...</div>}
      
      {!loading && items.length === 0 && !error && (
        <div className="text-center py-8 text-gray-600">
          No results yet. Enter a search term above.
        </div>
      )}

      {items.length > 0 && (
        <div>
          <h3 className="text-lg font-medium mb-3">Results ({items.length})</h3>
          <ArtifactList items={items} />
        </div>
      )}
    </div>
  )
}
