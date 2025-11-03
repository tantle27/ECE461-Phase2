import React, { useState } from 'react'
import axios from 'axios'

export default function SearchBox({ searchUrl }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)

  async function doSearch(e) {
    e && e.preventDefault()
    if (!query) return
    setLoading(true)
    try {
      const resp = await axios.get((searchUrl || import.meta.env.VITE_API_URL + '/search') + '?q=' + encodeURIComponent(query))
      setResults(resp.data)
    } catch (err) {
      setResults({ error: err.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white shadow rounded p-6">
      <form onSubmit={doSearch} className="flex gap-2 items-center" role="search" aria-label="Site search">
        <label htmlFor="searchInput" className="sr-only">Search</label>
        <input
          id="searchInput"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="flex-1 px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          placeholder="Search..."
          aria-label="Search"
        />
        <button className="px-4 py-2 bg-green-700 text-white rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">Search</button>
      </form>

      <div className="mt-4">
        {loading && <div role="status">Loading...</div>}
        {results && (
          <div role="region" aria-live="polite" aria-label="Search results">
            <pre className="text-sm bg-gray-50 p-3 rounded overflow-auto">{JSON.stringify(results, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
