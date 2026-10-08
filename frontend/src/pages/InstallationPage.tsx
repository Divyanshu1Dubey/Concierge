import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import {
  Key, Globe, Download, Copy, Check, RefreshCw, AlertTriangle,
  Code2, ExternalLink, ShieldCheck, Plus, Trash2, CheckCircle2
} from 'lucide-react';

export default function InstallationPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'universal' | 'html' | 'iframe' | 'wordpress' | 'webflow' | 'wix' | 'squarespace' | 'react' | 'nextjs' | 'gtm'>('universal');
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [copiedHosted, setCopiedHosted] = useState(false);
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [newDomain, setNewDomain] = useState('');

  // Fetch tenant info
  const { data: tenantData } = useQuery({
    queryKey: ['tenant'],
    queryFn: () => practicesApi.getTenant(),
  });

  // Fetch allowed domains
  const { data: domainsData } = useQuery({
    queryKey: ['domains'],
    queryFn: () => practicesApi.domains(),
  });

  const practice = tenantData?.practice || {};
  const clientKey = practice.client_key || practice.api_key || '351936c601d0a11d6f757cf6c45ad55513a5dad1b488a82404b477a619ef76c8';
  const tenantSlug = practice.slug || 'raleigh-dentistry';
  const publicAppUrl = window.location.origin;
  const hostedConciergeUrl = `${publicAppUrl}/concierge/${tenantSlug}`;
  const domains: any[] = domainsData?.domains || [];

  // Mutations
  const regenMutation = useMutation({
    mutationFn: () => practicesApi.regenerateKey(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenant'] });
      setShowRegenModal(false);
    },
  });

  const addDomainMutation = useMutation({
    mutationFn: (hostname: string) => practicesApi.addDomain(hostname),
    onSuccess: () => {
      setNewDomain('');
      queryClient.invalidateQueries({ queryKey: ['domains'] });
    },
  });

  const deleteDomainMutation = useMutation({
    mutationFn: (id: number) => practicesApi.deleteDomain(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains'] });
    },
  });

  const handleCopy = (text: string, type: 'key' | 'snippet' | 'hosted') => {
    navigator.clipboard.writeText(text);
    if (type === 'key') {
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } else if (type === 'snippet') {
      setCopiedSnippet(true);
      setTimeout(() => setCopiedSnippet(false), 2000);
    } else {
      setCopiedHosted(true);
      setTimeout(() => setCopiedHosted(false), 2000);
    }
  };

  const backendApiUrl = window.location.port === '3000' ? 'http://localhost:8000' : window.location.origin;

  // Snippets
  const universalSnippet = `<script async src="${backendApiUrl}/widget.js" data-api-url="${backendApiUrl}" data-practice="${tenantSlug}" data-heyjarvis-client="${clientKey}"></script>`;
  const plainHtmlSnippet = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>My Dental Website</title>
</head>
<body>
  <h1>Welcome to our Clinic</h1>

  <!-- HeyJarvis Concierge Widget -->
  <script async src="${backendApiUrl}/widget.js" data-api-url="${backendApiUrl}" data-practice="${tenantSlug}" data-heyjarvis-client="${clientKey}"></script>
</body>
</html>`;

  const iframeSnippet = `<iframe
  src="${hostedConciergeUrl}"
  width="100%"
  height="700px"
  frameborder="0"
  style="border-radius: 12px; border: 1px solid #e5e7eb; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);"
></iframe>`;

  const reactSnippet = `// In your React App (App.tsx or index.html)
import { useEffect } from 'react';

export function HeyJarvisWidget() {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = '${publicAppUrl}/widget.js';
    script.setAttribute('data-heyjarvis-client', '${clientKey}');
    script.async = true;
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, []);

  return null;
}`;

  const nextjsSnippet = `// In Next.js app/layout.tsx or pages/_app.tsx
import Script from 'next/script';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Script
          src="${publicAppUrl}/widget.js"
          data-heyjarvis-client="${clientKey}"
          strategy="lazyOnload"
        />
      </body>
    </html>
  );
}`;

  const gtmSnippet = `<!-- Google Tag Manager Custom HTML Tag -->
