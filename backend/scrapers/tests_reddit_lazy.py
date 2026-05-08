"""Tests for the lazy Reddit helper."""
from __future__ import annotations

import time
import unittest

from scrapers.reddit_lazy import (
    DEFAULT_SUBREDDITS,
    NICKNAME_MAP,
    _AliasMatcher,
    _clean_body,
    _institution_keyword,
    _query_for_sub,
    _split_sentences,
    _subreddits_for_institution,
    _walk,
)


class AliasMatcherBasicTests(unittest.TestCase):
    def test_full_name_matches_case_insensitive(self):
        m = _AliasMatcher("Mark Ogletree")
        self.assertTrue(m.matches("MARK OGLETREE is great"))
        self.assertTrue(m.matches("loved mark ogletree"))

    def test_last_name_word_boundary(self):
        m = _AliasMatcher("Mark Ogletree")
        self.assertTrue(m.matches("Ogletree gives easy A"))
        # Substring inside another word should not match.
        self.assertFalse(m.matches("ogletreebot is a chatbot"))

    def test_empty_text_no_match(self):
        m = _AliasMatcher("Mark Ogletree")
        self.assertFalse(m.matches(""))
        self.assertFalse(m.matches(None))

    def test_initial_and_last_matches(self):
        m = _AliasMatcher("Mark Ogletree")
        self.assertTrue(m.matches("M. Ogletree teaches well"))
        self.assertTrue(m.matches("M Ogletree teaches well"))

    def test_title_plus_last_matches(self):
        # Title forms should still match.
        m = _AliasMatcher("Mark Ogletree")
        self.assertTrue(m.matches("Dr. Ogletree was fair"))
        self.assertTrue(m.matches("Prof Ogletree's exams are hard"))


class AliasMatcherNicknameTests(unittest.TestCase):
    def test_first_name_plus_last_matches(self):
        m = _AliasMatcher("Michael Anderson")
        self.assertTrue(m.matches("Michael Anderson is fantastic"))

    def test_nickname_plus_last_matches(self):
        # Michael maps to Mike.
        m = _AliasMatcher("Michael Anderson")
        self.assertTrue(m.matches("Mike Anderson is fantastic"))
        self.assertTrue(m.matches("mike anderson rocks"))

    def test_robert_nicknames(self):
        m = _AliasMatcher("Robert Smith")
        self.assertTrue(m.matches("Bob Smith was patient"))
        self.assertTrue(m.matches("Rob Smith helped me a lot"))
        self.assertTrue(m.matches("Bobby Smith's class"))

    def test_title_plus_nickname_matches(self):
        m = _AliasMatcher("Michael Anderson")
        # Title plus first name is allowed.
        self.assertTrue(m.matches("Dr. Mike was incredible"))
        self.assertTrue(m.matches("Prof Michael runs a tight class"))

    def test_nickname_alone_does_not_match(self):
        # Nickname alone is too broad.
        m = _AliasMatcher("Michael Anderson")
        self.assertFalse(m.matches("Mike was great in his lecture"))

    def test_extra_alias_passthrough(self):
        m = _AliasMatcher(
            "Catherine Ogletree", extra_aliases=["kit"],
        )
        self.assertTrue(m.matches("kit ogletree was awesome"))
        self.assertTrue(m.matches("Dr. Kit was awesome"))

    def test_nickname_map_has_common_names(self):
        # Common aliases should be present.
        for name in ("michael", "robert", "william", "elizabeth", "thomas"):
            self.assertIn(name, NICKNAME_MAP)


class SentenceSplitterTests(unittest.TestCase):
    def test_basic_splitting(self):
        text = "First sentence. Second sentence! Third?"
        self.assertEqual(
            _split_sentences(text),
            ["First sentence.", "Second sentence!", "Third?"],
        )

    def test_protects_dr_abbreviation(self):
        # Keep titles attached to the name.
        text = "Took Dr. Smith last term. He was great."
        result = _split_sentences(text)
        self.assertEqual(len(result), 2)
        self.assertIn("Dr. Smith", result[0])

    def test_protects_prof_abbreviation(self):
        text = "Prof. Ogletree is fair. The exams are easy."
        result = _split_sentences(text)
        self.assertEqual(len(result), 2)

    def test_newline_acts_as_break(self):
        text = "Line one about Smith\nLine two about Jones"
        result = _split_sentences(text)
        self.assertEqual(len(result), 2)

    def test_handles_eg_ie(self):
        text = "Lots of work, e.g. weekly quizzes. But fair overall."
        result = _split_sentences(text)
        self.assertEqual(len(result), 2)

    def test_empty_input(self):
        self.assertEqual(_split_sentences(""), [])
        self.assertEqual(_split_sentences(None), [])


