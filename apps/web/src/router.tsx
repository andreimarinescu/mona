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

const shellRoutes = [
  page('/', 'nav.home'),
  page('/chat', 'nav.chat'),
  page('/chat/$conversationId', 'nav.chat'),
  page('/intake', 'nav.intake'),
  page('/review', 'nav.review'),
  page('/review/$documentId', 'nav.review'),
  page('/archive', 'nav.archive'),
  page('/archive/folders/$', 'nav.archive'),
  page('/documents/$documentId', 'nav.document'),
  page('/rules', 'nav.rules'),
  page('/rules/$ruleId', 'nav.rules'),
  page('/entities', 'nav.entities'),
  page('/entities/categories/$categoryId', 'nav.entities'),
  page('/activity', 'nav.activity'),
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
        validateSearch: (search: Record<string, unknown>): { c?: string } =>
          typeof search.c === 'string' ? { c: search.c } : {},
        component: lazyRouteComponent(() => import('./routes/dev/Chat'), 'Chat'),
      }),
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/pdf',
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
