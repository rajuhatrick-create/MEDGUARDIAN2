import type { Config } from "@netlify/functions";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { and, desc, eq, gt, isNull, lt } from "drizzle-orm";
import { db } from "../../db/index.js";
import { commands, devices, events, notes, sessions } from "../../db/schema.js";

const SESSION_SECONDS = 12 * 60 * 60;
const COMMAND_TTL_SECONDS = 60;
const ONLINE_WINDOW_SECONDS = 30;
const MAX_BODY_BYTES = 32 * 1024;
const DEVICE_ID = /^[a-zA-Z0-9_-]{1,40}$/;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const SLOTS = ["morning", "afternoon", "night"] as const;
const EVENT_KINDS = new Set([
  "reminder", "snoozed", "blocked", "attempt", "sensor_confirmed", "uncertain", "fault", "info",
]);
const NOTE_KINDS = new Set(["intake_report", "alert_ack"]);

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const now = () => Math.floor(Date.now() / 1000);
const sha256 = (value: string) => createHash("sha256").update(value).digest("hex");
const json = (data: unknown, status = 200) =>
  Response.json(data, { status, headers: { "Cache-Control": "no-store" } });

function safeEqual(a: string, b: string) {
  const ha = Buffer.from(sha256(a), "hex");
  const hb = Buffer.from(sha256(b), "hex");
  return timingSafeEqual(ha, hb);
}

async function readBody(req: Request): Promise<Record<string, any>> {
  const text = await req.text();
  if (text.length > MAX_BODY_BYTES) throw new HttpError(413, "Request body too large");
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed;
  } catch {
    throw new HttpError(400, "Body must be a JSON object");
  }
}

function bearer(req: Request) {
  const header = req.headers.get("authorization") || "";
  return header.startsWith("Bearer ") ? header.slice(7).trim() : "";
}

async function requireCaregiver(req: Request) {
  const token = bearer(req);
  if (!token) throw new HttpError(401, "Sign in required");
  const [session] = await db
    .select()
    .from(sessions)
    .where(and(eq(sessions.tokenHash, sha256(token)), gt(sessions.expiresAt, now())));
  if (!session) throw new HttpError(401, "Session expired. Sign in again.");
  return session;
}

async function loadDevice(id: string) {
  if (!DEVICE_ID.test(id)) throw new HttpError(400, "Invalid device ID");
  const [device] = await db.select().from(devices).where(eq(devices.id, id));
  if (!device) throw new HttpError(404, "Device not found");
  return device;
}

function publicDevice(d: typeof devices.$inferSelect) {
  return {
    id: d.id,
    online: d.lastSeen != null && now() - d.lastSeen <= ONLINE_WINDOW_SECONDS,
    last_seen: d.lastSeen,
    telemetry: d.telemetry,
    schedule: d.schedule,
  };
}

// Mirrors the dashboard preflight. The firmware enforces these again before moving anything.
function dispenseBlockReason(d: typeof devices.$inferSelect, occurrence: string) {
  const t = d.telemetry as Record<string, any> | null;
  if (d.lastSeen == null || now() - d.lastSeen > ONLINE_WINDOW_SECONDS) return "Device offline or telemetry is stale.";
  if (!t) return "No telemetry received.";
  if (t.clock_trusted !== true) return "Device clock is not trusted.";
  if (t.calibrated !== true) return "Load-cell calibration is incomplete.";
  if (t.actuation_verified !== true) return "Actuation commissioning is incomplete.";
  if (Array.isArray(t.faults) && t.faults.length) return "Device reports faults: " + t.faults.join(", ");
  if (t.docked !== false) return "Dock state is not confirmed undocked.";
  if (!t.limit_switch || t.limit_switch.ready !== true || t.limit_switch.active !== false)
    return "Limit switch is not ready/released.";
  if (t.lid_closed !== true) return "Lid-closed interlock is not confirmed.";
  if (!Array.isArray(t.current_occurrences) || !t.current_occurrences.includes(occurrence))
    return "Occurrence is not currently active on the device.";
  return "";
}

// ---------- Caregiver routes ----------

async function login(req: Request) {
  const configured = Netlify.env.get("CAREGIVER_PASSWORD") || "";
  if (configured.length < 12)
    throw new HttpError(503, "Caregiver password is not set up. Add CAREGIVER_PASSWORD (12+ characters) in the Netlify project's environment variables, then redeploy.");
  const { password } = await readBody(req);
  if (typeof password !== "string" || !safeEqual(password, configured)) {
    await new Promise((r) => setTimeout(r, 800));
    throw new HttpError(401, "Incorrect password");
  }
  const token = randomBytes(32).toString("base64url");
  const t = now();
  await db.delete(sessions).where(lt(sessions.expiresAt, t));
  await db.insert(sessions).values({ tokenHash: sha256(token), createdAt: t, expiresAt: t + SESSION_SECONDS });
  return json({ token, expires_at: t + SESSION_SECONDS });
}

