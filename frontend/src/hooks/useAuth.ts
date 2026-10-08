import { useState, useEffect } from 'react';
import type { User } from '@/types';

const API_URL = 'http://localhost:8000';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('auth_user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem('auth_user');
      }
    }
    setLoading(false);
  }, []);

  const login = async (email: string, password: string): Promise<User> => {
    const res = await fetch(`${API_URL}/api/auth/token/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'Login failed');
    }

    const { access } = await res.json();
    localStorage.setItem('auth_token', access);

    const userRes = await fetch(`${API_URL}/api/users/me/`, {
      headers: { Authorization: `Bearer ${access}` },
    });

    if (!userRes.ok) throw new Error('Failed to fetch user');
    const userData: User = await userRes.json();
    localStorage.setItem('auth_user', JSON.stringify(userData));
    setUser(userData);
    return userData;
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    setUser(null);
  };

  return { user, login, logout, loading };
}
