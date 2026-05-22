CREATE TYPE "public"."drill_type" AS ENUM('handshape', 'movement', 'sign');--> statement-breakpoint
CREATE TYPE "public"."mastery_level" AS ENUM('new', 'learning', 'familiar', 'known', 'mastered');--> statement-breakpoint
CREATE TYPE "public"."rep_outcome" AS ENUM('pass', 'fail', 'skip');--> statement-breakpoint
CREATE TYPE "public"."rep_source" AS ENUM('cv', 'self-report', 'dev');--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "drill_definition" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"sign_id" uuid NOT NULL,
	"drill_type" "drill_type" NOT NULL,
	"target_string" text NOT NULL,
	"order_index" integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "lesson" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"slug" text NOT NULL,
	"title" text NOT NULL,
	"category" text NOT NULL,
	"sign_count" integer NOT NULL,
	"order_index" integer NOT NULL,
	CONSTRAINT "lesson_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "mastery_state" (
	"user_id" uuid NOT NULL,
	"sign_id" uuid NOT NULL,
	"level" "mastery_level" DEFAULT 'new' NOT NULL,
	"last_practiced_at" timestamp with time zone,
	"advance_count" integer DEFAULT 0 NOT NULL,
	"regress_count" integer DEFAULT 0 NOT NULL,
	CONSTRAINT "mastery_state_user_id_sign_id_pk" PRIMARY KEY("user_id","sign_id")
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "notification_pref" (
	"user_id" uuid PRIMARY KEY NOT NULL,
	"daily_reminder_time" time,
	"weekly_summary_enabled" boolean DEFAULT true NOT NULL,
	"streak_at_risk_enabled" boolean DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "rep_log" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" uuid NOT NULL,
	"sign_id" uuid NOT NULL,
	"drill_type" "drill_type" NOT NULL,
	"outcome" "rep_outcome" NOT NULL,
	"source" "rep_source" NOT NULL,
	"hint_requested" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "sign" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"slug" text NOT NULL,
	"english_gloss" text NOT NULL,
	"lesson_id" uuid NOT NULL,
	"order_index" integer NOT NULL,
	CONSTRAINT "sign_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "streak_state" (
	"user_id" uuid PRIMARY KEY NOT NULL,
	"current_streak_days" integer DEFAULT 0 NOT NULL,
	"longest_streak_days" integer DEFAULT 0 NOT NULL,
	"freezes_remaining" integer DEFAULT 2 NOT NULL,
	"last_practice_date" date
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "user" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" text NOT NULL,
	"display_name" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"email_verified_at" timestamp with time zone
);
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "drill_definition" ADD CONSTRAINT "drill_definition_sign_id_sign_id_fk" FOREIGN KEY ("sign_id") REFERENCES "public"."sign"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "mastery_state" ADD CONSTRAINT "mastery_state_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "mastery_state" ADD CONSTRAINT "mastery_state_sign_id_sign_id_fk" FOREIGN KEY ("sign_id") REFERENCES "public"."sign"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "notification_pref" ADD CONSTRAINT "notification_pref_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "rep_log" ADD CONSTRAINT "rep_log_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "rep_log" ADD CONSTRAINT "rep_log_sign_id_sign_id_fk" FOREIGN KEY ("sign_id") REFERENCES "public"."sign"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "sign" ADD CONSTRAINT "sign_lesson_id_lesson_id_fk" FOREIGN KEY ("lesson_id") REFERENCES "public"."lesson"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "streak_state" ADD CONSTRAINT "streak_state_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "rep_log_user_date_idx" ON "rep_log" USING btree ("user_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "user_email_lower_unique" ON "user" USING btree (lower("email"));