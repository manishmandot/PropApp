import Link from "next/link";

export default function NotFound() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-ink-2">
        That suburb or page doesn&apos;t exist. Try the <Link href="/suburbs">suburb finder</Link>.
      </p>
    </div>
  );
}
