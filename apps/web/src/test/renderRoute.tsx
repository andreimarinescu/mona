import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { queryWrapper } from './mockApi';

/** Renders `ui` inside a memory router (every path resolves) with the query client and app state a screen needs. */
export async function renderRoute(ui: ReactNode, url = '/', wrap: (children: ReactNode) => ReactNode = (children) => children) {
  const { client, Wrapper } = queryWrapper();
  const root = createRootRoute({
    component: () => (
      <Wrapper>
        {wrap(ui)}
        <Outlet />
      </Wrapper>
    ),
  });
  const any = createRoute({ getParentRoute: () => root, path: '$', component: () => null });
  const index = createRoute({ getParentRoute: () => root, path: '/', component: () => null });
  const router = createRouter({ routeTree: root.addChildren([index, any]), history: createMemoryHistory({ initialEntries: [url] }) });
  await router.load();
  return { client, router, ...render(<RouterProvider router={router} />) };
}
