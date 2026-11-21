"""Seed a running Ferlance server with a demo account and realistic data.

Usage: python seed.py http://127.0.0.1:8770
"""
import csv, io, random, sys, datetime as dt
import httpx

BASE = sys.argv[1]
random.seed(7)
c = httpx.Client(base_url=BASE, timeout=30)
r = c.post("/api/auth/signup", json={"email": "demo@ferlance.test", "password": "demo-pass-123", "business_name": "Ama's Provisions"})
if r.status_code >= 400:
    r = c.post("/api/auth/login", json={"email": "demo@ferlance.test", "password": "demo-pass-123"})
r.raise_for_status()
tok = r.json()["access_token"]; bid = r.json()["business"]["id"]
H = {"Authorization": f"Bearer {tok}"}
P = f"/api/businesses/{bid}"

products = {"Rice 5kg": (95, 70), "Beans 1kg": (32, 22), "Cooking oil 1L": (48, 41), "Sugar 1kg": (18, 12),
            "Tomato paste": (9, 6.5), "Milo 400g": (55, 47), "Sardines": (14, 10.5)}
customers = ["Walk-in", "Kofi Mensah", "Abena Boateng", "Yaw Owusu", "Efua Asante", "Kwame Darko"]
buf = io.StringIO(); w = csv.writer(buf)
w.writerow(["transaction_id", "transaction_date", "product", "customer", "quantity", "unit_price", "unit_cost", "amount"])
start = dt.date(2026, 7, 1)
n = 0
for d in range(120):
    day = start + dt.timedelta(days=d)
    for _ in range(random.randint(2, 7)):
        name = random.choice(list(products)); price, cost = products[name]
        if name == "Cooking oil 1L" and d > 80: cost = price + 3  # becomes loss-making
        q = random.randint(1, 6); n += 1
        w.writerow([f"s-{n}", day.isoformat(), name, random.choice(customers), q, price, cost, round(price * q, 2)])
r = c.post(f"{P}/datasets", headers=H, files={"file": ("shop_sales_2026.csv", buf.getvalue(), "text/csv")}); print("upload", r.status_code, r.json().get("status"), r.json().get("accepted_rows"))
r = c.post(f"{P}/datasets", headers=H, files={"file": ("bad.csv", open(sys.argv[2]).read(), "text/csv")}) if len(sys.argv) > 2 else None
if r is not None: print("bad upload", r.status_code)
sms = "Payment received for GHS 120.00 from KOFI MENSAH 0244123456 Current Balance: GHS 1,520.00. Available Balance: GHS 1,520.00. Reference: rice. Transaction ID: 12345678901. Fee charged: GHS0.00"
print("momo", c.post(f"{P}/sources/momo", headers=H, json={"sms_text": sms}).status_code)
for name, (price, cost) in list(products.items())[:5]:
    r = c.post(f"{P}/inventory/products", headers=H, json={"name": name, "sku": name[:3].upper(), "unit": "pcs", "unit_cost": cost, "reorder_level": 10, "opening_stock": random.choice([4, 25, 60])})
    print("product", r.status_code)
inv = c.get(f"{P}/inventory", headers=H).json()
first = (inv.get("products") or inv.get("items") or [{}])[0]
if first.get("id"):
    print("movement", c.post(f"{P}/inventory/products/{first['id']}/movements", headers=H, json={"movement_type": "purchase", "quantity": 12, "note": "Restock from Makola"}).status_code)
for cat, acct, amt in [("cash", "Cash box", 2400), ("bank", "GCB current", 18500), ("receivables", "Customer credit", 1520), ("inventory", "Stock on hand", 9000), ("payables", "Supplier credit", 4200), ("loans", "Susu loan", 3000)]:
    r = c.post(f"{P}/financial-position/balances", headers=H, json={"as_of_date": "2026-10-28", "category": cat, "account_name": acct, "amount": amt, "note": ""})
    print("balance", cat, r.status_code, r.text[:80] if r.status_code >= 400 else "")
