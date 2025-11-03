import React, { createContext, useContext, useState, useCallback } from 'react'
import apiClient from '../lib/apiClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)

  const signIn = useCallback(async (username, password) => {
    // call backend authenticate
    try {
      const resp = await apiClient.put('/authenticate', { username, password }, { skipAuth: true })
      const tkn = resp.data?.token
      if (!tkn) throw new Error('No token returned')
      setToken(tkn)
      // Optionally fetch user info
      setUser({ username })
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err }
    }
  }, [])

  const signOut = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  // Provide an axios instance configured with the current token
  const client = apiClient.createInstance(token)

  return (
    <AuthContext.Provider value={{ token, user, signIn, signOut, client }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

export default AuthContext
