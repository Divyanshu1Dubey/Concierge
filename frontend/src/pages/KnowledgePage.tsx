import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { BookOpen, HelpCircle, Pencil, Plus, Trash2, X, Check, EyeOff, Eye } from 'lucide-react';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';
import { growthApi } from '@/services/growthApi';

type Category = 'faq' | 'insurance' | 'doctor' | 'service' | 'policy' | 'preparation' | 'other';
interface Entry { id: number; category: Category; title: string; content: string; is_active: boolean; updated_at: string; updated_by: string }
interface Question { id: number; question: string; times_asked: number; last_asked_at: string }

const CATEGORIES: { value: Category; label: string }[] = [
  { value: 'faq', label: 'Frequently asked' },
  { value: 'insurance', label: 'Insurance & payment' },
  { value: 'doctor', label: 'Doctors & team' },
  { value: 'service', label: 'Services & treatments' },
  { value: 'policy', label: 'Policies' },
  { value: 'preparation', label: 'Visit preparation' },
  { value: 'other', label: 'Other' },
];
const label = (c: string) => CATEGORIES.find((x) => x.value === c)?.label || c;

// Prompts only pre-fill the question; the practice writes every answer.
const STARTERS: { category: Category; title: string }[] = [
  { category: 'insurance', title: 'Which insurance plans do you accept?' },
  { category: 'insurance', title: 'Do you offer payment plans or financing?' },
  { category: 'faq', title: 'Is there parking at the office?' },
  { category: 'preparation', title: 'What should I bring to my first visit?' },
  { category: 'doctor', title: 'Who are the dentists at the practice?' },
  { category: 'service', title: 'Do you offer teeth whitening?' },
];

const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500';

function EntryForm({ initial, onCancel, onSave, saving }: {
  initial: { category: Category; title: string; content: string };
  onCancel: () => void;
  onSave: (v: { category: Category; title: string; content: string }) => void;
  saving: boolean;
}) {
  const [v, setV] = useState(initial);
  return (
    <form
      className="space-y-3 bg-gray-50 border border-gray-200 rounded-xl p-4"
      onSubmit={(e) => { e.preventDefault(); onSave(v); }}
    >
      <div className="grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-3">
        <div>
          <label htmlFor="kb-cat" className="text-xs font-semibold text-gray-700 block mb-1">Type</label>
          <select id="kb-cat" className={input} value={v.category} onChange={(e) => setV({ ...v, category: e.target.value as Category })}>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="kb-title" className="text-xs font-semibold text-gray-700 block mb-1">Question or topic</label>
          <input id="kb-title" className={input} maxLength={200} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })}
            placeholder="e.g. Do you accept Delta Dental?" />
        </div>
      </div>
      <div>
        <label htmlFor="kb-content" className="text-xs font-semibold text-gray-700 block mb-1">Answer patients should get</label>
        <textarea id="kb-content" rows={3} maxLength={3000} className={input} value={v.content} onChange={(e) => setV({ ...v, content: e.target.value })}
          placeholder="Write it the way your front desk would say it. Only facts you're happy for patients to see." />
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving || !v.title.trim() || !v.content.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
          <Check className="w-4 h-4" /> {saving ? 'Saving…' : 'Save answer'}
        </button>
        <button type="button" onClick={onCancel} className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-white">Cancel</button>
      </div>
    </form>
  );
}

