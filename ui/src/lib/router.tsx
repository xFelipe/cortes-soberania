import { createRouter, createRoute, createRootRoute, Navigate } from "@tanstack/react-router";
import RootLayout from "@/components/layout/RootLayout";
import InboxPage from "@/routes/index";
import BibliotecaPage from "@/routes/biblioteca";
import OperacaoPage from "@/routes/operacao";
import StatsPage from "@/routes/stats";
import SettingsPage from "@/routes/settings";
import ClipReviewPage from "@/routes/clip-review";

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => <Navigate to="/inbox" />,
});

const inboxRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inbox",
  component: InboxPage,
});

const bibliotecaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/biblioteca",
  component: BibliotecaPage,
});

const operacaoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/operacao",
  component: OperacaoPage,
});

const statsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/stats",
  component: StatsPage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsPage,
});

const clipReviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/clip-review/$clipId",
  component: ClipReviewPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  inboxRoute,
  bibliotecaRoute,
  operacaoRoute,
  statsRoute,
  settingsRoute,
  clipReviewRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
