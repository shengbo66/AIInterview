"""Unit tests for utils.parse_json_strict — pure parsing, no external deps."""
import pytest

from shared.eval_core.utils import parse_json_strict


class TestParseJsonStrict:
    def test_plain_json(self):
        assert parse_json_strict('{"a": 1}') == {"a": 1}

    def test_with_whitespace(self):
        assert parse_json_strict('   {"a": 1}  \n') == {"a": 1}

    def test_markdown_fenced_json(self):
        text = '```json\n{"a": 1, "b": "x"}\n```'
        assert parse_json_strict(text) == {"a": 1, "b": "x"}

    def test_markdown_fenced_plain(self):
        text = '```\n{"a": 1}\n```'
        assert parse_json_strict(text) == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_json_strict("not json")

    def test_nested(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        assert parse_json_strict(text) == {"outer": {"inner": [1, 2, 3]}}
