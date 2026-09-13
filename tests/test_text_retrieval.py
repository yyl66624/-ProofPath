"""Tests for CJK-safe normalization/tokenization and BM25 retrieval."""
from __future__ import annotations

import pytest

from proofpath.errors import EmptyIndexError
from proofpath.models import Chunk
from proofpath.retrieval import Bm25Index, build_context
from proofpath.text import collapse_for_display, coverage_ratio, normalize, tokenize


class TestNormalize:
    def test_strips_all_whitespace(self) -> None:
        assert normalize("年龄 不超过\n35 周岁") == "年龄不超过35周岁"

    def test_folds_fullwidth_to_halfwidth(self) -> None:
        assert normalize("１５００元") == normalize("1500元")

    def test_casefolds_latin(self) -> None:
        assert normalize("PhD Degree") == "phddegree"

    def test_removes_zero_width_characters(self) -> None:
        assert normalize("学​历﻿要求") == "学历要求"

    def test_idempotent(self) -> None:
        once = normalize("全日制 本科 及以上")
        assert normalize(once) == once

    def test_empty_string(self) -> None:
        assert normalize("") == ""


class TestTokenize:
    def test_latin_words(self) -> None:
        assert tokenize("PhD degree 2024") == ("phd", "degree", "2024")

    def test_cjk_produces_unigrams_and_bigrams(self) -> None:
        tokens = tokenize("学历要求")
        assert "学" in tokens and "历" in tokens
        assert "学历" in tokens and "历要" in tokens

    def test_mixed_script(self) -> None:
        tokens = tokenize("硕士 master 学位")
        assert "master" in tokens
        assert "硕士" in tokens

    def test_empty_string(self) -> None:
        assert tokenize("") == ()

    def test_punctuation_dropped(self) -> None:
        assert tokenize("(一)、;") == ("一",)


class TestCoverageRatio:
    def test_full_containment(self) -> None:
        assert coverage_ratio("abc", "xxabcxx") == 1.0

    def test_no_overlap(self) -> None:
        assert coverage_ratio("abcdef", "xyz") == 0.0

    def test_partial(self) -> None:
        # 5 of 6 chars present contiguously
        assert coverage_ratio("abcdef", "abcdeZ") == pytest.approx(5 / 6)

    def test_empty_needle(self) -> None:
        assert coverage_ratio("", "anything") == 0.0


class TestCollapseForDisplay:
    def test_collapses_newlines(self) -> None:
        assert collapse_for_display("a\n\nb   c") == "a b c"

    def test_truncates_with_ellipsis(self) -> None:
        result = collapse_for_display("x" * 200, limit=20)
        assert len(result) == 20
        assert result.endswith("…")

    def test_short_text_untouched(self) -> None:
        assert collapse_for_display("短文本") == "短文本"


def _chunks() -> tuple[Chunk, ...]:
    return (
        Chunk("c0", 1, "申请人应当具有全日制本科及以上学历,或具有中级及以上专业技术职称。"),
        Chunk("c1", 1, "申请时年龄不超过35周岁,其中具有博士学位的不超过40周岁。"),
        Chunk("c2", 2, "补贴标准:硕士研究生或副高级职称,每月1500元。"),
        Chunk("c3", 2, "申请人应当在租赁合同备案之日起6个月内提出申请,逾期不再受理。"),
    )


class TestBm25Index:
    def test_rejects_empty_chunks(self) -> None:
        with pytest.raises(EmptyIndexError):
            Bm25Index(())

    def test_len(self) -> None:
        assert len(Bm25Index(_chunks())) == 4

    def test_finds_relevant_chunk_first(self) -> None:
        index = Bm25Index(_chunks())
        hits = index.search("硕士每月多少钱")
        assert hits
        assert hits[0].chunk.chunk_id == "c2"

    def test_age_query_finds_age_chunk(self) -> None:
        index = Bm25Index(_chunks())
        hits = index.search("年龄限制是多少")
        assert hits[0].chunk.chunk_id == "c1"

    def test_respects_top_k(self) -> None:
        index = Bm25Index(_chunks())
        assert len(index.search("申请人", top_k=2)) <= 2

    def test_top_k_zero_returns_nothing(self) -> None:
        assert Bm25Index(_chunks()).search("申请人", top_k=0) == ()

    def test_unrelated_query_returns_nothing(self) -> None:
        """No lexical overlap must yield no hits, so the caller can refuse to answer."""
        assert Bm25Index(_chunks()).search("weather forecast tomorrow") == ()

    def test_empty_query_returns_nothing(self) -> None:
        assert Bm25Index(_chunks()).search("") == ()

    def test_scores_are_positive_and_descending(self) -> None:
        hits = Bm25Index(_chunks()).search("申请人 学历")
        scores = [h.score for h in hits]
        assert all(s > 0 for s in scores)
        assert scores == sorted(scores, reverse=True)

    def test_deterministic_across_runs(self) -> None:
        index = Bm25Index(_chunks())
        first = [h.chunk.chunk_id for h in index.search("申请")]
        second = [h.chunk.chunk_id for h in index.search("申请")]
        assert first == second


class TestBuildContext:
    def test_includes_page_labels(self) -> None:
        hits = Bm25Index(_chunks()).search("硕士补贴标准")
        context = build_context(hits)
        assert "[第 2 页]" in context

    def test_respects_char_budget(self) -> None:
        hits = Bm25Index(_chunks()).search("申请人")
        context = build_context(hits, char_budget=50)
        assert len(context) <= 60  # one block, plus its label

    def test_empty_hits_yield_empty_context(self) -> None:
        assert build_context(()) == ""
