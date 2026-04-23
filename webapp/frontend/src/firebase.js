import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onIdTokenChanged } from 'firebase/auth'

// Fill these in after running `terraform apply` (see SETUP.md step 8).
// Leave as-is for local development — auth will be skipped automatically.
const firebaseConfig = {
  apiKey:    "REPLACE_WITH_YOUR_API_KEY",
  authDomain: "trackcam-viewer.firebaseapp.com",
  projectId: "trackcam-viewer",
}

/** True only when real Firebase credentials have been configured. */
export const AUTH_ENABLED = firebaseConfig.apiKey !== "REPLACE_WITH_YOUR_API_KEY"

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

export { onIdTokenChanged }
