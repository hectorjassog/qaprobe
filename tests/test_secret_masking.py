"""Unit tests for secret masking in reports."""

from qaprobe.report import mask_secrets


def test_fill_text_is_masked_by_default():
    steps = [
        {"tool": "fill", "input": {"ref": "inp:password", "text": "s3cret"}, "result": "ok"},
        {"tool": "click", "input": {"ref": "btn:submit"}, "result": "ok"},
    ]
    masked = mask_secrets(steps)
    assert masked[0]["input"]["text"] == "***"
    assert masked[1]["input"]["ref"] == "btn:submit"


def test_reveal_fields_bypass_masking():
    steps = [
        {"tool": "fill", "input": {"ref": "inp:username", "text": "admin"}, "result": "ok"},
        {"tool": "fill", "input": {"ref": "inp:password", "text": "s3cret"}, "result": "ok"},
    ]
    masked = mask_secrets(steps, reveal_fields=["inp:username"])
    assert masked[0]["input"]["text"] == "admin"
    assert masked[1]["input"]["text"] == "***"


def test_non_fill_steps_unchanged():
    steps = [
        {"tool": "click", "input": {"ref": "btn:0"}, "result": "ok"},
        {"tool": "navigate", "input": {"url": "https://example.com"}, "result": "ok"},
    ]
    masked = mask_secrets(steps)
    assert masked == steps


def test_empty_steps():
    assert mask_secrets([]) == []
