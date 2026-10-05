"""Dialect-aware bulk upsert (PostgreSQL in production, SQLite in tests)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy.orm import Session


def upsert(db: Session, model, rows: Iterable[dict], conflict_cols: Sequence[str],
           update_cols: Sequence[str] | None = None, chunk: int = 2000) -> int:
    # De-duplicate on the conflict key (last wins): Postgres rejects a batch that touches the same row twice.
    rows = list({tuple(r.get(c) for c in conflict_cols): r for r in rows}.values())
    if not rows:
        return 0
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(dialect)
    cols = update_cols if update_cols is not None else [k for k in rows[0] if k not in conflict_cols]
    n = 0
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        stmt = insert(model).values(part)
        if cols:
            stmt = stmt.on_conflict_do_update(index_elements=list(conflict_cols),
                                              set_={c: getattr(stmt.excluded, c) for c in cols})
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_cols))
        db.execute(stmt)
        n += len(part)
    return n
