import React from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AuthRequired({ children }) {
  const { user } = useAuth()
  if (user) return children
  return (
    <div className="bg-white p-6 rounded shadow">
      <h3 className="text-lg font-semibold mb-2">Authentication required</h3>
      <p className="text-sm text-gray-700 mb-3">Please sign in to access this page.</p>
      <div className="mb-4 p-3 bg-gray-50 rounded text-xs text-gray-700">
        <div className="font-medium mb-1">Default credentials (for local dev):</div>
        <div>Username: <code>ece30861defaultadminuser</code></div>
        <div>Password: <code>correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages</code></div>
      </div>
      <NavLink to="/signin" className="px-3 py-2 bg-blue-700 text-white rounded">Go to Sign In</NavLink>
    </div>
  )
}
