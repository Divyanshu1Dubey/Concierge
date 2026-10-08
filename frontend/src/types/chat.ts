export interface Conversation {
  id: string
  visitor_id: string
  visitor_name: string
  visitor_email: string
  visitor_phone: string
  status: 'active' | 'closed' | 'escalated'
  assigned_to: string | null
  intent: string
  confidence: number
  messages: ChatMessage[]
  metadata: Record<string, unknown>
  started_at: string
  ended_at: string | null
  created_at: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  sender: 'user' | 'bot' | 'staff'
  content: string
  is_ai_generated: boolean
  metadata: Record<string, unknown>
  created_at: string
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  visitor_info?: {
    name: string
    email: string
    phone: string
  }
}

export interface ChatResponse {
  conversation_id: string
  message: ChatMessage
  intent: string
  confidence: number
}
