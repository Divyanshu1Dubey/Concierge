export interface Lead {
  id: number;
  tenant_id: number;
  conversation_id?: string;
  name?: string;
  email?: string;
  phone?: string;
  service?: string;
  intent?: string;
  urgency?: 'normal' | 'high' | 'urgent';
  preferred_date?: string;
  preferred_time?: string;
  insurance?: string;
  status: 'new' | 'contacted' | 'qualified' | 'booked' | 'closed' | 'spam';
  message?: string;
  created_at: string;
  updated_at?: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system' | 'agent';
  body: string;
  created_at: string;
}

export interface Note {
  id: number;
  lead_id: number;
  note: string;
  created_at: string;
}

export interface Task {
  id: number;
  lead_id?: number;
  title: string;
  priority: 'normal' | 'high' | 'urgent';
  due_at?: string;
  completed: boolean;
  created_at: string;
}

export interface Draft {
  id: number;
  lead_id: number;
  draft_body: string;
  subject?: string;
  created_at: string;
}

export interface DashboardStats {
  total_conversations: number;
  new_leads: number;
  emails_sent: number;
  open_tasks: number;
  overdue_tasks: number;
  pending_drafts: number;
  completed_tasks?: number;
  insights?: string[];
  tenant_name?: string;
}

export type CategoryFilter = 'all' | 'new' | 'waiting' | 'appointment' | 'urgent' | 'notes' | 'tasks';
