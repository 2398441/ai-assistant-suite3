"use client";

import { useState } from "react";
import { Spinner, SparkleIcon, GoogleIcon } from "@/components/ui/icons";

interface ConnectButtonProps {
  onConnect: (email: string) => Promise<void>;
  isLoading?: boolean;
}

export function ConnectButton({ onConnect, isLoading }: ConnectButtonProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Please enter a valid Gmail address.");
      return;
    }
    try {
      await onConnect(trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-4">
      {/* Logo / branding */}
      <div className="text-center">
        <div className="flex items-center justify-center w-16 h-16 mx-auto mb-4 rounded-2xl bg-indigo-600 shadow-lg">
          <SparkleIcon className="w-8 h-8 text-white" strokeWidth={1.5} />
        </div>
        <h1 className="text-2xl font-bold text-gray-900">AI Assistant</h1>
        <p className="mt-1 text-sm text-gray-500">
          Gmail &amp; Calendar Integration
        </p>
      </div>

      {/* Connect form */}
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-4">
          Connect your Google Account
        </h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="email"
            placeholder="your@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isLoading}
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
          />
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={isLoading || !email}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Spinner className="animate-spin h-4 w-4" />
                Connecting…
              </>
            ) : (
              <>
                <GoogleIcon className="w-4 h-4" />
                Continue with Google
              </>
            )}
          </button>
        </form>
        <p className="mt-4 text-xs text-gray-400 text-center">
          Your credentials are managed securely by Composio.
          <br />
          We never store your Google password.
        </p>
      </div>
    </div>
  );
}

