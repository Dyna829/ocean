export type LogLevel = "debug" | "info" | "warn" | "error";

const ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };
const STORAGE_KEY = "cca.logLevel";

function isLevel(value: string | null | undefined): value is LogLevel {
  return value === "debug" || value === "info" || value === "warn" || value === "error";
}

const fallback: LogLevel = import.meta.env.DEV ? "debug" : "info";

function readInitialLevel(): LogLevel {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLevel(stored)) return stored;
  } catch {
    // localStorage can be unavailable; fall through to the build-time default.
  }
  const envLevel = import.meta.env.VITE_LOG_LEVEL;
  return isLevel(envLevel) ? envLevel : fallback;
}

let currentLevel = readInitialLevel();

export function getLogLevel(): LogLevel {
  return currentLevel;
}

/** Change the console verbosity at runtime, e.g. `setLogLevel("debug")` in devtools. */
export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
  try {
    window.localStorage.setItem(STORAGE_KEY, level);
  } catch {
    // Persisting the level is best effort.
  }
  console.info("[info] log.level_changed", { level });
}

type Fields = Record<string, unknown>;

function emit(level: LogLevel, event: string, fields?: Fields): void {
  if (ORDER[level] < ORDER[currentLevel]) return;
  const entry = { ts: new Date().toISOString(), level, event, ...fields };
  const label = `[${level}] ${event}`;
  if (level === "debug") console.debug(label, entry);
  else if (level === "info") console.info(label, entry);
  else if (level === "warn") console.warn(label, entry);
  else console.error(label, entry);
}

export const log = {
  debug: (event: string, fields?: Fields) => emit("debug", event, fields),
  info: (event: string, fields?: Fields) => emit("info", event, fields),
  warn: (event: string, fields?: Fields) => emit("warn", event, fields),
  error: (event: string, fields?: Fields) => emit("error", event, fields),
};

declare global {
  interface Window {
    setLogLevel?: (level: LogLevel) => void;
    getLogLevel?: () => LogLevel;
  }
}

// Handy in the browser console during a demo: setLogLevel("debug").
window.setLogLevel = setLogLevel;
window.getLogLevel = getLogLevel;
