export type { User, AuthTokens, LoginCredentials, GoogleOAuthResponse, PaginatedResponse } from './auth'
export type { Conversation, ChatMessage, ChatRequest, ChatResponse } from './chat'
export type { Appointment, AvailableSlot } from './appointment'
export type { EmailThread, Email, EmailCadence } from './email'

export interface DashboardStats {
  total_conversations: number
  active_conversations: number
  total_appointments: number
  pending_appointments: number
  total_emails: number
  ai_accuracy: number
  response_time_avg: number
  weekly_stats: {
    conversations: number[]
    appointments: number[]
  }
}

export interface PracticeSettings {
  id: string
  practice_name: string
  practice_email: string
  practice_phone: string
  widget_enabled: boolean
  ai_provider: string
}
