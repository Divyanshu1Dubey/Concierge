import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ImagePlus, Trash2, Users, Eye, Plus, Check, Pencil, Camera } from 'lucide-react';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';

interface Doctor { id: number; name: string; credentials: string; bio?: string; photo_url: string }
interface Branding {
  practice_name: string;
  logo_url: string;
  logo_uploaded: boolean;
  tagline: string;
  primary_color: string;
  social_links: Record<string, string>;
  doctors: Doctor[];
}

const LINKS: { key: string; label: string; placeholder: string }[] = [
  { key: 'website', label: 'Website', placeholder: 'yourpractice.com' },
  { key: 'google_reviews', label: 'Google reviews page', placeholder: 'g.page/r/your-practice' },
  { key: 'instagram', label: 'Instagram', placeholder: 'instagram.com/yourpractice' },
  { key: 'facebook', label: 'Facebook', placeholder: 'facebook.com/yourpractice' },
];
const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500';
const ACCEPT = 'image/png,image/jpeg,image/webp';

function errorText(err: unknown, fallback: string) {
  const data = (err as any)?.response?.data;
  if (data?.social_links && typeof data.social_links === 'object') return Object.values(data.social_links).join(' ');
  return data?.error || apiErrorMessage(err, fallback);
}

function DoctorRow({ d, onChanged }: { d: Doctor; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: d.name, credentials: d.credentials, bio: d.bio || '' });
  const fileRef = useRef<HTMLInputElement>(null);
  const save = useMutation({
    mutationFn: () => practicesApi.updateBrandTeamMember(d.id, form),
    onSuccess: () => { setEditing(false); onChanged(); },
    onError: (e) => toast.error(errorText(e, 'Could not save.')),
  });
  const remove = useMutation({
    mutationFn: () => practicesApi.deleteBrandTeamMember(d.id),
    onSuccess: onChanged,
    onError: (e) => toast.error(errorText(e, 'Could not remove.')),
  });
  const photo = useMutation({
    mutationFn: (file: File) => practicesApi.uploadBrandTeamPhoto(d.id, file),
    onSuccess: () => { toast.success('Photo updated.'); onChanged(); },
    onError: (e) => toast.error(errorText(e, 'Could not upload the photo.')),
  });
  return (
    <li className="flex gap-3 py-3">
      <button type="button" onClick={() => fileRef.current?.click()} aria-label={`Upload a photo of ${d.name}`}
        className="relative w-14 h-14 rounded-full overflow-hidden bg-gray-100 flex-shrink-0 group border border-gray-200">
        {d.photo_url
          ? <img src={d.photo_url} alt="" className="w-full h-full object-cover" />
          : <span className="w-full h-full flex items-center justify-center text-gray-400"><Camera className="w-5 h-5" /></span>}
        <span className="absolute inset-0 bg-black/40 text-white text-[10px] font-semibold opacity-0 group-hover:opacity-100 flex items-center justify-center">
          {photo.isPending ? '…' : 'Change'}
        </span>
      </button>
      <input ref={fileRef} type="file" accept={ACCEPT} className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) photo.mutate(f); e.target.value = ''; }} />
      <div className="min-w-0 flex-1">
        {editing ? (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input className={input} aria-label="Name" maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <input className={input} aria-label="Credentials" maxLength={120} placeholder="e.g. DDS, Orthodontist" value={form.credentials} onChange={(e) => setForm({ ...form, credentials: e.target.value })} />
            </div>
            <textarea className={input} aria-label="Short bio" rows={2} maxLength={400} placeholder="One or two sentences patients will see" value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
            <div className="flex gap-2">
              <button type="submit" disabled={!form.name.trim() || save.isPending} className="px-3 py-1.5 rounded-lg bg-teal-600 text-white text-xs font-semibold disabled:opacity-50">Save</button>
              <button type="button" onClick={() => setEditing(false)} className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs">Cancel</button>
            </div>
          </form>
        ) : (
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900">{d.name}{d.credentials && <span className="font-normal text-gray-500">, {d.credentials}</span>}</p>
              {d.bio ? <p className="text-xs text-gray-600 mt-0.5">{d.bio}</p> : <p className="text-xs text-gray-500 mt-0.5">No bio yet.</p>}
            </div>
            <div className="flex gap-1 flex-shrink-0">
              <button type="button" aria-label={`Edit ${d.name}`} onClick={() => setEditing(true)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600"><Pencil className="w-4 h-4" /></button>
              <button type="button" aria-label={`Remove ${d.name}`} onClick={() => { if (window.confirm(`Remove ${d.name} from your team?`)) remove.mutate(); }} className="p-1.5 rounded-lg hover:bg-red-50 text-red-600"><Trash2 className="w-4 h-4" /></button>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

/** Logo, tagline, links and team: the identity patients see in chat, emails and appointment pages. */
export default function BrandingPanel() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery<Branding>({ queryKey: ['branding'], queryFn: () => practicesApi.branding() });
  const [tagline, setTagline] = useState('');
  const [links, setLinks] = useState<Record<string, string>>({});
  const [showLinks, setShowLinks] = useState(false);
  const [newDoc, setNewDoc] = useState<null | { name: string; credentials: string; bio: string }>(null);
  const [previewHtml, setPreviewHtml] = useState('');
  const logoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!data) return;
    setTagline(data.tagline || '');
    setLinks(data.social_links || {});
    if (Object.keys(data.social_links || {}).length) setShowLinks(true);
  }, [data]);

  const refresh = () => qc.invalidateQueries({ queryKey: ['branding'] });
  const uploadLogo = useMutation({
    mutationFn: (file: File) => practicesApi.uploadLogo(file),
    onSuccess: () => { toast.success('Logo updated. Patients will see it in emails and on appointment pages.'); refresh(); },
    onError: (e) => toast.error(errorText(e, 'Could not upload the logo.')),
  });
  const removeLogo = useMutation({
    mutationFn: () => practicesApi.removeLogo(),
    onSuccess: () => { toast.success('Logo removed.'); refresh(); },
    onError: (e) => toast.error(errorText(e, 'Could not remove the logo.')),
  });
  const saveDetails = useMutation({
    mutationFn: () => practicesApi.updateBranding({ tagline, social_links: links }),
    onSuccess: () => { toast.success('Branding saved.'); refresh(); },
    onError: (e) => toast.error(errorText(e, 'Could not save branding.')),
  });
  const addDoc = useMutation({
    mutationFn: (v: { name: string; credentials: string; bio: string }) => practicesApi.createBrandTeamMember(v),
    onSuccess: () => { setNewDoc(null); refresh(); },
    onError: (e) => toast.error(errorText(e, 'Could not add this person.')),
  });
  const preview = useMutation({
    mutationFn: () => practicesApi.brandEmailPreview(),
    onSuccess: (r: any) => setPreviewHtml(r.html || ''),
    onError: (e) => toast.error(errorText(e, 'Could not build the preview.')),
  });

  if (isLoading) return <div className="bg-white rounded-xl border border-gray-200 p-6 text-sm text-gray-500">Loading branding…</div>;
  if (isError || !data) return <div className="bg-white rounded-xl border border-gray-200 p-6 text-sm text-red-600">Could not load branding.</div>;
  const color = data.primary_color || '#0d9488';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-5" aria-labelledby="brand-title">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="brand-title" className="text-base font-bold text-gray-900">Practice branding</h2>
            <p className="text-xs text-gray-500 mt-0.5">Shown in patient emails, appointment pages and your website chat.</p>
          </div>
          <button type="button" onClick={() => preview.mutate()} disabled={preview.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 hover:bg-gray-50 whitespace-nowrap">
            <Eye className="w-4 h-4" /> {preview.isPending ? 'Preparing…' : 'Preview patient email'}
          </button>
        </div>

        <div className="flex items-center gap-4">
          <div className="w-40 h-16 rounded-xl border border-dashed border-gray-300 bg-gray-50 flex items-center justify-center overflow-hidden">
            {data.logo_url
              ? <img src={data.logo_url} alt={`${data.practice_name} logo`} className="max-h-14 max-w-[150px] object-contain" />
              : <span className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-semibold" style={{ background: color }}>{data.practice_name.charAt(0)}</span>}
          </div>
          <div className="space-y-1.5">
            <div className="flex gap-2">
              <button type="button" onClick={() => logoRef.current?.click()} disabled={uploadLogo.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-50">
                <ImagePlus className="w-4 h-4" /> {uploadLogo.isPending ? 'Uploading…' : data.logo_url ? 'Replace logo' : 'Upload logo'}
              </button>
              {data.logo_url && (
                <button type="button" onClick={() => removeLogo.mutate()} className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 hover:bg-gray-50">Remove</button>
              )}
            </div>
            <p className="text-[11px] text-gray-500">PNG, JPG or WebP up to 5 MB. A wide logo with a transparent background works best; we resize it for you.</p>
          </div>
          <input ref={logoRef} type="file" accept={ACCEPT} className="hidden" aria-label="Logo file"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadLogo.mutate(f); e.target.value = ''; }} />
        </div>

        <div>
          <label htmlFor="brand-tagline" className="text-xs font-semibold text-gray-700 block mb-1">Tagline (optional)</label>
          <input id="brand-tagline" className={input} maxLength={120} value={tagline} placeholder="e.g. Gentle family dentistry in downtown Raleigh"
            onChange={(e) => setTagline(e.target.value)} />
        </div>

        <div>
          <button type="button" onClick={() => setShowLinks((v) => !v)} className="text-xs font-semibold text-teal-700 hover:text-teal-900">
            {showLinks ? 'Hide links' : '+ Add website, reviews and social links (optional)'}
          </button>
          {showLinks && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              {LINKS.map((l) => (
                <div key={l.key}>
                  <label htmlFor={`brand-${l.key}`} className="text-xs font-semibold text-gray-700 block mb-1">{l.label}</label>
                  <input id={`brand-${l.key}`} className={input} placeholder={l.placeholder} value={links[l.key] || ''}
                    onChange={(e) => setLinks({ ...links, [l.key]: e.target.value })} />
                </div>
              ))}
              <p className="sm:col-span-2 text-[11px] text-gray-500">Links appear in the footer of patient emails. Use your own pages only.</p>
            </div>
          )}
        </div>

        <button type="button" onClick={() => saveDetails.mutate()} disabled={saveDetails.isPending}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
          <Check className="w-4 h-4" /> {saveDetails.isPending ? 'Saving…' : 'Save branding'}
        </button>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-3" aria-labelledby="team-title">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="team-title" className="text-base font-bold text-gray-900 flex items-center gap-2"><Users className="w-5 h-5 text-teal-600" /> Meet the team</h2>
            <p className="text-xs text-gray-500 mt-0.5">Shown in your website chat and used to answer “Who are the dentists?”. Write only what you’re happy for patients to see.</p>
          </div>
          {!newDoc && (
            <button type="button" onClick={() => setNewDoc({ name: '', credentials: '', bio: '' })}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg bg-teal-600 hover:bg-teal-700 text-white whitespace-nowrap">
              <Plus className="w-4 h-4" /> Add person
            </button>
          )}
        </div>
        {newDoc && (
          <form className="space-y-2 bg-gray-50 border border-gray-200 rounded-xl p-3" onSubmit={(e) => { e.preventDefault(); addDoc.mutate(newDoc); }}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input className={input} aria-label="New team member name" placeholder="Name, e.g. Dr. Ana Lee" maxLength={120} value={newDoc.name} onChange={(e) => setNewDoc({ ...newDoc, name: e.target.value })} />
              <input className={input} aria-label="New team member credentials" placeholder="Credentials, e.g. DDS" maxLength={120} value={newDoc.credentials} onChange={(e) => setNewDoc({ ...newDoc, credentials: e.target.value })} />
            </div>
            <textarea className={input} aria-label="New team member bio" rows={2} maxLength={400} placeholder="Short bio (optional)" value={newDoc.bio} onChange={(e) => setNewDoc({ ...newDoc, bio: e.target.value })} />
            <div className="flex gap-2">
              <button type="submit" disabled={!newDoc.name.trim() || addDoc.isPending} className="px-3 py-1.5 rounded-lg bg-teal-600 text-white text-xs font-semibold disabled:opacity-50">Add</button>
              <button type="button" onClick={() => setNewDoc(null)} className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs">Cancel</button>
            </div>
            <p className="text-[11px] text-gray-500">You can add a photo after saving.</p>
          </form>
        )}
        {data.doctors.length === 0 && !newDoc ? (
          <p className="text-sm text-gray-500 bg-gray-50 rounded-lg px-3 py-3">No one added yet. Patients trust practices more when they can see who will care for them.</p>
        ) : (
          <ul className="divide-y divide-gray-100">{data.doctors.map((d) => <DoctorRow key={d.id} d={d} onChanged={refresh} />)}</ul>
        )}
      </section>

      {previewHtml && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/50" role="dialog" aria-modal="true" aria-labelledby="brand-preview-title">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl h-[85vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b">
              <h2 id="brand-preview-title" className="text-sm font-semibold text-gray-900">How a reply looks to patients</h2>
              <button type="button" onClick={() => setPreviewHtml('')} className="text-sm px-3 py-1 rounded-lg border border-gray-200 hover:bg-gray-50">Close</button>
            </div>
            <iframe title="Patient email preview" srcDoc={previewHtml} sandbox="" className="flex-1 w-full border-0" />
          </div>
        </div>
      )}
    </div>
  );
}