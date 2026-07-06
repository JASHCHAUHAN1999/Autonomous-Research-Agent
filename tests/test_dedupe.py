# tests/test_dedupe.py
import pytest

from app.sources.base import SourceResult
from app.processing.dedupe import dedupe, filter_relevant


def _mk(source="web", title="t", url="https://example.com", content="c"):
    return SourceResult(source=source, title=title, url=url, content=content)


def test_dedupe_removes_duplicate_url():
    # a and b are the same page once normalized (scheme/case/query/trailing slash differ).
    a = SourceResult(
        source="web", title="A",
        url="https://Example.com/page/?q=1",
        content="Alpha content that is quite unique here.",
    )
    b = SourceResult(
        source="web", title="B",
        url="http://example.com/page",
        content="Totally different words appear in this one only.",
    )
    c = SourceResult(
        source="web", title="C",
        url="https://other.com/x",
        content="Some other completely unrelated unique text.",
    )
    out = dedupe([a, b, c])
    urls = [r.url for r in out]
    assert len(out) == 2
    assert a.url in urls
    assert b.url not in urls  # dropped: same normalized URL as a
    assert c.url in urls


def test_dedupe_removes_near_identical_content():
    base = (
        "Artificial intelligence is transforming how modern businesses "
        "operate across many industries worldwide."
    )
    near = (
        "Artificial intelligence is transforming how modern businesses "
        "operate across many industries world wide."  # one char differs -> ratio > 0.9
    )
    unrelated = "Local weather forecast predicts heavy rain and strong winds this weekend."

    a = SourceResult(source="web", title="A", url="https://a.com/1", content=base)
    b = SourceResult(source="web", title="B", url="https://b.com/2", content=near)
    c = SourceResult(source="web", title="C", url="https://c.com/3", content=unrelated)

    out = dedupe([a, b, c])
    contents = [r.content for r in out]
    assert len(out) == 2
    assert base in contents
    assert near not in contents  # dropped: near-identical to base
    assert unrelated in contents


@pytest.mark.asyncio
async def test_filter_relevant_identity_when_no_llm():
    results = [_mk(url="https://a.com/1"), _mk(url="https://b.com/2")]
    out = await filter_relevant("some query", results, llm=None)
    assert out == results  # unchanged content, same order


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self._content = content
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return _FakeMessage(self._content)


@pytest.mark.asyncio
async def test_filter_relevant_keeps_selected_indices():
    results = [
        _mk(title="keep0", url="https://a.com/0"),
        _mk(title="drop1", url="https://b.com/1"),
        _mk(title="keep2", url="https://c.com/2"),
    ]
    fake = _FakeLLM('```json\n{"keep": [0, 2]}\n```')  # fenced JSON to exercise tolerant parse
    out = await filter_relevant("my query", results, llm=fake)
    assert [r.title for r in out] == ["keep0", "keep2"]
    assert fake.calls, "llm.ainvoke should have been called"


@pytest.mark.asyncio
async def test_filter_relevant_preserves_original_order_when_keep_is_out_of_order():
    results = [
        _mk(title="r0", url="https://a.com/0"),
        _mk(title="r1", url="https://b.com/1"),
        _mk(title="r2", url="https://c.com/2"),
    ]
    # LLM returns indices out of order: index 2 first, then index 0.
    fake = _FakeLLM('{"keep": [2, 0]}')
    out = await filter_relevant("my query", results, llm=fake)
    # Output must follow original `results` order (source ranking), not the
    # order the LLM listed indices in.
    assert [r.title for r in out] == ["r0", "r2"]


@pytest.mark.asyncio
async def test_filter_relevant_ignores_garbage_out_of_range_and_duplicate_indices():
    results = [
        _mk(title="r0", url="https://a.com/0"),
        _mk(title="r1", url="https://b.com/1"),
        _mk(title="r2", url="https://c.com/2"),
    ]
    # 5 is out of range, "x" is not an int, -1 is out of range, 1 is duplicated.
    fake = _FakeLLM('{"keep": [5, "x", -1, 1, 1]}')
    out = await filter_relevant("my query", results, llm=fake)
    assert [r.title for r in out] == ["r1"]


@pytest.mark.asyncio
async def test_filter_relevant_fails_open_on_missing_keep_key():
    results = [_mk(title="r0", url="https://a.com/0"), _mk(title="r1", url="https://b.com/1")]
    fake = _FakeLLM('{"foo": "bar"}')  # valid JSON, but no "keep" key
    out = await filter_relevant("my query", results, llm=fake)
    assert out == results  # fails open: full unfiltered list, original order


@pytest.mark.asyncio
async def test_filter_relevant_fails_open_on_malformed_json():
    results = [_mk(title="r0", url="https://a.com/0"), _mk(title="r1", url="https://b.com/1")]
    fake = _FakeLLM("not json at all, sorry")  # unparseable -> _parse_json returns {}
    out = await filter_relevant("my query", results, llm=fake)
    assert out == results  # fails open: full unfiltered list, original order
