import math
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from . import db


class InventoryError(ValueError):
    pass


def _nonnegative(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value) or value < 0:
        raise InventoryError(f"{field} must be a finite, non-negative number.")
    return value


def _required_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InventoryError(f"{field} is required.")
    return cleaned


def _product(conn: sqlite3.Connection, product_id: str, business_id: str) -> sqlite3.Row:
    product = conn.execute(
        "SELECT * FROM inventory_products WHERE id = ? AND business_id = ?",
        (product_id, business_id),
    ).fetchone()
    if product is None:
        raise InventoryError("Product not found.")
    return product


def _stock(conn: sqlite3.Connection, product_id: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity_delta), 0) AS quantity "
        "FROM inventory_movements WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    return float(row["quantity"])


def _record_movement(
    conn: sqlite3.Connection,
    business_id: str,
    product_id: str,
    user_id: str,
    movement_type: str,
    quantity_delta: float,
    note: str,
    source: str,
    unit_cost: float | None = None,
) -> None:
    product = _product(conn, product_id, business_id)
    stock_value = (
        round((_stock(conn, product_id) + quantity_delta) * product["unit_cost"], 2)
        if product["unit_cost"] is not None
        else None
    )
    conn.execute(
        "INSERT INTO inventory_movements "
        "(id, business_id, product_id, movement_type, quantity_delta, unit_cost, stock_value_after, note, source, user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            business_id,
            product_id,
            movement_type,
            quantity_delta,
            unit_cost,
            stock_value,
            note.strip(),
            source,
            user_id,
            db.now(),
        ),
    )


def _product_response(conn: sqlite3.Connection, product: sqlite3.Row) -> dict[str, Any]:
    quantity = _stock(conn, product["id"])
    unit_cost = product["unit_cost"]
    return {
        "id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "unit": product["unit"],
        "unit_cost": unit_cost,
        "reorder_level": product["reorder_level"],
        "quantity_on_hand": quantity,
        "stock_value": quantity * unit_cost if unit_cost is not None else None,
        "low_stock": quantity <= product["reorder_level"],
        "active": bool(product["active"]),
        "created_at": product["created_at"],
        "updated_at": product["updated_at"],
    }


def list_products(path: Path, business_id: str, include_archived: bool = False) -> dict[str, Any]:
    with db.connection(path) as conn:
        products = conn.execute(
            "SELECT * FROM inventory_products WHERE business_id = ? ORDER BY name COLLATE NOCASE",
            (business_id,),
        ).fetchall()
        all_items = [_product_response(conn, product) for product in products]
    items = [item for item in all_items if include_archived or item["active"]]
    low_stock_count = sum(item["low_stock"] for item in all_items if item["active"])
    units_on_hand = sum(item["quantity_on_hand"] for item in all_items)
    uncosted_items = [
        item["name"]
        for item in all_items
        if item["quantity_on_hand"] > 0 and item["unit_cost"] is None
    ]
    inventory_value = (
        sum(item["stock_value"] or 0 for item in all_items)
        if not uncosted_items
        else None
    )
    return {
        "items": items,
        "summary": {
            "product_count": sum(item["active"] for item in all_items),
            "units_on_hand": units_on_hand,
            "low_stock_count": low_stock_count,
            "inventory_value": inventory_value,
            "inventory_value_complete": not uncosted_items,
            "uncosted_stock_items": uncosted_items,
        },
    }


def create_product(
    path: Path,
    business_id: str,
    user_id: str,
    *,
    name: str,
    sku: str | None,
    unit: str,
    unit_cost: float | None,
    reorder_level: float,
    opening_stock: float,
) -> dict[str, Any]:
    name = _required_text(name, "Product name")
    unit = _required_text(unit, "Unit")
    unit_cost = _nonnegative(unit_cost, "Unit cost")
    reorder_level = _nonnegative(reorder_level, "Reorder level")
    opening_stock = _nonnegative(opening_stock, "Opening stock")
    sku = sku.strip() if sku and sku.strip() else None
    product_id = str(uuid.uuid4())
    timestamp = db.now()
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM inventory_products WHERE business_id = ? AND name = ? COLLATE NOCASE",
            (business_id, name),
        ).fetchone():
            raise InventoryError("A product with this name already exists.")
        if sku and conn.execute(
            "SELECT 1 FROM inventory_products WHERE business_id = ? AND sku = ? COLLATE NOCASE",
            (business_id, sku),
        ).fetchone():
            raise InventoryError("A product with this SKU already exists.")
        conn.execute(
            "INSERT INTO inventory_products "
            "(id, business_id, sku, name, unit, unit_cost, reorder_level, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (product_id, business_id, sku, name, unit, unit_cost, reorder_level, timestamp, timestamp),
        )
        if opening_stock:
            _record_movement(
                conn, business_id, product_id, user_id, "opening", opening_stock,
                "Opening stock", "manual", unit_cost,
            )
        product = _product(conn, product_id, business_id)
        return _product_response(conn, product)


