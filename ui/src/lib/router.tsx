import { createRouter, createRoute, createRootRoute, Navigate } from "@tanstack/react-router";
import RootLayout from "@/components/layout/RootLayout";
import InboxPage from "@/routes/index";
import BibliotecaPage from "@/routes/biblioteca";
import OperacaoLayout from "@/routes/operacao/layout";
import PipelinePage from "@/routes/operacao/pipeline";
import DiscoverPage from "@/routes/operacao/discover";
import CanaisPage from "@/routes/operacao/canais";
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
  component: OperacaoLayout,
});

const operacaoIndexRoute = createRoute({
  getParentRoute: () => operacaoRoute,
  path: "/",
  component: () => <Navigate to="/operacao/pipeline" />,
});

const pipelineRoute = createRoute({
  getParentRoute: () => operacaoRoute,
  path: "/pipeline",
  component: PipelinePage,
});

const discoverRoute = createRoute({
  getParentRoute: () => operacaoRoute,
  path: "/discover",
  component: DiscoverPage,
});

const canaisRoute = createRoute({
  getParentRoute: () => operacaoRoute,
  path: "/canais",
  component: CanaisPage,
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
  operacaoRoute.addChildren([operacaoIndexRoute, pipelineRoute, discoverRoute, canaisRoute]),
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
