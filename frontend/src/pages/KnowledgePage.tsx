import { useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '@/services/api';
import { BookOpen, Plus, Search } from 'lucide-react';
import { useState } from 'react';

export default function KnowledgePage() {
  const [search, setSearch] = useState('');
  const { data, isLoading } = useQuery({
    queryKey: ['knowledge'],
    queryFn: () => knowledgeApi.getAll(),
  });

  const entries: any[] = Array.isArray(data) ? data : (data?.results ?? []);

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      faq: 'bg-blue-100 text-blue-700',
      service: 'bg-green-100 text-green-700',
      insurance: 'bg-purple-100 text-purple-700',
      policy: 'bg-yellow-100 text-yellow-700',
      emergency: 'bg-red-100 text-red-700',
      general: 'bg-gray-100 text-gray-700',
      pricing: 'bg-emerald-100 text-emerald-700',
      hours: 'bg-teal-100 text-teal-700',
    };
    return colors[category] || 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Knowledge Base</h1>
          <p className="text-gray-500 mt-1">Manage FAQ entries and clinic information for the AI.</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700">
          <Plus className="w-4 h-4" />
          Add Entry
        </button>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search knowledge base..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        {isLoading ? (
          <div className="p-12 text-center">
            <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-gray-500 mt-3">Loading...</p>
          </div>
        ) : entries.length === 0 ? (
          <div className="p-12 text-center">
            <BookOpen className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No knowledge entries yet</p>
            <p className="text-sm text-gray-400 mt-1">Add FAQs and information to train your AI</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {entries.map((entry) => (
              <div key={entry.id} className="px-6 py-4 hover:bg-gray-50">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-medium text-gray-900">{entry.question || 'General Information'}</h3>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(entry.category)}`}>
                        {entry.category}
                      </span>
                      {!entry.is_published && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
                          Draft
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 line-clamp-2">{entry.answer}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
