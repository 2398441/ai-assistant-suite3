"use client";

import { Inter } from "next/font/google";
import { useEffect } from "react";
import "./globals.css";

// ── Client-side error logging ─────────────────────────────────────────────────
// Import the logger that ships browser errors to the backend log endpoint.
// To disable: comment out this import and the useEffect block below.
import { logClientError } from "@/lib/logger";
// ── End client-side error logging ────────────────────────────────────────────

const inter = Inter({ subsets: ["latin"] });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // ── Runtime error capture ───────────────────────────────────────────────────
  // Attaches global handlers to catch unhandled JS errors and promise rejections
  // in the browser and forward them to the backend log file.
  // To disable: comment out this entire useEffect block.
  useEffect(() => {
    // Catch synchronous errors (e.g. null reference, type errors)
    const handleError = (
      event: ErrorEvent
    ) => {
      logClientError(
        `${event.message} (${event.filename}:${event.lineno})`,
        "window.onerror"
      );
    };

    // Catch unhandled promise rejections (e.g. failed fetch, async errors)
    const handleRejection = (event: PromiseRejectionEvent) => {
      logClientError(event.reason, "unhandledrejection");
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);

    // Clean up listeners when the component unmounts
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);
  // ── End runtime error capture ───────────────────────────────────────────────

  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} h-full bg-gray-50 text-gray-900`}>
        {children}
      </body>
    </html>
  );
}
