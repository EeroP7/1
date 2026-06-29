"use client";

import { useState } from "react";

export function EmailCapture({ compact = false }: { compact?: boolean }) {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.includes("@")) return;
    // In production, POST to your ESP (Klaviyo / ConvertKit / Beehiiv).
    // Stored locally here so the flow is demonstrable without keys.
    try {
      const list = JSON.parse(localStorage.getItem("lumora-emails") || "[]");
      list.push({ email, at: new Date().toISOString() });
      localStorage.setItem("lumora-emails", JSON.stringify(list));
    } catch {
      /* ignore */
    }
    setDone(true);
  }

  if (done)
    return (
      <p className="text-sm text-sage">
        You&apos;re in. Check your inbox for your free planner + code.
      </p>
    );

  return (
    <form
      onSubmit={submit}
      className={compact ? "flex gap-2" : "flex flex-col gap-3 sm:flex-row"}
    >
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@email.com"
        className="w-full rounded-full border border-ink/20 bg-white px-4 py-3 text-sm outline-none focus:border-terracotta"
      />
      <button className="btn-accent whitespace-nowrap" type="submit">
        {compact ? "Get it" : "Send my free planner"}
      </button>
    </form>
  );
}
