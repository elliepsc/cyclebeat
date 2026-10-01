"""The phase-4 exit criterion: `openapi.yaml` and the implementation must not diverge.

Two independent checks, because either alone is escapable:

* **Divergence** — the hand-written `openapi.yaml` is compared against the schema FastAPI
  generates from the code. This is the one that enforces contract-*first*: it fails when the
  code grows an endpoint, a status or a required field the contract never promised.
* **Schemathesis** — generates requests from `openapi.yaml` and asserts the app's real
  responses conform. This catches the opposite failure, where both documents agree on paper
  and the server does something else.

Note which document is authoritative when they disagree: `openapi.yaml` is the contract, and a
failure here means the *code* is wrong, not the YAML. Regenerating the YAML from the app to
make this file pass would delete the only thing criterion 5 actually grades.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "openapi.yaml"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture(scope="module")
def generated() -> dict[str, Any]:
    """What FastAPI derives from the code. Never written to disk — see the module docstring."""
    schema: dict[str, Any] = app.openapi()
    return schema


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ── The contract file itself ─────────────────────────────────────────────────────────────


def test_the_contract_is_a_valid_openapi_document(contract: dict[str, Any]) -> None:
    openapi_spec_validator = pytest.importorskip("openapi_spec_validator")
    openapi_spec_validator.validate(contract)


def test_the_contract_declares_openapi_31(contract: dict[str, Any]) -> None:
    assert contract["openapi"].startswith("3.1")


def test_the_contract_and_the_app_agree_on_the_version(
    contract: dict[str, Any], generated: dict[str, Any]
) -> None:
    assert contract["info"]["version"] == generated["info"]["version"]


# ── Divergence: contract vs generated schema ─────────────────────────────────────────────


def test_no_endpoint_exists_that_the_contract_does_not_declare(
    contract: dict[str, Any], generated: dict[str, Any]
) -> None:
    """The contract-first direction. An endpoint added to the code without being contracted
    first fails here, which is the whole point of writing the YAML by hand."""
    contracted = _operations(contract)
    implemented = _operations(generated)

    undeclared = implemented - contracted
    assert not undeclared, f"implemented but not in openapi.yaml: {sorted(undeclared)}"


def test_every_contracted_endpoint_is_implemented(
    contract: dict[str, Any], generated: dict[str, Any]
) -> None:
    missing = _operations(contract) - _operations(generated)
    assert not missing, f"in openapi.yaml but not implemented: {sorted(missing)}"


def test_every_contracted_success_status_is_implemented(
    contract: dict[str, Any], generated: dict[str, Any]
) -> None:
    """Statuses the contract promises must exist in the app.

    Only 2xx are compared. FastAPI adds its own 422 to every operation with a body or a
    typed parameter, and asserting on the error statuses would make this test track FastAPI's
    behaviour rather than the contract's promises.
    """
    for path, method in sorted(_operations(contract)):
        promised = {
            code
            for code in contract["paths"][path][method]["responses"]
            if code.startswith("2")
        }
        actual = set(generated["paths"][path][method]["responses"])
        assert promised <= actual, f"{method.upper()} {path}: missing {promised - actual}"


def test_no_schema_diverges_from_the_contract(
    contract: dict[str, Any], generated: dict[str, Any]
) -> None:
    """Property sets and `required` sets, per shared schema. The load-bearing check.

    Without it the divergence tests compare only paths, methods, operationIds and 2xx
    statuses — so **dropping `SessionPlan.warnings` from the code passed CI**, which is exactly
    the silent mutation the contract exists to prevent. Found by contract-guardian, and
    `test_the_divergence_check_actually_catches_a_dropped_field` proves this one bites.
    """
    contracted = contract["components"]["schemas"]
    implemented = generated.get("components", {}).get("schemas", {})

    problems: list[str] = []
    for name, schema in contracted.items():
        actual = implemented.get(name)
        if actual is None:
            # Not every contract schema is a response model FastAPI emits — `Problem` is
            # rendered by an exception handler, so it has no generated counterpart.
            continue

        expected_props = set(schema.get("properties", {}))
        actual_props = set(actual.get("properties", {}))
        if missing := expected_props - actual_props:
            problems.append(f"{name}: contracted but not implemented: {sorted(missing)}")
        if extra := actual_props - expected_props:
            problems.append(f"{name}: implemented but not contracted: {sorted(extra)}")

        expected_required = set(schema.get("required", []))
        actual_required = set(actual.get("required", []))
        if expected_required != actual_required:
            problems.append(
                f"{name}: required differs — contract-only "
                f"{sorted(expected_required - actual_required)}, "
                f"code-only {sorted(actual_required - expected_required)}"
            )

    assert not problems, " | ".join(problems)


def test_the_divergence_check_actually_catches_a_dropped_field(
    contract: dict[str, Any]
) -> None:
    """The check on the check.

    Mutates the *generated* schema the way a careless edit to `api/schemas.py` would — drops a
    required field — and asserts the comparison above reports it. Without this, a weakened
    divergence test would look exactly like a passing one.
    """
    mutated = {
        "components": {
            "schemas": {
                name: {
                    **schema,
                    "properties": {
                        k: v for k, v in schema.get("properties", {}).items() if k != "warnings"
                    },
                    "required": [r for r in schema.get("required", []) if r != "warnings"],
                }
                if name == "SessionPlan"
                else schema
                for name, schema in app.openapi()["components"]["schemas"].items()
            }
        }
    }

    with pytest.raises(AssertionError) as raised:
        test_no_schema_diverges_from_the_contract(contract, mutated)

    assert "SessionPlan" in str(raised.value)
    assert "warnings" in str(raised.value)


def test_operation_ids_match(contract: dict[str, Any], generated: dict[str, Any]) -> None:
    """`operationId` is what generates the phase-5 TypeScript client's method names.

    A drift here silently renames a function in the frontend client, so it is pinned.
    """
    for path, method in sorted(_operations(contract)):
        expected = contract["paths"][path][method].get("operationId")
        actual = generated["paths"][path][method].get("operationId")
        assert expected == actual, f"{method.upper()} {path}: {expected!r} != {actual!r}"


@pytest.mark.parametrize(
    ("schema_name", "field"),
    [
        ("SessionPlan", "session_id"),
        ("SessionPlan", "verdict"),
        ("SessionPlan", "segments"),
        ("SessionPlan", "duration_gap_s"),
        ("SessionPlan", "warnings"),
        ("Segment", "order"),
        ("Segment", "zone"),
        ("Segment", "duration_s"),
        ("Problem", "type"),
        ("Problem", "title"),
        ("Problem", "status"),
    ],
)
def test_the_e3_normative_fields_are_required_in_the_contract(
    contract: dict[str, Any], schema_name: str, field: str
) -> None:
    """E.3 fixes these shapes; a field quietly becoming optional is a contract break."""
    schema = contract["components"]["schemas"][schema_name]
    assert field in schema["required"], f"{schema_name}.{field} is no longer required"


def test_the_copilot_endpoints_are_absent_until_phase_6(contract: dict[str, Any]) -> None:
    """They need fct_llm_calls, fct_agent_runs and the agent — none of which exist.

    Contracting them now would make the divergence check above a lie.
    """
    paths = set(contract["paths"])
    assert not [p for p in paths if "copilot" in p or "llm-costs" in p]


# ── The app actually behaves ─────────────────────────────────────────────────────────────


def test_health_conforms(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_errors_use_the_rfc_7807_shape(client: TestClient) -> None:
    """E.3 requires it, and FastAPI's default `{"detail": [...]}` is not it."""
    response = client.post("/v1/sessions/nonexistent/feedback", json={"rating": "up"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert {"type", "title", "status"} <= set(body)
    assert body["status"] == 404


def test_a_validation_failure_is_also_rfc_7807(client: TestClient) -> None:
    response = client.post(
        "/v1/sessions/generate",
        json={
            "source": {"type": "demo", "value": ""},
            "level": "advanced",
            "goal": "intervals",
            "duration_min": 5,  # E.3 floor is 20
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["reasons"], "a validation problem should name what failed"


# ── Schemathesis ─────────────────────────────────────────────────────────────────────────


def test_schemathesis_drives_the_contract_against_the_app() -> None:
    """Generate requests from `openapi.yaml` and assert the responses conform.

    Run as one test rather than via the `schemathesis.parametrize()` plugin so the suite has
    no dependency on that plugin's pytest integration, which changes across major versions.
    Read-only operations only: the generated bodies are arbitrary, and pointing them at
    `POST /v1/sessions/generate` would write junk sessions into the developer's warehouse on
    every run.
    """
    schemathesis = pytest.importorskip("schemathesis")

    # schemathesis 3.x refuses OpenAPI 3.1 unless this is enabled. The contract stays 3.1
    # rather than being downgraded to satisfy the tool: FastAPI 0.115 *generates* 3.1, so a
    # 3.0 contract would guarantee a version mismatch in the divergence checks above — the
    # tail wagging the dog. Drop this line when schemathesis 4 lands.
    schemathesis.experimental.OPEN_API_3_1.enable()

    schema = schemathesis.from_path(str(CONTRACT_PATH), app=app)
    client = TestClient(app)

    checked = 0
    for path in ("/health", "/v1/quality/coverage", "/v1/quality/summary", "/v1/sessions"):
        operation = schema[path]["GET"]
        case = operation.make_case()
        response = client.request(case.method, case.formatted_path, params=case.query)
        case.validate_response(
            _AsRequestsResponse(response), checks=(schemathesis.checks.status_code_conformance,)
        )
        assert response.status_code == 200
        checked += 1

    assert checked == 4


class _AsRequestsResponse:
    """Adapt httpx's response to what schemathesis' checks expect.

    `TestClient` returns an httpx response; schemathesis' `validate_response` is written
    against the requests API. Only the handful of attributes the checks touch are bridged.
    """

    def __init__(self, response: Any) -> None:
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.content = response.content
        self.text = response.text
        self.request = response.request
        self.elapsed = response.elapsed

    def json(self) -> Any:
        return self._response.json()


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Every `(path, method)` an OpenAPI document declares.

    `/metrics` is excluded: the Prometheus instrumentator mounts it with
    `include_in_schema=False`, so it is deliberately outside the contract.
    """
    methods = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
    return {
        (path, method)
        for path, operations in schema.get("paths", {}).items()
        for method in operations
        if method in methods
    }
