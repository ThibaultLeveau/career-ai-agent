type Theme = "light" | "dark";

const storageKey = "career-theme";
const changeEvent = "career-theme-change";
let preference: Theme | null = null;
let initialized = false;

function validTheme(value: string | null): Theme | null {
  return value === "light" || value === "dark" ? value : null;
}

// Runs in the document head before content can paint, independently of hydration.
export const themeInitScript = `(function(){var t;try{t=localStorage.getItem("${storageKey}")}catch(e){}document.documentElement.dataset.theme=t==="light"||t==="dark"?t:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"})()`;

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function serverTheme(): null {
  return null;
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(changeEvent));
}

export function subscribeTheme(listener: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  if (!initialized) {
    try { preference = validTheme(localStorage.getItem(storageKey)); } catch { /* Keep the in-memory preference when storage is unavailable. */ }
    initialized = true;
  }
  const systemTheme = () => media.matches ? "dark" : "light";
  const onSystemChange = () => { if (!preference) applyTheme(systemTheme()); };
  const onStorage = (event: StorageEvent) => {
    if (event.key !== storageKey && event.key !== null) return;
    preference = validTheme(event.newValue);
    applyTheme(preference ?? systemTheme());
  };
  window.addEventListener(changeEvent, listener);
  media.addEventListener("change", onSystemChange);
  window.addEventListener("storage", onStorage);
  applyTheme(preference ?? systemTheme());
  return () => {
    window.removeEventListener(changeEvent, listener);
    media.removeEventListener("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function toggleTheme() {
  preference = currentTheme() === "dark" ? "light" : "dark";
  try { localStorage.setItem(storageKey, preference); } catch { /* The switch still works for this page session. */ }
  applyTheme(preference);
}
