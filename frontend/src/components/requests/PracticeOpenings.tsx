import { useQuery } from '@tanstack/react-query';
import apiClient from '@/utils/api';

interface Slot { time: string; end_time: string; provider_id: number | null; operatory_id: number | null }

/** "2026-10-14T09:00:00.000-04:00" -> { date: "2026-10-14", label: "9:00 AM" } in the location's own offset. */
export function slotParts(iso: string) {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
  if (!m) return null;
  const h = Number(m[2]);
  const label = `${((h + 11) % 12) + 1}:${m[3]} ${h < 12 ? 'AM' : 'PM'}`;
  return { date: m[1], label };
}

/** Real openings from the practice-management system (NexHealth). Hidden unless the integration is connected. */
export default function PracticeOpenings({ onPick, selected }: { onPick: (date: string, time: string) => void; selected?: string }) {
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const q = useQuery({
    queryKey: ['pms-openings', today],
    queryFn: () => apiClient.get('/growth/integrations/nexhealth/slots/', { params: { start_date: today } }).then((r) => r.data),
    staleTime: 60000,
    retry: false,
  });
  if (!q.data?.connected && !q.isError) return null;
  if (q.isError) {
    return <p className="text-[11px] text-amber-700">Could not load openings from your practice software. Pick a time below.</p>;
  }
  const slots: Slot[] = q.data.slots || [];
  const parts = slots.map((s) => ({ s, p: slotParts(s.time) })).filter((x) => x.p).slice(0, 12);
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="pms-openings">
      <span className="text-[10px] font-extrabold text-teal-700 uppercase tracking-wider w-16">Open now:</span>
      {parts.length === 0 && <span className="text-xs text-slate-500">No openings in the next week{q.data.next_available_date ? ` (next: ${q.data.next_available_date})` : ''}.</span>}
      {parts.map(({ s, p }) => (
        <button key={s.time + (s.provider_id ?? '')} type="button" onClick={() => onPick(p!.date, p!.label)}
          title="From your practice software"
          className={`px-2.5 py-1 text-xs font-semibold rounded-lg border ${selected === p!.label ? 'bg-teal-600 text-white border-teal-600' : 'bg-teal-50 text-teal-900 border-teal-200 hover:bg-teal-100'}`}>
          {p!.date.slice(5)} {p!.label}
        </button>
      ))}
    </div>
  );
}
