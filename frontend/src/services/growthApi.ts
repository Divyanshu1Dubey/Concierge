import apiClient from '@/utils/api';

// Growth & conversion: follow-ups, analytics, briefing, website check, recall, SMS and integrations.
const g = (path: string) => `/growth/${path}`;
const data = (r: { data: any }) => r.data;

export const growthApi = {
  followUps: (params: Record<string, string> = {}) => apiClient.get(g('follow-ups/'), { params }).then(data),
  createFollowUp: (body: Record<string, unknown>) => apiClient.post(g('follow-ups/'), body).then(data),
  updateFollowUp: (id: string, body: Record<string, unknown>) => apiClient.patch(g(`follow-ups/${id}/`), body).then(data),
  sendFollowUp: (id: string, body: Record<string, unknown>) => apiClient.post(g(`follow-ups/${id}/send/`), body).then(data),
  aiDraft: (id: string, body: Record<string, unknown>) => apiClient.post(g(`follow-ups/${id}/ai-draft/`), body).then(data),
  sendBatch: (ids: string[]) => apiClient.post(g('follow-ups/send-batch/'), { ids }).then(data),

  analytics: (days: number) => apiClient.get(g('analytics/'), { params: { days } }).then(data),
  briefing: () => apiClient.get(g('briefing/')).then(data),
  sendBriefing: () => apiClient.post(g('briefing/send/')).then(data),
  settings: () => apiClient.get(g('settings/')).then(data),
  updateSettings: (body: Record<string, unknown>) => apiClient.patch(g('settings/'), body).then(data),

  visibility: () => apiClient.get(g('visibility/')).then(data),
  runVisibility: (url?: string) => apiClient.post(g('visibility/run/'), url ? { url } : {}, { timeout: 60000 }).then(data),
  visibilityReport: (id: string) => apiClient.get(g(`visibility/${id}/`)).then(data),
  facts: () => apiClient.get(g('visibility/facts/')).then(data),

  suggestAnswer: (questionId: number) => apiClient.post(g(`knowledge-suggest/${questionId}/`)).then(data),

  recall: (params: Record<string, string> = {}) => apiClient.get(g('recall/'), { params }).then(data),
  addRecall: (body: Record<string, unknown>) => apiClient.post(g('recall/'), body).then(data),
  updateRecall: (id: number, body: Record<string, unknown>) => apiClient.patch(g(`recall/${id}/`), body).then(data),
  deleteRecall: (id: number) => apiClient.delete(g(`recall/${id}/`)).then(data),
  importRecall: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiClient.post(g('recall/import/'), fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then(data);
  },
  optOuts: () => apiClient.get(g('contact-preferences/')).then(data),
  setOptOut: (body: Record<string, unknown>) => apiClient.post(g('contact-preferences/'), body).then(data),

  sms: (appointment?: string) => apiClient.get(g('sms/'), { params: appointment ? { appointment } : {} }).then(data),
  sendSms: (body: Record<string, unknown>) => apiClient.post(g('sms/'), body).then(data),

  integrations: () => apiClient.get(g('integrations/')).then(data),
  googleConnect: () => apiClient.post(g('integrations/google/connect/')).then(data),
  googleLocations: () => apiClient.get(g('integrations/google/locations/')).then(data),
  googleSelectLocation: (body: Record<string, unknown>) => apiClient.post(g('integrations/google/locations/'), body).then(data),
  googleReviews: () => apiClient.get(g('integrations/google/reviews/')).then(data),
  googleReviewDraft: (body: Record<string, unknown>) => apiClient.post(g('integrations/google/reviews/draft/'), body).then(data),
  googleReviewReply: (body: Record<string, unknown>) => apiClient.post(g('integrations/google/reviews/reply/'), body).then(data),
  googlePost: (body: Record<string, unknown>) => apiClient.post(g('integrations/google/posts/'), body).then(data),
  googleDisconnect: () => apiClient.post(g('integrations/google/disconnect/')).then(data),
  nexhealthSave: (body: Record<string, unknown>) => apiClient.post(g('integrations/nexhealth/'), body).then(data),
  nexhealthTest: () => apiClient.post(g('integrations/nexhealth/test/')).then(data),
  nexhealthSlots: (start_date: string) => apiClient.get(g('integrations/nexhealth/slots/'), { params: { start_date } }).then(data),
  nexhealthDisconnect: () => apiClient.post(g('integrations/nexhealth/disconnect/')).then(data),
  twilioSave: (body: Record<string, unknown>) => apiClient.post(g('integrations/twilio/'), body).then(data),
  twilioDisconnect: () => apiClient.post(g('integrations/twilio/disconnect/')).then(data),
};

export const isAdminUser = (user: any) => {
  const role = String(user?.role || '').toUpperCase();
  return Boolean(user?.is_agency_admin || user?.is_practice_admin || ['AGENCY_ADMIN', 'PRACTICE_ADMIN', 'ADMIN', 'OWNER'].includes(role));
};
