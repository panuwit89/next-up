import { ChartLineUp, MonitorPlay } from "@phosphor-icons/react";

import AnimePage from "./anime/AnimePage.jsx";
import FinancePage from "./finance/FinancePage.jsx";
import Logo from "./components/Logo.jsx";
import { ToastProvider } from "./components/Toast.jsx";
import { useRoute } from "./lib/hooks.js";

// Change here and in index.html's <title> to rename the app.
const APP_NAME = "NextUp";

const TABS = [
  { id: "anime", label: "Anime", icon: MonitorPlay },
  { id: "finance", label: "Finance", icon: ChartLineUp },
];

/**
 * App shell. Everything outside the content slot — header, tab bar, page
 * padding, max width — is identical for both tabs; only the content density
 * differs. Tabs are real links so every view is deep-linkable and the browser
 * back button behaves.
 */
export default function App() {
  const { tab, param, navigate } = useRoute();

  return (
    <ToastProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-[70] focus:rounded-control focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      <div className="min-h-dvh">
        <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur-xl">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
            <a
              href="#/anime"
              aria-label={`${APP_NAME} — home`}
              className="flex shrink-0 items-center gap-2 rounded-control transition-opacity duration-150 hover:opacity-80"
            >
              <Logo size={26} />
              <span className="hidden text-sm font-semibold tracking-tight text-fg sm:inline">
                {APP_NAME}
              </span>
            </a>

            <nav aria-label="Sections" className="flex items-center gap-1">
              {TABS.map(({ id, label, icon: Icon }) => {
                const active = tab === id;
                return (
                  <a
                    key={id}
                    href={`#/${id}`}
                    aria-current={active ? "page" : undefined}
                    className={[
                      "touch-target relative flex items-center gap-2 rounded-control px-3 py-2",
                      "text-sm font-medium transition-colors duration-150",
                      active
                        ? "bg-surface-2 text-fg"
                        : "text-fg-subtle hover:bg-surface/70 hover:text-fg-muted",
                    ].join(" ")}
                  >
                    <Icon
                      size={17}
                      weight={active ? "fill" : "regular"}
                      aria-hidden="true"
                      className={active ? "text-primary-fg" : undefined}
                    />
                    {label}
                    {active ? (
                      <span
                        aria-hidden="true"
                        className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-primary-fg"
                      />
                    ) : null}
                  </a>
                );
              })}
            </nav>
          </div>
        </header>

        <main id="main" className="mx-auto max-w-7xl px-4 pt-6 pb-16 sm:px-6">
          {tab === "finance" ? (
            <FinancePage
              openSymbol={param}
              onOpenSymbol={(symbol) => navigate("finance", symbol)}
            />
          ) : (
            <AnimePage
              openAnimeId={param ? Number(param) : null}
              onOpenAnime={(animeId, morphFrom) => navigate("anime", animeId, { morphFrom })}
            />
          )}
        </main>
      </div>
    </ToastProvider>
  );
}
