"""Tests for critical path schema: load, save, and round-trip."""

import yaml

from qaprobe.critical_path import (
    CriticalPath,
    CriticalPathFile,
    Locator,
    PathStep,
    load_critical_paths,
    save_critical_paths,
)


def _sample_yaml():
    return (
        "name: checkout-flow\n"
        "base_url: https://example.com\n"
        "auth:\n"
        "  storage_state: .auth/state.json\n"
        "critical_paths:\n"
        "  - name: add_to_cart\n"
        "    description: Add item and checkout\n"
        "    steps:\n"
        "      - action: navigate\n"
        "        url: /products\n"
        "      - action: click\n"
        "        locator:\n"
        "          role: button\n"
        "          name: Add to Cart\n"
        "      - action: fill\n"
        "        locator:\n"
        "          role: textbox\n"
        "          name: Email\n"
        "        value: test@example.com\n"
        "      - action: press_key\n"
        "        key: Enter\n"
        "    verify: Order confirmation is visible\n"
    )


def test_load_basic(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(_sample_yaml())
    cpf = load_critical_paths(str(f))

    assert cpf.name == "checkout-flow"
    assert cpf.base_url == "https://example.com"
    assert cpf.auth_storage_state == ".auth/state.json"
    assert len(cpf.paths) == 1

    cp = cpf.paths[0]
    assert cp.name == "add_to_cart"
    assert cp.description == "Add item and checkout"
    assert cp.verify == "Order confirmation is visible"
    assert len(cp.steps) == 4


def test_load_step_types(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(_sample_yaml())
    cpf = load_critical_paths(str(f))
    steps = cpf.paths[0].steps

    assert steps[0].action == "navigate"
    assert steps[0].url == "/products"
    assert steps[0].locator is None

    assert steps[1].action == "click"
    assert steps[1].locator is not None
    assert steps[1].locator.role == "button"
    assert steps[1].locator.name == "Add to Cart"

    assert steps[2].action == "fill"
    assert steps[2].locator.role == "textbox"
    assert steps[2].value == "test@example.com"

    assert steps[3].action == "press_key"
    assert steps[3].key == "Enter"


def test_load_no_auth(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(
        "name: simple\n"
        "base_url: http://localhost:3000\n"
        "critical_paths:\n"
        "  - name: homepage\n"
        "    steps:\n"
        "      - action: navigate\n"
        "        url: /\n"
    )
    cpf = load_critical_paths(str(f))
    assert cpf.auth_storage_state is None


def test_save_and_reload(tmp_path):
    cpf = CriticalPathFile(
        base_url="https://example.com",
        name="test-suite",
        paths=[
            CriticalPath(
                name="login_flow",
                description="Test login",
                steps=[
                    PathStep(action="navigate", url="/login"),
                    PathStep(
                        action="fill",
                        locator=Locator(role="textbox", name="Username"),
                        value="admin",
                    ),
                    PathStep(action="click", locator=Locator(role="button", name="Sign In")),
                ],
                verify="Dashboard is visible",
            )
        ],
    )

    out = tmp_path / "out.yml"
    save_critical_paths(cpf, out)
    assert out.exists()

    reloaded = load_critical_paths(str(out))
    assert reloaded.name == "test-suite"
    assert reloaded.base_url == "https://example.com"
    assert len(reloaded.paths) == 1
    assert reloaded.paths[0].name == "login_flow"
    assert reloaded.paths[0].verify == "Dashboard is visible"
    assert len(reloaded.paths[0].steps) == 3
    assert reloaded.paths[0].steps[1].value == "admin"


def test_locator_nth(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(
        "name: nth\n"
        "base_url: http://localhost\n"
        "critical_paths:\n"
        "  - name: test\n"
        "    steps:\n"
        "      - action: click\n"
        "        locator:\n"
        "          role: button\n"
        "          name: Delete\n"
        "          nth: 2\n"
    )
    cpf = load_critical_paths(str(f))
    assert cpf.paths[0].steps[0].locator.nth == 2


def test_locator_to_dict():
    loc = Locator(role="button", name="Submit")
    d = loc.to_dict()
    assert d == {"role": "button", "name": "Submit"}

    loc_nth = Locator(role="link", name="", nth=3)
    d = loc_nth.to_dict()
    assert d == {"role": "link", "nth": 3}


def test_path_step_to_dict():
    step = PathStep(action="click", locator=Locator(role="button", name="OK"))
    d = step.to_dict()
    assert d["action"] == "click"
    assert d["locator"]["role"] == "button"
    assert "url" not in d

    nav = PathStep(action="navigate", url="/home")
    d = nav.to_dict()
    assert d["url"] == "/home"
    assert "locator" not in d


def test_multiple_paths(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(
        "name: multi\n"
        "base_url: http://localhost\n"
        "critical_paths:\n"
        "  - name: path_a\n"
        "    steps:\n"
        "      - action: navigate\n"
        "        url: /a\n"
        "  - name: path_b\n"
        "    steps:\n"
        "      - action: navigate\n"
        "        url: /b\n"
        "      - action: click\n"
        "        locator:\n"
        "          role: button\n"
        "          name: Go\n"
    )
    cpf = load_critical_paths(str(f))
    assert len(cpf.paths) == 2
    assert cpf.paths[0].name == "path_a"
    assert cpf.paths[1].name == "path_b"
    assert len(cpf.paths[1].steps) == 2


def test_save_creates_parent_dirs(tmp_path):
    cpf = CriticalPathFile(
        base_url="http://localhost",
        name="test",
        paths=[CriticalPath(name="t", steps=[PathStep(action="navigate", url="/")])],
    )
    out = tmp_path / "deep" / "nested" / "file.yml"
    save_critical_paths(cpf, out)
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert data["name"] == "test"
