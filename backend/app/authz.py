from typing import Any, Iterable, List, Optional, Sequence, Set

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.models import DocumentUpload


SEEDED_CONTRACTS = [
    {
        "id": "contract-demo-modernization",
        "title": "Facilities Modernization Support",
        "contractor_ids": ["contractor-demo"],
        "official_ids": ["official-demo"],
        "category_code": "D",
        "status": "active",
    },
    {
        "id": "contract-demo-operations",
        "title": "Operations Support Services",
        "contractor_ids": [],
        "official_ids": ["official-demo"],
        "category_code": "R",
        "status": "active",
    },
]


def visible_contract_ids(user: CurrentUser, db: Session) -> List[str]:
    ids: Set[str] = set()

    if user.role == "official":
        ids.update(contract["id"] for contract in SEEDED_CONTRACTS)
        ids.update(_granted_contract_ids(user, db))
        if not _contract_grants_exist(db):
            ids.update(_document_contract_ids(db))
            ids.update(_contract_table_ids(db))
    else:
        ids.update(_own_upload_contract_ids(user, db))
        ids.update(_granted_contract_ids(user, db))
        ids.update(_seeded_contract_ids_for_user(user))

    return sorted(ids)


def can_view_contract(user: CurrentUser, db: Session, contract_id: str) -> bool:
    return contract_id in set(visible_contract_ids(user, db))


def can_upload_to_contract(user: CurrentUser, db: Session, contract_id: str) -> bool:
    if user.role == "official":
        return can_view_contract(user, db, contract_id)
    return contract_id in set(visible_contract_ids(user, db))


def can_query_contract_ai(user: CurrentUser, db: Session, contract_id: str) -> bool:
    return can_view_contract(user, db, contract_id)


def can_admin_unmatched(user: CurrentUser) -> bool:
    return user.role == "official"


def require_contract_view(user: CurrentUser, db: Session, contract_id: str) -> None:
    if not can_view_contract(user, db, contract_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")


def require_contract_ai_query(user: CurrentUser, db: Session, contract_id: str) -> None:
    if not can_query_contract_ai(user, db, contract_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")


def require_unmatched_admin(user: CurrentUser) -> None:
    if not can_admin_unmatched(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")


def seeded_contract(contract_id: str) -> Optional[dict]:
    for contract in SEEDED_CONTRACTS:
        if contract["id"] == contract_id:
            return contract
    return None


def _document_contract_ids(db: Session) -> List[str]:
    rows = list(db.scalars(select(DocumentUpload)).all())
    return _contract_ids_from_documents(rows)


def _own_upload_contract_ids(user: CurrentUser, db: Session) -> List[str]:
    rows = list(db.scalars(select(DocumentUpload).where(DocumentUpload.uploader_id == user.id)).all())
    return _contract_ids_from_documents(rows)


def _seeded_contract_ids_for_user(user: CurrentUser) -> List[str]:
    return [
        contract["id"]
        for contract in SEEDED_CONTRACTS
        if user.id in contract.get("contractor_ids", []) or user.id in contract.get("official_ids", [])
    ]


def _contract_grants_exist(db: Session) -> bool:
    model = _first_model("ContractAccessGrant", "ContractGrant", "ContractUserGrant")
    if model is None or not _model_table_exists(db, model):
        return False
    try:
        return db.scalar(select(func.count()).select_from(model)) > 0
    except SQLAlchemyError:
        return False


def _granted_contract_ids(user: CurrentUser, db: Session) -> List[str]:
    model = _first_model("ContractAccessGrant", "ContractGrant", "ContractUserGrant")
    if model is None or not _model_table_exists(db, model):
        return []
    try:
        grants = db.scalars(select(model)).all()
    except SQLAlchemyError:
        return []
    ids = [_attr(grant, "contract_id", "contract_record_id", "contract_key") for grant in grants if _matches_grant(grant, user)]
    return [str(contract_id) for contract_id in ids if contract_id]


def _contract_table_ids(db: Session) -> List[str]:
    model = _first_model("Contract", "ContractRecord")
    if model is None or not _model_table_exists(db, model):
        return []
    try:
        rows = db.scalars(select(model)).all()
    except SQLAlchemyError:
        return []
    ids = [_attr(row, "id", "contract_id", "contract_key") for row in rows]
    return [str(contract_id) for contract_id in ids if contract_id]


def _matches_grant(grant: Any, user: CurrentUser) -> bool:
    principal_type = _attr(grant, "principal_type")
    principal_id = _attr(grant, "principal_id")
    if principal_type == "role" and principal_id == user.role:
        return True

    user_values = _attrs(
        grant,
        (
            "user_id",
            "principal_id",
            "grantee_id",
            "subject_id",
            "contractor_id",
            "official_id",
        ),
    )
    role_values = _attrs(grant, ("role", "principal_role", "grantee_role", "subject_role"))
    group_values = _attrs(grant, ("group_id", "group_name", "principal_group"))
    return (
        user.id in user_values
        or user.email in user_values
        or bool(set(getattr(user, "group_ids", ())).intersection(user_values | group_values))
        or user.role in role_values
        or f"{user.role}-demo" in group_values
    )


def _first_model(*names: str) -> Optional[type]:
    try:
        import app.models as models
    except ImportError:
        return None
    for name in names:
        model = getattr(models, name, None)
        if model is not None:
            return model
    return None


def _model_table_exists(db: Session, model: type) -> bool:
    try:
        table_name = model.__table__.name
        return sqlalchemy_inspect(db.get_bind()).has_table(table_name)
    except SQLAlchemyError:
        return False


def _attr(row: Any, *names: str) -> Optional[Any]:
    for name in names:
        value = getattr(row, name, None)
        if value is not None:
            return value
    return None


def _attrs(row: Any, names: Sequence[str]) -> Set[str]:
    values: Set[str] = set()
    for name in names:
        value = getattr(row, name, None)
        if value is None:
            continue
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, Iterable):
            values.update(str(item) for item in value)
        else:
            values.add(str(value))
    return values


def _contract_ids_from_documents(documents: Sequence[DocumentUpload]) -> List[str]:
    ids: Set[str] = set()
    for document in documents:
        ids.add(document.id)
        contract_id = getattr(document, "contract_id", None)
        if contract_id:
            ids.add(str(contract_id))
    return sorted(ids)
