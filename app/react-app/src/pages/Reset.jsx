import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import Modal from '../components/Modal'
import ErrorBanner from '../components/ErrorBanner'

export default function ResetPage() {
  const { client } = useAuth()
  const [showConfirm, setShowConfirm] = useState(false)
  const [message, setMessage] = useState(null)

  async function doReset() {
    setMessage(null)
    try {
      await client.delete('/reset')
      setMessage({ ok: true, text: 'Registry reset successfully' })
    } catch (err) {
      setMessage({ ok: false, text: err.message || 'Reset failed' })
    } finally {
      setShowConfirm(false)
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-4">Reset Registry (Admin)</h2>
      <p className="text-sm text-gray-700 mb-4">This operation will delete all data in the registry. Admins only.</p>
      {message && <div className={message.ok ? 'p-3 bg-green-50 text-green-800 rounded' : 'p-3 bg-red-50 text-red-800 rounded'}>{message.text}</div>}
      <div className="mt-4">
        <button onClick={() => setShowConfirm(true)} className="px-3 py-2 bg-red-700 text-white rounded">Reset Registry</button>
      </div>

      {showConfirm && (
        <Modal title="Confirm Reset" onClose={() => setShowConfirm(false)} actions={(
          <>
            <button onClick={() => setShowConfirm(false)} className="px-3 py-2 bg-gray-200 rounded">Cancel</button>
            <button onClick={doReset} className="px-3 py-2 bg-red-700 text-white rounded">Confirm Reset</button>
          </>
        )}>
          <p className="text-sm">Are you sure you want to DELETE all registry data? This action cannot be undone.</p>
        </Modal>
      )}
    </div>
  )
}
