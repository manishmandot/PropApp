import { execFileSync, spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { EMPTY_PORT, SEEDED_PORT } from "../../playwright.config";
import { createTestDatabase } from "../setup-db";

const WEB = path.resolve(__dirname, "..", "..");
export const STATE_FILE = path.join(WEB, ".e2e-state.json");

async function waitFor(url: string, timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      if ((await fetch(url)).status < 500) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`server at ${url} did not start`);
}

function buildAndStart(databaseUrl: string, distDir: string, port: number) {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    DATABASE_URL: databaseUrl,
    NEXT_DIST_DIR: distDir,
    NEXT_TELEMETRY_DISABLED: "1",
  };
  delete env.NEXT_PUBLIC_TILES_URL;
  execFileSync("npx", ["next", "build"], { cwd: WEB, env, stdio: "inherit" });
  const server = spawn("npx", ["next", "start", "-p", String(port)], { cwd: WEB, env, stdio: "ignore", detached: true });
  server.unref();
  return server.pid!;
}

export default async function globalSetup() {
  const seeded = await createTestDatabase("propapp_web_e2e", true);
  const empty = await createTestDatabase("propapp_web_e2e_empty", false);
  const pids = [
    buildAndStart(seeded.url, ".next-e2e", SEEDED_PORT),
    buildAndStart(empty.url, ".next-e2e-empty", EMPTY_PORT),
  ];
  writeFileSync(STATE_FILE, JSON.stringify({ pids }));
  await waitFor(`http://localhost:${SEEDED_PORT}/`);
  await waitFor(`http://localhost:${EMPTY_PORT}/`);
}
