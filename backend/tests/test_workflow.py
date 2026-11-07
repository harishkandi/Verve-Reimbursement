from datetime import date, timedelta

from .conftest import PDF, PNG, line, submitted_claim, this_period, upload


def test_full_lifecycle_to_paid(as_, people):
    claim = submitted_claim(as_, lines=[line(amount="300.00"), line(category_id=2, amount="450.00")])
    assert claim["status"] == "submitted"
    assert claim["approver"]["email"] == "manager@t.co"
    assert claim["total_claimed"] == "750.00"
    cab, food = claim["lines"]

    mgr = as_("manager")
    assert [c["id"] for c in mgr.get("/api/inbox/approvals").json()] == [claim["id"]]
    res = mgr.post(f"/api/claims/{claim['id']}/approve", {
        "lines": [{"line_id": food["id"], "decision": "approve", "approved_amount": "400.00",
                   "reason": "Alcohol not covered"}],
        "comment": "Looks fine",
    })
    assert res.status_code == 200, res.text
    claim = res.json()
    assert claim["status"] == "manager_approved"
    assert claim["total_approved"] == "700.00"
    adjusted = next(ln for ln in claim["lines"] if ln["id"] == food["id"])
    assert adjusted["amount"] == "450.00"  # original kept (BR-6)
    assert adjusted["adjust_reason"] == "Alcohol not covered"

    acc = as_("accounts")
    assert [c["id"] for c in acc.get("/api/inbox/verification").json()] == [claim["id"]]
    claim = acc.post(f"/api/claims/{claim['id']}/verify", {"lines": []}).json()
    assert claim["status"] == "verified"

    assert [c["id"] for c in acc.get("/api/payouts/ready").json()] == [claim["id"]]
    batch = acc.post("/api/payouts", {"payout_date": date.today().isoformat(), "claim_ids": [claim["id"]]})
    assert batch.status_code == 201, batch.text
    batch = batch.json()
    assert batch["total"] == "700.00"

    csv_res = acc.get(f"/api/payouts/{batch['id']}/export?format=csv")
    assert csv_res.status_code == 200
    assert "1234567890" in csv_res.content.decode("utf-8-sig")
    assert acc.get(f"/api/payouts/{batch['id']}/export").content[:2] == b"PK"  # xlsx is a zip

    paid = acc.post(f"/api/payouts/{batch['id']}/mark-paid",
                    {"paid_on": date.today().isoformat(), "reference": "UTR123"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"

    final = as_("dev1").get(f"/api/claims/{claim['id']}").json()
    assert final["status"] == "paid"
    assert final["payment_reference"] == "UTR123"
    assert [e["action"] for e in final["events"]] == [
        "created", "submitted", "manager_approved", "verified", "added_to_batch", "paid",
    ]
    assert final["allowed_actions"] == ["comment"]


def test_online_line_needs_bill_but_cash_can_be_declared(as_, people):
    api = as_("dev1")
    claim = api.post("/api/claims", {"period": this_period()}).json()
    claim = api.post(f"/api/claims/{claim['id']}/lines", line(mode="online")).json()
    res = api.post(f"/api/claims/{claim['id']}/submit")
    assert res.status_code == 422
    assert "online payments need a bill" in res.json()["detail"]

    online_id = claim["lines"][0]["id"]
    api.delete(f"/api/claims/{claim['id']}/lines/{online_id}")
    api.post(f"/api/claims/{claim['id']}/lines", line(mode="cash", amount="80.00"))
    assert api.post(f"/api/claims/{claim['id']}/submit").status_code == 422
    claim = api.get(f"/api/claims/{claim['id']}").json()
    api.put(f"/api/claims/{claim['id']}/lines/{claim['lines'][0]['id']}",
            line(mode="cash", amount="80.00", no_bill_declaration=True))
    assert api.post(f"/api/claims/{claim['id']}/submit").status_code == 200


def test_visibility_and_role_checks(as_, people):
    claim = submitted_claim(as_)
    cid = claim["id"]
    assert as_("dev2").get(f"/api/claims/{cid}").status_code == 404
    assert as_("accounts").post(f"/api/claims/{cid}/approve", {}).status_code == 403
    assert as_("dev1").post(f"/api/claims/{cid}/approve", {}).status_code == 403
    assert as_("manager").post(f"/api/claims/{cid}/verify", {}).status_code == 409
    assert as_("dev1").get("/api/inbox/verification").status_code == 403
    assert as_("dev1").get("/api/payouts/ready").status_code == 403
    assert as_("dev1").get("/api/reports/pending").status_code == 403
    assert as_("manager").get("/api/admin/users").status_code == 403


def test_drafts_are_private_until_submitted(as_, people):
    api = as_("dev1")
    claim = api.post("/api/claims", {"period": this_period()}).json()
    assert as_("manager").get(f"/api/claims/{claim['id']}").status_code == 404
    assert as_("accounts").get(f"/api/claims/{claim['id']}").status_code == 404
    assert as_("admin").get(f"/api/claims/{claim['id']}").status_code == 200


def test_one_claim_per_month(as_, people):
    api = as_("dev1")
    first = api.post("/api/claims", {"period": this_period()})
    again = api.post("/api/claims", {"period": this_period()})
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    next_month = date.today().replace(day=28) + timedelta(days=5)
    assert api.post("/api/claims", {"period": f"{next_month:%Y-%m}"}).status_code == 422


def test_return_edit_resubmit_resets_decisions(as_, people):
    claim = submitted_claim(as_)
    cid = claim["id"]
    mgr = as_("manager")
    assert mgr.post(f"/api/claims/{cid}/return", {"comment": ""}).status_code == 422
    claim = mgr.post(f"/api/claims/{cid}/return", {"comment": "Wrong date"}).json()
    assert claim["status"] == "returned"

    api = as_("dev1")
    ln = claim["lines"][0]
    api.put(f"/api/claims/{cid}/lines/{ln['id']}", line(amount="250.00"))
    claim = api.post(f"/api/claims/{cid}/submit").json()
    assert claim["status"] == "submitted"
    assert claim["lines"][0]["status"] == "pending"

    # Accounts returning after manager approval sends it back to the employee, then the manager again.
    mgr.post(f"/api/claims/{cid}/approve", {})
    claim = as_("accounts").post(f"/api/claims/{cid}/return", {"comment": "Bill unreadable"}).json()
    assert claim["status"] == "returned"
    claim = api.post(f"/api/claims/{cid}/submit").json()
    assert claim["status"] == "submitted"
    assert claim["approver"]["email"] == "manager@t.co"


def test_reject_is_final(as_, people):
    claim = submitted_claim(as_)
    cid = claim["id"]
    res = as_("manager").post(f"/api/claims/{cid}/reject", {"comment": "Personal expense"})
    assert res.json()["status"] == "rejected"
    api = as_("dev1")
    assert api.post(f"/api/claims/{cid}/lines", line()).status_code == 409
    assert api.post(f"/api/claims/{cid}/submit").status_code == 409


def test_adjustment_rules(as_, people):
    claim = submitted_claim(as_, lines=[line(amount="300.00"), line(category_id=2, amount="200.00")])
    cid, (a, b) = claim["id"], claim["lines"]
    mgr = as_("manager")

    def approve(*decisions):
        return mgr.post(f"/api/claims/{cid}/approve", {"lines": list(decisions)})

    assert approve({"line_id": a["id"], "decision": "approve", "approved_amount": "250.00"}).status_code == 422
    assert approve({"line_id": a["id"], "decision": "approve", "approved_amount": "350.00",
                    "reason": "x"}).status_code == 422
    assert approve({"line_id": a["id"], "decision": "reject"}).status_code == 422
    both_rejected = approve(
        {"line_id": a["id"], "decision": "reject", "reason": "no"},
        {"line_id": b["id"], "decision": "reject", "reason": "no"},
    )
    assert both_rejected.status_code == 422
    assert "reject the whole claim" in both_rejected.json()["detail"]
    # Failed attempts must not have left partial changes behind.
    assert as_("dev1").get(f"/api/claims/{cid}").json()["status"] == "submitted"

    claim = approve({"line_id": b["id"], "decision": "reject", "reason": "Not official"}).json()
    assert claim["status"] == "manager_approved"
    assert claim["total_approved"] == "300.00"
    event = claim["events"][-1]
    assert event["details"]["changes"][0]["after"]["status"] == "rejected"

    acc = as_("accounts")
    res = acc.post(f"/api/claims/{cid}/verify",
                   {"lines": [{"line_id": b["id"], "decision": "approve"}]})
    assert res.status_code == 409
    res = acc.post(f"/api/claims/{cid}/verify", {"lines": [
        {"line_id": a["id"], "decision": "approve", "approved_amount": "280.00", "reason": "Toll not on bill"},
    ]})
    assert res.json()["total_approved"] == "280.00"


def test_managers_claim_goes_up_and_top_level_needs_fallback(as_, people):
    claim = submitted_claim(as_, owner="manager")
    assert claim["approver"]["email"] == "founder@t.co"

    api = as_("founder")
    c = api.post("/api/claims", {"period": this_period()}).json()
    c = api.post(f"/api/claims/{c['id']}/lines", line(mode="cash", no_bill_declaration=True)).json()
    res = api.post(f"/api/claims/{c['id']}/submit")
    assert res.status_code == 409  # only fallback approver is the founder themself
    assert "No approver" in res.json()["detail"]


def test_withdraw_back_to_draft(as_, people):
    claim = submitted_claim(as_)
    res = as_("dev1").post(f"/api/claims/{claim['id']}/withdraw")
    assert res.json()["status"] == "draft"
    assert as_("manager").get("/api/inbox/approvals").json() == []


def test_upload_validation_and_duplicates(as_, people):
    api = as_("dev1")
    claim = api.post("/api/claims", {"period": this_period()}).json()
    claim = api.post(f"/api/claims/{claim['id']}/lines", line()).json()
    lid = claim["lines"][0]["id"]

    assert upload(api, claim["id"], lid, b"not a pdf").status_code == 422
    assert upload(api, claim["id"], lid, PDF, "text/plain", "x.txt").status_code == 422
    first = upload(api, claim["id"], lid, PNG, "image/png", "bill.png")
    assert first.status_code == 200 and first.json()["duplicate_of_claim_ids"] == []

    other = as_("dev2")
    c2 = other.post("/api/claims", {"period": this_period()}).json()
    c2 = other.post(f"/api/claims/{c2['id']}/lines", line()).json()
    dup = upload(other, c2["id"], c2["lines"][0]["id"], PNG, "image/png", "same.png")
    assert dup.json()["duplicate_of_claim_ids"] == [claim["id"]]
    warnings = other.get(f"/api/claims/{c2['id']}").json()["warnings"]
    assert any(w["code"] == "duplicate_bill" for w in warnings)

    att_id = first.json()["attachment"]["id"]
    res = api.get(f"/api/claims/{claim['id']}/attachments/{att_id}")
    assert res.status_code == 200 and res.content == PNG
    assert other.get(f"/api/claims/{claim['id']}/attachments/{att_id}").status_code == 404


def test_policy_warnings(as_, people):
    old = date.today() - timedelta(days=90)
    claim = submitted_claim(as_, lines=[line(amount="600.00"), line(amount="100.00", day=old)])
    codes = {w["code"] for w in claim["warnings"]}
    assert "over_item_limit" in codes
    assert "too_old" in codes
    assert "outside_period" in codes
    # Warnings never block (v1): the claim is submitted.
    assert claim["status"] == "submitted"
    # The manager's inbox carries the count for triage; the employee's own list doesn't compute it.
    inbox = as_("manager").get("/api/inbox/approvals").json()
    assert inbox[0]["warning_count"] == len(claim["warnings"])
    assert as_("dev1").get("/api/claims").json()[0]["warning_count"] is None


def test_line_validation(as_, people):
    api = as_("dev1")
    claim = api.post("/api/claims", {"period": this_period()}).json()
    url = f"/api/claims/{claim['id']}/lines"
    assert api.post(url, line(category_id=3)).status_code == 422  # inactive
    assert api.post(url, line(amount="0")).status_code == 422
    assert api.post(url, line(day=date.today() + timedelta(days=2))).status_code == 422
    assert api.post(url, line(amount="100.00", tax_amount="150.00")).status_code == 422


def test_payout_batch_rules(as_, people):
    claim = submitted_claim(as_)
    acc = as_("accounts")
    today = date.today().isoformat()
    assert acc.post("/api/payouts", {"payout_date": today, "claim_ids": [claim["id"]]}).status_code == 409

    as_("manager").post(f"/api/claims/{claim['id']}/approve", {})
    acc.post(f"/api/claims/{claim['id']}/verify", {})
    batch = acc.post("/api/payouts", {"payout_date": today, "claim_ids": [claim["id"]]}).json()
    batch = acc.post(f"/api/payouts/{batch['id']}/remove/{claim['id']}").json()
    assert batch["claims"] == []
    assert as_("dev1").get(f"/api/claims/{claim['id']}").json()["status"] == "verified"
    res = acc.post(f"/api/payouts/{batch['id']}/mark-paid", {"paid_on": today, "reference": "X"})
    assert res.status_code == 409


def test_reports(as_, people):
    claim = submitted_claim(as_)
    acc = as_("accounts")
    pending = acc.get("/api/reports/pending").json()
    assert pending[0]["claim"]["id"] == claim["id"]
    assert pending[0]["waiting_with"] == "Manager (Manager)"
    reg = acc.get(f"/api/reports/register?month={this_period()}").json()
    assert [c["id"] for c in reg] == [claim["id"]]
    export = acc.get("/api/reports/register/export").content.decode("utf-8-sig")
    assert "Cab to client office" in export


def test_comments_are_logged(as_, people):
    claim = submitted_claim(as_)
    res = as_("manager").post(f"/api/claims/{claim['id']}/comments", {"comment": "Which client?"})
    assert res.json()["events"][-1]["comment"] == "Which client?"
    assert as_("dev2").post(f"/api/claims/{claim['id']}/comments", {"comment": "hi"}).status_code == 404
