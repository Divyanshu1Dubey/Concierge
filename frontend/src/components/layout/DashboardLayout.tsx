import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { emailsApi } from '@/services/api';
import Sidebar from './Sidebar';
import Header from './Header';
import { useAuthStore } from '@/stores/authStore';
import { api } from '@/utils/api';

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const setUser = useAuthStore((state) => state.setUser);
  const token = useAuthStore((state) => state.token);

  useEffect(() => {
    if (token) {
      api.get('/auth/me/')
        .then((res) => {
          if (res.data) setUser(res.data);
        })
        .catch(() => {});
    }
  }, [token, setUser]);

  // Collect patient email replies in the background while staff have the dashboard open.
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user) as any;
  const hasPractice = Boolean(user?.practice || user?.practice_id);
  useEffect(() => {
    if (!token || !hasPractice) return;
    let stopped = false;
    const check = () => {
      if (stopped || document.hidden) return;
      emailsApi.checkReplies()
        .then((res: any) => {
          if (res?.configured === false) {
            stopped = true; // reply collection is not set up; nothing to poll
            return;
          }
          if (res?.new_replies > 0) {
            toast.success(`${res.new_replies} new patient repl${res.new_replies === 1 ? 'y' : 'ies'} received.`);
            queryClient.invalidateQueries({ queryKey: ['appointment-requests'] });
            queryClient.invalidateQueries({ queryKey: ['appointment-request'] });
          }
        })
        .catch(() => {});
    };
    const first = window.setTimeout(check, 4000);
    const timer = window.setInterval(check, 180000);
    return () => {
      stopped = true;
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [token, hasPractice, queryClient]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="lg:ml-64 flex flex-col min-h-screen">
        <Header onMenuToggle={() => setSidebarOpen(true)} />
        <main className="flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

