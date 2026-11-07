import csv
import io

from fastapi import APIRouter, File, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select

from ..auth import DB, AdminUser
from ..models import Category, User
from ..schemas import (
    CategoryIn,
    CategoryOut,
    ImportResult,
    PolicyIn,
    PolicyOut,
    UserAdminOut,
    UserIn,
)
from ..services.errors import Conflict, Invalid, NotFound
from ..services.notify import commit
from ..services.policy import get_policy

router = APIRouter(prefix="/api/admin", tags=["admin"])

BOOL_TRUE = {"1", "true", "yes", "y"}
IMPORT_COLUMNS = [
    "email", "name", "employee_code", "department", "manager_email", "is_admin", "can_verify",
    "can_pay", "is_fallback_approver", "is_active", "bank_account_name", "bank_account_number",
    "bank_ifsc",
]


def _check_manager(db, user_id: int | None, manager_id: int | None) -> None:
    if manager_id is None:
        return
    if manager_id == user_id:
        raise Invalid("A person can't be their own manager")
    seen = {user_id}
    current = db.get(User, manager_id)
    if current is None:
        raise Invalid("Manager not found")
    # Walk up the chain so reporting lines can't form a loop.
    while current is not None:
        if current.id in seen:
            raise Invalid("That manager would create a reporting loop")
        seen.add(current.id)
        current = current.manager


def _email_taken(db, email: str, exclude_id: int | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) is not None


@router.get("/users", response_model=list[UserAdminOut])
def list_users(admin: AdminUser, db: DB):
    return db.scalars(select(User).order_by(User.name)).all()


@router.post("/users", response_model=UserAdminOut, status_code=201)
def create_user(body: UserIn, admin: AdminUser, db: DB):
    if _email_taken(db, body.email):
        raise Conflict("A user with that email already exists")
    _check_manager(db, None, body.manager_id)
    user = User(**body.model_dump())
    db.add(user)
    commit(db)
    return user


@router.put("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, body: UserIn, admin: AdminUser, db: DB):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    if _email_taken(db, body.email, exclude_id=user_id):
        raise Conflict("A user with that email already exists")
    if user.id == admin.id and not body.is_admin:
        raise Conflict("You can't remove your own admin access")
    _check_manager(db, user_id, body.manager_id)
    for key, value in body.model_dump().items():
        setattr(user, key, value)
    commit(db)
    return user


@router.get("/users/import-template")
def import_template(admin: AdminUser):
    return {"columns": IMPORT_COLUMNS}


@router.post("/users/import", response_model=ImportResult)
async def import_users(admin: AdminUser, db: DB, file: UploadFile = File(...)):
    """Upsert users by email from a CSV; managers are linked in a second pass (FR-26)."""
    text = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = {"email", "name"} - set(reader.fieldnames or [])
    if missing:
        raise Invalid(f"CSV is missing columns: {', '.join(sorted(missing))}")

    created = updated = 0
    errors: list[str] = []
    pending_managers: list[tuple[int, User, str]] = []
    for row_no, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        try:
            data = UserIn(
                email=row["email"],
                name=row["name"],
                employee_code=row.get("employee_code") or None,
                department=row.get("department") or None,
                is_admin=row.get("is_admin", "").lower() in BOOL_TRUE,
                can_verify=row.get("can_verify", "").lower() in BOOL_TRUE,
                can_pay=row.get("can_pay", "").lower() in BOOL_TRUE,
                is_fallback_approver=row.get("is_fallback_approver", "").lower() in BOOL_TRUE,
                is_active=row.get("is_active", "true").lower() in BOOL_TRUE or row.get("is_active") == "",
                bank_account_name=row.get("bank_account_name") or None,
                bank_account_number=row.get("bank_account_number") or None,
                bank_ifsc=row.get("bank_ifsc") or None,
            )
        except ValidationError as exc:
            errors.append(f"Row {row_no}: {exc.errors()[0]['msg']}")
            continue
        user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
        fields = data.model_dump(exclude={"manager_id"})
        if user is None:
            user = User(**fields)
            db.add(user)
            created += 1
        else:
            for key, value in fields.items():
                setattr(user, key, value)
            updated += 1
        if row.get("manager_email"):
            pending_managers.append((row_no, user, row["manager_email"]))
    db.flush()

    for row_no, user, manager_email in pending_managers:
        manager = db.scalar(select(User).where(func.lower(User.email) == manager_email.lower()))
        if manager is None:
            errors.append(f"Row {row_no}: manager {manager_email} not found")
            continue
        try:
            _check_manager(db, user.id, manager.id)
        except Invalid as exc:
            errors.append(f"Row {row_no}: {exc.message}")
            continue
        user.manager_id = manager.id
        user.manager = manager
    commit(db)
    return ImportResult(created=created, updated=updated, errors=errors)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(admin: AdminUser, db: DB):
    return db.scalars(select(Category).order_by(Category.sort_order, Category.name)).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, admin: AdminUser, db: DB):
    if db.scalar(select(Category.id).where(func.lower(Category.name) == body.name.lower())):
        raise Conflict("A category with that name already exists")
    cat = Category(**body.model_dump())
    db.add(cat)
    commit(db)
    return cat


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, admin: AdminUser, db: DB):
    cat = db.get(Category, category_id)
    if cat is None:
        raise NotFound("Category not found")
    clash = db.scalar(
        select(Category.id).where(func.lower(Category.name) == body.name.lower(), Category.id != category_id)
    )
    if clash:
        raise Conflict("A category with that name already exists")
    for key, value in body.model_dump().items():
        setattr(cat, key, value)
    commit(db)
    return cat


@router.get("/policy", response_model=PolicyOut)
def read_policy(admin: AdminUser, db: DB):
    return get_policy(db)


@router.put("/policy", response_model=PolicyOut)
def update_policy(body: PolicyIn, admin: AdminUser, db: DB):
    policy = get_policy(db)
    for key, value in body.model_dump().items():
        setattr(policy, key, value)
    commit(db)
    return policy
