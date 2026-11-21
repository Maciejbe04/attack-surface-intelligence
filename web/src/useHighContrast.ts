import { useEffect, useState } from "react";

const STORAGE_KEY = "surfacex.a11y.highContrast";

export function useHighContrast() {
  const [highContrast, setHighContrast] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("theme-high-contrast", highContrast);
    document.documentElement.dataset.contrast = highContrast ? "high" : "standard";
    try {
      localStorage.setItem(STORAGE_KEY, highContrast ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [highContrast]);

  function toggleHighContrast() {
    setHighContrast((prev) => !prev);
  }

  return { highContrast, toggleHighContrast };
}
