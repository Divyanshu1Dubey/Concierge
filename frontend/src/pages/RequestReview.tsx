import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { requestsApi, patientsApi } from '../services/api';

export default function RequestReview() {
  const { id } = useParams<{ id: string }>();
  const [request, setRequest] = useState<any | null>(null);
  const [patient, setPatient] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState('');

  const [offeredDate, setOfferedDate] = useState('');
  const [offeredTime, setOfferedTime] = useState('');
  const [notes, setNotes] = useState('');
  const [draftContent, setDraftContent] = useState('');

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    if (!id) return;
    try {
      const reqData = await requestsApi.get(id);
      setRequest(reqData);
      if (reqData.patient) {
        const patData = await patientsApi.get(String(reqData.patient)).catch(() => null);
        setPatient(patData);
      }
      if (reqData.offered_date) setOfferedDate(reqData.offered_date);
      if (reqData.offered_time) setOfferedTime(reqData.offered_time);
      setNotes(reqData.notes || '');
      if (reqData.generated_response) {
        setDraftContent(reqData.generated_response);
      }
    } catch (err) {
      console.error('Failed to load request:', err);
    } finally {
      setLoading(false);
    }
  };

  const generateDraft = () => {
    if (!request || !patient) return;
    const typeLabel = request.appointment_type.replace(/_/g, ' ');
    const draft = `Hi ${patient.name},

Thank you for reaching out to us! We'd love to get you scheduled for your ${typeLabel} appointment.

We have availability on ${offeredDate || '[date]'} at ${offeredTime || '[time]'}.

Would this work for you?

Please reply to this email to confirm or let us know if you need a different time.

Best regards,
Raleigh Comprehensive & Cosmetic Dentistry Team`;
    setDraftContent(draft);
  };

  const handleSend = async () => {
    if (!request) return;
    setSending(true);
    try {
      await requestsApi.respond(request.id, {
        offered_date: offeredDate,
        offered_time: offeredTime,
        notes,
        generated_response: draftContent,
      });
      setMessage('Response sent successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      console.error('Failed to send:', err);
      setMessage('Failed to send. Please try again.');
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (!request) return <div className="error">Request not found</div>;

  return (
    <div className="request-review">
      <div className="request-header">
        <h2>Appointment Request #{request.id}</h2>
        <span className={`status-badge status-${request.status}`}>
          {request.status}
        </span>
      </div>

      <div className="request-layout">
        <div className="request-sidebar">
          {patient && (
            <div className="patient-card">
              <h3>Patient Info</h3>
              <p><strong>Name:</strong> {patient.name}</p>
              <p><strong>Email:</strong> {patient.email}</p>
              {patient.phone && <p><strong>Phone:</strong> {patient.phone}</p>}
              <p><strong>Existing Patient:</strong> {patient.existing_patient ? 'Yes' : 'New'}</p>
            </div>
          )}

          <div className="request-details">
            <h3>Request Details</h3>
            <p><strong>Type:</strong> {request.appointment_type.replace(/_/g, ' ')}</p>
            <p><strong>Reason:</strong> {request.reason}</p>
            <p><strong>Urgency:</strong> {request.urgency}</p>
            {request.preferred_date && (
              <p><strong>Preferred Date:</strong> {request.preferred_date}</p>
            )}
            {request.preferred_time && (
              <p><strong>Preferred Time:</strong> {request.preferred_time}</p>
            )}
            <p><strong>Created:</strong> {new Date(request.created_at).toLocaleString()}</p>
          </div>
        </div>

        <div className="response-panel">
          <div className="form-section">
            <h3>Offer Details</h3>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="offeredDate">Offered Date</label>
                <input
                  id="offeredDate"
                  type="date"
                  value={offeredDate}
                  onChange={(e) => setOfferedDate(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="offeredTime">Offered Time</label>
                <input
                  id="offeredTime"
                  type="time"
                  value={offeredTime}
                  onChange={(e) => setOfferedTime(e.target.value)}
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="notes">Internal Notes</label>
              <textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                placeholder="Internal notes about this request..."
              />
            </div>
          </div>

          <div className="form-section">
            <div className="section-header">
              <h3>Response Email</h3>
              <button type="button" className="btn btn-secondary" onClick={generateDraft}>
                Generate Draft
              </button>
            </div>
            <textarea
              className="draft-editor"
              value={draftContent}
              onChange={(e) => setDraftContent(e.target.value)}
              rows={12}
              placeholder="Click 'Generate Draft' or type your response..."
            />
          </div>

          <div className="response-actions">
            {message && <div className={`message ${message.includes('Failed') ? 'error' : 'success'}`}>{message}</div>}
            <div className="action-buttons">
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={sending || !offeredDate || !offeredTime || !draftContent}
              >
                {sending ? 'Sending...' : 'Send Response'}
              </button>
              <button className="btn btn-secondary" onClick={loadData}>
                Reset
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
