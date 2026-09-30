import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
} from '@tanstack/react-router';
import { Home } from './routes/Home';

const rootRoute = createRootRoute({ component: Outlet });

const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home });

const devRoutes = import.meta.env.DEV
  ? [
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/ds',
        component: lazyRouteComponent(() => import('./routes/dev/DsGallery'), 'DsGallery'),
      }),
      createRoute({
        getParentRoute: () => rootRoute,
        path: '/dev/pdf',
        component: lazyRouteComponent(() => import('./routes/dev/PdfFind'), 'PdfFind'),
      }),
    ]
  : [];

export const routeTree = rootRoute.addChildren([homeRoute, ...devRoutes]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
