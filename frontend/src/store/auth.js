/**
 * store/auth.js
 * Global auth state using Zustand.
 *
 * WHY MEMORY STORAGE?
 *   localStorage is vulnerable to XSS — any injected script can steal the token.
 *   We store the access token in JS memory (Zustand state) instead.
 *   On page refresh it's gone — but the httpOnly refresh cookie silently gets
 *   a new access token via /api/auth/refresh, so the user stays logged in.
 */
import { create } from 'zustand'

export const useAuthStore = create((set, get) => ({
  // Access token in memory — never persisted to localStorage
  accessToken: null,
  user: null,
  isLoading: true,   // true while checking session on app load

  setAccessToken: (token) => set({ accessToken: token }),

  setUser: (user) => set({ user }),

  login: (token, user) => set({ accessToken: token, user, isLoading: false }),

  logout: () => set({ accessToken: null, user: null, isLoading: false }),

  setLoading: (isLoading) => set({ isLoading }),

  // Helpers
  isAuthenticated: () => !!get().accessToken,
  isPro: () => ['pro', 'team'].includes(get().user?.plan),
  isTeam: () => get().user?.plan === 'team',
}))
