import React from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import Home from './pages/Home'
import Upload from './pages/Upload'
import Search from './pages/Search'
import Artifacts from './pages/Artifacts'
import Tracks from './pages/Tracks'
import Reset from './pages/Reset'
import SignIn from './pages/SignIn'
import { useAuth } from './context/AuthContext'
import AuthRequired from './components/AuthRequired'

export default function App() {
  const linkBase = "px-2 py-1 rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"

  const { user, signOut } = useAuth()

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header>
        <nav className="bg-white shadow" aria-label="Main navigation">
          <div className="max-w-4xl mx-auto px-4 py-4 flex gap-4 items-center justify-between">
            <div className="flex gap-4 items-center">
              <NavLink to="/" className={({isActive}) => (isActive ? `${linkBase} font-bold` : `${linkBase} text-sm text-gray-700`)} aria-current={({isActive}) => isActive ? 'page' : undefined}>Home</NavLink>
              <NavLink to="/artifacts" className={({isActive}) => (isActive ? `${linkBase} font-bold` : `${linkBase} text-sm text-gray-700`)} >Artifacts</NavLink>
              <NavLink to="/info/tracks" className={({isActive}) => (isActive ? `${linkBase} font-bold` : `${linkBase} text-sm text-gray-700`)} >Info</NavLink>
            </div>

            <div className="flex gap-3 items-center">
              {user ? (
                <>
                  <span className="text-sm text-gray-700">Signed in: {user.username}</span>
                  <button onClick={signOut} className="px-2 py-1 bg-gray-200 rounded">Sign out</button>
                </>
              ) : (
                <NavLink to="/signin" className={`${linkBase} text-sm text-gray-700`}>Sign in</NavLink>
              )}
            </div>
          </div>
        </nav>
      </header>

      <main id="main-content" tabIndex={-1} className="max-w-4xl mx-auto p-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/upload" element={<AuthRequired><Upload /></AuthRequired>} />
          <Route path="/search" element={<AuthRequired><Search /></AuthRequired>} />
          <Route path="/artifacts" element={<AuthRequired><Artifacts /></AuthRequired>} />
          <Route path="/info/tracks" element={<Tracks />} />
          <Route path="/info/reset" element={<AuthRequired><Reset /></AuthRequired>} />
          <Route path="/signin" element={<SignIn />} />
        </Routes>
      </main>
    </div>
  )
}
