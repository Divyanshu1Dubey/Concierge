export const WIDGET_CONFIG = {
  apiUrl: '', // Set by embed code or auto-detected
  practiceSlug: '',
  primaryColor: '#2563eb',
  title: 'Chat with us',
  subtitle: 'We\'re here to help you schedule an appointment.',
  greeting: 'Hello! How can I help you today?',
  placeholder: 'Type your message...',
} as const;

export type WidgetConfig = typeof WIDGET_CONFIG;
