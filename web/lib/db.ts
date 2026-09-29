import "server-only";
import postgres, { type Sql } from "postgres";

let client: Sql | null = null;
let override: string | null = null;

/** The server's read-only database client (role web_reader), created on first use. */
export function db(): Sql {
  if (!client) {
    const url = override ?? process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set");
    // prepare: false keeps it compatible with the Supabase transaction pooler.
    client = postgres(url, {
      max: 5,
      prepare: false,
      idle_timeout: 20,
      connect_timeout: 5,
      onnotice: () => {},
    });
  }
  return client;
}

/** Tests only: point the client at another database (null closes it). */
export async function useDatabase(url: string | null): Promise<void> {
  const previous = client;
  client = null;
  override = url;
  await previous?.end({ timeout: 5 });
}
