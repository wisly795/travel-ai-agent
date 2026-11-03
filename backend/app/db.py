"""資料庫連線。"""
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
MIGRATIONS = Path(__file__).with_name("migrations.sql")


def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def query(sql, params=()):
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def migrate():
    """補上新版本需要的資料表；可重複執行。"""
    with connect() as conn:
        conn.execute(MIGRATIONS.read_text(encoding="utf-8"))
