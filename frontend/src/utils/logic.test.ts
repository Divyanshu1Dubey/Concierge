import { describe, expect, it } from 'vitest';
import { ago, fmtMinutes } from './format';
import { slotParts } from '../components/requests/PracticeOpenings';
import { isAdminUser } from '../services/growthApi';
import { apiErrorMessage } from './api';

describe('ago', () => {
  const now = Date.parse('2026-10-11T12:00:00Z');
  it('formats minutes, hours and days', () => {
    expect(ago('2026-10-11T11:55:00Z', now)).toBe('5 min ago');
    expect(ago('2026-10-11T09:00:00Z', now)).toBe('3 h ago');
    expect(ago('2026-10-08T12:00:00Z', now)).toBe('3 days ago');
  });
  it('never shows negative times for clock skew', () => {
    expect(ago('2026-10-11T12:05:00Z', now)).toBe('0 min ago');
  });
});

describe('fmtMinutes', () => {
  it('handles unknown, minutes, hours and days', () => {
    expect(fmtMinutes(null)).toBe('–');
    expect(fmtMinutes(undefined)).toBe('–');
    expect(fmtMinutes(45)).toBe('45 min');
    expect(fmtMinutes(90)).toBe('1.5 h');
    expect(fmtMinutes(720)).toBe('12 h');
    expect(fmtMinutes(60 * 72)).toBe('3 days');
  });
});

describe('slotParts', () => {
  it('keeps the practice location time, not the browser time zone', () => {
    expect(slotParts('2026-10-14T09:00:00.000-04:00')).toEqual({ date: '2026-10-14', label: '9:00 AM' });
    expect(slotParts('2026-10-14T13:30:00.000-07:00')).toEqual({ date: '2026-10-14', label: '1:30 PM' });
    expect(slotParts('2026-10-14T00:15:00Z')).toEqual({ date: '2026-10-14', label: '12:15 AM' });
    expect(slotParts('2026-10-14T12:00:00Z')).toEqual({ date: '2026-10-14', label: '12:00 PM' });
  });
  it('rejects malformed input', () => {
    expect(slotParts('')).toBeNull();
    expect(slotParts('tomorrow at 9')).toBeNull();
  });
});

describe('isAdminUser', () => {
  it('recognises admin roles and flags only', () => {
    expect(isAdminUser({ role: 'PRACTICE_ADMIN' })).toBe(true);
    expect(isAdminUser({ role: 'owner' })).toBe(true);
    expect(isAdminUser({ is_agency_admin: true })).toBe(true);
    expect(isAdminUser({ role: 'FRONT_DESK' })).toBe(false);
    expect(isAdminUser(null)).toBe(false);
  });
});

describe('apiErrorMessage', () => {
  it('prefers the server message and never leaks raw HTML', () => {
    expect(apiErrorMessage({ response: { data: { error: 'Choose email.' } } })).toBe('Choose email.');
    expect(apiErrorMessage({ response: { data: { detail: 'Not found.' } } })).toBe('Not found.');
    expect(apiErrorMessage({ response: { data: '<html>500</html>' } }, 'Try again.')).toBe('Try again.');
    expect(apiErrorMessage({})).toMatch(/Network error/);
  });
});
