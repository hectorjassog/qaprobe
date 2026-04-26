"""Unit tests for a11y finding detection."""

from qaprobe.a11y import audit_snapshot
from qaprobe.browser import AXElement, Snapshot


def _snap(*elements):
    s = Snapshot(elements=list(elements))
    return s


def test_no_findings_on_clean_page():
    snap = _snap(
        AXElement(ref="btn:0", role="button", name="Submit"),
        AXElement(ref="lnk:0", role="link", name="Home"),
    )
    findings = audit_snapshot(snap)
    assert findings == []


def test_unlabeled_button():
    snap = _snap(AXElement(ref="btn:0", role="button", name=""))
    findings = audit_snapshot(snap)
    assert len(findings) == 1
    assert findings[0].type == "unlabeled_button"


def test_unlabeled_input():
    snap = _snap(AXElement(ref="inp:0", role="textbox", name=""))
    findings = audit_snapshot(snap)
    assert len(findings) == 1
    assert findings[0].type == "missing_label"


def test_missing_alt():
    snap = _snap(AXElement(ref="img:0", role="img", name=""))
    findings = audit_snapshot(snap)
    assert len(findings) == 1
    assert findings[0].type == "missing_alt"


def test_heading_skip():
    snap = _snap(
        AXElement(ref="hd:0", role="heading", name="Title", level=1),
        AXElement(ref="hd:1", role="heading", name="Section", level=3),  # skips h2
    )
    findings = audit_snapshot(snap)
    assert any(f.type == "heading_skip" for f in findings)


def test_no_heading_skip_on_sequential():
    snap = _snap(
        AXElement(ref="hd:0", role="heading", name="Title", level=1),
        AXElement(ref="hd:1", role="heading", name="Sub", level=2),
        AXElement(ref="hd:2", role="heading", name="SubSub", level=3),
    )
    findings = audit_snapshot(snap)
    assert not any(f.type == "heading_skip" for f in findings)


def test_unlabeled_link():
    snap = _snap(AXElement(ref="lnk:0", role="link", name=""))
    findings = audit_snapshot(snap)
    assert len(findings) == 1
    assert findings[0].type == "unlabeled_link"
