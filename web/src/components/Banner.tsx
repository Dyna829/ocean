import type { ReactNode } from "react";

interface BannerProps {
  kind: "error" | "success" | "info";
  children: ReactNode;
  onDismiss?: () => void;
}

export function Banner({ kind, children, onDismiss }: BannerProps) {
  return (
    <div className={`banner banner-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span>{children}</span>
      {onDismiss ? (
        <button type="button" className="banner-close" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      ) : null}
    </div>
  );
}
