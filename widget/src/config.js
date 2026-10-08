/**
 * HeyJarvis Widget - Configuration Defaults
 */

export const DEFAULT_CONFIG = {
  practiceId: null,
  apiUrl: 'https://api.heyjarvis.com/api',
  primaryColor: '#0d9488',
  title: 'HeyJarvis AI',
  subtitle: 'Chat with us',
  welcomeMessage: "Hi! I'm Jarvis, your dental concierge. How can I help you today?",
  placeholder: 'Type your message...',
  position: 'right', // 'left' or 'right'
  borderRadius: '12px',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  zIndex: 9999,
  openOnLoad: false,
  storeMessages: true,
  sessionKey: 'heyjarvis_session',
};

export const QUICK_REPLIES = {
  initial: [
    { label: 'Book an Appointment', value: 'I\'d like to book an appointment' },
    { label: 'Office Hours', value: 'What are your office hours?' },
    { label: 'Insurance & Payment', value: 'Do you accept my insurance?' },
    { label: 'Speak to Staff', value: 'I\'d like to speak to someone' },
  ],
  appointment: [
    { label: 'New Patient', value: 'I\'m a new patient' },
    { label: 'Existing Patient', value: 'I\'m an existing patient' },
    { label: 'Emergency', value: 'I have a dental emergency' },
    { label: 'Consultation', value: 'I\'d like a consultation' },
  ],
};
