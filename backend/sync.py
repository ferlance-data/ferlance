"""Inventory ↔ sales sync: link sales product names to stock products, post a file's sales to stock.

Sales imports still never change stock on their own (DATA_CONTRACT). Posting is an explicit,
per-file action:
- Only sales lines whose product name is linked to a stock product, and that carry a quantity,
  are posted, as 'sale' movements tagged with the dataset (source ``sales:<dataset_id>``).
- A file can be posted once. Posting again is refused until the file is reversed.
- Excluding a posted file from analysis reverses its movements (append-only: equal and opposite
  adjustments), so stock and numbers stay consistent.
- The ledger cannot go negative. If posting would take any product below zero, nothing is
  posted and the products in conflict are returned, so the owner can record a purchase or
  stocktake first. Conflicts are surfaced, never clamped.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import dataset_store, db, ocr
from .inventory import InventoryError, _record_movement, _stock


def _norm(name: str) -> str:
    return " ".join(name.casefold().split())


def links(path: Path, business_id: str) -> dict[str, str | None]:
    """normalised sales name -> inventory product id (None means "not stock, ignore")."""
    rows = db.many(path, "SELECT sales_name_norm, product_id FROM product_links WHERE business_id = ?", (business_id,))
    return {row["sales_name_norm"]: row["product_id"] for row in rows}


def resolve(sales_name: str, link_map: dict[str, str | None], by_name: dict[str, dict[str, Any]]) -> str | None:
    """The stock product for a sales name: an explicit link wins, then an exact name match."""
    key = _norm(sales_name)
    if key in link_map:
        return link_map[key]
    product = by_name.get(key)
    return product["id"] if product else None


def sales_names(path: Path, business_id: str) -> list[dict[str, Any]]:
    """Every product name in the business's sales files, with units sold and its stock link."""
    totals: dict[str, dict[str, Any]] = {}
    for record in dataset_store.records_for(dataset_store.analysable(business_id)):
        name = str(record.get("product") or "").strip()
        if not name:
            continue
        entry = totals.setdefault(_norm(name), {"sales_name": name, "units": 0.0, "lines": 0, "missing_quantity": 0})
        entry["lines"] += 1
        if record.get("quantity") is None:
            entry["missing_quantity"] += 1
        else:
            entry["units"] += float(record["quantity"])
    link_map = links(path, business_id)
    products = db.many(path, "SELECT id, name, sku, active FROM inventory_products WHERE business_id = ?", (business_id,))
    by_name = {_norm(p["name"]): p for p in products}
    rows = []
    for key, entry in sorted(totals.items(), key=lambda item: -item[1]["units"]):
        linked = key in link_map
        product_id = resolve(entry["sales_name"], link_map, by_name)
        suggestion = None
        if not linked and product_id is None:
            hint = ocr.match_products([{"name": entry["sales_name"]}], [dict(p) for p in products])[0]["match"]
            suggestion = hint if hint and hint["kind"] == "similar" else None
        rows.append({
            **entry,
            "product_id": product_id,
            "status": "ignored" if linked and product_id is None else "linked" if linked else "matched" if product_id else "unlinked",
            "suggestion": suggestion,
        })
    return rows


def set_link(path: Path, business_id: str, sales_name: str, product_id: str | None) -> None:
    name = sales_name.strip()
    if not name:
        raise InventoryError("Sales name is required.")
    if product_id and not db.one(path, "SELECT 1 FROM inventory_products WHERE id = ? AND business_id = ?", (product_id, business_id)):
        raise InventoryError("Product not found.")
    db.insert(
        path,
        "INSERT INTO product_links (business_id, sales_name_norm, sales_name, product_id, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(business_id, sales_name_norm) DO UPDATE SET sales_name = excluded.sales_name, product_id = excluded.product_id, updated_at = excluded.updated_at",
        (business_id, _norm(name), name, product_id, db.now()),
    )


def clear_link(path: Path, business_id: str, sales_name: str) -> None:
    db.insert(path, "DELETE FROM product_links WHERE business_id = ? AND sales_name_norm = ?", (business_id, _norm(sales_name)))


class StockConflict(InventoryError):
    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__("Posting these sales would take stock below zero.")
        self.conflicts = conflicts


