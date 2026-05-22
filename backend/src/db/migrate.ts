import 'dotenv/config';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

/**
 * Programmatic migration runner.
 *
 * Used by `npm run db:migrate:js`. The default `npm run db:migrate` invokes
 * `drizzle-kit migrate` (the CLI). This file is the fallback if the CLI is
 * unavailable or behaves unexpectedly across drizzle-kit minor versions.
 */
async function main() {
  const connectionString =
    process.env.DATABASE_URL ?? 'postgres://asl:asl_dev_only@localhost:5432/asl_pilot';

  const __dirname = dirname(fileURLToPath(import.meta.url));
  const migrationsFolder = resolve(__dirname, './migrations');

  const migrationClient = postgres(connectionString, { max: 1 });
  const db = drizzle(migrationClient);

  try {
    await migrate(db, { migrationsFolder });
    console.log('[migrate] migrations applied successfully');
  } finally {
    await migrationClient.end();
  }
}

main().catch((err) => {
  console.error('[migrate] failed:', err);
  process.exit(1);
});
