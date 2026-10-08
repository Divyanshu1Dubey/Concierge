import type { Message } from './types';

const API_BASE = '/api/v1';

export async function sendMessage(
  practiceSlug: string,
  sessionId: string,
  message: string
): Promise<{ messages: Message[]; sessionId: string }> {
  const response = await fetch(`${API_BASE}/chat/${practiceSlug}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`);
  }

  return response.json();
}

export async function createSession(
  practiceSlug: string
): Promise<{ session_id: string }> {
  const response = await fetch(`${API_BASE}/chat/${practiceSlug}/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Session API error: ${response.status}`);
  }

  return response.json();
}
