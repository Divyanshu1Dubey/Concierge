export interface Appointment {
  id: string
  conversation_id: string
  patient_name: string
  patient_email: string
  patient_phone: string
  preferred_date: string
  preferred_time: string
  service: string
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed'
  notes: string
  confirmation_code: string
  created_at: string
  updated_at: string
}

export interface AvailableSlot {
  date: string
  time: string
  available: boolean
  provider: string
}
