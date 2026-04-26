from __future__ import annotations

from .browser import Snapshot
from .report import A11yFinding


def audit_snapshot(snapshot: Snapshot) -> list[A11yFinding]:
    """Passively audit an AX tree snapshot for accessibility issues."""
    findings: list[A11yFinding] = []

    last_heading_level = 0

    for el in snapshot.elements:
        # Inputs with no accessible name
        if el.role in ("textbox", "combobox", "spinbutton", "searchbox") and not el.name:
            findings.append(
                A11yFinding(
                    type="missing_label",
                    severity="error",
                    element_ref=el.ref,
                    element_role=el.role,
                    element_name=el.name,
                    message=(
                        f"Input ({el.role}) has no accessible name — "
                        "screen readers cannot identify this field"
                    ),
                )
            )

        # Buttons with no accessible name
        if el.role == "button" and not el.name:
            findings.append(
                A11yFinding(
                    type="unlabeled_button",
                    severity="error",
                    element_ref=el.ref,
                    element_role=el.role,
                    element_name="",
                    message=(
                        "Button has no accessible name — "
                        "screen readers cannot describe its purpose"
                    ),
                )
            )

        # Images with no alt text (empty name for img role)
        if el.role == "img" and not el.name:
            findings.append(
                A11yFinding(
                    type="missing_alt",
                    severity="error",
                    element_ref=el.ref,
                    element_role=el.role,
                    element_name="",
                    message="Image has no alt text — screen readers cannot convey its content",
                )
            )

        # Links with no accessible name
        if el.role == "link" and not el.name:
            findings.append(
                A11yFinding(
                    type="unlabeled_link",
                    severity="warning",
                    element_ref=el.ref,
                    element_role=el.role,
                    element_name="",
                    message=(
                        "Link has no accessible name — "
                        "screen readers cannot describe its destination"
                    ),
                )
            )

        # Headings that skip levels (h1 → h3, etc.)
        if el.role == "heading" and el.level > 0:
            if last_heading_level > 0 and el.level > last_heading_level + 1:
                findings.append(
                    A11yFinding(
                        type="heading_skip",
                        severity="warning",
                        element_ref=el.ref,
                        element_role=el.role,
                        element_name=el.name,
                        message=(
                            f"Heading level skipped from h{last_heading_level} to h{el.level} "
                            "— breaks document outline"
                        ),
                    )
                )
            last_heading_level = el.level

    return findings
