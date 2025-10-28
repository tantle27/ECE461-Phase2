import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ErrorBanner from '../components/ErrorBanner'

export default function SignInPage() {
  const { signIn, user } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    const res = await signIn(username, password)
    setLoading(false)
    if (!res.ok) setError(res.error?.message || 'Sign in failed')
  }

  return (
    <div className="max-w-md">
      <h2 className="text-2xl font-semibold mb-4">Sign In</h2>
      <ErrorBanner error={error} />
      {user ? (
        <div className="p-4 bg-green-50 text-green-800 rounded">Signed in as {user.username}</div>
      ) : (
        <form onSubmit={submit} className="bg-white p-4 rounded shadow space-y-3">
          <div>
            <label className="block text-sm text-gray-700">Username</label>
            <input value={username} onChange={e => setUsername(e.target.value)} className="mt-1 p-2 border rounded w-full" />
          </div>
          <div>
            <label className="block text-sm text-gray-700">Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 p-2 border rounded w-full" />
          </div>
          <div>
            <button disabled={loading} className="px-3 py-2 bg-blue-700 text-white rounded">Sign In</button>
          </div>
        </form>
      )}
    </div>
  )
}
