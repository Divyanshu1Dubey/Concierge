export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ConversationState {
  sessionId: string;
  messages: Message[];
  patientInfo?: {
    name?: string;
    email?: string;
    phone?: string;
  };
  appointmentType?: string;
  urgency?: string;
  preferredDate?: string;
  status: 'active' | 'scheduled' | 'closed';
}