class AliasMatcherSentenceSliceTests(unittest.TestCase):
    """Sentence-slice matching cases."""

    def test_mixed_comment_returns_only_relevant_sentence(self):
        # Keep only the matched professor's sentence.
        text = "Anderson is great. Smith is awful and you should avoid him."
        m = _AliasMatcher("Michael Anderson")
        sentences = m.select_sentences(text)
        self.assertEqual(len(sentences), 1)
        self.assertIn("Anderson", sentences[0])
        self.assertNotIn("Smith", sentences[0])

    def test_off_topic_comment_returns_empty(self):
        text = "Anyone know a good chemistry prof? I heard Jones is decent."
        m = _AliasMatcher("Mark Ogletree")
        self.assertEqual(m.select_sentences(text), [])

    def test_multiple_relevant_sentences_kept(self):
        text = (
            "Ogletree is great. He grades fairly. "
            "Smith on the other hand should be avoided."
        )
        m = _AliasMatcher("Mark Ogletree")
        sentences = m.select_sentences(text)
        # Pronoun-only follow-ups should not be kept.
        self.assertEqual(len(sentences), 1)
        self.assertIn("Ogletree", sentences[0])

    def test_nickname_in_one_sentence_kept(self):
        text = "Smith is bad. Mike Anderson on the other hand is amazing."
        m = _AliasMatcher("Michael Anderson")
        sentences = m.select_sentences(text)
        self.assertEqual(len(sentences), 1)
        self.assertIn("Anderson", sentences[0])

    def test_dr_title_with_nickname_kept(self):
        text = "Class size is small. Dr. Mike makes lectures engaging."
        m = _AliasMatcher("Michael Anderson")
        sentences = m.select_sentences(text)
        self.assertEqual(len(sentences), 1)
        self.assertIn("Mike", sentences[0])


class InstitutionKeywordTests(unittest.TestCase):
    def test_strips_university_of(self):
        self.assertEqual(_institution_keyword("University of California, Berkeley"), "California")

    def test_returns_none_for_empty(self):
        self.assertIsNone(_institution_keyword(""))
        self.assertIsNone(_institution_keyword(None))

    def test_keeps_proper_acronyms(self):
        # Short acronyms can still be useful.
        self.assertEqual(_institution_keyword("MIT"), "MIT")

    def test_drops_only_stop_words(self):
        # Stop-word-only school names are ignored.
        self.assertIsNone(_institution_keyword("The University of"))


class SubredditDerivationTests(unittest.TestCase):
    def test_known_school_routes_to_specific_sub(self):
        subs = _subreddits_for_institution("Brigham Young University")
        self.assertEqual(subs[0], "BYU")
        self.assertIn("college", subs)

    def test_prefix_match_works(self):
        subs = _subreddits_for_institution("Brigham Young University - Idaho")
        self.assertEqual(subs[0], "BYU")

    def test_unknown_school_falls_back_to_generics(self):
        subs = _subreddits_for_institution("Some Tiny College Nobody Has Heard Of")
        self.assertEqual(subs, list(DEFAULT_SUBREDDITS))

    def test_no_institution_returns_generics_only(self):
        self.assertEqual(_subreddits_for_institution(None), list(DEFAULT_SUBREDDITS))

    def test_dedupes_across_overlap(self):
        # Returned subreddit names should be unique.
        subs = _subreddits_for_institution("Brigham Young University")
        self.assertEqual(len(subs), len(set(s.lower() for s in subs)))


class QueryShapingTests(unittest.TestCase):
    def test_school_specific_sub_uses_last_name_only(self):
        q = _query_for_sub("Mark Ogletree", "Brigham", "BYU")
        self.assertEqual(q, "Ogletree")

    def test_generic_sub_uses_quoted_full_name_plus_kw(self):
        q = _query_for_sub("Mark Ogletree", "Brigham", "college")
        self.assertEqual(q, '"Mark Ogletree" Brigham')

    def test_generic_sub_without_kw(self):
        q = _query_for_sub("Mark Ogletree", None, "AskAcademia")
        self.assertEqual(q, '"Mark Ogletree"')


