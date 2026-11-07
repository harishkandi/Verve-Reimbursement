import os
import tempfile
from datetime import date

import pytest

# Settings are read at import time, so point them at throwaway locations first.
_tmp = tempfile.mkdtemp(prefix="reimb-test-")
# TEST_DATABASE_URL lets the same suite run against Postgres before deploying.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["ENV"] = "dev"

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import create_token  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, User  # noqa: E402

PDF = b"%PDF-1.4\n% test bill\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def people():
    """founder (fallback approver) <- manager <- dev1, dev2; accounts (verify+pay); admin."""
    with SessionLocal() as db:
        founder = User(email="founder@t.co", name="Founder", is_fallback_approver=True)
        db.add(founder)
        db.flush()
        manager = User(email="manager@t.co", name="Manager", manager_id=founder.id)
        db.add(manager)
        db.flush()
        dev1 = User(email="dev1@t.co", name="Dev One", manager_id=manager.id,
                    bank_account_name="Dev One", bank_account_number="1234567890", bank_ifsc="HDFC0000001")
        dev2 = User(email="dev2@t.co", name="Dev Two", manager_id=manager.id)
        accounts = User(email="accounts@t.co", name="Accounts", manager_id=founder.id,
                        can_verify=True, can_pay=True)
        admin = User(email="admin@t.co", name="Admin", is_admin=True, manager_id=founder.id)
        db.add_all([dev1, dev2, accounts, admin])
        db.add_all([
            Category(name="Cab fare", per_item_limit=500, monthly_limit=2000),
            Category(name="Food"),
            Category(name="Retired", is_active=False),
        ])
        db.commit()
        return {u.email.split("@")[0]: u for u in [founder, manager, dev1, dev2, accounts, admin]}


class Api:
    def __init__(self, client: TestClient, user: User):
        self.c = client
        self.h = {"Authorization": f"Bearer {create_token(user)}"}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self.h, **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self.h, **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self.h, **kw)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def as_(client, people):
    return lambda name: Api(client, people[name])


def this_period() -> str:
    return f"{date.today():%Y-%m}"


def line(category_id=1, amount="300.00", mode="online", day=None, **extra):
    return {
        "expense_date": (day or date.today()).isoformat(),
        "category_id": category_id,
        "description": "Cab to client office",
        "payment_mode": mode,
        "amount": amount,
        **extra,
    }


def upload(api: Api, claim_id: int, line_id: int, data: bytes = PDF, ctype="application/pdf", name="bill.pdf"):
    return api.post(
        f"/api/claims/{claim_id}/lines/{line_id}/attachments",
        files={"file": (name, data, ctype)},
    )


def submitted_claim(as_, owner="dev1", lines=None):
    """Creates a claim with lines (each with a bill) and submits it. Returns the claim JSON."""
    api = as_(owner)
    claim = api.post("/api/claims", {"period": this_period()}).json()
    for spec in lines or [line()]:
        claim = api.post(f"/api/claims/{claim['id']}/lines", spec).json()
        # Lines come back sorted by date, so the newest is the highest id, not the last.
        new_line = max(claim["lines"], key=lambda ln: ln["id"])
        if not spec.get("no_bill_declaration"):
            # Distinct bytes per line so they aren't flagged as duplicates of each other.
            assert upload(api, claim["id"], new_line["id"], PDF + str(new_line["id"]).encode()).status_code == 200
    res = api.post(f"/api/claims/{claim['id']}/submit")
    assert res.status_code == 200, res.text
    return res.json()
