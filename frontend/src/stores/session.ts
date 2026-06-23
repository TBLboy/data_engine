import { defineStore } from 'pinia'
import type { UserProfile } from '../types/qc'
import { ApiError, fetchSession, login, logout } from '../api/client'

interface SessionState {
  user: UserProfile | null
  isAuthenticated: boolean
  initialized: boolean
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    user: null,
    isAuthenticated: false,
    initialized: false
  }),
  actions: {
    async bootstrap() {
      try {
        const session = await fetchSession()
        this.user = session.user
        this.isAuthenticated = true
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          this.user = null
          this.isAuthenticated = false
        } else {
          throw error
        }
      } finally {
        this.initialized = true
      }
    },
    async signIn(username: string, password: string) {
      const payload = await login({ username, password })
      this.user = payload.user
      this.isAuthenticated = true
      this.initialized = true
    },
    async signOut() {
      await logout()
      this.user = null
      this.isAuthenticated = false
      this.initialized = true
    }
  }
})
