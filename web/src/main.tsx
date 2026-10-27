import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { log } from "./log";
import "./styles.css";

const container = document.getElementById("root");
if (!container) throw new Error("Root container missing");

window.addEventListener("unhandledrejection", (event) => {
  log.error("window.unhandled_rejection", { reason: String(event.reason) });
});

window.addEventListener("error", (event) => {
  log.error("window.error", {
    message: event.message,
    source: event.filename,
    line: event.lineno,
  });
});

log.info("app.boot", { mode: import.meta.env.MODE });

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
