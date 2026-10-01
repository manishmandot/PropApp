import { existsSync, readFileSync, rmSync } from "node:fs";
import postgres from "postgres";
import { STATE_FILE } from "./global-setup";

export default async function globalTeardown() {
  if (existsSync(STATE_FILE)) {
    const { pids } = JSON.parse(readFileSync(STATE_FILE, "utf8")) as { pids: number[] };
    for (const pid of pids) {
      try {
        process.kill(-pid, "SIGTERM"); // the whole `npx next start` process group
      } catch {
        // already gone
      }
    }
    rmSync(STATE_FILE);
  }
  const admin = postgres(
    process.env.TEST_DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/postgres",
    { max: 1, onnotice: () => {} },
  );
  for (const name of ["propapp_web_e2e", "propapp_web_e2e_empty"]) {
    await admin.unsafe(`drop database if exists "${name}" with (force)`);
  }
  await admin.end();
}
