import { create } from 'zustand';
import type { User } from '../types';
import { API_BASE, REFRESH_KEY, TOKEN_KEY, setSessionExpiredHandler } from '../utils/api';
import { queryClient } from '../queryClient';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  activePracticeId: string | null;
  activePracticeName: string | null;
  login: (token: string, user: User, refresh?: string) => void;
  /** Revokes the refresh token server-side (best effort) and clears local state. */
  logout: () => void;
  setUser: (user: User) => void;
  setLoading: (loading: boolean) => void;
  setActivePractice: (id: string | null, name?: string | null) => void;
}

const getInitialUser = (): User | null => {
  try {
    const saved = localStorage.getItem('auth_user');
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
};

const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem('auth_user');
  localStorage.removeItem('active_practice_id');
  localStorage.removeItem('active_practice_name');
};

export const useAuthStore = create<AuthState>((set) => ({
  user: getInitialUser(),
  token: localStorage.getItem(TOKEN_KEY),
  isAuthenticated: !!localStorage.getItem(TOKEN_KEY),
  isLoading: false,
  activePracticeId: localStorage.getItem('active_practice_id'),
  activePracticeName: localStorage.getItem('active_practice_name'),

  login: (token: string, user: User, refresh?: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true, isLoading: false });
  },

  logout: () => {
    const access = localStorage.getItem(TOKEN_KEY);
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (access && refresh) {
      // Fire-and-forget: local logout must succeed even if the server is unreachable.
      fetch(`${API_BASE}/auth/logout/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
        body: JSON.stringify({ refresh }),
        keepalive: true,
      }).catch(() => undefined);
    }
    clearSession();
    queryClient.clear();
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      activePracticeId: null,
      activePracticeName: null,
    });
  },

  setUser: (user: User) => {
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ user });
  },

  setLoading: (loading: boolean) => {
    set({ isLoading: loading });
  },

  setActivePractice: (id: string | null, name?: string | null) => {
    // Cached data belongs to the previous workspace; never show it under the new one.
    queryClient.clear();
    if (id) {
      localStorage.setItem('active_practice_id', id);
      if (name) localStorage.setItem('active_practice_name', name);
      set({ activePracticeId: id, activePracticeName: name || null });
    } else {
      localStorage.removeItem('active_practice_id');
      localStorage.removeItem('active_practice_name');
      set({ activePracticeId: null, activePracticeName: null });
    }
  },
}));

// Refresh failed / token revoked: drop the session and send the user to login.
setSessionExpiredHandler((reason) => {
  clearSession();
  useAuthStore.setState({ user: null, token: null, isAuthenticated: false, activePracticeId: null, activePracticeName: null });
  if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
    window.location.assign(reason === 'suspended' ? '/login?suspended=1' : '/login?expired=1');
  }
});
