import React from 'react'

export default function ErrorBanner({ error }) {
  if (!error) return null
  const msg = error?.message || String(error)
  return (
    <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-800 rounded">
      {msg}
    </div>
  )
}
