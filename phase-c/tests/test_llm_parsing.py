"""Model replies are not all strict JSON. The boundary must accept what the
configured model actually emits, without loosening what counts as valid."""

import pytest
from pydantic import BaseModel

from phase_c.llm.base import LLMError, parse_structured


class Answer(BaseModel):
    claim: str
    limits: str = ""


def test_plain_json():
    assert parse_structured('{"claim": "a"}', Answer).claim == "a"


def test_fenced_json():
    assert parse_structured('```json\n{"claim": "a"}\n```', Answer).claim == "a"


def test_python_style_single_quotes():
    """Granite 4 sometimes replies with a Python dict rather than JSON."""
    assert parse_structured("{'claim': 'a', 'limits': 'b'}", Answer).limits == "b"


def test_apostrophes_survive_the_python_literal_path():
    """A naive quote swap would corrupt this; literal_eval does not."""
    result = parse_structured(r"{'claim': 'NASA\'s guidance', 'limits': ''}", Answer)
    assert result.claim == "NASA's guidance"


def test_prose_around_the_object_is_ignored():
    assert parse_structured('Sure!\n{"claim": "a"}\nHope that helps.', Answer).claim == "a"


def test_no_object_at_all_is_an_error():
    with pytest.raises(LLMError, match="No JSON object"):
        parse_structured("I cannot answer that.", Answer)


def test_a_wrong_shape_is_still_rejected():
    with pytest.raises(LLMError, match="did not match"):
        parse_structured('{"unrelated": 1}', Answer)


def test_truncated_output_is_still_rejected():
    with pytest.raises(LLMError):
        parse_structured('{"claim": "a', Answer)


def test_the_fallback_evaluates_literals_only():
    """literal_eval must not become an execution path for model output."""
    with pytest.raises(LLMError):
        parse_structured("{'claim': __import__('os').getcwd()}", Answer)
