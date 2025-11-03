import React from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AuthRequired({ children }) {
  const { user } = useAuth()
  if (user) return children
  return (
    <div className="bg-white p-6 rounded-lg shadow border">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 text-blue-600" aria-hidden>
          <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor"><path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10Zm0-14a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm1 9h-2v-7h2v7Z"/></svg>
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold mb-1">Sign in required</h3>
          <p className="text-sm text-gray-700 mb-4">You need to sign in to access this feature.</p>
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-900">
            <div className="font-medium mb-1">Default credentials (dev/testing):</div>
            <div>Username: <code className="bg-white/60 px-1 rounded">ece30861defaultadminuser</code></div>
            <div className="mt-0.5">Password: <code className="bg-white/60 px-1 rounded">correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages</code></div>
          </div>
          <NavLink to="/signin" className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M10 17l5-5-5-5v10zm-6 4V3h2v18H4z"/></svg>
            Go to Sign In
          </NavLink>
        </div>
      </div>
    </div>
  )
}
