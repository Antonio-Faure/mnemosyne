import pytest

from mnemosyne.config import MemoryConfig
from mnemosyne.db import Database
from mnemosyne.memory import Memory


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        return "ROLLING SUMMARY"


def _memory(config, llm):
    db = Database(config.db_file())
    mem = Memory(
        db,
        llm,
        session="s1",
        config=MemoryConfig(max_recent_messages=2, compact_after_messages=3),
    )
    return db, mem


def test_build_context_without_summary(config):
    db, mem = _memory(config, FakeLLM())
    mem.add("user", "hello")
    mem.add("assistant", "hi")
    ctx = mem.build_context("SYSTEM")
    assert ctx[0] == {"role": "system", "content": "SYSTEM"}
    assert ctx[1] == {"role": "user", "content": "hello"}
    db.close()


@pytest.mark.asyncio
async def test_compaction_folds_and_prunes(config):
    db, mem = _memory(config, FakeLLM())
    for i in range(6):
        mem.add("user", f"m{i}")
    assert mem.count() == 6

    assert await mem.maybe_compact() is True
    assert mem.summary() == "ROLLING SUMMARY"
    assert mem.count() == 2  # only the recent window remains

    ctx = mem.build_context("SYSTEM")
    roles = [m["role"] for m in ctx]
    assert roles[0] == "system"
    assert "Memory summary" in ctx[1]["content"]
    assert len(ctx) == 4  # system + summary + 2 recent
    db.close()


@pytest.mark.asyncio
async def test_no_compaction_below_threshold(config):
    db, mem = _memory(config, FakeLLM())
    mem.add("user", "a")
    assert await mem.maybe_compact() is False
    db.close()


@pytest.mark.asyncio
async def test_reply_stores_both_turns(config):
    db, mem = _memory(config, FakeLLM())
    answer = await mem.reply("question", system="S")
    assert answer == "ROLLING SUMMARY"
    assert mem.count() == 2  # user + assistant
    db.close()
