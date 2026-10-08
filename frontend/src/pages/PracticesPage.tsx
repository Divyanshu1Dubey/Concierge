import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { practicesApi } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import {
  Building2,
  Plus,
  Search,
  CheckCircle2,
  XCircle,
  Users,
  MessageSquare,
  Calendar,
  ExternalLink,
  Shield,
  Phone,
  Mail,
  MapPin,
  RefreshCw,
  Power,
  Code,
  Download,
  Copy,
  Check,
  Key,
  ArrowRight,
  UserPlus,
  Layers,
  UserCheck,
  UserX,
  Stethoscope,
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function PracticesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activePracticeId, activePracticeName, setActivePractice } = useAuthStore();

  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Modals for selected dentistry
  const [selectedStaffPractice, setSelectedStaffPractice] = useState<any | null>(null);
  const [selectedIntegrationPractice, setSelectedIntegrationPractice] = useState<any | null>(null);

  // New practice form
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('919-555-0100');
  const [address, setAddress] = useState('100 Medical Park Blvd');
  const [city, setCity] = useState('Raleigh');
  const [state, setState] = useState('NC');
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('Password123!');

  // New staff / doctor form
  const [newStaffFirstName, setNewStaffFirstName] = useState('');
  const [newStaffLastName, setNewStaffLastName] = useState('');
  const [newStaffEmail, setNewStaffEmail] = useState('');
  const [newStaffPassword, setNewStaffPassword] = useState('DoctorPass123!');
  const [newStaffRole, setNewStaffRole] = useState<'PRACTICE_ADMIN' | 'FRONT_DESK'>('PRACTICE_ADMIN');
  const [newStaffPhone, setNewStaffPhone] = useState('');

  // Reset password state
  const [resetTargetUser, setResetTargetUser] = useState<any | null>(null);
  const [newResetPassword, setNewResetPassword] = useState('NewPass123!');

  // Copy feedback state
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSnippet(label);
    toast.success(`${label} copied to clipboard!`);
    setTimeout(() => setCopiedSnippet(null), 2500);
  };

  // Queries
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['agency-practices'],
    queryFn: () => practicesApi.listAll(),
  });

  const practices = data?.results ?? data ?? [];
  const filtered = practices.filter((p: any) =>
    (p.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (p.email || '').toLowerCase().includes(search.toLowerCase()) ||
    (p.city || '').toLowerCase().includes(search.toLowerCase())
  );

  // Query for staff of selected dentistry
  const {
    data: staffData,
    isLoading: staffLoading,
    refetch: refetchStaff,
  } = useQuery({
    queryKey: ['practice-users', selectedStaffPractice?.id],
    queryFn: () => practicesApi.getPracticeUsers(selectedStaffPractice.id),
    enabled: !!selectedStaffPractice?.id,
  });

  // Query for integration data of selected dentistry
  const {
    data: integrationData,
    isLoading: integrationLoading,
  } = useQuery({
    queryKey: ['practice-integration', selectedIntegrationPractice?.id],
    queryFn: () => practicesApi.getPracticeIntegration(selectedIntegrationPractice.id),
    enabled: !!selectedIntegrationPractice?.id,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (newPractice: any) => practicesApi.createPractice(newPractice),
    onSuccess: (res: any) => {
      toast.success(`Practice "${res.name || name}" onboarded successfully!`);
      setShowCreateModal(false);
      setName('');
      setEmail('');
      setAdminName('');
      setAdminEmail('');
      queryClient.invalidateQueries({ queryKey: ['agency-practices'] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error || 'Failed to onboard practice');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (id: number | string) => practicesApi.toggleStatus(id),
    onSuccess: (res: any) => {
      toast.success(`Practice status updated to ${res.active ? 'Active' : 'Disabled'}`);
      queryClient.invalidateQueries({ queryKey: ['agency-practices'] });
    },
    onError: () => {
      toast.error('Failed to change status');
    },
  });

  const addStaffMutation = useMutation({
    mutationFn: (payload: any) =>
      practicesApi.addPracticeUser(selectedStaffPractice.id, payload),
    onSuccess: (res: any) => {
      toast.success(res.message || 'Staff member added successfully!');
      setNewStaffEmail('');
      setNewStaffFirstName('');
      setNewStaffLastName('');
      setNewStaffPhone('');
      setNewStaffPassword('DoctorPass123!');
      refetchStaff();
      queryClient.invalidateQueries({ queryKey: ['agency-practices'] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error || 'Failed to add staff member');
    },
  });

  const staffActionMutation = useMutation({
    mutationFn: ({ userId, action, payload }: { userId: string; action: string; payload?: any }) =>
      practicesApi.practiceUserAction(selectedStaffPractice.id, userId, action, payload),
    onSuccess: (res: any) => {
      toast.success(res.message || 'Staff member updated successfully');
      setResetTargetUser(null);
      refetchStaff();
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error || 'Failed to update user');
    },
  });

  const deleteStaffMutation = useMutation({
    mutationFn: (userId: string) =>
      practicesApi.deletePracticeUser(selectedStaffPractice.id, userId),
    onSuccess: () => {
      toast.success('User deactivated successfully');
      refetchStaff();
      queryClient.invalidateQueries({ queryKey: ['agency-practices'] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error || 'Failed to deactivate user');
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim()) {
      toast.error('Please enter practice name and email');
      return;
    }
    createMutation.mutate({
      name,
      email,
      phone,
      address,
      city,
      state,
      admin_name: adminName,
      admin_email: adminEmail,
      admin_password: adminPassword,
    });
  };

  const handleAddStaffSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStaffEmail.trim() || !newStaffPassword.trim()) {
      toast.error('Email ID and password are required');
      return;
    }
    addStaffMutation.mutate({
      email: newStaffEmail.trim(),
      password: newStaffPassword.trim(),
      role: newStaffRole,
      first_name: newStaffFirstName.trim(),
      last_name: newStaffLastName.trim(),
      phone: newStaffPhone.trim(),
    });
  };

  const handleSwitchWorkspace = (practice: any) => {
    setActivePractice(practice.id.toString(), practice.name);
    toast.success(`Switched workspace to ${practice.name}`);
    navigate('/dashboard');
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Active Practice Alert Banner */}
      {activePracticeId && (
        <div className="bg-gradient-to-r from-purple-900 to-indigo-900 text-white rounded-2xl p-4 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/30 border border-purple-400/40 flex items-center justify-center flex-shrink-0">
              <Layers className="w-5 h-5 text-purple-200" />
            </div>
            <div>
              <p className="text-xs font-semibold text-purple-200 uppercase tracking-wider">
                Currently Managing Dentistry Workspace
              </p>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                {activePracticeName || 'Selected Dentistry'}
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-500/40 text-purple-100">
                  ID: {activePracticeId}
                </span>
              </h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-3.5 py-1.5 rounded-xl bg-white text-purple-950 font-bold text-xs hover:bg-purple-50 shadow-sm transition flex items-center gap-1.5"
            >
              Go to Workspace Dashboard <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => {
                setActivePractice(null, null);
                toast.success('Switched back to Global Agency View');
              }}
              className="px-3 py-1.5 rounded-xl bg-purple-800/80 hover:bg-purple-700/80 text-purple-200 font-semibold text-xs transition"
            >
              Reset to All Practices
            </button>
          </div>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 flex items-center gap-1">
              <Shield className="w-3 h-3" /> Agency Administration
            </span>
            <span className="text-xs text-gray-500 font-medium">Multi-Dentistry Control Hub</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">Dental Practices & Doctors</h1>
          <p className="text-sm text-gray-500">
            Create IDs and passwords for dentists and front-desk staff, configure website embeds, and manage multi-tenant clinic portals.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="p-2 border border-gray-200 rounded-xl hover:bg-gray-50 text-gray-600 transition"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Onboard Practice
          </button>
        </div>
      </div>

      {/* Overview Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Practices</span>
            <Building2 className="w-5 h-5 text-teal-600" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">{practices.length}</p>
          <p className="text-xs text-teal-600 font-medium mt-1">
            {practices.filter((p: any) => p.active).length} Active accounts
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Doctors & Staff</span>
            <Users className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {practices.reduce((sum: number, p: any) => sum + (p.staff_count || 0), 0)}
          </p>
          <p className="text-xs text-gray-500 mt-1">Dentists & front-desk users</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">AI Conversations</span>
            <MessageSquare className="w-5 h-5 text-purple-600" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {practices.reduce((sum: number, p: any) => sum + (p.conversation_count || 0), 0)}
          </p>
          <p className="text-xs text-purple-600 font-medium mt-1">Platform-wide triage</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Patient Inquiries</span>
            <Calendar className="w-5 h-5 text-emerald-600" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {practices.reduce((sum: number, p: any) => sum + (p.appointment_count || 0), 0)}
          </p>
          <p className="text-xs text-emerald-600 font-medium mt-1">Captured leads & appointments</p>
        </div>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-2xl border border-gray-200 shadow-sm flex items-center gap-3">
        <Search className="w-4 h-4 text-gray-400 ml-1" />
        <input
          type="text"
          placeholder="Search practices by name, email, or city..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full text-sm outline-none bg-transparent placeholder-gray-400"
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 bg-gray-100 rounded-md"
          >
            Clear
          </button>
        )}
      </div>

      {/* Practice Directory List */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-gray-500 text-sm">Loading practices...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-base font-semibold text-gray-900">No practices found</p>
            <p className="text-sm text-gray-500 mt-1">
              {search ? 'Try adjusting your search criteria.' : 'Click "Onboard Practice" above to add your first clinic.'}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filtered.map((practice: any) => {
              const isCurrentActive = activePracticeId === practice.id?.toString();

              return (
                <div
                  key={practice.id}
                  className={`p-5 transition-colors flex flex-col xl:flex-row xl:items-center justify-between gap-5 ${
                    isCurrentActive ? 'bg-purple-50/50 hover:bg-purple-50/80 border-l-4 border-l-purple-600' : 'hover:bg-gray-50/80'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-600 text-white flex items-center justify-center flex-shrink-0 font-black text-lg shadow-sm">
                      {practice.name.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-base font-bold text-gray-900">{practice.name}</h3>
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                            practice.active
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-red-100 text-red-700'
                          }`}
                        >
                          {practice.active ? (
                            <>
                              <CheckCircle2 className="w-3 h-3" /> Active
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3 h-3" /> Disabled
                            </>
                          )}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600 font-mono">
                          slug: {practice.slug}
                        </span>
                        {isCurrentActive && (
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 font-bold flex items-center gap-1">
                            <Layers className="w-3 h-3" /> Current Active Workspace
                          </span>
                        )}
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-y-1 gap-x-4 mt-2 text-xs text-gray-500">
                        <span className="flex items-center gap-1.5">
                          <Mail className="w-3.5 h-3.5 text-gray-400" />
                          {practice.email}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <Phone className="w-3.5 h-3.5 text-gray-400" />
                          {practice.phone}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <MapPin className="w-3.5 h-3.5 text-gray-400" />
                          {practice.city}, {practice.state}
                        </span>
                      </div>

                      <div className="flex items-center gap-4 mt-3 text-xs text-gray-600 font-medium">
                        <span>
                          Admin: <strong className="text-gray-900">{practice.admin_name || 'Dr. Administrator'}</strong>
                        </span>
                        <span>•</span>
                        <span>
                          Doctors & Staff: <strong className="text-gray-900">{practice.staff_count || 1}</strong>
                        </span>
                        <span>•</span>
                        <span>
                          Inquiries: <strong className="text-gray-900">{practice.appointment_count || 0}</strong>
                        </span>
                        <span>•</span>
                        <span className="font-mono text-gray-400">
                          Key: {practice.client_key ? `${practice.client_key.substring(0, 8)}...` : 'Pre-generated'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Practice Action Buttons */}
                  <div className="flex items-center gap-2 flex-wrap self-start xl:self-center">
                    {/* Manage Doctors & Staff Button */}
                    <button
                      onClick={() => setSelectedStaffPractice(practice)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 transition shadow-sm"
                      title="Add doctors, create passwords, and manage clinic staff"
                    >
                      <Users className="w-3.5 h-3.5" />
                      Manage Doctors & Staff
                    </button>

                    {/* How to Embed in Website Button */}
                    <button
                      onClick={() => setSelectedIntegrationPractice(practice)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border border-teal-200 bg-teal-50 text-teal-800 hover:bg-teal-100 transition shadow-sm"
                      title="Website embed codes, WordPress plugin, and widget instructions"
                    >
                      <Code className="w-3.5 h-3.5" />
                      Website Embed
                    </button>

                    {/* Switch Workspace Button */}
                    <button
                      onClick={() => handleSwitchWorkspace(practice)}
                      className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition shadow-sm ${
                        isCurrentActive
                          ? 'bg-purple-900 text-white hover:bg-purple-800'
                          : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-100'
                      }`}
                      title="Switch to this dentistry's workspace context to edit settings, hours, templates"
                    >
                      <Layers className="w-3.5 h-3.5 text-purple-500" />
                      {isCurrentActive ? 'Active Workspace' : 'Switch Workspace'}
                    </button>

                    {/* Live Concierge External Link */}
                    <a
                      href={`/concierge/${practice.slug}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-2 border border-gray-200 hover:bg-gray-100 text-gray-600 rounded-xl text-xs font-semibold transition"
                      title="View live patient-facing AI Concierge page"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Live Concierge
                    </a>

                    {/* Enable / Disable Button */}
                    <button
                      onClick={() => toggleMutation.mutate(practice.id)}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-2 rounded-xl text-xs font-semibold border transition ${
                        practice.active
                          ? 'border-gray-200 text-gray-500 hover:bg-gray-100'
                          : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                      }`}
                      title={practice.active ? 'Disable this practice' : 'Enable this practice'}
                    >
                      <Power className="w-3.5 h-3.5" />
                      {practice.active ? 'Disable' : 'Enable'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ────────────────────────────────────────────────────────────────────────── */}
      {/* MODAL 1: Manage Doctors & Staff (Create ID/Password for Dentistry Staff)   */}
      {/* ────────────────────────────────────────────────────────────────────────── */}
      {selectedStaffPractice && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-5 border-b border-gray-200 bg-slate-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-300 font-bold">
                  <Stethoscope className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase font-extrabold tracking-wider text-blue-400">
                      Dentistry Staff & Credentials Management
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-blue-900/60 text-blue-200 font-mono">
                      {selectedStaffPractice.slug}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-white mt-0.5">{selectedStaffPractice.name}</h3>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedStaffPractice(null);
                  setResetTargetUser(null);
                }}
                className="w-8 h-8 rounded-lg hover:bg-slate-800 flex items-center justify-center text-gray-400 hover:text-white text-lg transition"
              >
                ×
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Doctor / Staff Creation Form Box */}
              <div className="bg-gradient-to-br from-blue-50/70 to-indigo-50/70 border border-blue-200/80 rounded-2xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <UserPlus className="w-4 h-4 text-blue-600" />
                    <h4 className="text-sm font-bold text-gray-900">
                      Add New Doctor / Front Desk User (Set ID & Password)
                    </h4>
                  </div>
                  <span className="text-xs text-gray-500">Assigns credentials directly to this practice</span>
                </div>

                <form onSubmit={handleAddStaffSubmit} className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        First Name
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Dr. Jane"
                        value={newStaffFirstName}
                        onChange={(e) => setNewStaffFirstName(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        Last Name
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Smith, DDS"
                        value={newStaffLastName}
                        onChange={(e) => setNewStaffLastName(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        Role & Permissions *
                      </label>
                      <select
                        value={newStaffRole}
                        onChange={(e) => setNewStaffRole(e.target.value as any)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none font-medium"
                      >
                        <option value="PRACTICE_ADMIN">Doctor / Dentist (Practice Admin)</option>
                        <option value="FRONT_DESK">Front Desk Coordinator</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        Login ID / Email *
                      </label>
                      <input
                        type="email"
                        required
                        placeholder="doctor@dentistry.com"
                        value={newStaffEmail}
                        onChange={(e) => setNewStaffEmail(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        Initial Password *
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          required
                          value={newStaffPassword}
                          onChange={(e) => setNewStaffPassword(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                        Phone (Optional)
                      </label>
                      <input
                        type="text"
                        placeholder="919-555-0144"
                        value={newStaffPhone}
                        onChange={(e) => setNewStaffPhone(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      type="submit"
                      disabled={addStaffMutation.isPending}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold shadow-sm transition disabled:opacity-50 flex items-center gap-1.5"
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                      {addStaffMutation.isPending ? 'Creating Account...' : 'Create Credentials & Add User'}
                    </button>
                  </div>
                </form>
              </div>

              {/* Password Reset Sub-panel (if active) */}
              {resetTargetUser && (
                <div className="p-4 bg-amber-50 border border-amber-300 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in">
                  <div className="flex items-center gap-3">
                    <Key className="w-5 h-5 text-amber-600 flex-shrink-0" />
                    <div>
                      <p className="text-xs font-bold text-amber-900">
                        Reset Password for {resetTargetUser.full_name || resetTargetUser.email}
                      </p>
                      <p className="text-[11px] text-amber-700">Enter a new secure password for this user account.</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <input
                      type="text"
                      value={newResetPassword}
                      onChange={(e) => setNewResetPassword(e.target.value)}
                      className="px-3 py-1.5 border border-amber-300 rounded-xl text-xs font-mono bg-white focus:outline-none focus:ring-2 focus:ring-amber-500 w-44"
                      placeholder="New password"
                    />
                    <button
                      onClick={() =>
                        staffActionMutation.mutate({
                          userId: resetTargetUser.id,
                          action: 'reset_password',
                          payload: { password: newResetPassword },
                        })
                      }
                      disabled={staffActionMutation.isPending || !newResetPassword}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold transition disabled:opacity-50"
                    >
                      Save Password
                    </button>
                    <button
                      onClick={() => setResetTargetUser(null)}
                      className="px-2.5 py-1.5 border border-amber-200 text-amber-800 rounded-xl text-xs font-medium hover:bg-amber-100/50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Existing Staff Table */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    <Users className="w-4 h-4 text-gray-600" />
                    Doctors & Staff Members in this Practice ({staffData?.count || 0})
                  </h4>
                  <button
                    onClick={() => refetchStaff()}
                    className="text-xs text-gray-500 hover:text-gray-800 flex items-center gap-1 font-medium"
                  >
                    <RefreshCw className="w-3 h-3" /> Refresh Staff
                  </button>
                </div>

                <div className="border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
                  {staffLoading ? (
                    <div className="p-8 text-center text-xs text-gray-500">Loading practice staff...</div>
                  ) : !staffData?.results || staffData.results.length === 0 ? (
                    <div className="p-8 text-center text-xs text-gray-500">
                      No staff accounts found. Use the form above to add doctors or front-desk staff.
                    </div>
                  ) : (
                    <table className="w-full text-left text-xs">
                      <thead className="bg-gray-50/80 border-b border-gray-200 text-gray-600 font-bold uppercase tracking-wider">
                        <tr>
                          <th className="py-3 px-4">User / Doctor</th>
                          <th className="py-3 px-4">Login Email (ID)</th>
                          <th className="py-3 px-4">Role</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4">Phone</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {staffData.results.map((u: any) => (
                          <tr key={u.id} className="hover:bg-gray-50/60 transition">
                            <td className="py-3 px-4 font-bold text-gray-900">
                              <div className="flex items-center gap-2.5">
                                <div className="w-7 h-7 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center font-extrabold text-slate-700 text-xs">
                                  {u.first_name ? u.first_name.charAt(0) : u.email.charAt(0).toUpperCase()}
                                </div>
                                <span>{u.full_name || 'Staff User'}</span>
                              </div>
                            </td>
                            <td className="py-3 px-4 font-mono text-gray-600">{u.email}</td>
                            <td className="py-3 px-4">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-bold text-[11px] ${
                                  ['PRACTICE_ADMIN', 'ADMIN', 'OWNER'].includes(u.role)
                                    ? 'bg-purple-100 text-purple-800'
                                    : 'bg-blue-100 text-blue-800'
                                }`}
                              >
                                {['PRACTICE_ADMIN', 'ADMIN', 'OWNER'].includes(u.role)
                                  ? 'Doctor / Admin'
                                  : 'Front Desk'}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-bold text-[10px] ${
                                  u.is_active
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-red-100 text-red-800'
                                }`}
                              >
                                {u.is_active ? <UserCheck className="w-3 h-3" /> : <UserX className="w-3 h-3" />}
                                {u.is_active ? 'Active' : 'Disabled'}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-gray-500">{u.phone || '—'}</td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => {
                                    setResetTargetUser(u);
                                    setNewResetPassword('DoctorPass2026!');
                                  }}
                                  className="px-2 py-1 rounded-lg border border-gray-200 hover:bg-gray-100 text-gray-700 font-semibold text-[11px] flex items-center gap-1 transition"
                                  title="Reset password"
                                >
                                  <Key className="w-3 h-3 text-amber-600" /> Reset Password
                                </button>
                                <button
                                  onClick={() =>
                                    staffActionMutation.mutate({
                                      userId: u.id,
                                      action: 'toggle_status',
                                    })
                                  }
                                  className={`px-2 py-1 rounded-lg border text-[11px] font-semibold transition ${
                                    u.is_active
                                      ? 'border-gray-200 text-gray-600 hover:bg-gray-100'
                                      : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                  }`}
                                  title={u.is_active ? 'Disable account' : 'Enable account'}
                                >
                                  {u.is_active ? 'Disable' : 'Enable'}
                                </button>
                                <button
                                  onClick={() => {
                                    if (confirm(`Are you sure you want to deactivate ${u.email}?`)) {
                                      deleteStaffMutation.mutate(u.id);
                                    }
                                  }}
                                  className="px-2 py-1 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 text-[11px] font-semibold transition"
                                  title="Deactivate account"
                                >
                                  Remove
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-end">
              <button
                onClick={() => {
                  setSelectedStaffPractice(null);
                  setResetTargetUser(null);
                }}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-sm"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────────── */}
      {/* MODAL 2: Website Embed & Integration (How to embed in website)             */}
      {/* ────────────────────────────────────────────────────────────────────────── */}
      {selectedIntegrationPractice && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-5 border-b border-gray-200 bg-slate-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-teal-500/20 border border-teal-400/30 flex items-center justify-center text-teal-300 font-bold">
                  <Code className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase font-extrabold tracking-wider text-teal-400">
                      Website Embed & Integration Hub
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-teal-900/60 text-teal-200 font-mono">
                      {selectedIntegrationPractice.slug}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-white mt-0.5">{selectedIntegrationPractice.name}</h3>
                </div>
              </div>
              <button
                onClick={() => setSelectedIntegrationPractice(null)}
                className="w-8 h-8 rounded-lg hover:bg-slate-800 flex items-center justify-center text-gray-400 hover:text-white text-lg transition"
              >
                ×
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {integrationLoading ? (
                <div className="p-12 text-center text-sm text-gray-500">Loading embed credentials...</div>
              ) : (
                <>
                  {/* Credentials Strip */}
                  <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    <div>
                      <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                        Dentistry Public Client Key
                      </span>
                      <p className="font-mono text-xs font-bold text-slate-900 mt-0.5 select-all">
                        {integrationData?.client_key || selectedIntegrationPractice.client_key || 'Pre-configured'}
                      </p>
                    </div>
                    <button
                      onClick={() =>
                        handleCopy(
                          integrationData?.client_key || selectedIntegrationPractice.client_key,
                          'Client Key'
                        )
                      }
                      className="px-3 py-1.5 border border-gray-200 rounded-xl bg-white hover:bg-gray-100 text-xs font-bold text-gray-700 flex items-center gap-1.5 shadow-sm transition"
                    >
                      {copiedSnippet === 'Client Key' ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Copy className="w-3.5 h-3.5" />}
                      Copy Key
                    </button>
                  </div>

                  {/* Option 1: WordPress 1-Click Plugin Download */}
                  <div className="border border-teal-200 rounded-2xl p-5 bg-gradient-to-br from-teal-50/60 to-emerald-50/60 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-teal-200 text-teal-900 uppercase">
                            Recommended for WordPress
                          </span>
                          <h4 className="text-sm font-bold text-gray-900">1-Click WordPress Plugin</h4>
                        </div>
                        <p className="text-xs text-gray-600 mt-1 max-w-xl">
                          Pre-packaged WordPress plugin configured specifically for <strong>{selectedIntegrationPractice.name}</strong>.
                          Includes automated bubble script injection, admin settings page, and client key validation.
                        </p>
                      </div>

                      <a
                        href={practicesApi.getWordPressPluginUrl(selectedIntegrationPractice.id)}
                        download
                        className="px-4 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-xs font-bold shadow-sm transition flex items-center gap-2 flex-shrink-0"
                      >
                        <Download className="w-4 h-4" />
                        Download Plugin (.zip)
                      </a>
                    </div>

                    <div className="mt-4 pt-3 border-t border-teal-200/80 text-xs text-gray-600">
                      <p className="font-bold text-gray-800 mb-1">WordPress Installation Steps:</p>
                      <ol className="list-decimal list-inside space-y-1 text-[11px] text-gray-600">
                        <li>Download the plugin ZIP file using the button above.</li>
                        <li>In the WordPress Admin Dashboard, navigate to <strong>Plugins &gt; Add New &gt; Upload Plugin</strong>.</li>
                        <li>Choose the downloaded ZIP file and click <strong>Install Now</strong>.</li>
                        <li>Click <strong>Activate Plugin</strong>. The HeyJarvis Concierge will immediately appear on the dental website!</li>
                      </ol>
                    </div>
                  </div>

                  {/* Option 2: 1-Line JavaScript Script Tag */}
                  <div className="border border-gray-200 rounded-2xl p-5 bg-white shadow-sm">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <h4 className="text-sm font-bold text-gray-900">
                          1-Line HTML Script Tag (Squarespace, Wix, Webflow, Shopify, Custom HTML)
                        </h4>
                        <p className="text-xs text-gray-500">
                          Paste this single tag before the closing <code className="bg-gray-100 px-1 rounded">&lt;/body&gt;</code> tag on any dental website.
                        </p>
                      </div>
                      <button
                        onClick={() => handleCopy(integrationData?.embed_script || '', 'Script Tag')}
                        className="px-3 py-1.5 border border-gray-200 rounded-xl bg-gray-50 hover:bg-gray-100 text-xs font-bold text-gray-700 flex items-center gap-1.5 transition"
                      >
                        {copiedSnippet === 'Script Tag' ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Script
                      </button>
                    </div>

                    <div className="bg-slate-900 text-emerald-400 p-3.5 rounded-xl font-mono text-xs overflow-x-auto border border-slate-800">
                      <code>{integrationData?.embed_script || 'Loading snippet...'}</code>
                    </div>

                    {/* Platform guides */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
                      <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                        <p className="font-bold text-gray-900 text-xs">Squarespace</p>
                        <p className="text-[11px] text-gray-500 mt-1">
                          Go to <strong>Settings &gt; Advanced &gt; Code Injection</strong> and paste into <strong>Footer</strong>.
                        </p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                        <p className="font-bold text-gray-900 text-xs">Wix</p>
                        <p className="text-[11px] text-gray-500 mt-1">
                          Go to <strong>Settings &gt; Custom Code</strong>, paste snippet, and set placement to <strong>Body - End</strong>.
                        </p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-xl border border-gray-100">
                        <p className="font-bold text-gray-900 text-xs">Webflow / Custom HTML</p>
                        <p className="text-[11px] text-gray-500 mt-1">
                          Paste into <strong>Project Settings &gt; Custom Code &gt; Footer Code</strong> before <code className="text-[10px]">&lt;/body&gt;</code>.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Option 3: Full Page iFrame */}
                  <div className="border border-gray-200 rounded-2xl p-5 bg-white shadow-sm">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <h4 className="text-sm font-bold text-gray-900">Embedded iFrame Container</h4>
                        <p className="text-xs text-gray-500">
                          Embed the full 24/7 AI Concierge inside a dedicated "Book Online" page or modal.
                        </p>
                      </div>
                      <button
                        onClick={() => handleCopy(integrationData?.iframe_snippet || '', 'iFrame Snippet')}
                        className="px-3 py-1.5 border border-gray-200 rounded-xl bg-gray-50 hover:bg-gray-100 text-xs font-bold text-gray-700 flex items-center gap-1.5 transition"
                      >
                        {copiedSnippet === 'iFrame Snippet' ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy iFrame
                      </button>
                    </div>

                    <div className="bg-slate-900 text-emerald-400 p-3.5 rounded-xl font-mono text-xs overflow-x-auto border border-slate-800">
                      <code>{integrationData?.iframe_snippet || 'Loading snippet...'}</code>
                    </div>
                  </div>

                  {/* Option 4: Hosted Patient Concierge Link */}
                  <div className="border border-gray-200 rounded-2xl p-5 bg-white shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-bold text-gray-900">Hosted Concierge Direct Link</h4>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Standalone patient portal URL for SMS recalls, QR codes on clinic brochures, or Google Business buttons.
                      </p>
                      <p className="font-mono text-xs font-bold text-teal-700 mt-1">
                        {integrationData?.hosted_concierge_url || `/concierge/${selectedIntegrationPractice.slug}`}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() =>
                          handleCopy(
                            integrationData?.hosted_concierge_url || `${window.location.origin}/concierge/${selectedIntegrationPractice.slug}`,
                            'Hosted URL'
                          )
                        }
                        className="px-3 py-2 border border-gray-200 rounded-xl bg-white hover:bg-gray-100 text-xs font-bold text-gray-700 flex items-center gap-1.5 shadow-sm transition"
                      >
                        {copiedSnippet === 'Hosted URL' ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Link
                      </button>
                      <a
                        href={integrationData?.hosted_concierge_url || `/concierge/${selectedIntegrationPractice.slug}`}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold shadow-sm transition flex items-center gap-1.5"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Open Concierge
                      </a>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-end">
              <button
                onClick={() => setSelectedIntegrationPractice(null)}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────────── */}
      {/* MODAL 3: Onboard New Practice                                              */}
      {/* ────────────────────────────────────────────────────────────────────────── */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Onboard New Practice</h3>
                <p className="text-xs text-gray-500">Create an isolated tenant practice and assign its practice administrator.</p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-500"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Practice / Clinic Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Pine Valley Dental Care"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                    Clinic Email *
                  </label>
                  <input
                    type="email"
                    required
                    placeholder="contact@pinevalleydental.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                    Phone Number
                  </label>
                  <input
                    type="text"
                    placeholder="919-555-0199"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Street Address
                </label>
                <input
                  type="text"
                  placeholder="100 Medical Park Blvd"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                    State
                  </label>
                  <input
                    type="text"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="border-t border-gray-200 pt-4 mt-2">
                <h4 className="text-xs font-black text-gray-900 uppercase tracking-wider mb-3">
                  Assign Practice Administrator / Dentist
                </h4>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Doctor / Practice Admin Full Name
                    </label>
                    <input
                      type="text"
                      placeholder="Dr. Michael Vance, DDS"
                      value={adminName}
                      onChange={(e) => setAdminName(e.target.value)}
                      className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        Admin Login Email
                      </label>
                      <input
                        type="email"
                        placeholder="doctor@pinevalleydental.com"
                        value={adminEmail}
                        onChange={(e) => setAdminEmail(e.target.value)}
                        className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        Initial Password
                      </label>
                      <input
                        type="text"
                        value={adminPassword}
                        onChange={(e) => setAdminPassword(e.target.value)}
                        className="w-full px-3.5 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-teal-500 focus:outline-none font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-5 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold shadow-sm transition disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Onboarding...' : 'Onboard Practice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
