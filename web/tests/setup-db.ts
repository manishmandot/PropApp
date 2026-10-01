/**
 * Creates a throwaway Postgres database with every Supabase migration applied (and
 * optionally the web seed), and returns a connection URL for the read-only `web_reader`
 * role. Used by the DB tests and by Playwright's global setup.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import postgres from "postgres";

const ROOT = path.resolve(__dirname, "..", "..");
const MIGRATIONS = path.join(ROOT, "supabase", "migrations");
const SEED = path.join(__dirname, "seed.sql");
const ADMIN_URL =
  process.env.TEST_DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/postgres";

export type TestDatabase = { url: string; adminUrl: string; drop: () => Promise<void> };

function withDatabase(url: string, name: string, user?: string): string {
  const u = new URL(url);
  u.pathname = `/${name}`;
  if (user) {
    u.username = user;
    u.password = user;
  }
  return u.toString();
}

export async function createTestDatabase(name: string, seed: boolean): Promise<TestDatabase> {
  const admin = postgres(ADMIN_URL, { max: 1, onnotice: () => {} });
  await admin.unsafe(`drop database if exists "${name}" with (force)`);
  await admin.unsafe(`create database "${name}" template template0`);
  await admin.end();

  const adminUrl = withDatabase(ADMIN_URL, name);
  const db = postgres(adminUrl, { max: 1, onnotice: () => {} });
  for (const file of readdirSync(MIGRATIONS).filter((f) => f.endsWith(".sql")).sort()) {
    await db.unsafe(readFileSync(path.join(MIGRATIONS, file), "utf8"));
  }
  if (seed) await db.unsafe(readFileSync(SEED, "utf8"));
  await db.unsafe("alter role web_reader with login password 'web_reader'");
  await db.end();

  return {
    url: withDatabase(ADMIN_URL, name, "web_reader"),
    adminUrl,
    drop: async () => {
      const a = postgres(ADMIN_URL, { max: 1, onnotice: () => {} });
      await a.unsafe(`drop database if exists "${name}" with (force)`);
      await a.end();
    },
  };
}