def post_dataset(path: Path, business_id: str, dataset_id: str, user_id: str) -> dict[str, Any]:
    dataset = dataset_store.get(business_id, dataset_id)
    if not dataset or dataset["status"] == "failed":
        raise InventoryError("Dataset not found.")
    if dataset.get("review_status") == dataset_store.EXCLUDED:
        raise InventoryError("Include this file in analysis before posting its sales to stock.")
    records = dataset_store.read_records(dataset)
    link_map = links(path, business_id)
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute("SELECT status FROM dataset_stock_posts WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if state and state["status"] == "posted":
            raise AlreadyPosted("This file's sales are already in stock.")
        products = conn.execute("SELECT id, name, unit_cost FROM inventory_products WHERE business_id = ?", (business_id,)).fetchall()
        by_name = {_norm(p["name"]): dict(p) for p in products}
        names = {p["id"]: p["name"] for p in products}
        units: dict[str, float] = defaultdict(float)
        skipped = {"unlinked": 0, "ignored": 0, "no_quantity": 0, "not_sales": 0}
        for record in records:
            name = str(record.get("product") or "").strip()
            if not name or float(record.get("amount") or 0) <= 0:
                skipped["not_sales"] += 1
                continue
            product_id = resolve(name, link_map, by_name)
            if not product_id:
                skipped["ignored" if _norm(name) in link_map else "unlinked"] += 1
                continue
            if record.get("quantity") is None:
                skipped["no_quantity"] += 1
                continue
            units[product_id] += float(record["quantity"])
        conflicts = []
        for product_id, quantity in units.items():
            on_hand = _stock(conn, product_id)
            if on_hand - quantity < 0:
                conflicts.append({"product_id": product_id, "name": names[product_id], "on_hand": on_hand, "sold": quantity, "short": quantity - on_hand})
        if conflicts:
            raise StockConflict(sorted(conflicts, key=lambda c: -c["short"]))
        for product_id, quantity in units.items():
            if quantity:
                _record_movement(conn, business_id, product_id, user_id, "sale", -quantity, f"Sales from {dataset['filename']}", f"sales:{dataset_id}")
        summary = {"products": len(units), "units": sum(units.values()), "skipped": skipped}
        conn.execute(
            "INSERT INTO dataset_stock_posts (dataset_id, business_id, status, summary, posted_at) VALUES (?, ?, 'posted', ?, ?) "
            "ON CONFLICT(dataset_id) DO UPDATE SET status = 'posted', summary = excluded.summary, posted_at = excluded.posted_at, reversed_at = NULL",
            (dataset_id, business_id, json.dumps(summary), db.now()),
        )
    return {"dataset_id": dataset_id, "status": "posted", **summary}


def reverse_dataset(path: Path, business_id: str, dataset_id: str, user_id: str) -> bool:
    """Undo a posted file's stock movements with equal and opposite adjustments. True if anything was reversed."""
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute(
            "SELECT status FROM dataset_stock_posts WHERE dataset_id = ? AND business_id = ?", (dataset_id, business_id)
        ).fetchone()
        if not state or state["status"] != "posted":
            return False
        # Net effect of this file on stock now: every posting minus every earlier reversal, so a
        # post -> reverse -> post -> reverse cycle never adds back more than is currently posted.
        rows = conn.execute(
            "SELECT product_id, SUM(quantity_delta) AS delta FROM inventory_movements WHERE business_id = ? AND source IN (?, ?) GROUP BY product_id",
            (business_id, f"sales:{dataset_id}", f"sales-reversal:{dataset_id}"),
        ).fetchall()
        for row in rows:
            if row["delta"]:
                _record_movement(conn, business_id, row["product_id"], user_id, "adjustment", -row["delta"], "Reversed: file left out of analysis", f"sales-reversal:{dataset_id}")
        conn.execute("UPDATE dataset_stock_posts SET status = 'reversed', reversed_at = ? WHERE dataset_id = ?", (db.now(), dataset_id))
    return True


def post_states(path: Path, business_id: str) -> dict[str, dict[str, Any]]:
    rows = db.many(path, "SELECT dataset_id, status, summary, posted_at, reversed_at FROM dataset_stock_posts WHERE business_id = ?", (business_id,))
    return {row["dataset_id"]: {**row, "summary": json.loads(row["summary"] or "{}")} for row in rows}


def reconciliation(path: Path, business_id: str) -> list[dict[str, Any]]:
    """Per product: the difference the last stocktake found between the ledger and the count."""
    rows = db.many(
        path,
        """
        SELECT p.id, p.name, p.unit_cost, m.quantity_delta AS variance, m.created_at
        FROM inventory_products p
        JOIN inventory_movements m ON m.id = (
            SELECT id FROM inventory_movements WHERE product_id = p.id AND movement_type = 'stocktake'
            ORDER BY created_at DESC LIMIT 1)
        WHERE p.business_id = ?
        ORDER BY ABS(m.quantity_delta) DESC
        """,
        (business_id,),
    )
    return [{**row, "value": round(row["variance"] * row["unit_cost"], 2) if row["unit_cost"] is not None else None} for row in rows]


class AlreadyPosted(InventoryError):
    """A posted file must be reversed before it can be posted again."""