export default function KnowledgePage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user) as any;
  const role = String(user?.role || '').toUpperCase();
  const canEdit = Boolean(user?.is_agency_admin || user?.is_practice_admin || ['AGENCY_ADMIN', 'PRACTICE_ADMIN', 'ADMIN', 'OWNER'].includes(role));

  const entriesQ = useQuery({ queryKey: ['knowledge'], queryFn: () => practicesApi.knowledge() });
  const questionsQ = useQuery({ queryKey: ['knowledge-unanswered'], queryFn: () => practicesApi.unansweredQuestions() });
  const entries: Entry[] = entriesQ.data?.results || [];
  const questions: Question[] = questionsQ.data?.results || [];

  const [adding, setAdding] = useState<null | { category: Category; title: string; content: string }>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [answering, setAnswering] = useState<number | null>(null);
  const [suggested, setSuggested] = useState<Record<number, string>>({});
  const suggest = useMutation({
    mutationFn: (id: number) => growthApi.suggestAnswer(id),
    onSuccess: (r, id) => {
      if (r.suggestion) { setSuggested((s) => ({ ...s, [id]: r.suggestion })); setAnswering(id); toast.success(r.reason); }
      else toast(r.reason);
    },
    onError: (err: unknown) => toast.error(apiErrorMessage(err, 'Could not suggest an answer.')),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['knowledge'] });
    qc.invalidateQueries({ queryKey: ['knowledge-unanswered'] });
  };
  const onError = (err: unknown) => toast.error(apiErrorMessage(err, 'Could not save. Please try again.'));

  const create = useMutation({
    mutationFn: (v: { category: Category; title: string; content: string }) => practicesApi.createKnowledge(v),
    onSuccess: () => { toast.success('Answer added. Concierge will use it right away.'); setAdding(null); refresh(); },
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Entry> }) => practicesApi.updateKnowledge(id, data),
    onSuccess: () => { setEditing(null); refresh(); },
    onError,
  });
  const remove = useMutation({
    mutationFn: (id: number) => practicesApi.deleteKnowledge(id),
    onSuccess: () => { toast.success('Answer removed.'); refresh(); },
    onError,
  });
  const resolve = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, string> }) => practicesApi.resolveUnanswered(id, data),
    onSuccess: (_r, vars) => {
      toast.success(vars.data.action === 'dismiss' ? 'Question dismissed.' : 'Answer saved. Concierge will use it from now on.');
      setAnswering(null);
      refresh();
    },
    onError,
  });

  const grouped = useMemo(() => {
    const map = new Map<string, Entry[]>();
    entries.forEach((e) => map.set(e.category, [...(map.get(e.category) || []), e]));
    return CATEGORIES.filter((c) => map.has(c.value)).map((c) => ({ ...c, items: map.get(c.value)! }));
  }, [entries]);
  const unusedStarters = STARTERS.filter((s) => !entries.some((e) => e.title.toLowerCase() === s.title.toLowerCase()));

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><BookOpen className="w-6 h-6 text-teal-600" /> Practice knowledge</h1>
        <p className="text-gray-500 mt-1 text-sm">
          What Concierge can tell patients. It answers only from what you add here and in Hours &amp; Services, and sends anything else to your front desk.
        </p>
        {!canEdit && <p className="mt-2 text-xs text-gray-500">You can view these answers. Ask a practice administrator to change them.</p>}
      </div>

      {/* Questions Concierge could not answer */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-3" aria-labelledby="kb-unanswered">
        <div className="flex items-center justify-between gap-2">
          <h2 id="kb-unanswered" className="text-base font-semibold text-gray-900 flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-amber-600" /> Questions patients asked
          </h2>
          {questions.length > 0 && <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">{questions.length} to answer</span>}
        </div>
        <p className="text-xs text-gray-500">Concierge had to send these patients to your front desk. Add an answer once and it will handle the question next time.</p>
        {questionsQ.isLoading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : questionsQ.isError ? (
          <p className="text-sm text-red-600">Could not load questions.</p>
        ) : questions.length === 0 ? (
          <p className="text-sm text-gray-500 bg-gray-50 rounded-lg px-3 py-3">No unanswered questions right now.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {questions.map((q) => (
              <li key={q.id} className="py-3 space-y-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 break-words">“{q.question}”</p>
                    <p className="text-[11px] text-gray-500">Asked {q.times_asked} time{q.times_asked === 1 ? '' : 's'} · last {new Date(q.last_asked_at).toLocaleDateString()}</p>
                  </div>
                  {canEdit && answering !== q.id && (
                    <div className="flex gap-2">
                      <button type="button" onClick={() => setAnswering(q.id)} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white">Answer</button>
                      <button type="button" disabled={suggest.isPending} onClick={() => suggest.mutate(q.id)} className="text-xs px-3 py-1.5 rounded-lg border border-teal-200 text-teal-700 hover:bg-teal-50 disabled:opacity-50">{suggest.isPending && suggest.variables === q.id ? 'Thinking…' : 'Suggest an answer'}</button>
                      <button type="button" onClick={() => resolve.mutate({ id: q.id, data: { action: 'dismiss' } })} className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">Dismiss</button>
                    </div>
                  )}
                </div>
                {answering === q.id && (
                  <EntryForm
                    initial={{ category: 'faq', title: q.question, content: suggested[q.id] || '' }}
                    saving={resolve.isPending}
                    onCancel={() => setAnswering(null)}
                    onSave={(v) => resolve.mutate({ id: q.id, data: { action: 'answer', ...v } })}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Approved answers */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4" aria-labelledby="kb-answers">
        <div className="flex items-center justify-between gap-2">
          <h2 id="kb-answers" className="text-base font-semibold text-gray-900">Answers Concierge can give</h2>
          {canEdit && !adding && (
            <button type="button" onClick={() => setAdding({ category: 'faq', title: '', content: '' })}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold">
              <Plus className="w-4 h-4" /> Add answer
            </button>
          )}
        </div>
        {adding && <EntryForm initial={adding} saving={create.isPending} onCancel={() => setAdding(null)} onSave={(v) => create.mutate(v)} />}
        {canEdit && !adding && unusedStarters.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Common patient questions you may want to answer:</p>
            <div className="flex flex-wrap gap-2">
              {unusedStarters.map((s) => (
                <button key={s.title} type="button" onClick={() => setAdding({ ...s, content: '' })}
                  className="text-xs px-3 py-1.5 rounded-full border border-teal-200 text-teal-800 bg-teal-50 hover:bg-teal-100">
                  + {s.title}
                </button>
              ))}
            </div>
          </div>
        )}
        {entriesQ.isLoading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : entriesQ.isError ? (
          <p className="text-sm text-red-600">Could not load answers.</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-gray-500 bg-gray-50 rounded-lg px-3 py-3">No answers yet. Start with the questions above, or the ones patients ask your front desk most often.</p>
        ) : (
          grouped.map((g) => (
            <div key={g.value}>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{g.label}</h3>
              <ul className="space-y-2">
                {g.items.map((e) => (
                  <li key={e.id} className={`rounded-lg border p-3 ${e.is_active ? 'border-gray-200' : 'border-dashed border-gray-300 bg-gray-50'}`}>
                    {editing === e.id ? (
                      <EntryForm
                        initial={{ category: e.category, title: e.title, content: e.content }}
                        saving={update.isPending}
                        onCancel={() => setEditing(null)}
                        onSave={(v) => update.mutate({ id: e.id, data: v })}
                      />
                    ) : (
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-gray-900 break-words">{e.title}{!e.is_active && <span className="ml-2 text-[11px] font-normal text-gray-500">(paused)</span>}</p>
                          <p className="text-sm text-gray-700 whitespace-pre-wrap break-words mt-0.5">{e.content}</p>
                          <p className="text-[11px] text-gray-500 mt-1">{label(e.category)} · updated {new Date(e.updated_at).toLocaleDateString()}{e.updated_by ? ` by ${e.updated_by}` : ''}</p>
                        </div>
                        {canEdit && (
                          <div className="flex gap-1">
                            <button type="button" aria-label={`Edit ${e.title}`} onClick={() => setEditing(e.id)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"><Pencil className="w-4 h-4" /></button>
                            <button type="button" aria-label={e.is_active ? `Pause ${e.title}` : `Use ${e.title} again`}
                              onClick={() => update.mutate({ id: e.id, data: { is_active: !e.is_active } })} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">
                              {e.is_active ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                            <button type="button" aria-label={`Delete ${e.title}`}
                              onClick={() => { if (window.confirm('Delete this answer? Concierge will stop using it.')) remove.mutate(e.id); }}
                              className="p-2 rounded-lg hover:bg-red-50 text-red-600"><Trash2 className="w-4 h-4" /></button>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
      <p className="text-xs text-gray-500 flex items-center gap-1"><X className="w-3 h-3" /> Concierge never quotes prices, coverage or appointment times unless you write them here.</p>
    </div>
  );
}