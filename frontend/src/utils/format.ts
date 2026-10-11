/** Small display helpers shared by dashboard pages (kept pure so they can be unit tested). */

/** "5 min ago", "3 h ago", "2 days ago" relative to `now` (defaults to the current time). */
export function ago(iso: string, now: number = Date.now()): string {
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

/** Minutes as a short duration: "45 min", "1.5 h", "12 h", "3 days"; "–" when unknown. */
export function fmtMinutes(m: number | null | undefined): string {
  if (m === null || m === undefined) return '–';
  if (m < 60) return `${m} min`;
  const h = m / 60;
  return h < 48 ? `${h.toFixed(h < 10 ? 1 : 0)} h` : `${Math.round(h / 24)} days`;
}
