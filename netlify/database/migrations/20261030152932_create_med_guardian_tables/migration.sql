CREATE TABLE "commands" (
	"id" serial PRIMARY KEY,
	"device_id" text NOT NULL,
	"type" text NOT NULL,
	"occurrence" text NOT NULL,
	"created_at" bigint NOT NULL,
	"expires_at" bigint NOT NULL,
	"delivered_at" bigint,
	"acked_at" bigint,
	"result" text,
	"dispense_lock" boolean
);
--> statement-breakpoint
CREATE TABLE "devices" (
	"id" text PRIMARY KEY,
	"key_hash" text NOT NULL,
	"schedule" jsonb NOT NULL,
	"schedule_version" integer DEFAULT 1 NOT NULL,
	"telemetry" jsonb,
	"last_seen" bigint,
	"created_at" bigint NOT NULL
);
--> statement-breakpoint
CREATE TABLE "events" (
	"id" serial PRIMARY KEY,
	"device_id" text NOT NULL,
	"event_uid" text NOT NULL,
	"occurrence" text NOT NULL,
	"kind" text NOT NULL,
	"detail" text DEFAULT '' NOT NULL,
	"at" bigint NOT NULL
);
--> statement-breakpoint
CREATE TABLE "notes" (
	"id" serial PRIMARY KEY,
	"device_id" text NOT NULL,
	"occurrence" text NOT NULL,
	"kind" text NOT NULL,
	"note" text NOT NULL,
	"at" bigint NOT NULL
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"token_hash" text PRIMARY KEY,
	"expires_at" bigint NOT NULL,
	"created_at" bigint NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX "commands_one_dispense_idx" ON "commands" ("device_id","occurrence","dispense_lock");--> statement-breakpoint
CREATE INDEX "commands_device_idx" ON "commands" ("device_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "events_device_uid_idx" ON "events" ("device_id","event_uid");--> statement-breakpoint
CREATE INDEX "events_device_at_idx" ON "events" ("device_id","at");--> statement-breakpoint
ALTER TABLE "commands" ADD CONSTRAINT "commands_device_id_devices_id_fkey" FOREIGN KEY ("device_id") REFERENCES "devices"("id") ON DELETE CASCADE;--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_device_id_devices_id_fkey" FOREIGN KEY ("device_id") REFERENCES "devices"("id") ON DELETE CASCADE;--> statement-breakpoint
ALTER TABLE "notes" ADD CONSTRAINT "notes_device_id_devices_id_fkey" FOREIGN KEY ("device_id") REFERENCES "devices"("id") ON DELETE CASCADE;