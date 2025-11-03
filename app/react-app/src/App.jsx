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
  const linkBase = "px-3 py-2 rounded-md transition-colors"

  const { user, signOut } = useAuth()

  return (
  <div className="min-h-screen bg-gray-50 text-gray-900">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header>
        <nav className="bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/80 border-b" aria-label="Main navigation">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="font-semibold text-lg tracking-tight">Model Registry</div>
              <div className="flex gap-1">
                <NavLink to="/" className={({isActive}) => (isActive ? `${linkBase} bg-blue-600 text-white` : `${linkBase} text-gray-700 hover:bg-gray-100`)} aria-current={({isActive}) => isActive ? 'page' : undefined}>Home</NavLink>
                <NavLink to="/artifacts" className={({isActive}) => (isActive ? `${linkBase} bg-blue-600 text-white` : `${linkBase} text-gray-700 hover:bg-gray-100`)} >Artifacts</NavLink>
                <NavLink to="/search" className={({isActive}) => (isActive ? `${linkBase} bg-blue-600 text-white` : `${linkBase} text-gray-700 hover:bg-gray-100`)} >Search</NavLink>
                <NavLink to="/upload" className={({isActive}) => (isActive ? `${linkBase} bg-blue-600 text-white` : `${linkBase} text-gray-700 hover:bg-gray-100`)} >Upload</NavLink>
              </div>
            </div>

            <div className="flex gap-3 items-center">
              {user ? (
                <>
                  <span className="text-sm text-gray-700 hidden sm:inline">{user.username}</span>
                  <button onClick={signOut} className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-md">Sign out</button>
                </>
              ) : (
                <NavLink to="/signin" className={`${linkBase} text-gray-700 hover:bg-gray-100`}>Sign in</NavLink>
              )}
            </div>
          </div>
        </nav>
      </header>

  <main id="main-content" tabIndex={-1} className="max-w-6xl mx-auto p-6">
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
