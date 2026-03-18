"""
init/__init__.py

Startup initialisation module.

Responsibilities:
  1. Verify MySQL connectivity (with retries).
  2. Verify Redis connectivity (with retries).
  3. Ensure the schema-migration tracking table exists.
  4. Discover every *.sql file inside  init/database/
     and apply any that have not yet been recorded as applied.
"""

import os
import glob
import hashlib
import time
from typing import Set

import jsonlog
from mysql.connector import Error as MySQLError

from database import DatabaseClient
from redis_cache import RedisClient

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = jsonlog.setup_logger("init")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCHEMA_DIR: str = os.path.join(os.path.dirname(__file__), "database")

# ---------------------------------------------------------------------------
# Internal DDL: migration tracking table
# ---------------------------------------------------------------------------
_MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `mw_schema_migrations` (
    `id`         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `filename`   VARCHAR(255) NOT NULL,
    `checksum`   VARCHAR(64)  NOT NULL,
    `applied_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_filename` (`filename`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def check_mysql(db: DatabaseClient, max_retries: int = 5, delay: float = 3.0) -> bool:
    """
    Ping MySQL until it responds or the retry limit is reached.

    Returns True on success, raises RuntimeError on failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            if db.is_connected():
                logger.info("MySQL connection OK")
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"MySQL ping attempt {attempt}/{max_retries} failed: {exc}")

        if attempt < max_retries:
            time.sleep(delay)

    raise RuntimeError(
        f"MySQL is not reachable after {max_retries} attempts. Aborting init."
    )


def _ensure_migrations_table(db: DatabaseClient) -> None:
    """Create the migration-tracking table when it does not exist yet."""
    try:
        with db.connection_cursor() as (conn, cursor):
            cursor.execute(_MIGRATIONS_TABLE_DDL)
            conn.commit()
        logger.info("Migration tracking table is ready (mw_schema_migrations)")
    except MySQLError as exc:
        logger.error(f"Failed to create mw_schema_migrations table: {exc}")
        raise


def _get_applied_migrations(db: DatabaseClient) -> Set[str]:
    """Return the set of already-applied SQL filenames."""
    try:
        rows = db.execute_query("SELECT `filename` FROM `mw_schema_migrations`")
        return {row["filename"] for row in rows}
    except MySQLError as exc:
        logger.error(f"Failed to fetch applied migrations: {exc}")
        raise


def _file_checksum(filepath: str) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    with open(filepath, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _run_sql_file(db: DatabaseClient, filepath: str) -> None:
    """
    Execute every statement in a *.sql file and record it as applied.

    Statements are split on ';' so that a single file may contain multiple DDL
    commands (e.g. CREATE TABLE + INSERT seed data).
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        raw_sql = fh.read()

    statements = [s.strip() for s in raw_sql.split(";") if s.strip()]

    try:
        with db.connection_cursor() as (conn, cursor):
            for stmt in statements:
                cursor.execute(stmt)
            conn.commit()
    except MySQLError as exc:
        logger.error(f"Error executing {os.path.basename(filepath)}: {exc}")
        raise

    # Record the migration as applied
    checksum = _file_checksum(filepath)
    filename = os.path.basename(filepath)
    db.execute_update(
        "INSERT INTO `mw_schema_migrations` (`filename`, `checksum`) VALUES (%s, %s)",
        (filename, checksum),
    )
    logger.info(f"Schema applied: {filename}")


def apply_schemas(db: DatabaseClient) -> None:
    """
    Discover *.sql files in init/database/, sorted by name,
    and execute those not yet recorded in mw_schema_migrations.
    """
    _ensure_migrations_table(db)
    applied = _get_applied_migrations(db)

    pattern = os.path.join(_SCHEMA_DIR, "*.sql")
    sql_files = sorted(glob.glob(pattern))

    if not sql_files:
        logger.warning(f"No SQL schema files found in {_SCHEMA_DIR}")
        return

    pending = [f for f in sql_files if os.path.basename(f) not in applied]

    if not pending:
        logger.info("All schema migrations are already applied. Nothing to do.")
        return

    logger.info(f"Found {len(pending)} pending schema file(s) to apply")
    for filepath in pending:
        _run_sql_file(db, filepath)

    logger.info("Schema migrations completed successfully")


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def check_redis(max_retries: int = 5, delay: float = 3.0) -> bool:
    """
    Attempt to connect to Redis until it responds or the retry limit is reached.

    Returns True on success, raises RuntimeError on failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            client = RedisClient()
            if client.health_check():
                logger.info("Redis connection OK")
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Redis ping attempt {attempt}/{max_retries} failed: {exc}")

        if attempt < max_retries:
            time.sleep(delay)

    raise RuntimeError(
        f"Redis is not reachable after {max_retries} attempts. Aborting init."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def initialize(db: DatabaseClient | None = None) -> None:
    """
    Run all startup checks and schema migrations.

    Args:
        db: An existing DatabaseClient instance.  When *None* a new one is
            created using the default configuration from environment variables.

    Raises:
        RuntimeError: If MySQL or Redis cannot be reached.
        mysql.connector.Error: If a schema migration fails.
    """
    logger.info("=== Starting application initialisation ===")

    # 1. MySQL connectivity
    if db is None:
        db = DatabaseClient()
    check_mysql(db)

    # 2. Redis connectivity
    check_redis()

    # 3. Apply pending SQL schemas
    apply_schemas(db)

    logger.info("=== Initialisation complete ===")
