"""Reset the local database and load a realistic demo: a small team with three months of claims
in every status. Runs the real workflow code, then back-dates timestamps so history reads naturally.

    venv/Scripts/python seed.py
"""

import shutil
import struct
import zlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Category, Claim, PayoutBatch, User
from app.schemas import LineDecision, LineIn, ReviewIn
from app.services import claims as svc
from app.services import payouts
from app.services.policy import get_policy

IST = timezone(timedelta(hours=5, minutes=30))

# email prefix, name, department, manager prefix, flags
PEOPLE = [
    ("aditi", "Aditi Rao", "Leadership", None, {"is_admin": True, "is_fallback_approver": True}),
    ("vikram", "Vikram Mehta", "Finance", None, {"is_fallback_approver": True}),
    ("meera", "Meera Iyer", "Finance", "vikram", {"can_verify": True, "can_pay": True}),
    ("rohan", "Rohan Kapoor", "Engineering", "aditi", {}),
    ("priya", "Priya Sharma", "Engineering", "rohan", {}),
    ("kiran", "Kiran Nair", "Engineering", "rohan", {}),
    ("sneha", "Sneha Kulkarni", "Design", "aditi", {}),
    ("arjun", "Arjun Desai", "Design", "sneha", {}),
    ("neha", "Neha Joshi", "Client Services", "aditi", {}),
]

CATEGORIES = [
    ("Cab & local travel", Decimal("1500"), Decimal("6000")),
    ("Food & client meals", Decimal("2500"), None),
    ("Software subscriptions", None, Decimal("5000")),
    ("Workcation travel & stay", None, None),
    ("Internet & phone", None, Decimal("1500")),
    ("Other official expense", None, None),
]


# ---- bill files ----------------------------------------------------------------


def pdf_bill(vendor: str, lines: list[str], total: str) -> bytes:
    """A small but valid single-page PDF that looks like a receipt."""

    def esc(s: str) -> str:
        # PDF strings are bracketed, and the base font only knows Latin-1.
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("—", "-").replace("→", "to")

    text = [f"BT /F1 16 Tf 50 780 Td ({esc(vendor)}) Tj ET", "BT /F1 10 Tf 50 760 Td (Tax invoice / receipt) Tj ET"]
    y = 720
    for ln in lines:
        text.append(f"BT /F1 11 Tf 50 {y} Td ({esc(ln)}) Tj ET")
        y -= 18
    text.append(f"BT /F1 13 Tf 50 {y - 12} Td (Total paid: INR {total}) Tj ET")
    stream = "\n".join(text).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def png_photo(seed: int) -> bytes:
    """A small valid PNG standing in for a phone photo of a bill."""
    # A cream receipt on a grey table with dark "printed" lines, so it reads as a photographed bill.
    w, h = 300, 420
    table, paper, ink = (196, 199, 204), (250, 248, 241), (70, 72, 78)
    rows = []
    for y in range(h):
        row = bytearray()
        line_no, in_line = divmod(y - 60, 22)
        for x in range(w):
            on_paper = 30 <= x < 270 and 20 <= y < 400
            # Line lengths vary with the seed so no two demo photos are byte-identical (they'd be flagged as duplicates).
            length = 60 + ((seed * 37 + line_no * 53) % 150) if line_no < 14 else 0
            if y == 0 and x == 0:
                row += bytes([seed % 256, 0, 0])
            elif on_paper and y >= 60 and in_line < 7 and 50 <= x < 50 + length:
                row += bytes(ink)
            elif on_paper and 30 <= y < 44 and 50 <= x < 170:
                row += bytes((35, 71, 136))  # vendor header
            else:
                row += bytes(paper if on_paper else table)
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---- helpers --------------------------------------------------------------------


def at(d: str, hh: int = 11, mm: int = 0) -> datetime:
    return datetime.combine(date.fromisoformat(d), time(hh, mm), IST).astimezone(timezone.utc)


def stamp(claim: Claim, when: datetime) -> None:
    """Back-date the step that just happened."""
    ev = claim.events[-1]
    ev.created_at = when
    if ev.to_status:
        claim.status_changed_at = when
    field = {"submitted": "submitted_at", "manager_approved": "manager_approved_at",
             "verified": "verified_at", "paid": "paid_at"}.get(ev.action)
    if field:
        setattr(claim, field, when)


