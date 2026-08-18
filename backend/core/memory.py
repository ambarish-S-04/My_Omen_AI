import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "aether_memory.db"

class MemoryStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE,
                    goal TEXT,
                    status TEXT,
                    steps_json TEXT,
                    summary TEXT,
                    created_at REAL,
                    completed_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    description TEXT,
                    steps_json TEXT,
                    created_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orchestration_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE,
                    strategy TEXT,
                    subtasks_json TEXT,
                    results_json TEXT,
                    total_workers INTEGER,
                    created_at REAL
                )
            """)
            conn.commit()

    def save_task_history(self, task_id: str, goal: str, status: str, steps: List[Dict[str, Any]], summary: str = ""):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO task_history (task_id, goal, status, steps_json, summary, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                goal,
                status,
                json.dumps(steps, ensure_ascii=False),
                summary,
                time.time(),
                time.time()
            ))
            conn.commit()

    def get_recent_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "task_id": r["task_id"],
                    "goal": r["goal"],
                    "status": r["status"],
                    "steps": json.loads(r["steps_json"]) if r["steps_json"] else [],
                    "summary": r["summary"],
                    "created_at": r["created_at"]
                })
            return results

    def save_recipe(self, name: str, description: str, steps: List[Dict[str, Any]]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO recipes (name, description, steps_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (name, description, json.dumps(steps, ensure_ascii=False), time.time()))
            conn.commit()

    def list_recipes(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recipes ORDER BY id DESC")
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "steps": json.loads(r["steps_json"]),
                    "created_at": r["created_at"]
                }
                for r in rows
            ]

    def set_preference(self, key: str, value: Any):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            val_str = json.dumps(value) if not isinstance(value, str) else value
            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, val_str, time.time()))
            conn.commit()

    def get_preference(self, key: str, default: Any = None) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return default

    def save_orchestration_log(self, session_id: str, strategy: str, subtasks: List[Dict[str, Any]],
                                results: List[Dict[str, Any]], total_workers: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO orchestration_log (session_id, strategy, subtasks_json, results_json, total_workers, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                strategy,
                json.dumps(subtasks, ensure_ascii=False),
                json.dumps([{"worker": r.get("worker_name"), "goal": r.get("goal"), "status": r.get("status"), "summary": r.get("summary")} for r in results], ensure_ascii=False),
                total_workers,
                time.time()
            ))
            conn.commit()

    def get_recent_orchestrations(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orchestration_log ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "session_id": r["session_id"],
                    "strategy": r["strategy"],
                    "subtasks": json.loads(r["subtasks_json"]) if r["subtasks_json"] else [],
                    "results": json.loads(r["results_json"]) if r["results_json"] else [],
                    "total_workers": r["total_workers"],
                    "created_at": r["created_at"]
                }
                for r in rows
            ]

memory_store = MemoryStore()