def update_product(
    path: Path, business_id: str, product_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    allowed = {"name", "sku", "unit", "unit_cost", "reorder_level", "active"}
    if not changes or set(changes) - allowed:
        raise InventoryError("Provide at least one valid product field to update.")
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        product = _product(conn, product_id, business_id)
        values: dict[str, Any] = {}
        for field, value in changes.items():
            if field in {"name", "unit"}:
                values[field] = _required_text(value, "Product name" if field == "name" else "Unit")
            elif field == "sku":
                values[field] = value.strip() if value and value.strip() else None
            elif field == "unit_cost":
                values[field] = _nonnegative(value, "Unit cost")
            elif field == "reorder_level":
                if value is None:
                    raise InventoryError("Reorder level must be a finite, non-negative number.")
                values[field] = _nonnegative(value, "Reorder level")
            elif field == "active":
                if value is None:
                    raise InventoryError("Product active status must be true or false.")
                values[field] = int(value)
        candidate_name = values.get("name", product["name"])
        if conn.execute(
            "SELECT 1 FROM inventory_products WHERE business_id = ? AND name = ? COLLATE NOCASE AND id != ?",
            (business_id, candidate_name, product_id),
        ).fetchone():
            raise InventoryError("A product with this name already exists.")
        candidate_sku = values.get("sku", product["sku"])
        if candidate_sku and conn.execute(
            "SELECT 1 FROM inventory_products WHERE business_id = ? AND sku = ? COLLATE NOCASE AND id != ?",
            (business_id, candidate_sku, product_id),
        ).fetchone():
            raise InventoryError("A product with this SKU already exists.")
        assignments = ", ".join(f"{field} = ?" for field in values)
        conn.execute(
            f"UPDATE inventory_products SET {assignments}, updated_at = ? WHERE id = ? AND business_id = ?",
            (*values.values(), db.now(), product_id, business_id),
        )
        updated = _product(conn, product_id, business_id)
        return _product_response(conn, updated)


def record_movement(
    path: Path,
    business_id: str,
    product_id: str,
    user_id: str,
    movement_type: str,
    quantity: float,
    note: str,
    unit_cost: float | None = None,
) -> dict[str, Any]:
    if not math.isfinite(quantity) or quantity == 0:
        raise InventoryError("Movement quantity must be a finite, non-zero number.")
    if movement_type not in {"purchase", "sale", "adjustment"}:
        raise InventoryError("Unsupported inventory movement type.")
    unit_cost = _nonnegative(unit_cost, "Unit cost")
    if movement_type == "adjustment":
        quantity_delta = quantity
    elif quantity < 0:
        raise InventoryError("Purchase and sale quantities must be positive.")
    else:
        quantity_delta = quantity if movement_type == "purchase" else -quantity
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        product = _product(conn, product_id, business_id)
        if not product["active"]:
            raise InventoryError("Archived products must be restored before recording stock movements.")
        next_quantity = _stock(conn, product_id) + quantity_delta
        if next_quantity < -1e-9:
            raise InventoryError("This movement would make stock negative.")
        if next_quantity < 0:
            quantity_delta = -_stock(conn, product_id)
        current_quantity = _stock(conn, product_id)
        average_cost = product["unit_cost"]
        movement_cost = average_cost
        if movement_type == "purchase" and quantity_delta > 0:
            purchase_cost = unit_cost if unit_cost is not None else average_cost
            if purchase_cost is None:
                raise InventoryError("Enter a unit cost for the purchase to value inventory.")
            if current_quantity > 0 and average_cost is None:
                raise InventoryError("Existing stock has no cost; record a stocktake with unit cost before purchasing.")
            new_quantity = current_quantity + quantity_delta
            new_average = (
                ((current_quantity * average_cost) + (quantity_delta * purchase_cost)) / new_quantity
                if current_quantity > 0 and average_cost is not None
                else purchase_cost
            )
            conn.execute(
                "UPDATE inventory_products SET unit_cost = ?, updated_at = ? WHERE id = ? AND business_id = ?",
                (new_average, db.now(), product_id, business_id),
            )
            movement_cost = purchase_cost
        elif movement_type == "adjustment" and quantity_delta > 0 and unit_cost is not None:
            if current_quantity > 0 and average_cost is not None:
                new_quantity = current_quantity + quantity_delta
                average_cost = (
                    current_quantity * average_cost + quantity_delta * unit_cost
                ) / new_quantity
                conn.execute(
                    "UPDATE inventory_products SET unit_cost = ?, updated_at = ? WHERE id = ? AND business_id = ?",
                    (average_cost, db.now(), product_id, business_id),
                )
                movement_cost = unit_cost
            else:
                conn.execute(
                    "UPDATE inventory_products SET unit_cost = ?, updated_at = ? WHERE id = ? AND business_id = ?",
                    (unit_cost, db.now(), product_id, business_id),
                )
                movement_cost = unit_cost
        _record_movement(
            conn, business_id, product_id, user_id, movement_type, quantity_delta,
            note, "manual", movement_cost,
        )
        return _product_response(conn, _product(conn, product_id, business_id))


def list_movements(path: Path, business_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return db.many(
        path,
        "SELECT m.id, m.product_id, p.name AS product_name, p.sku, p.unit, "
        "m.movement_type, m.quantity_delta, m.unit_cost, m.stock_value_after, m.note, m.source, u.email AS recorded_by, m.created_at "
        "FROM inventory_movements m "
        "JOIN inventory_products p ON p.id = m.product_id "
        "JOIN users u ON u.id = m.user_id "
        "WHERE m.business_id = ? ORDER BY m.created_at DESC, m.id DESC LIMIT ?",
        (business_id, limit),
    )


def import_stocktake(
    path: Path,
    business_id: str,
    user_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        raise InventoryError("The inventory file has no stock rows.")
    seen_names: set[str] = set()
    seen_skus: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        row["name"] = _required_text(row["name"], f"Row {row_number} product name")
        row["sku"] = row["sku"].strip() if row.get("sku") and row["sku"].strip() else None
        row["unit"] = _required_text(row.get("unit") or "unit", f"Row {row_number} unit")
        row["quantity_on_hand"] = _nonnegative(row["quantity_on_hand"], f"Row {row_number} quantity") or 0
        row["unit_cost"] = _nonnegative(row.get("unit_cost"), f"Row {row_number} unit cost")
        row["reorder_level"] = _nonnegative(row.get("reorder_level"), f"Row {row_number} reorder level")
        normalized_name = row["name"].casefold()
        normalized_sku = row["sku"].casefold() if row["sku"] else None
        if normalized_name in seen_names:
            raise InventoryError(f"Row {row_number} repeats a product name.")
        if normalized_sku and normalized_sku in seen_skus:
            raise InventoryError(f"Row {row_number} repeats a SKU.")
        seen_names.add(normalized_name)
        if normalized_sku:
            seen_skus.add(normalized_sku)

    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        updated_count = 0
        created_count = 0
        for row in rows:
            product = None
            if row["sku"]:
                product = conn.execute(
                    "SELECT * FROM inventory_products WHERE business_id = ? AND sku = ? COLLATE NOCASE",
                    (business_id, row["sku"]),
                ).fetchone()
                if product and product["name"].casefold() != row["name"].casefold():
                    raise InventoryError(
                        f"SKU {row['sku']} already belongs to {product['name']}; import matching product names."
                    )
            if product is None:
                product = conn.execute(
                    "SELECT * FROM inventory_products WHERE business_id = ? AND name = ? COLLATE NOCASE",
                    (business_id, row["name"]),
                ).fetchone()
            if row["sku"] and conn.execute(
                "SELECT 1 FROM inventory_products WHERE business_id = ? AND sku = ? COLLATE NOCASE AND id != ?",
                (business_id, row["sku"], product["id"] if product else ""),
            ).fetchone():
                raise InventoryError(f"SKU {row['sku']} is already assigned to another product.")
            if product is None:
                product_id = str(uuid.uuid4())
                timestamp = db.now()
                conn.execute(
                    "INSERT INTO inventory_products "
                    "(id, business_id, sku, name, unit, unit_cost, reorder_level, active, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        product_id, business_id, row["sku"], row["name"], row["unit"],
                        row["unit_cost"], row["reorder_level"] or 0, timestamp, timestamp,
                    ),
                )
                quantity_delta = row["quantity_on_hand"]
                movement_type = "opening"
                movement_cost = row["unit_cost"]
                created_count += 1
            else:
                product_id = product["id"]
                quantity_delta = row["quantity_on_hand"] - _stock(conn, product_id)
                movement_type = "stocktake"
                updates: dict[str, Any] = {
                    "unit": row["unit"],
                    "reorder_level": row["reorder_level"] if row["reorder_level"] is not None else product["reorder_level"],
                    "unit_cost": row["unit_cost"] if row["unit_cost"] is not None else product["unit_cost"],
                    "sku": row["sku"] or product["sku"],
                }
                movement_cost = updates["unit_cost"]
                conn.execute(
                    "UPDATE inventory_products SET unit = ?, reorder_level = ?, unit_cost = ?, sku = ?, updated_at = ? "
                    "WHERE id = ? AND business_id = ?",
                    (*updates.values(), db.now(), product_id, business_id),
                )
                updated_count += 1
            _record_movement(
                conn, business_id, product_id, user_id, movement_type, quantity_delta,
                "Imported counted stock level", "stocktake_import", movement_cost,
            )
    return {"created": created_count, "updated": updated_count, "rows_imported": len(rows)}
