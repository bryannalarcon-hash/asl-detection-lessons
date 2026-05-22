import 'dotenv/config';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import * as schema from './schema';

const connectionString =
  process.env.DATABASE_URL ?? 'postgres://asl:asl_dev_only@localhost:5432/asl_pilot';

export const sql = postgres(connectionString, { max: 10 });
export const db = drizzle(sql, { schema });

export type DB = typeof db;
