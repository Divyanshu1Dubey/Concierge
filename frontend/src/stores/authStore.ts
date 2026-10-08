import { create } from 'zustand';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  activePracticeId: string | null;
  activePracticeName: string | null;
  login: (token: string, user: User) => void;
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

export const useAuthStore = create<AuthState>((set) => ({
  user: getInitialUser(),
  token: localStorage.getItem('auth_token'),
  isAuthenticated: !!localStorage.getItem('auth_token'),
  isLoading: false,
  activePracticeId: localStorage.getItem('active_practice_id'),
  activePracticeName: localStorage.getItem('active_practice_name'),

  login: (token: string, user: User) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true, isLoading: false });
  },

  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    localStorage.removeItem('active_practice_id');
    localStorage.removeItem('active_practice_name');
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
