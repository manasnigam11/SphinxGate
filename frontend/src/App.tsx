import React, { useState, useEffect } from "react";
import { Sidebar } from "./components/layout/Sidebar";
import { Navbar } from "./components/layout/Navbar";
import { Dashboard } from "./pages/Dashboard";
import { Playground } from "./pages/Playground";
import { Providers } from "./pages/Providers";
import { Requests } from "./pages/Requests";
import { Logs } from "./pages/Logs";
import { Analytics } from "./pages/Analytics";
import { ProviderHealth } from "./pages/ProviderHealth";
import { Policies } from "./pages/Policies";
import { CircuitBreakers } from "./pages/CircuitBreakers";
import { FaultInjection } from "./pages/FaultInjection";
import { Incidents } from "./pages/Incidents";
import { Copilot } from "./pages/Copilot";

type Theme = "light" | "dark";

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("ng-theme") as Theme) ?? "light";
    } catch {
      return "dark";
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    try {
      localStorage.setItem("ng-theme", theme);
    } catch { }
  }, [theme]);

  return [theme, setTheme] as const;
}

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [theme, setTheme] = useTheme();
  const [environment, setEnvironment] = useState("production");

  function handleThemeToggle() {
    setTheme(t => t === "dark" ? "light" : "dark");
  }

  function handleThemeChange(t: "light" | "dark" | "system") {
    if (t === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(prefersDark ? "dark" : "light");
    } else {
      setTheme(t);
    }
  }

  function renderPage() {
    switch (page) {
      case "dashboard": return <Dashboard />;
      case "playground": return <Playground />;
      case "providers": return <Providers />;
      case "requests": return <Requests />;
      case "logs": return <Logs />;
      case "analytics": return <Analytics />;
      case "health": return <ProviderHealth />;
      case "policies": return <Policies />;
      case "circuit-breakers": return <CircuitBreakers />;
      case "fault-injection": return <FaultInjection />;
      case "incidents": return <Incidents />;
      case "copilot": return <Copilot />;
      default: return <Dashboard />;
    }
  }

  return (
    <div className="flex h-screen bg-[var(--background)] overflow-hidden">
      <Sidebar active={page} onNav={setPage} />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Navbar
          page={page}
          theme={theme}
          onThemeToggle={handleThemeToggle}
          environment={environment}
          onEnvironmentChange={setEnvironment}
        />
        <main className="flex-1 overflow-y-auto">
          {renderPage()}
        </main>
      </div>
    </div>
  );
}
