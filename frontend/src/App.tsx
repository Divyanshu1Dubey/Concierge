import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './components/layout/DashboardLayout';
import LoginPage from './components/auth/LoginPage';
import LandingPage from './pages/LandingPage';
import DashboardPage from './pages/DashboardPage';
import PracticesPage from './pages/PracticesPage';
import ConciergePage from './pages/ConciergePage';
import ConversationsPage from './pages/ConversationsPage';
import MessagesPage from './pages/MessagesPage';
import RequestsPage from './pages/RequestsPage';
import RequestDetailPage from './pages/RequestDetailPage';
import RequestReview from './pages/RequestReview';
import PatientsPage from './pages/PatientsPage';
import LeadsPage from './pages/LeadsPage';
import KnowledgePage from './pages/KnowledgePage';
import SettingsPage from './pages/SettingsPage';
import ChatPage from './pages/ChatPage';
import NotFoundPage from './pages/NotFoundPage';
import WidgetPreview from './components/WidgetPreview/WidgetPreview';
import EmailComposerPage from './pages/EmailComposerPage';
import InstallationPage from './pages/InstallationPage';
import WidgetSettingsPage from './pages/WidgetSettingsPage';
import BusinessRulesPage from './pages/BusinessRulesPage';
import EmailSettingsPage from './pages/EmailSettingsPage';
import EmailTemplatesPage from './pages/EmailTemplatesPage';
import TeamPage from './pages/TeamPage';
import SecurityPage from './pages/SecurityPage';
import HostedConciergePage from './pages/HostedConciergePage';
import { useAuthStore } from './stores/authStore';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const RoleRoute = ({
  children,
  allowedRoles,
}: {
  children: React.ReactNode;
  allowedRoles: string[];
}) => {
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);

  if (!token && !localStorage.getItem('auth_token')) {
    return <Navigate to="/login" replace />;
  }

  const currentUser = user || (() => {
    try {
      const saved = localStorage.getItem('auth_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  })();

  if (!currentUser) {
    return <>{children}</>;
  }

  const rawRole = (currentUser.role || '').toUpperCase();
  const normalizedRole = (currentUser.normalized_role || '').toUpperCase();

  const isAgencyAdmin = Boolean(
    currentUser.is_agency_admin ||
    rawRole === 'AGENCY_ADMIN' ||
    normalizedRole === 'AGENCY_ADMIN' ||
    currentUser.is_superuser
  );

  const isPracticeAdmin = Boolean(
    isAgencyAdmin ||
    currentUser.is_practice_admin ||
    ['ADMIN', 'OWNER', 'PRACTICE_ADMIN'].includes(rawRole) ||
    ['ADMIN', 'OWNER', 'PRACTICE_ADMIN'].includes(normalizedRole)
  );

  // Agency admin has platform-wide access
  if (isAgencyAdmin) {
    return <>{children}</>;
  }

  // Practice admin access
  if (allowedRoles.includes('PRACTICE_ADMIN') && isPracticeAdmin) {
    return <>{children}</>;
  }

  // Direct role match
  if (allowedRoles.includes(rawRole) || allowedRoles.includes(normalizedRole)) {
    return <>{children}</>;
  }

  // Redirect unauthorized front-desk staff away from admin sections
  return <Navigate to="/dashboard" replace />;
};

function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/widget" element={<WidgetPreview />} />
      <Route path="/concierge/:slug" element={<HostedConciergePage />} />

      {/* Protected dashboard routes */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        {/* Landing Home View */}
        <Route index element={<DashboardPage />} />

        {/* Agency-Only Practice Management */}
        <Route
          path="practices"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN']}>
              <PracticesPage />
            </RoleRoute>
          }
        />

        {/* Front Desk & Common Operational Workflows */}
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="concierge" element={<ConciergePage />} />
        <Route path="messages" element={<MessagesPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="requests/:id" element={<RequestDetailPage />} />
        <Route path="requests/:id/review" element={<RequestReview />} />
        <Route path="patients" element={<PatientsPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="email" element={<EmailComposerPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />

        {/* Practice Admin & Agency Admin Only: Configuration, Security, Team, Integrations */}
        <Route
          path="team"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <TeamPage />
            </RoleRoute>
          }
        />
        <Route
          path="security"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <SecurityPage />
            </RoleRoute>
          }
        />
        <Route
          path="settings"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <SettingsPage />
            </RoleRoute>
          }
        />
        <Route
          path="widget-settings"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <WidgetSettingsPage />
            </RoleRoute>
          }
        />
        <Route
          path="installation"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <InstallationPage />
            </RoleRoute>
          }
        />
        <Route
          path="business-rules"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <BusinessRulesPage />
            </RoleRoute>
          }
        />
        <Route
          path="email-settings"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <EmailSettingsPage />
            </RoleRoute>
          }
        />
        <Route
          path="templates"
          element={
            <RoleRoute allowedRoles={['AGENCY_ADMIN', 'PRACTICE_ADMIN']}>
              <EmailTemplatesPage />
            </RoleRoute>
          }
        />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default App;
