import { pgTable, serial, text, integer, bigint, jsonb, boolean, uniqueIndex, index } from "drizzle-orm/pg-core";

// All timestamps are Unix seconds (bigint) to match the dashboard and firmware.

export const sessions = pgTable("sessions", {
  tokenHash: text("token_hash").primaryKey(),
  expiresAt: bigint("expires_at", { mode: "number" }).notNull(),
  createdAt: bigint("created_at", { mode: "number" }).notNull(),
});

export const devices = pgTable("devices", {
  id: text().primaryKey(),
  keyHash: text("key_hash").notNull(),
  schedule: jsonb().$type<Record<"morning" | "afternoon" | "night", string | null>>().notNull(),
  scheduleVersion: integer("schedule_version").notNull().default(1),
  telemetry: jsonb().$type<Record<string, unknown> | null>(),
  lastSeen: bigint("last_seen", { mode: "number" }),
  createdAt: bigint("created_at", { mode: "number" }).notNull(),
});

export const events = pgTable(
  "events",
  {
    id: serial().primaryKey(),
    deviceId: text("device_id").notNull().references(() => devices.id, { onDelete: "cascade" }),
    // Device-generated id so retried uploads are never recorded twice.
    eventUid: text("event_uid").notNull(),
    occurrence: text().notNull(),
    kind: text().notNull(),
    detail: text().notNull().default(""),
    at: bigint({ mode: "number" }).notNull(),
  },
  (t) => [
    uniqueIndex("events_device_uid_idx").on(t.deviceId, t.eventUid),
    index("events_device_at_idx").on(t.deviceId, t.at),
  ],
);

export const notes = pgTable("notes", {
  id: serial().primaryKey(),
  deviceId: text("device_id").notNull().references(() => devices.id, { onDelete: "cascade" }),
  occurrence: text().notNull(),
  kind: text().notNull(),
  note: text().notNull(),
  at: bigint({ mode: "number" }).notNull(),
});

export const commands = pgTable(
  "commands",
  {
    id: serial().primaryKey(),
    deviceId: text("device_id").notNull().references(() => devices.id, { onDelete: "cascade" }),
    type: text().notNull(),
    occurrence: text().notNull(),
    createdAt: bigint("created_at", { mode: "number" }).notNull(),
    expiresAt: bigint("expires_at", { mode: "number" }).notNull(),
    deliveredAt: bigint("delivered_at", { mode: "number" }),
    ackedAt: bigint("acked_at", { mode: "number" }),
    result: text(),
    // Only one dispense command can ever exist per device + occurrence.
    dispenseLock: boolean("dispense_lock"),
  },
  (t) => [
    uniqueIndex("commands_one_dispense_idx").on(t.deviceId, t.occurrence, t.dispenseLock),
    index("commands_device_idx").on(t.deviceId, t.createdAt),
  ],
);