async function logout(req: Request) {
  const token = bearer(req);
  if (token) await db.delete(sessions).where(eq(sessions.tokenHash, sha256(token)));
  return json({ ok: true });
}

async function listDevices() {
  const rows = await db.select().from(devices).orderBy(devices.id);
  return json({ devices: rows.map(publicDevice) });
}

async function registerDevice(req: Request) {
  const { device_id } = await readBody(req);
  if (typeof device_id !== "string" || !DEVICE_ID.test(device_id))
    throw new HttpError(400, "Device ID must be 1-40 letters, numbers, - or _");
  const key = randomBytes(24).toString("base64url");
  const inserted = await db
    .insert(devices)
    .values({
      id: device_id,
      keyHash: sha256(key),
      schedule: { morning: null, afternoon: null, night: null },
      createdAt: now(),
    })
    .onConflictDoNothing()
    .returning();
  if (!inserted.length) throw new HttpError(409, "That device ID is already registered");
  return json({ device_id, device_key: key }, 201);
}

async function history(id: string) {
  await loadDevice(id);
  const [ev, nt, cm] = await Promise.all([
    db.select().from(events).where(eq(events.deviceId, id)).orderBy(desc(events.at)).limit(200),
    db.select().from(notes).where(eq(notes.deviceId, id)).orderBy(desc(notes.at)).limit(200),
    db.select().from(commands).where(eq(commands.deviceId, id)).orderBy(desc(commands.createdAt)).limit(50),
  ]);
  return json({
    events: ev.map((e) => ({ at: e.at, occurrence: e.occurrence, kind: e.kind, detail: e.detail })),
    notes: nt.map((n) => ({ at: n.at, occurrence: n.occurrence, kind: n.kind, note: n.note })),
    commands: cm.map((c) => ({
      id: c.id, type: c.type, occurrence: c.occurrence, created_at: c.createdAt,
      expires_at: c.expiresAt, delivered_at: c.deliveredAt, acked_at: c.ackedAt, result: c.result,
    })),
  });
}

async function addNote(req: Request, id: string) {
  await loadDevice(id);
  const { occurrence, kind, note } = await readBody(req);
  if (typeof occurrence !== "string" || occurrence.length > 64) throw new HttpError(400, "Invalid occurrence");
  if (!NOTE_KINDS.has(kind)) throw new HttpError(400, "Invalid note kind");
  if (typeof note !== "string" || !note.trim() || note.length > 1000) throw new HttpError(400, "Note must be 1-1000 characters");
  await db.insert(notes).values({ deviceId: id, occurrence, kind, note: note.trim(), at: now() });
  return json({ ok: true }, 201);
}

async function saveSchedule(req: Request, id: string) {
  const device = await loadDevice(id);
  const body = await readBody(req);
  const schedule = {} as Record<(typeof SLOTS)[number], string | null>;
  for (const slot of SLOTS) {
    const v = body[slot];
    if (v == null || v === "") schedule[slot] = null;
    else if (typeof v === "string" && TIME.test(v)) schedule[slot] = v;
    else throw new HttpError(400, `Invalid ${slot} time (use HH:MM)`);
  }
  await db
    .update(devices)
    .set({ schedule, scheduleVersion: device.scheduleVersion + 1 })
    .where(eq(devices.id, id));
  return json({ ok: true, schedule });
}

async function queueCommand(req: Request, id: string) {
  const device = await loadDevice(id);
  const { type, occurrence } = await readBody(req);
  if (type !== "dispense" && type !== "snooze") throw new HttpError(400, "Unknown command type");
  if (typeof occurrence !== "string" || !occurrence || occurrence.length > 64) throw new HttpError(400, "Select an occurrence");
  const t = now();

  if (type === "snooze") {
    if (device.lastSeen == null || t - device.lastSeen > ONLINE_WINDOW_SECONDS)
      throw new HttpError(409, "Cannot snooze: device is offline or telemetry is stale.");
  } else {
    const reason = dispenseBlockReason(device, occurrence);
    if (reason) throw new HttpError(409, "Dispense blocked: " + reason);
    const [attempt] = await db
      .select({ id: events.id })
      .from(events)
      .where(and(eq(events.deviceId, id), eq(events.occurrence, occurrence), eq(events.kind, "attempt")))
      .limit(1);
    if (attempt) throw new HttpError(409, "An attempt is already recorded for this occurrence.");
  }

  const inserted = await db
    .insert(commands)
    .values({
      deviceId: id, type, occurrence, createdAt: t, expiresAt: t + COMMAND_TTL_SECONDS,
      dispenseLock: type === "dispense" ? true : null,
    })
    .onConflictDoNothing()
    .returning({ id: commands.id });
  if (!inserted.length)
    throw new HttpError(409, "A dispense request was already made for this occurrence. It is never repeated automatically.");
  return json({ ok: true, id: inserted[0].id, expires_at: t + COMMAND_TTL_SECONDS }, 201);
}

