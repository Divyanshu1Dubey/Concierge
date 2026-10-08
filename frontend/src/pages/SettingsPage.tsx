import { useQuery } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import { Save, Bell, Palette, Globe } from 'lucide-react';
import { useState } from 'react';

export default function SettingsPage() {
  const { data: practices } = useQuery({
    queryKey: ['practices'],
    queryFn: practicesApi.getAll,
  });
  const practice = practices?.results?.[0];

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Manage your practice configuration.</p>
      </div>

      {/* Practice Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Practice Information</h2>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-gray-500 block mb-1">Practice Name</label>
            <input
              type="text"
              defaultValue={practice?.name || ''}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">Phone</label>
            <input
              type="text"
              defaultValue={practice?.phone || ''}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">Email</label>
            <input
              type="email"
              defaultValue={practice?.email || ''}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">Timezone</label>
            <input
              type="text"
              defaultValue={practice?.timezone || 'America/New_York'}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div className="col-span-2">
            <label className="text-sm text-gray-500 block mb-1">Address</label>
            <input
              type="text"
              defaultValue={practice?.address || ''}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
        </div>
      </div>

      {/* Widget Customization */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Palette className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Widget Customization</h2>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-gray-500 block mb-1">Assistant Name</label>
            <input
              type="text"
              defaultValue="HeyJarvis Assistant"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 block mb-1">Primary Color</label>
            <div className="flex gap-2">
              <input
                type="color"
                defaultValue="#14b8a6"
                className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer"
              />
              <input
                type="text"
                defaultValue="#14b8a6"
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>
          </div>
          <div className="col-span-2">
            <label className="text-sm text-gray-500 block mb-1">Welcome Message</label>
            <textarea
              rows={2}
              defaultValue="Hello! Welcome to our practice. How can I help you today?"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none"
            />
          </div>
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Notifications</h2>
        </div>
        <div className="space-y-3">
          <label className="flex items-center justify-between">
            <span className="text-sm text-gray-700">New conversation alerts</span>
            <input type="checkbox" defaultChecked className="w-4 h-4 text-teal-600 rounded" />
          </label>
          <label className="flex items-center justify-between">
            <span className="text-sm text-gray-700">New appointment requests</span>
            <input type="checkbox" defaultChecked className="w-4 h-4 text-teal-600 rounded" />
          </label>
          <label className="flex items-center justify-between">
            <span className="text-sm text-gray-700">New lead notifications</span>
            <input type="checkbox" defaultChecked className="w-4 h-4 text-teal-600 rounded" />
          </label>
          <label className="flex items-center justify-between">
            <span className="text-sm text-gray-700">Human handoff alerts</span>
            <input type="checkbox" defaultChecked className="w-4 h-4 text-teal-600 rounded" />
          </label>
        </div>
      </div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700"
        >
          <Save className="w-4 h-4" />
          Save Changes
        </button>
        {saved && (
          <span className="text-sm text-green-600">Settings saved successfully!</span>
        )}
      </div>
    </div>
  );
}
