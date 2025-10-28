import React from 'react'

export default function Loading({ message = 'Loading...' }) {
  return (
    <div role="status" className="p-4 text-sm text-gray-700">
      {message}
    </div>
  )
}
