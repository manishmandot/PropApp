"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">PropApp is temporarily unavailable</h1>
      <p className="text-ink-2">We couldn&apos;t load suburb data just now. Please try again in a minute.</p>
      <button type="button" onClick={reset} className="rounded-md border border-line px-4 py-1.5">
        Try again
      </button>
    </div>
  );
}
