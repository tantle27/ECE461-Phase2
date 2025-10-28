import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import Loading from '../components/Loading'
import ErrorBanner from '../components/ErrorBanner'

export default function TracksPage() {
  const { client } = useAuth()
  const [tracks, setTracks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let mounted = true
    setLoading(true)
    client.get('/tracks').then(r => { if (mounted) setTracks(r.data || []) }).catch(e => { if (mounted) setError(e) }).finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [client])

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-4">Tracks</h2>
      <ErrorBanner error={error} />
      {loading && <Loading />}
      <ul className="space-y-2">
        {tracks.map((t, i) => (
          <li key={i} className="p-3 bg-white rounded shadow">{t}</li>
        ))}
      </ul>
    </div>
  )
}
