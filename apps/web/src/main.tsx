import '@design/mona-handoff/tokens.css';
import '@mona/ui';
import './styles/app.css';
import './i18n';
import './dev-hooks';

import { RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppProviders } from './AppProviders';
import { router } from './router';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
