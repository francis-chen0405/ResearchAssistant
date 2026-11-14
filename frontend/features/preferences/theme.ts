import { useCallback, useSyncExternalStore } from "react";
import { THEME_STORAGE_KEY as KEY } from "./theme-script";

export type ThemeChoice = "system" | "light" | "dark";

// Appearance is a per-device convenience, not a research setting. Only an
// explicit Light/Dark choice is stored; System leaves browser storage empty.
const listeners = new Set<() => void>();

function read(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const theme = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    read,
    () => "system" as ThemeChoice,
  );
  const setTheme = useCallback((choice: ThemeChoice) => {
    try {
      if (choice === "system") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, choice);
    } catch {
      // Storage can be unavailable; the choice still applies to this window.
    }
    applyTheme(choice);
    listeners.forEach((listener) => listener());
  }, []);
  return [theme, setTheme];
}