class CleanBodyTests(unittest.TestCase):
    def test_drops_deleted_markers(self):
        self.assertEqual(_clean_body("[deleted]"), "")
        self.assertEqual(_clean_body("[removed]"), "")

    def test_strips_quote_markers(self):
        self.assertEqual(_clean_body("> hi\nthere"), "hi\nthere")

    def test_collapses_runs_of_blank_lines(self):
        self.assertIn("\n\n", _clean_body("a\n\n\n\nb"))
        self.assertNotIn("\n\n\n", _clean_body("a\n\n\n\nb"))


class CommentTreeWalkTests(unittest.TestCase):
    """Comment-tree walking cases."""

    def _t1(self, body: str, replies=None, comment_id="c1") -> dict:
        return {
            "kind": "t1",
            "data": {
                "body": body,
                "id": comment_id,
                "permalink": f"/r/test/comments/abc/_/{comment_id}/",
                "created_utc": 1700000000,
                "replies": (
                    {"data": {"children": replies}} if replies else ""
                ),
            },
        }

    def test_direct_mention_kept(self):
        forest = [
            self._t1(
                "Took Ogletree last fall and the class was super easy. "
                "Highly recommend taking him for an easy A.",
                comment_id="c1",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 1)
        self.assertIn("Ogletree", out[0]["text"])

    def test_chain_inheritance_no_longer_pulls_in_unrelated_replies(self):
        # Child reply must mention the professor itself.
        forest = [
            self._t1(
                "Took Ogletree last fall. " + "x" * 60,
                replies=[
                    self._t1(
                        "Yeah that class was super easy. " + "x" * 60,
                        comment_id="c2",
                    ),
                ],
                comment_id="c1",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        # Only the direct mention is kept.
        self.assertEqual(len(out), 1)
        self.assertIn("Ogletree", out[0]["text"])

    def test_descendant_with_own_mention_still_kept(self):
        # A reply can match even if its parent does not.
        forest = [
            self._t1(
                "What classes are you taking next term? " + "x" * 60,
                replies=[
                    self._t1(
                        "I'm signed up for Ogletree's section next term and "
                        "I've heard nothing but glowing things from "
                        "upperclassmen who took him already.",
                        comment_id="c2",
                    ),
                ],
                comment_id="c1",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 1)
        self.assertIn("Ogletree", out[0]["text"])

    def test_mixed_prof_comment_sliced_to_relevant_sentence(self):
        # Mixed-professor comments get sliced.
        forest = [
            self._t1(
                "Smith is awful and you should avoid his class like the plague. "
                "Ogletree on the other hand is patient and grades fairly.",
                comment_id="c1",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 1)
        self.assertIn("Ogletree", out[0]["text"])
        self.assertNotIn("Smith", out[0]["text"])
        self.assertNotIn("plague", out[0]["text"])

    def test_off_topic_sibling_excluded(self):
        forest = [
            self._t1(
                "Ogletree is great. " + "x" * 60,
                comment_id="a",
            ),
            self._t1(
                "Anyone know a good chemistry prof? " + "x" * 60,
                replies=[
                    self._t1(
                        "Try Smith for chem. " + "x" * 60,
                        comment_id="a2",
                    ),
                ],
                comment_id="b",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 1)
        self.assertIn("Ogletree", out[0]["text"])

    def test_skips_short_comments(self):
        forest = [self._t1("Ogletree good.", comment_id="c1")]  # < MIN_TEXT_LEN
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(out, [])

    def test_respects_max_comments_cap(self):
        forest = [
            self._t1(
                f"Ogletree is solid in section {i}. " + "x" * 60,
                comment_id=f"c{i}",
            )
            for i in range(10)
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Mark Ogletree")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=3, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 3)

    def test_nickname_in_descendant_kept(self):
        forest = [
            self._t1(
                "What's everyone's experience with the philosophy department?"
                + " " + "x" * 60,
                replies=[
                    self._t1(
                        "Dr. Mike taught my intro course and was amazing. "
                        "I'd take any class he teaches.",
                        comment_id="c2",
                    ),
                ],
                comment_id="c1",
            ),
        ]
        out: list[dict] = []
        matcher = _AliasMatcher("Michael Anderson")
        _walk(forest, matcher=matcher, out=out, post_url="https://r/",
              max_comments=10, deadline=time.monotonic() + 5)
        self.assertEqual(len(out), 1)
        self.assertIn("Mike", out[0]["text"])


if __name__ == "__main__":
    unittest.main()