class Demo:
    def __init__(self, db):
        self.db = db
        self.users: dict[str, User] = {}
        self.cats: dict[str, Category] = {}
        self.bill_no = 0

    def claim(self, who: str, period: str, created: str, items: list[tuple]) -> Claim:
        """items: (date, category prefix, description, mode, amount, bill) where bill is 'pdf', 'png', 'declare' or None."""
        user = self.users[who]
        claim, _ = svc.get_or_create_claim(self.db, user, period)
        stamp(claim, at(created, 10, 5))
        claim.created_at = at(created, 10, 5)
        for d, cat, desc, mode, amount, bill in items:
            category = next(c for name, c in self.cats.items() if name.startswith(cat))
            line = svc.add_line(self.db, user, claim, LineIn(
                expense_date=date.fromisoformat(d), category_id=category.id, description=desc,
                payment_mode=mode, amount=Decimal(amount), no_bill_declaration=(bill == "declare"),
            ))
            if bill in ("pdf", "png"):
                self.bill_no += 1
                vendor = desc.split(" — ")[0].split(",")[0]
                if bill == "pdf":
                    data = pdf_bill(vendor, [f"Date: {d}", desc, f"Invoice no: INV-{20260000 + self.bill_no}"], amount)
                    name = f"{vendor.lower().replace(' ', '-')[:24]}-invoice.pdf"
                    ctype = "application/pdf"
                else:
                    data, name, ctype = png_photo(self.bill_no), f"IMG_{4100 + self.bill_no}.png", "image/png"
                att, _ = svc.add_attachment(self.db, user, claim, line.id, name, ctype, data)
                att.created_at = at(d, 20, 15)
        return claim

    def submit(self, claim: Claim, when: datetime) -> None:
        svc.submit(self.db, claim.employee, claim)
        stamp(claim, when)

    def approve(self, claim: Claim, when: datetime, decisions=(), comment=None) -> None:
        svc.manager_approve(self.db, claim.approver, claim, ReviewIn(lines=list(decisions), comment=comment))
        stamp(claim, when)

    def verify(self, claim: Claim, when: datetime, decisions=(), comment=None) -> None:
        svc.verify(self.db, self.users["meera"], claim, ReviewIn(lines=list(decisions), comment=comment))
        stamp(claim, when)

    def comment(self, claim: Claim, who: str, text: str, when: datetime) -> None:
        svc.add_comment(self.db, self.users[who], claim, text)
        stamp(claim, when)

    def batch(self, claims: list[Claim], payout: str, created: datetime, paid: tuple[str, str] | None = None) -> PayoutBatch:
        meera = self.users["meera"]
        b = payouts.create_batch(self.db, meera, date.fromisoformat(payout), [c.id for c in claims])
        b.created_at = created
        for c in claims:
            stamp(c, created)
        if paid:
            paid_on, ref = paid
            payouts.mark_paid(self.db, meera, b, date.fromisoformat(paid_on), ref, {})
            for c in claims:
                stamp(c, at(paid_on, 16, 40))
        return b


def line_id(claim: Claim, startswith: str) -> int:
    return next(l.id for l in claim.lines if l.description.startswith(startswith))