<script>
  (function() {
    var script = document.createElement('script');
    script.src = '${publicAppUrl}/widget.js';
    script.setAttribute('data-heyjarvis-client', '${clientKey}');
    script.async = true;
    document.head.appendChild(script);
  })();
</script>`;

  const webflowSnippet = `<!-- 1. Open Webflow Page Settings -->
<!-- 2. Scroll to "Custom Code" -> "Before </body> tag" -->
<!-- 3. Paste this snippet: -->
<script async src="${publicAppUrl}/widget.js" data-heyjarvis-client="${clientKey}"></script>`;

  const wixSnippet = `<!-- In Wix Dashboard: Settings -> Custom Code -> Body - End -->
<script async src="${publicAppUrl}/widget.js" data-heyjarvis-client="${clientKey}"></script>`;

  const squarespaceSnippet = `<!-- In Squarespace: Settings -> Developer -> Code Injection -> Footer -->
<script async src="${publicAppUrl}/widget.js" data-heyjarvis-client="${clientKey}"></script>`;

  const getActiveSnippet = () => {
    switch (activeTab) {
      case 'universal': return universalSnippet;
      case 'html': return plainHtmlSnippet;
      case 'iframe': return iframeSnippet;
      case 'react': return reactSnippet;
      case 'nextjs': return nextjsSnippet;
      case 'gtm': return gtmSnippet;
      case 'webflow': return webflowSnippet;
      case 'wix': return wixSnippet;
      case 'squarespace': return squarespaceSnippet;
      default: return universalSnippet;
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Installation Center</h1>
        <p className="text-gray-500 mt-1">
          Connect HeyJarvis Concierge to your website in seconds. All snippets are automatically scoped to your tenant.
        </p>
      </div>

      {/* Client Key & Hosted Concierge Cards */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Client Key */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
              <Key className="w-4 h-4 text-teal-600" />
              Public Client Key
            </span>
            <button
              onClick={() => setShowRegenModal(true)}
              className="text-xs font-medium text-red-600 hover:text-red-700 flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" />
              Regenerate
            </button>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              type="text"
              readOnly
              value={clientKey}
              className="w-full font-mono text-xs bg-gray-50 border border-gray-200 px-3 py-2 rounded-lg text-gray-700 select-all"
            />
            <button
              onClick={() => handleCopy(clientKey, 'key')}
              className="p-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg flex-shrink-0 transition"
              title="Copy Client Key"
            >
              {copiedKey ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Safe for public browser usage. Binds incoming conversations to your tenant.
          </p>
        </div>

        {/* Hosted Concierge */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
              <Globe className="w-4 h-4 text-cyan-600" />
              Hosted Concierge URL
            </span>
            <a
              href={hostedConciergeUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-medium text-teal-600 hover:text-teal-700 flex items-center gap-1"
            >
              <ExternalLink className="w-3 h-3" />
              Open Live
            </a>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              type="text"
              readOnly
              value={hostedConciergeUrl}
              className="w-full font-mono text-xs bg-gray-50 border border-gray-200 px-3 py-2 rounded-lg text-gray-700 select-all"
            />
            <button
              onClick={() => handleCopy(hostedConciergeUrl, 'hosted')}
              className="p-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg flex-shrink-0 transition"
              title="Copy Hosted Concierge URL"
            >
              {copiedHosted ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Share directly on Google My Business, SMS, social media, or bio links.
          </p>
        </div>
      </div>

      {/* WordPress Plugin Official Card */}
      <div className="bg-gradient-to-r from-blue-900 to-indigo-900 rounded-xl p-6 text-white shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-blue-500/30 text-blue-200 rounded text-xs font-bold uppercase">Official Plugin</span>
            <h3 className="text-lg font-bold">HeyJarvis WordPress Plugin (.zip)</h3>
          </div>
          <p className="text-blue-100 text-sm mt-1 max-w-2xl">
            Upload to any WordPress site. Automatically injects the isolated widget with zero theme conflicts.
          </p>
        </div>
        <a
          href="/api/practices/integration/wordpress/"
          download="heyjarvis-concierge.zip"
          className="flex items-center gap-2 px-5 py-2.5 bg-white text-blue-900 hover:bg-blue-50 rounded-xl text-sm font-bold transition shadow"
        >
          <Download className="w-4 h-4" />
          Download Plugin ZIP
        </a>
      </div>

      {/* Code Snippets Section */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Code2 className="w-5 h-5 text-teal-600" />
            <h2 className="text-base font-bold text-gray-900">Embedding Snippets & Integrations</h2>
          </div>
          <button
            onClick={() => handleCopy(getActiveSnippet(), 'snippet')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold transition"
          >
            {copiedSnippet ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copiedSnippet ? 'Copied to Clipboard' : 'Copy Snippet'}
          </button>
        </div>

        {/* Integration Navigation Tabs */}
        <div className="flex border-b border-gray-200 overflow-x-auto bg-gray-50 text-xs font-medium">
          {[
            { id: 'universal', label: 'Universal Script (Recommended)' },
            { id: 'html', label: 'Plain HTML' },
            { id: 'iframe', label: 'iframe' },
            { id: 'react', label: 'React' },
            { id: 'nextjs', label: 'Next.js' },
            { id: 'gtm', label: 'Google Tag Manager' },
            { id: 'webflow', label: 'Webflow' },
            { id: 'wix', label: 'Wix' },
            { id: 'squarespace', label: 'Squarespace' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-3 whitespace-nowrap border-b-2 transition ${
                activeTab === tab.id
                  ? 'border-teal-600 text-teal-700 font-bold bg-white'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Code Display */}
        <div className="p-6 bg-gray-950 text-gray-100 font-mono text-xs overflow-x-auto">
          <pre>{getActiveSnippet()}</pre>
        </div>

        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 text-xs text-gray-500">
          💡 The widget script is loaded asynchronously, isolated in Shadow DOM, and auto-detects mobile vs desktop screens.
        </div>
      </div>

      {/* Allowed Domains Security Manager */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              Allowed Origin Domains
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Widget requests will only be accepted from verified domains. Add your customer's website URLs below.
            </p>
          </div>
        </div>

        {/* Add Domain Input */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="e.g. raleighdentistry.com or localhost:3000"
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          <button
            onClick={() => newDomain && addDomainMutation.mutate(newDomain)}
            disabled={!newDomain || addDomainMutation.isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50 transition"
          >
            <Plus className="w-4 h-4" />
            Add Domain
          </button>
        </div>

        {/* Domains List */}
        <div className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
          {domains.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-xs">
              No custom domains configured yet. All origins accepted in development.
            </div>
          ) : (
            domains.map((d: any) => (
              <div key={d.id} className="px-4 py-3 flex items-center justify-between hover:bg-gray-50">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="font-mono text-xs text-gray-800">{d.hostname}</span>
                  <span className="text-[10px] bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-bold">
                    VERIFIED
                  </span>
                </div>
                <button
                  onClick={() => deleteDomainMutation.mutate(d.id)}
                  className="text-red-500 hover:text-red-700 p-1"
                  title="Remove Domain"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Regeneration Warning Modal */}
      {showRegenModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-3 text-red-600">
              <AlertTriangle className="w-6 h-6 flex-shrink-0" />
              <h3 className="text-lg font-bold text-gray-900">Regenerate Client Key?</h3>
            </div>
            <p className="text-sm text-gray-600">
              <strong className="text-red-600">Warning:</strong> Existing website installations using this key will immediately stop working until you update their snippet.
            </p>
            <div className="flex justify-end gap-3 pt-3">
              <button
                onClick={() => setShowRegenModal(false)}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-semibold text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => regenMutation.mutate()}
                disabled={regenMutation.isPending}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold"
              >
                {regenMutation.isPending ? 'Regenerating...' : 'Yes, Regenerate Key'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
