import { useEffect, useState } from "react";

const STORAGE_KEY = "surfacex.theme.dark";

function readStored(): boolean | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "1") return true;
    if (value === "0") return false;
  } catch {
    /* ignore */
  }
  return null;
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches === true
  );
}

export function useDarkMode() {
  const [darkMode, setDarkMode] = useState(() => readStored() ?? systemPrefersDark());

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", darkMode);
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    try {
      localStorage.setItem(STORAGE_KEY, darkMode ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [darkMode]);

  function toggleDarkMode() {
    setDarkMode((prev) => !prev);
  }

  return { darkMode, toggleDarkMode };
}
