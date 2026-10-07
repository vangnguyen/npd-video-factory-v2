"""Additive Native cost intents, separate from provider authority and billed receipts."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re

from .contracts import WorkflowError, digest
from .store import now


def amount(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise WorkflowError("COST_AMOUNT_INVALID", 400)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise WorkflowError("COST_AMOUNT_INVALID", 400) from None
    if not parsed.is_finite() or parsed < 0 or parsed > Decimal("1000000000000") or parsed.as_tuple().exponent < -6:
        raise WorkflowError("COST_AMOUNT_INVALID", 400)
    return parsed


def wire(value):
    return format(value, "f") if value is not None else None


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        raise WorkflowError("COST_OPERATION_BINDING_INVALID", 400)
    return value


class CostLedger:
    """Same owned Native SQLite boundary; no API/Hub database or secrets accessed."""
    def __init__(self, store):
        self.store = store
        with store.transaction() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS native_cost_operations (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT,
                provider TEXT NOT NULL, model TEXT, operation TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, estimated_cost TEXT, actual_cost TEXT,
                status TEXT NOT NULL, external_call INTEGER NOT NULL, paid INTEGER NOT NULL,
                needs_approval INTEGER NOT NULL, receipt TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            con.execute("CREATE INDEX IF NOT EXISTS native_cost_project ON native_cost_operations(project_id,created_at)")

    @staticmethod
    def record(row):
        return {**dict(row), "external_call": bool(row["external_call"]), "paid": bool(row["paid"]),
                "needs_approval": bool(row["needs_approval"]), "currency": "VND",
                "receipt": json.loads(row["receipt"]) if row["receipt"] else None,
                "budget_reserved_vnd": row["estimated_cost"], "reservation_is_billed_cost": False}

    @staticmethod
    def project(con, identifier):
        row = con.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise WorkflowError("PROJECT_NOT_FOUND", 404)
        return row, json.loads(row["document"])

    def begin(self, *, project_id, job_id=None, provider, model, operation, request_sha256,
              estimated_cost=None, external_call=True, paid=True):
        """Commit a conservative dispatch intent before the call. This grants no provider authority."""
        provider, operation = label(provider), label(operation)
        if model is not None:
            label(model)
        if not isinstance(request_sha256, str) or not re.fullmatch("[a-f0-9]{64}", request_sha256):
            raise WorkflowError("COST_OPERATION_BINDING_INVALID", 400)
        if type(external_call) is not bool or type(paid) is not bool:
            raise WorkflowError("COST_OPERATION_BINDING_INVALID", 400)
        estimate = amount(estimated_cost)
        identifier = digest({"project": project_id, "job": job_id, "provider": provider, "operation": operation})
        blocked = False
        with self.store.transaction() as con:
            _, document = self.project(con, project_id)
            if job_id is not None:
                job = con.execute("SELECT project_id,snapshot FROM jobs WHERE id=?", (job_id,)).fetchone()
                if job is None or job["project_id"] != project_id:
                    raise WorkflowError("COST_JOB_SCOPE_MISMATCH", 400)
                # Job budget is frozen in its approved/requested document, with current
                # spending still counted atomically from the ledger.
                document = json.loads(job["snapshot"])["document"]
            prior = con.execute("SELECT * FROM native_cost_operations WHERE id=?", (identifier,)).fetchone()
            if prior:
                if (prior["request_sha256"] != request_sha256 or prior["model"] != model
                        or prior["estimated_cost"] != wire(estimate)
                        or bool(prior["paid"]) != paid or bool(prior["external_call"]) != external_call):
                    raise WorkflowError("COST_OPERATION_CONFLICT")
                raise WorkflowError("COST_OPERATION_ALREADY_DISPATCHED_NO_REPLAY")
            limit = amount((document.get("cost_policy") or {}).get("max_ai_cost_vnd"))
            exposure = Decimal(0)
            unknown = False
            for row in con.execute("SELECT * FROM native_cost_operations WHERE project_id=? AND paid=1 AND status!='needs_approval'", (project_id,)):
                reserved = amount(row["actual_cost"] if row["actual_cost"] is not None else row["estimated_cost"])
                if reserved is None:
                    unknown = True
                else:
                    exposure += reserved
            blocked = bool(paid and limit is not None and
                           (unknown or estimate is None or exposure + estimate > limit))
            stamp = now()
            con.execute("INSERT INTO native_cost_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                identifier, project_id, job_id, provider, model, operation, request_sha256,
                wire(estimate), None, "needs_approval" if blocked else "dispatch_intent",
                int(external_call), int(paid), int(blocked), None, stamp, stamp))
            self.store.event(con, project_id, "cost_approval_required" if blocked else "cost_dispatch_intent", {
                "cost_operation_id": identifier, "job_id": job_id, "provider": provider,
                "estimated_cost_vnd": wire(estimate), "currency": "VND", "provider_authorized": False})
        if blocked:
            raise WorkflowError("AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH")
        return identifier

    def settle(self, identifier, *, status, actual_cost=None, billing_receipt_sha256=None,
               usage=None, response_sha256=None, error_code=None):
        if status not in {"response_received", "outcome_unknown", "rejected"}:
            raise WorkflowError("COST_RECEIPT_INVALID", 400)
        actual = amount(actual_cost)
        for checksum in (billing_receipt_sha256, response_sha256):
            if checksum is not None and (not isinstance(checksum, str) or not re.fullmatch("[a-f0-9]{64}", checksum)):
                raise WorkflowError("COST_RECEIPT_INVALID", 400)
        if usage is not None and (not isinstance(usage, dict) or set(usage) - {"input_tokens", "output_tokens", "total_tokens"}
                                  or any(type(v) is not int or not 0 <= v <= 1000000000 for v in usage.values())):
            raise WorkflowError("COST_RECEIPT_INVALID", 400)
        if error_code is not None and (not isinstance(error_code, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,120}", error_code)):
            raise WorkflowError("COST_RECEIPT_INVALID", 400)
        receipt = {"schema": "native-cost-receipt-v1", "usage": usage,
                   "provider_response_sha256": response_sha256, "billing_receipt_sha256": billing_receipt_sha256,
                   "error_code": error_code, "actual_cost_known": actual is not None,
                   "actual_cost_basis": "billing_receipt" if actual is not None else "billed_cost_unavailable"}
        with self.store.transaction() as con:
            row = con.execute("SELECT * FROM native_cost_operations WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise WorkflowError("COST_OPERATION_NOT_FOUND", 404)
            if row["paid"] and actual is not None and billing_receipt_sha256 is None:
                raise WorkflowError("COST_BILLING_RECEIPT_REQUIRED", 400)
            if row["status"] != "dispatch_intent":
                if row["status"] == status and row["actual_cost"] == wire(actual) and json.loads(row["receipt"] or "null") == receipt:
                    return self.record(row)
                raise WorkflowError("COST_IMMUTABLE_RECEIPT_CONFLICT")
            con.execute("UPDATE native_cost_operations SET status=?,actual_cost=?,receipt=?,updated_at=? WHERE id=?", (
                status, wire(actual), json.dumps(receipt), now(), identifier))
            self.store.event(con, row["project_id"], "cost_operation_observed", {
                "cost_operation_id": identifier, "job_id": row["job_id"], "status": status,
                "actual_cost_vnd": wire(actual), "currency": "VND", "billing_known": actual is not None})
            return self.record(con.execute("SELECT * FROM native_cost_operations WHERE id=?", (identifier,)).fetchone())

    def summary(self, project_id):
        with self.store.transaction() as con:
            _, document = self.project(con, project_id)
            records = [self.record(row) for row in con.execute(
                "SELECT * FROM native_cost_operations WHERE project_id=? ORDER BY created_at,id", (project_id,))]
        attempted = [row for row in records if row["status"] != "needs_approval"]
        unknown_estimate = sum(row["estimated_cost"] is None for row in attempted)
        unknown_actual = sum(row["actual_cost"] is None for row in attempted)
        known_estimate = sum((amount(row["estimated_cost"]) or Decimal(0) for row in attempted), Decimal(0))
        known_actual = sum((amount(row["actual_cost"]) or Decimal(0) for row in attempted), Decimal(0))
        exposure = sum((amount(row["actual_cost"] if row["actual_cost"] is not None else row["estimated_cost"]) or Decimal(0)
                        for row in attempted if row["paid"]), Decimal(0))
        limit = amount((document.get("cost_policy") or {}).get("max_ai_cost_vnd"))
        return {"schema": "native-cost-summary-v1", "project_id": project_id, "currency": "VND",
            "records": records, "attempted_operations": len(attempted),
            "known_estimated_cost_subtotal": wire(known_estimate), "known_actual_cost_subtotal": wire(known_actual),
            "estimated_cost_total": None if unknown_estimate else wire(known_estimate),
            "actual_cost_total": None if unknown_actual else wire(known_actual),
            "unknown_estimated_cost_operations": unknown_estimate, "unknown_actual_cost_operations": unknown_actual,
            "estimated_cost_complete": not unknown_estimate, "actual_cost_complete": not unknown_actual,
            "max_ai_cost_vnd": wire(limit), "known_budget_exposure_vnd": wire(exposure),
            "needs_approval": any(row["needs_approval"] for row in records) or (limit is not None and exposure > limit),
            "needs_attention": any(row["status"] in {"dispatch_intent", "outcome_unknown"} for row in attempted),
            "totals_basis": "recorded_operations_only_v1", "historical_capture_complete": False,
            "full_project_cost_capture_verified": False, "local_compute_cost": None,
            "provider_authorized": False, "publishing_enabled": False}

    def pending(self, identifier):
        with self.store.transaction() as con:
            row = con.execute("SELECT status FROM native_cost_operations WHERE id=?", (identifier,)).fetchone()
            return row is not None and row["status"] == "dispatch_intent"

    def set_budget(self, project_id, revision, value):
        limit = amount(value)
        with self.store.transaction() as con:
            project = self.store.editable(con, project_id, revision)
            document = project["document"]
            document["cost_policy"] = {"schema": "native-project-cost-policy-v1", "max_ai_cost_vnd": wire(limit)}
            con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?", (
                revision + 1, json.dumps(document, ensure_ascii=False), now(), project_id))
            self.store.version(con, project_id)
            self.store.event(con, project_id, "cost_policy_saved_review_required", {
                "revision": revision + 1, "max_ai_cost_vnd": wire(limit), "provider_authorized": False})
        return self.store.get(project_id)


def token_usage(usage):
    """No prompt, response body, aliases or credential values enter cost receipts."""
    if usage is None:
        return None
    values = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if not isinstance(values, dict):
        return None
    return {key: values[key] for key in ("input_tokens", "output_tokens", "total_tokens")
            if type(values.get(key)) is int and 0 <= values[key] <= 1000000000}
