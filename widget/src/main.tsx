import { createRoot } from 'react-dom/client';
import { ChatWidget } from './components/ChatWidget';
import { WIDGET_CONFIG } from './config';

// Override config from URL params
const params = new URLSearchParams(window.location.search);
if (params.get('practice')) {
  WIDGET_CONFIG.practiceSlug = params.get('practice')!;
}

const container = document.createElement('div');
document.body.appendChild(container);
const root = createRoot(container);
root.render(<ChatWidget config={WIDGET_CONFIG} />);