def main() -> None:
    if not settings.is_dev:
        raise SystemExit("seed.py wipes the database; it only runs with ENV=dev")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(Path(settings.upload_dir), ignore_errors=True)

    with SessionLocal() as db:
        demo = Demo(db)
        for i, (name, item_limit, month_limit) in enumerate(CATEGORIES):
            cat = Category(name=name, per_item_limit=item_limit, monthly_limit=month_limit, sort_order=i)
            db.add(cat)
            demo.cats[name] = cat
        for i, (key, name, dept, _, flags) in enumerate(PEOPLE, start=1):
            u = User(email=f"{key}@verve.example", name=name, department=dept, employee_code=f"VRV{100 + i}",
                     bank_account_name=name, bank_account_number=f"5010{(7310452 + i * 9137):08d}",
                     bank_ifsc=["HDFC0000240", "ICIC0000104", "SBIN0001234", "UTIB0000553"][i % 4], **flags)
            db.add(u)
            demo.users[key] = u
        db.flush()
        for key, _, _, mgr, _ in PEOPLE:
            if mgr:
                demo.users[key].manager = demo.users[mgr]
        policy = get_policy(db)
        policy.cash_no_bill_item_limit = Decimal("500")
        policy.cash_no_bill_month_limit = Decimal("2000")
        db.flush()

        # ---- August: paid in September ------------------------------------------------
        p_aug = demo.claim("priya", "2026-08", "2026-08-06", [
            ("2026-08-06", "Cab", "Uber — Andheri office to client site, BKC", "online", "412.00", "pdf"),
            ("2026-08-14", "Software", "Figma Professional — monthly seat", "online", "1250.00", "pdf"),
            ("2026-08-22", "Food", "Team lunch with Lumen Bank stakeholders, Bastian", "online", "2180.00", "png"),
        ])
        demo.submit(p_aug, at("2026-09-02", 18, 20))
        demo.approve(p_aug, at("2026-09-03", 10, 45))
        demo.verify(p_aug, at("2026-09-05", 12, 10))

        k_aug = demo.claim("kiran", "2026-08", "2026-08-10", [
            ("2026-08-17", "Cab", "Ola — weekend trip to Lonavala", "online", "2850.00", "pdf"),
        ])
        demo.submit(k_aug, at("2026-09-03", 9, 30))
        svc.reject_claim(db, demo.users["rohan"], k_aug, "This was a personal trip, not a client visit. Happy to discuss if I've misread it.")
        stamp(k_aug, at("2026-09-03", 15, 5))

        demo.batch([p_aug], "2026-09-10", at("2026-09-08", 11), ("2026-09-10", "UTR HDFCR52026091001"))

        # ---- September: all paid in October -------------------------------------------
        p_sep = demo.claim("priya", "2026-09", "2026-09-04", [
            ("2026-09-04", "Cab", "Uber — client workshop at Lower Parel", "online", "386.00", "pdf"),
            ("2026-09-11", "Software", "Figma Professional — monthly seat", "online", "1250.00", "pdf"),
            ("2026-09-19", "Internet", "Airtel Xstream — home broadband, September", "online", "1178.82", "pdf"),
            ("2026-09-26", "Cab", "Auto rickshaw — station to office", "cash", "140.00", "declare"),
        ])
        demo.submit(p_sep, at("2026-10-01", 19, 5))
        demo.approve(p_sep, at("2026-10-02", 9, 50))
        demo.verify(p_sep, at("2026-10-06", 14, 30))

        k_sep = demo.claim("kiran", "2026-09", "2026-09-08", [
            ("2026-09-08", "Food", "Swiggy dinner — late production release", "online", "684.00", "png"),
            ("2026-09-15", "Cab", "Uber — airport drop for Pune client visit", "online", "1640.00", "pdf"),
        ])
        demo.submit(k_sep, at("2026-10-03", 11, 15))
        demo.approve(k_sep, at("2026-10-03", 17, 40), [
            LineDecision(line_id=line_id(k_sep, "Swiggy"), decision="approve", approved_amount=Decimal("600.00"),
                         reason="Dinner allowance is ₹600 per person"),
        ])
        demo.verify(k_sep, at("2026-10-07", 10, 20))

        n_sep = demo.claim("neha", "2026-09", "2026-09-05", [
            ("2026-09-05", "Food", "Client lunch with Arcadia Retail, The Table", "online", "4820.00", "pdf"),
            ("2026-09-18", "Cab", "Uber — Arcadia HQ visit, Powai", "online", "534.00", "pdf"),
            ("2026-09-18", "Other", "Printing — proposal decks for Arcadia pitch", "cash", "960.00", "png"),
        ])
        demo.submit(n_sep, at("2026-10-04", 16, 0))
        demo.approve(n_sep, at("2026-10-05", 11, 30), comment="Good pitch, approved.")
        demo.verify(n_sep, at("2026-10-07", 15, 45))

        demo.batch([p_sep, k_sep, n_sep], "2026-10-10", at("2026-10-08", 12), ("2026-10-10", "UTR HDFCR52026101004"))

        # ---- October: every stage in flight ----------------------------------------------
        # Priya: verified, ready for the November payout
        p_oct = demo.claim("priya", "2026-10", "2026-10-03", [
            ("2026-10-03", "Cab", "Uber — Lumen Bank quarterly review, BKC", "online", "448.00", "pdf"),
            ("2026-10-11", "Software", "Figma Professional — monthly seat", "online", "1250.00", "pdf"),
            ("2026-10-16", "Food", "Working dinner, sprint planning with Lumen team", "online", "1860.00", "pdf"),
            ("2026-10-24", "Internet", "Airtel Xstream — home broadband, October", "online", "1178.82", "pdf"),
        ])
        demo.submit(p_oct, at("2026-11-01", 10, 10))
        demo.approve(p_oct, at("2026-11-02", 9, 35))
        demo.verify(p_oct, at("2026-11-03", 16, 5))

        # Neha: in an open payout batch
        n_oct = demo.claim("neha", "2026-10", "2026-10-07", [
            ("2026-10-07", "Workcation", "IndiGo 6E-5321 — Mumbai to Goa (team workcation)", "online", "5640.00", "pdf"),
            ("2026-10-07", "Workcation", "Taj Holiday Village — 3 nights, shared room", "online", "13200.00", "pdf"),
            ("2026-10-10", "Workcation", "IndiGo 6E-5428 — Goa to Mumbai", "online", "6125.00", "pdf"),
        ])
        demo.submit(n_oct, at("2026-10-28", 12, 0))
        demo.approve(n_oct, at("2026-10-29", 10, 0))
        demo.verify(n_oct, at("2026-10-31", 11, 20))
        demo.batch([n_oct], "2026-11-10", at("2026-11-03", 17, 30))

        # Sneha: approved by Aditi, waiting for Accounts
        s_oct = demo.claim("sneha", "2026-10", "2026-10-02", [
            ("2026-10-02", "Software", "Adobe Creative Cloud — monthly", "online", "4230.00", "pdf"),
            ("2026-10-09", "Software", "Maze — usability testing credits", "online", "2950.00", "pdf"),
            ("2026-10-21", "Cab", "Uber — user interviews at Thane", "online", "1720.00", "pdf"),
        ])
        demo.submit(s_oct, at("2026-11-01", 15, 40))
        demo.approve(s_oct, at("2026-11-03", 12, 15), comment="Maze credits are for the Lumen research, fine.")

        # Kiran: waiting for Rohan
        k_oct = demo.claim("kiran", "2026-10", "2026-10-06", [
            ("2026-10-06", "Cab", "Uber — client office, Nariman Point", "online", "612.00", "pdf"),
            ("2026-10-15", "Food", "Swiggy dinner — on-call incident", "online", "540.00", "png"),
            ("2026-10-29", "Software", "JetBrains All Products — monthly", "online", "2390.00", "pdf"),
        ])
        demo.submit(k_oct, at("2026-11-02", 18, 50))
        demo.comment(k_oct, "kiran", "JetBrains is for the Android build work; Rohan okayed it in standup.", at("2026-11-02", 18, 55))

        # Rohan: waiting a week for Aditi (shows up as overdue)
        r_oct = demo.claim("rohan", "2026-10", "2026-10-01", [
            ("2026-10-01", "Food", "Team offsite lunch — 9 people, Bombay Canteen", "online", "11400.00", "pdf"),
            ("2026-10-13", "Cab", "Uber — Lumen Bank escalation meeting", "online", "498.00", "pdf"),
        ])
        demo.submit(r_oct, at("2026-10-28", 9, 15))

        # Arjun: returned by Sneha for a better bill
        a_oct = demo.claim("arjun", "2026-10", "2026-10-08", [
            ("2026-10-08", "Workcation", "Zostel Goa — 3 nights (team workcation)", "online", "4800.00", "png"),
            ("2026-10-08", "Cab", "Goa airport taxi to Zostel", "cash", "1200.00", "declare"),
        ])
        demo.submit(a_oct, at("2026-10-30", 20, 0))
        svc.return_claim(db, demo.users["sneha"], a_oct,
                         "The Zostel image is a booking screenshot. Please attach the final invoice, and a bill for the airport taxi if the driver gave one.")
        stamp(a_oct, at("2026-10-31", 10, 30))

        # ---- November: Priya's draft in progress ------------------------------------------
        demo.claim("priya", "2026-11", "2026-11-02", [
            ("2026-11-02", "Cab", "Uber — Lumen Bank sprint demo, BKC", "online", "436.00", "pdf"),
            ("2026-11-03", "Food", "Coffee with design partner, Blue Tokai", "cash", "380.00", "declare"),
        ])

        db.info.pop("outbox", None)  # demo data sends no email
        db.commit()

    print("Demo data loaded: 9 people, 14 claims, 3 payout batches.")
    print("Sign in as priya@ (employee), rohan@ (manager), aditi@ (admin), meera@ (Accounts); all @verve.example")


if __name__ == "__main__":
    main()
