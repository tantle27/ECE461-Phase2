import React, { createContext, useContext, useState, useCallback } from 'react'
import apiClient from '../lib/apiClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)

  const signIn = useCallback(async (username, password) => {
    // call backend authenticate - backend expects user and secret objects
    try {
      const resp = await apiClient.put('/authenticate', { 
        user: { name: username },
        secret: { password: password }
      }, { skipAuth: true })
      
      // Backend returns token as a JSON string like "bearer t_123456789"
      const tkn = resp.data
      if (!tkn) throw new Error('No token returned')
      
      setToken(tkn)
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
