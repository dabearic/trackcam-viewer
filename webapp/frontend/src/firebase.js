import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onIdTokenChanged } from 'firebase/auth'
import { ref } from 'vue'

const firebaseConfig = {
  apiKey:    "AIzaSyA5CGlWuvCriQPUWk0l4CrER55tFvSz2Vc",
  authDomain: "trackcam-viewer.firebaseapp.com",
  projectId: "trackcam-viewer",
}

// Auth is skipped in local dev (`npm run dev`) and enabled in production builds.
export const AUTH_ENABLED = import.meta.env.PROD

const firebaseApp = initializeApp(firebaseConfig)
const auth        = getAuth(firebaseApp)
const provider    = new GoogleAuthProvider()

export { auth, provider }

export function signInWithGoogle() {
  return signInWithPopup(auth, provider)
}

export function signOutUser() {
  return signOut(auth)
}

/**
 * Authenticated fetch — automatically attaches a fresh Firebase ID token.
 * Falls back to plain fetch when auth is not configured (local dev).
 * The Firebase SDK refreshes the token silently when it is within 5 min of expiry.
 */
export async function apiFetch(url, options = {}) {
  if (!AUTH_ENABLED) return fetch(url, options)
  const user = auth.currentUser
  if (!user) throw new Error('Not authenticated')
  const token = await user.getIdToken()   // auto-refreshes if needed
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  })
}

// Reactive cached token, updated whenever Firebase refreshes it.
// Used to build <img src> URLs since browsers don't attach Authorization headers.
export const idToken = ref(null)

if (AUTH_ENABLED) {
  onIdTokenChanged(auth, async (user) => {
    idToken.value = user ? await user.getIdToken() : null
  })
}

/** Build an /api/image URL that includes the current ID token as a query param. */
export function imageUrl(path) {
  const base = `/api/image?path=${encodeURIComponent(path)}`
  if (!AUTH_ENABLED || !idToken.value) return base
  return `${base}&token=${encodeURIComponent(idToken.value)}`
}

export { onIdTokenChanged }
