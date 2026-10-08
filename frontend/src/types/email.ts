export interface EmailThread {
  id: string
  patient_email: string
  patient_name: string
  subject: string
  status: 'active' | 'closed' | 'pending'
  assigned_to: string | null
  metadata: Record<string, unknown>
  last_message_at: string
  created_at: string
  emails: Email[]
  latest_email: Email | null
}

export interface Email {
  id: string
  thread: string
  direction: 'incoming' | 'outgoing' | 'internal'
  status: 'sending' | 'sent' | 'failed' | 'draft'
  from_email: string
  to_email: string
  cc: string
  subject: string
  body: string
  body_html: string
  is_ai_draft: boolean
  is_staff_reply: boolean
  sent_at: string | null
  created_at: string
}

export interface EmailCadence {
  id: string
  patient_email: string
  patient_name: string
  template: string
  status: 'active' | 'paused' | 'completed' | 'cancelled'
  current_step: number
  total_steps: number
  next_scheduled_at: string | null
  completed_at: string | null
  created_at: string
}
