import Database from 'better-sqlite3';
import path from 'path';

const DB_PATH = path.join(process.cwd(), 'data.db');

let db: Database.Database;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    initSchema(db);
  }
  return db;
}

function initSchema(db: Database.Database) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT DEFAULT 'member' CHECK(role IN ('admin', 'member')),
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS user_tokens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER UNIQUE NOT NULL,
      google_access_token TEXT,
      google_refresh_token TEXT,
      google_token_expiry TEXT,
      updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS deals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      status TEXT DEFAULT 'active' CHECK(status IN ('active', 'won', 'lost', 'pending')),
      created_by INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS thread_cache (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      thread_id TEXT NOT NULL,
      subject TEXT,
      snippet TEXT,
      from_email TEXT,
      to_email TEXT,
      last_message_at TEXT,
      message_count INTEGER DEFAULT 1,
      needs_reply INTEGER DEFAULT 0,
      deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
      assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
      is_done INTEGER DEFAULT 0,
      next_action TEXT,
      next_action_due TEXT,
      snooze_until TEXT,
      synced_at TEXT DEFAULT (datetime('now', 'localtime')),
      UNIQUE(thread_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS routing_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      match_domain TEXT,
      match_keyword TEXT,
      assign_to INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done')),
      priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
      assigned_to INTEGER REFERENCES users(id),
      due_date TEXT,
      thread_id TEXT,
      deal_id INTEGER REFERENCES deals(id),
      created_by INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      description TEXT,
      status TEXT DEFAULT 'active' CHECK(status IN ('active', 'closed')),
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS templates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS gmail_threads (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL,
      thread_id TEXT NOT NULL,
      subject TEXT,
      snippet TEXT,
      from_email TEXT,
      last_message_at TEXT,
      message_count INTEGER DEFAULT 1,
      has_unread INTEGER DEFAULT 0,
      synced_at TEXT DEFAULT (datetime('now', 'localtime')),
      UNIQUE(thread_id, user_id)
    );
  `);
}
