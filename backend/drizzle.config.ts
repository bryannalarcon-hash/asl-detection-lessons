/**
 * Drizzle Kit configuration for the ASL Pilot Postgres database. Points the
 * migration tooling at the schema in src/db/schema.ts and the migrations output
 * folder, using DATABASE_URL (or the local dev fallback) for connection.
 */
import 'dotenv/config';
import type { Config } from 'drizzle-kit';

export default {
  schema: './src/db/schema.ts',
  out: './src/db/migrations',
  dialect: 'postgresql',
  dbCredentials: {
    url: process.env.DATABASE_URL ?? 'postgres://asl:asl_dev_only@localhost:5432/asl_pilot',
  },
  verbose: true,
  strict: true,
} satisfies Config;
