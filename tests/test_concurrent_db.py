"""Tests for concurrent database access under batch enrichment load.

Verifies that two simultaneous batch jobs against the same SQLite database
produce no data corruption, deadlocks, or lost writes.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import uuid

import pytest

from data.database import Database
from data.models import Person


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(db_path: str) -> Database:
    """Create a fresh database with schema applied."""
    return Database(db_path)


def _make_person(i: int, domain: str = "acme.com") -> Person:
    return Person(
        id=str(uuid.uuid4()),
        first_name=f"Person{i}",
        last_name="Test",
        company_domain=domain,
    )


# ---------------------------------------------------------------------------
# Test: concurrent inserts
# ---------------------------------------------------------------------------

class TestConcurrentInserts:
    @pytest.mark.asyncio
    async def test_parallel_person_inserts_no_lost_writes(self):
        """Two coroutines inserting different people in parallel — no lost writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = _make_db(db_path)

            async def insert_batch(start: int, count: int):
                for i in range(start, start + count):
                    await db.upsert_person(_make_person(i))

            await asyncio.gather(
                insert_batch(0, 50),
                insert_batch(50, 50),
            )

            async with db._connect() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM people")
                count = (await cursor.fetchone())[0]

            assert count == 100

            await db.close()

    @pytest.mark.asyncio
    async def test_parallel_cache_writes_no_corruption(self):
        """Two coroutines writing different cache entries — no corruption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = _make_db(db_path)

            async def write_cache(prefix: str, count: int):
                for i in range(count):
                    await db.cache_set(
                        provider=f"provider_{prefix}",
                        enrichment_type="email",
                        query_input={"name": f"{prefix}{i}", "domain": "test.com"},
                        response_data={"email": f"{prefix}{i}@test.com"},
                        found=True,
                    )

            await asyncio.gather(
                write_cache("a", 30),
                write_cache("b", 30),
            )

            async with db._connect() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM cache")
                count = (await cursor.fetchone())[0]

            assert count == 60

            await db.close()


# ---------------------------------------------------------------------------
# Test: concurrent reads and writes
# ---------------------------------------------------------------------------

class TestConcurrentReadsWrites:
    @pytest.mark.asyncio
    async def test_read_during_write_no_deadlock(self):
        """Concurrent reads and writes do not deadlock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = _make_db(db_path)

            # Seed some data
            for i in range(20):
                await db.upsert_person(_make_person(i))

            read_results = []

            async def reader():
                for _ in range(10):
                    result = await db.get_person_by_name_domain(
                        "Person0", "Test", "acme.com"
                    )
                    read_results.append(result)
                    await asyncio.sleep(0.01)

            async def writer():
                for i in range(20, 40):
                    await db.upsert_person(_make_person(i))
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(
                asyncio.gather(reader(), writer()),
                timeout=15.0,
            )

            assert len(read_results) == 10
            assert all(r is not None for r in read_results)

            await db.close()


# ---------------------------------------------------------------------------
# Test: concurrent budget operations
# ---------------------------------------------------------------------------

class TestConcurrentBudgetOps:
    @pytest.mark.asyncio
    async def test_concurrent_credit_usage_no_lost_updates(self):
        """Two coroutines updating the same credit_usage row — no lost updates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = _make_db(db_path)

            async def record_usage(count: int):
                for _ in range(count):
                    usage_id = str(uuid.uuid4())
                    async with db._connect() as conn:
                        await conn.execute(
                            """INSERT INTO credit_usage
                               (id, provider, date, credits_used, api_calls_made,
                                successful_lookups, failed_lookups)
                               VALUES (?, 'apollo', '2026-03-04', 1.0, 1, 1, 0)
                               ON CONFLICT(provider, date) DO UPDATE SET
                                   credits_used = credit_usage.credits_used + 1.0,
                                   api_calls_made = credit_usage.api_calls_made + 1,
                                   successful_lookups = credit_usage.successful_lookups + 1""",
                            (usage_id,),
                        )

            await asyncio.gather(
                record_usage(25),
                record_usage(25),
            )

            async with db._connect() as conn:
                cursor = await conn.execute(
                    "SELECT credits_used, api_calls_made FROM credit_usage "
                    "WHERE provider = 'apollo' AND date = '2026-03-04'"
                )
                row = await cursor.fetchone()

            assert row is not None
            assert row[0] == 50.0  # credits_used
            assert row[1] == 50    # api_calls_made

            await db.close()


# ---------------------------------------------------------------------------
# Test: WAL checkpoint during concurrent access
# ---------------------------------------------------------------------------

class TestWALConcurrent:
    @pytest.mark.asyncio
    async def test_wal_checkpoint_during_writes(self):
        """WAL checkpoint does not crash when concurrent writes are happening."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = _make_db(db_path)

            async def writer():
                for i in range(30):
                    await db.upsert_person(_make_person(i, domain="wal-test.com"))
                    await asyncio.sleep(0.01)

            async def checkpointer():
                for _ in range(3):
                    await asyncio.sleep(0.1)
                    await db.wal_checkpoint()

            await asyncio.wait_for(
                asyncio.gather(writer(), checkpointer()),
                timeout=15.0,
            )

            async with db._connect() as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM people WHERE company_domain = 'wal-test.com'"
                )
                count = (await cursor.fetchone())[0]

            assert count == 30

            await db.close()
