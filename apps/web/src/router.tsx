import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
} from '@tanstack/react-router';
import { LanguageSync } from './shell/LanguageSync';
import { AppShell } from './shell/AppShell';
import { SkipLink } from './shell/SkipLink';
import { NotFound } from './routes/NotFound';
import { Placeholder } from './routes/Placeholder';
import { Unlock } from './routes/Unlock';
import { parseArchiveSearch } from './data/archive';
import { ActivityPage } from './routes/activity/ActivityPage';
import { ArchivePage } from './routes/archive/ArchivePage';
import { ChatPage } from './routes/chat/ChatPage';
import { FoldersPage } from './routes/archive/FoldersPage';
import { DocumentPage } from './routes/document/DocumentPage';
import { parseDocumentSearch } from './routes/document/search';
import { IntakePage } from './routes/intake/IntakePage';
import { ReviewPage } from './routes/review/ReviewPage';

const rootRoute = createRootRoute({
  component: () => (
    <>
      <SkipLink />
      <LanguageSync />
      <Outlet />
    </>
  ),
  notFoundComponent: NotFound,
});

const shellRoute = createRoute({ getParentRoute: () => rootRoute, id: 'shell', component: AppShell, notFoundComponent: NotFound });

const page = <const TPath extends string>(path: TPath, title: string) =>
  createRoute({ getParentRoute: () => shellRoute, path, component: () => <Placeholder title={title} /> });

const screen = <const TPath extends string>(path: TPath, component: () => React.JSX.Element) =>
  createRoute({ getParentRoute: () => shellRoute, path, component });

const archiveRoute = createRoute({ getParentRoute: () => shellRoute, path: '/archive', validateSearch: parseArchiveSearch, component: ArchivePage });
const documentRoute = createRoute({ getParentRoute: () => shellRoute, path: '/documents/$documentId', validateSearch: parseDocumentSearch, component: DocumentPage });

const shellRoutes = [
  page('/', 'nav.home'),
  screen('/chat', ChatPage),
  screen('/chat/$conversationId', ChatPage),
  screen('/intake', IntakePage),
  screen('/review', ReviewPage),
  screen('/review/$documentId', ReviewPage),
  archiveRoute,
  screen('/archive/folders/$', FoldersPage),
  documentRoute,
  page('/rules', 'nav.rules'),
  page('/rules/$ruleId', 'nav.rules'),
  page('/entities', 'nav.entities'),
  page('/entities/categories/$categoryId', 'nav.entities'),
  screen('/activity', ActivityPage),
  page('/settings', 'nav.settings'),
];

const unlockRoute = createRoute({ getParentRoute: () => rootRoute, path: '/unlock', component: Unlock });

const devRoutes = import.meta.env.DEV
  ? [
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/ds',
        component: lazyRouteComponent(() => import('./routes/dev/DsGallery'), 'DsGallery'),
      }),
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/chat',
        validateSearch: (search: Record<string, unknown>): { c?: string; route?: string; summary?: string } => {
          const out: { c?: string; route?: string; summary?: string } = {};
          for (const key of ['c', 'route', 'summary'] as const) {
            if (typeof search[key] === 'string') out[key] = search[key];
          }
          return out;
        },
        component: lazyRouteComponent(() => import('./routes/dev/Chat'), 'Chat'),
      }),
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/pdf',
        validateSearch: (search: Record<string, unknown>): { file?: string; page?: number; q?: string } => {
          const out: { file?: string; page?: number; q?: string } = {};
          if (typeof search.file === 'string' && search.file.startsWith('/')) out.file = search.file;
          if (typeof search.q === 'string') out.q = search.q;
          const page = Number(search.page);
          if (Number.isInteger(page) && page >= 1) out.page = page;
          return out;
        },
        component: lazyRouteComponent(() => import('./routes/dev/PdfFind'), 'PdfFind'),
      }),
    ]
  : [];

export const routeTree = rootRoute.addChildren([shellRoute.addChildren(shellRoutes), unlockRoute, ...devRoutes]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
