import { Outlet, useRouterState } from '@tanstack/react-router';
import { useHeartbeat } from '../data/auth';
import { ChatPanel } from './ChatPanel';
import { MobileTabBar } from './MobileTabBar';
import { Sidebar } from './Sidebar';
import { ToastRegion } from './ToastRegion';
import { useShellShortcuts } from './shortcuts';

export function AppShell() {
  const home = useRouterState({ select: (s) => s.location.pathname === '/' });
  useShellShortcuts(home);
  useHeartbeat();
  return (
    <div className="min-h-screen bg-bg font-ui text-text lg:flex">
      <Sidebar />
      <main id="main-content" className="min-w-0 flex-1 pb-24 outline-none lg:pb-0">
        <Outlet />
      </main>
      <MobileTabBar />
      <ChatPanel />
      <ToastRegion />
    </div>
  );
}