// ---------- Device route ----------

async function deviceSync(req: Request) {
  const id = req.headers.get("x-device-id") || "";
  const key = bearer(req);
  if (!DEVICE_ID.test(id) || !key) throw new HttpError(401, "Device credentials required");
  const [device] = await db.select().from(devices).where(eq(devices.id, id));
  if (!device || !safeEqual(sha256(key), device.keyHash)) throw new HttpError(401, "Unknown device or wrong key");

  const body = await readBody(req);
  const t = now();

  if (body.telemetry != null && (typeof body.telemetry !== "object" || Array.isArray(body.telemetry)))
    throw new HttpError(400, "telemetry must be an object");

  const incoming = Array.isArray(body.events) ? body.events.slice(0, 50) : [];
  const rows = [];
  for (const e of incoming) {
    if (!e || typeof e.uid !== "string" || e.uid.length > 64 || !EVENT_KINDS.has(e.kind)) continue;
    const at = Number.isInteger(e.at) && Math.abs(e.at - t) < 7 * 86400 ? e.at : t;
    rows.push({
      deviceId: id, eventUid: e.uid, kind: e.kind,
      occurrence: String(e.occurrence ?? "").slice(0, 64),
      detail: String(e.detail ?? "").slice(0, 500), at,
    });
  }
  if (rows.length) await db.insert(events).values(rows).onConflictDoNothing();

  const acks = Array.isArray(body.acks) ? body.acks.slice(0, 20) : [];
  for (const a of acks) {
    if (!a || !Number.isInteger(a.id)) continue;
    await db
      .update(commands)
      .set({ ackedAt: t, result: String(a.result ?? "").slice(0, 200) })
      .where(and(eq(commands.id, a.id), eq(commands.deviceId, id), isNull(commands.ackedAt)));
  }

  await db
    .update(devices)
    .set({ telemetry: body.telemetry ?? device.telemetry, lastSeen: t })
    .where(eq(devices.id, id));

  // Each command is delivered at most once and only before it expires.
  const pending = await db
    .update(commands)
    .set({ deliveredAt: t })
    .where(and(eq(commands.deviceId, id), isNull(commands.deliveredAt), gt(commands.expiresAt, t)))
    .returning();

  return json({
    server_time: t,
    schedule: device.schedule,
    schedule_version: device.scheduleVersion,
    accepted_event_uids: rows.map((r) => r.eventUid),
    commands: pending.map((c) => ({ id: c.id, type: c.type, occurrence: c.occurrence, expires_at: c.expiresAt })),
  });
}

// ---------- Router ----------

export default async (req: Request) => {
  const path = new URL(req.url).pathname.replace(/^\/api\/v1/, "").replace(/\/+$/, "") || "/";
  const m = req.method;
  try {
    if (path === "/login" && m === "POST") return await login(req);
    if (path === "/logout" && m === "POST") return await logout(req);
    if (path === "/device/sync" && m === "POST") return await deviceSync(req);

    await requireCaregiver(req);
    if (path === "/devices" && m === "GET") return await listDevices();
    if (path === "/devices" && m === "POST") return await registerDevice(req);

    const match = path.match(/^\/devices\/([^/]+)\/(history|notes|schedule|commands)$/);
    if (match) {
      const id = decodeURIComponent(match[1]);
      const action = match[2];
      if (action === "history" && m === "GET") return await history(id);
      if (action === "notes" && m === "POST") return await addNote(req, id);
      if (action === "schedule" && m === "PUT") return await saveSchedule(req, id);
      if (action === "commands" && m === "POST") return await queueCommand(req, id);
    }
    return json({ error: "Not found" }, 404);
  } catch (err) {
    if (err instanceof HttpError) return json({ error: err.message }, err.status);
    console.error("API error", err);
    return json({ error: "Server error" }, 500);
  }
};

export const config: Config = {
  path: "/api/v1/*",
};
