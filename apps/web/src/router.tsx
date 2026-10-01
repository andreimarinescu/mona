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
import { Unlock } from './routes/Unlock';
import { AuthWatcher } from './shell/AuthWatcher';
import { parseArchiveSearch } from './data/archive';
import { safeNext } from './data/auth';
import { ActivityPage } from './routes/activity/ActivityPage';
import { ArchivePage } from './routes/archive/ArchivePage';
import { ChatPage } from './routes/chat/ChatPage';
import { FoldersPage } from './routes/archive/FoldersPage';
import { DocumentPage } from './routes/document/DocumentPage';
import { parseDocumentSearch } from './routes/document/search';
import { IntakePage } from './routes/intake/IntakePage';
import { EntitiesPage } from './routes/entities/EntitiesPage';
import { HomePage } from './routes/home/HomePage';
import { ReviewPage } from './routes/review/ReviewPage';
import { RuleDetail } from './routes/rules/RuleDetail';
import { RulesPage } from './routes/rules/RulesPage';
import { SettingsPage } from './routes/settings/SettingsPage';

const rootRoute = createRootRoute({
  component: () => (
    <>
      <SkipLink />
      <LanguageSync />
      <AuthWatcher />
      <Outlet />
    </>
  ),
  notFoundComponent: NotFound,
});

const shellRoute = createRoute({ getParentRoute: () => rootRoute, id: 'shell', component: AppShell, notFoundComponent: NotFound });

const screen = <const TPath extends string>(path: TPath, component: () => React.JSX.Element) =>
  createRoute({ getParentRoute: () => shellRoute, path, component });

const archiveRoute = createRoute({ getParentRoute: () => shellRoute, path: '/archive', validateSearch: parseArchiveSearch, component: ArchivePage });
const documentRoute = createRoute({ getParentRoute: () => shellRoute, path: '/documents/$documentId', validateSearch: parseDocumentSearch, component: DocumentPage });

const shellRoutes = [
  screen('/', HomePage),
  screen('/chat', ChatPage),
  screen('/chat/$conversationId', ChatPage),
  screen('/intake', IntakePage),
  screen('/review', ReviewPage),
  screen('/review/$documentId', ReviewPage),
  archiveRoute,
  screen('/archive/folders/$', FoldersPage),
  documentRoute,
  screen('/rules', RulesPage),
  screen('/rules/$ruleId', RuleDetail),
  screen('/entities', () => <EntitiesPage tab="entities" />),
  screen('/entities/categories/$categoryId', () => <EntitiesPage tab="categories" />),
  screen('/activity', ActivityPage),
  screen('/settings', SettingsPage),
];

const unlockRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/unlock',
  validateSearch: (search: Record<string, unknown>): { next?: string } => (typeof search.next === 'string' && safeNext(search.next) !== '/' ? { next: safeNext(search.next) } : {}),
  component: Unlock,
});

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
