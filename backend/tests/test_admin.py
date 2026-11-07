CSV = """email,name,employee_code,department,manager_email,can_verify,can_pay,is_admin,bank_ifsc
lead@t.co,Team Lead,E100,Sales,manager@t.co,,,,
rep@t.co,Sales Rep,E101,Sales,lead@t.co,,,,
bad-email,Broken,,,,,,,
ghost@t.co,Ghost,E102,Sales,nobody@t.co,,,,
dev1@t.co,Dev One Renamed,,Engineering,manager@t.co,yes,,,
"""


def test_csv_import_upserts_and_links_managers(as_, people):
    admin = as_("admin")
    res = admin.post("/api/admin/users/import", files={"file": ("users.csv", CSV.encode(), "text/csv")})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["created"] == 3 and out["updated"] == 1
    assert any("Row 4" in e for e in out["errors"])  # bad email
    assert any("nobody@t.co" in e for e in out["errors"])

    users = {u["email"]: u for u in admin.get("/api/admin/users").json()}
    assert users["rep@t.co"]["manager_id"] == users["lead@t.co"]["id"]
    assert users["dev1@t.co"]["name"] == "Dev One Renamed"
    assert users["dev1@t.co"]["can_verify"] is True


def test_reporting_loops_are_blocked(as_, people):
    admin = as_("admin")
    users = {u["email"]: u for u in admin.get("/api/admin/users").json()}
    founder = users["founder@t.co"]
    body = {k: founder[k] for k in ("email", "name", "is_fallback_approver")}
    res = admin.put(f"/api/admin/users/{founder['id']}", {**body, "manager_id": users["dev1@t.co"]["id"]})
    assert res.status_code == 422
    assert "loop" in res.json()["detail"]
    res = admin.put(f"/api/admin/users/{founder['id']}", {**body, "manager_id": founder["id"]})
    assert res.status_code == 422


def test_categories_and_policy(as_, people):
    admin = as_("admin")
    cat = admin.post("/api/admin/categories", {"name": "Internet", "monthly_limit": "1000.00"})
    assert cat.status_code == 201
    assert admin.post("/api/admin/categories", {"name": "internet"}).status_code == 409
    names = [c["name"] for c in as_("dev1").get("/api/categories").json()]
    assert "Internet" in names and "Retired" not in names

    res = admin.put("/api/admin/policy", {"submission_due_day": 7, "max_age_days": 45,
                                          "cash_no_bill_item_limit": "200.00"})
    assert res.status_code == 200
    assert as_("dev1").get("/api/policy").json()["submission_due_day"] == 7


def test_admin_cannot_demote_self(as_, people):
    admin = as_("admin")
    me = admin.get("/api/auth/me").json()
    res = admin.put(f"/api/admin/users/{me['id']}", {"email": me["email"], "name": me["name"], "is_admin": False})
    assert res.status_code == 409


def test_dev_login_and_me(client, people):
    res = client.post("/api/auth/dev-login", json={"email": "MANAGER@t.co"})
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["is_approver"] is True
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "manager@t.co"
    assert me.json()["manager"]["email"] == "founder@t.co"
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
