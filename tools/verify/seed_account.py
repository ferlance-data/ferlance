"""Fill an existing Ferlance account with six months of realistic shop data.

Usage:
    .venv/bin/python tools/verify/seed_account.py BASE_URL EMAIL [--business NAME] [--dry-run]

It signs in (the password is asked for and never stored), picks the business by name
(default "Ferlance") and adds: a sales file and an expenses file (Jun–Nov 2026), stock items,
debts with part payments, invoices, rent and power as confirmed recurring payments, budgets
and balances. The books post themselves from these.

It never signs up, invites anyone, sends reminders, shares a report, ticks a tax rule as
checked, sets opening balances or a lock date, or calls an AI provider. It refuses to run twice:
it stops if the sales file is already in the account.

The data is made up (seeded, so every run is the same) but shaped like a small Accra mini-mart:
one product turns loss-making in October, one customer pays slowly, two items are running low.
"""
import argparse, csv, datetime as dt, getpass, io, random, sys

import httpx

SALES_FILE = "ferlance_sales_jun-nov_2026.csv"
EXPENSES_FILE = "ferlance_expenses_jun-nov_2026.csv"
START, END = dt.date(2026, 6, 1), dt.date(2026, 11, 24)
MONTHS = ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]

# name: (price, cost, weekly demand weight)
PRODUCTS = {
    "Rice 5kg (Royal Aroma)": (110, 88, 5), "Gari 2kg": (28, 19, 6), "Beans 1kg": (32, 23, 4),
    "Cooking oil 1L (Frytol)": (52, 44, 5), "Sugar 1kg": (19, 13, 4), "Tomato paste 400g": (12, 8.5, 7),
    "Milo 400g": (58, 48, 3), "Sardines (Titus)": (15, 11, 6), "Indomie noodles (pack)": (4.5, 3.4, 12),
    "Bottled water (pack of 12)": (22, 15, 5), "Bread (sliced)": (15, 11, 8), "Key soap": (8, 5.5, 4),
    "Omo 500g": (25, 19, 3), "Toilet roll (4 pack)": (18, 13, 3),
}
CUSTOMERS = ["Walk-in"] * 12 + ["Kofi Mensah", "Abena Boateng", "Yaw Owusu", "Efua Asante", "Kwame Darko", "Akosua Frimpong", "Nana Adjei"]
PAY = ["cash"] * 5 + ["MTN MoMo"] * 4 + ["Telecel Cash"] + ["bank transfer"]


def sales_csv() -> str:
    rnd = random.Random(2026)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["transaction_id", "transaction_date", "product", "customer", "quantity", "unit_price", "unit_cost", "amount", "payment_method"])
    names, weights = list(PRODUCTS), [p[2] for p in PRODUCTS.values()]
    n, day = 0, START
    while day <= END:
        busy = 1.4 if day.weekday() == 5 else 0.6 if day.weekday() == 6 else 1.0
        busy *= 1.25 if day.month == 11 else 1.0  # Christmas stock-up starts
        for _ in range(round(rnd.randint(8, 16) * busy)):
            name = rnd.choices(names, weights)[0]; price, cost, _w = PRODUCTS[name]
            if name.startswith("Cooking oil") and day >= dt.date(2026, 10, 1):
                cost = 55  # supplier raised the price; shelf price never moved
            if name.startswith("Rice") and day >= dt.date(2026, 9, 15):
                price = 120
            q = rnd.choice([1, 1, 1, 2, 2, 3, 4]); n += 1
            w.writerow([f"FS-{n:05d}", day.isoformat(), name, rnd.choice(CUSTOMERS), q, price, cost, round(price * q, 2), rnd.choice(PAY)])
        day += dt.timedelta(days=1)
    return buf.getvalue()


def expenses_csv() -> str:
    rnd = random.Random(11)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["expense_id", "expense_date", "category", "vendor", "expense_amount", "payment_method"])
    n = 0
    def add(day, cat, vendor, amt, pay):
        nonlocal n; n += 1
        w.writerow([f"FE-{n:04d}", day.isoformat(), cat, vendor, amt, pay])
    day = START
    while day <= END:
        if day.weekday() in (1, 4):
            add(day, "Transport", "Makola restock trotro + truck pusher", rnd.choice([45, 60, 80]), "cash")
        if day.weekday() == 0:
            add(day, "Airtime and data bundle", "MTN", 50, "MTN MoMo")
        if day.day == 28 or (day == END and day.day < 28):
            for staff in ("Esi (shop assistant)", "Kojo (shop helper)"):
                add(day, "Staff wages", staff, 1200 if staff.startswith("Esi") else 900, "MTN MoMo")
            add(day, "MoMo fee and e-levy charges", "MTN", round(rnd.uniform(35, 70), 2), "MTN MoMo")
        if day.day == 15:
            add(day, "Water bill", "GWCL", rnd.choice([80, 95, 110]), "MTN MoMo")
        day += dt.timedelta(days=1)
    add(dt.date(2026, 8, 9), "Repairs", "Fridge compressor repair", 650, "cash")
    add(dt.date(2026, 10, 3), "Shop signage", "Sign writer, Adabraka", 400, "cash")
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url"); ap.add_argument("email")
    ap.add_argument("--business", default="Ferlance"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sales, expenses = sales_csv(), expenses_csv()
    print(f"Plan: {sales.count(chr(10)) - 1} sale lines, {expenses.count(chr(10)) - 1} expense lines, {len(PRODUCTS)} stock items, 6 debts, 5 invoices, 2 recurring payments, budgets, balances.")
    if a.dry_run:
        return

    c = httpx.Client(base_url=a.base_url.rstrip("/"), timeout=120)
    r = c.post("/api/auth/login", json={"email": a.email, "password": getpass.getpass(f"Password for {a.email}: ")})
    if r.status_code != 200:
        sys.exit(f"Sign-in failed ({r.status_code}): {r.text[:200]}")
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = c.get("/api/auth/me", headers=H).json()
    match = [b for b in me.get("businesses", []) if (b.get("name") or "").strip().casefold() == a.business.casefold()]
    if len(match) != 1:
        sys.exit(f"Expected one business named {a.business!r}; found: {[b.get('name') for b in me.get('businesses', [])]}")
    P = f"/api/businesses/{match[0]['id']}"
    print(f"Business: {match[0]['name']} ({match[0]['id']})")

    existing = c.get(f"{P}/datasets", headers=H).json()
    if any(d.get("filename") == SALES_FILE for d in existing):
        sys.exit("This account already has the seeded sales file. Nothing added.")

    def call(method, path, **kw):
        r = c.request(method, P + path, headers=H, **kw)
        if r.status_code >= 400:
            print(f"  ! {method} {path} → {r.status_code} {r.text[:160]}")
            return None
        return r.json()

    for name, body in ((SALES_FILE, sales), (EXPENSES_FILE, expenses)):
        d = call("POST", "/datasets", files={"file": (name, body, "text/csv")})
        print(f"file {name}: {d and d.get('status')}, {d and d.get('accepted_rows')} rows")

    stock = {"Cooking oil 1L (Frytol)": 6, "Milo 400g": 3, "Indomie noodles (pack)": 140, "Tomato paste 400g": 48}
    for name, (price, cost, _w) in PRODUCTS.items():
        unit = "pack" if "pack" in name else "pcs"
        call("POST", "/inventory/products", json={"name": name, "sku": "FL-" + "".join(x[0] for x in name.split()[:3]).upper(),
             "unit": unit, "unit_cost": 55 if name.startswith("Cooking oil") else cost, "reorder_level": 10, "opening_stock": stock.get(name, 24)})
    print(f"stock items: {len(PRODUCTS)}")

    today = dt.date(2026, 11, 25)
    debts = [
        ("owed_to_us", "Kofi Mensah", "Rice and oil on credit for his chop bar", 860, dt.date(2026, 9, 2), dt.date(2026, 10, 2), "new_sale", [(200, dt.date(2026, 10, 20), "momo_mtn")]),
        ("owed_to_us", "Akosua Frimpong", "Provisions for church harvest", 1450, dt.date(2026, 10, 18), dt.date(2026, 11, 17), "new_sale", [(500, dt.date(2026, 11, 10), "cash")]),
        ("owed_to_us", "Yaw Owusu", "Weekly provisions, pays at month end", 320, dt.date(2026, 11, 8), dt.date(2026, 12, 8), "new_sale", []),
        ("owed_to_us", "Nana Adjei", "Bottled water for a funeral", 440, dt.date(2026, 8, 1), dt.date(2026, 8, 31), "new_sale", [(440, dt.date(2026, 9, 5), "momo_mtn")]),
        ("we_owe", "Makola Wholesale (Auntie Comfort)", "Rice and sugar on supplier credit", 3200, dt.date(2026, 11, 3), dt.date(2026, 12, 3), "recorded_purchase", [(1200, dt.date(2026, 11, 17), "cash")]),
        ("we_owe", "Kasoa Water Distributors", "Bottled water, 40 packs", 600, dt.date(2026, 11, 12), dt.date(2026, 11, 26), "recorded_purchase", []),
    ]
    for direction, party, desc, amt, issued, due, basis, pays in debts:
        d = call("POST", "/debts", json={"direction": direction, "party_name": party, "description": desc, "amount": amt,
                 "issued_on": issued.isoformat(), "due_on": due.isoformat(), "basis": basis})
        for p_amt, on, method in (pays if d else []):
            call("POST", f"/debts/{d['id']}/payments", json={"amount": p_amt, "paid_on": on.isoformat(), "method": method})
    print(f"debts: {len(debts)}")

    call("PUT", "/invoices/settings", json={"address": "Shop 12, Kaneshie Market Road, Accra", "phone": "", "footer": "Thank you for buying from Ferlance."})
    invoices = [
        ("invoice", "St. Mary's Basic School canteen", dt.date(2026, 11, 4), dt.date(2026, 12, 4), [("Rice 5kg (Royal Aroma)", 6, 120), ("Cooking oil 1L (Frytol)", 6, 52), ("Tomato paste 400g", 24, 12)], None),
        ("invoice", "Grace Events Catering", dt.date(2026, 10, 10), dt.date(2026, 10, 24), [("Bottled water (pack of 12)", 30, 22)], None),
        ("receipt", "Efua Asante", dt.date(2026, 11, 20), None, [("Milo 400g", 2, 58), ("Sugar 1kg", 3, 19)], "momo_mtn"),
        ("quote", "Adom Office Supplies (staff Christmas hampers)", dt.date(2026, 11, 22), dt.date(2026, 12, 6), [("Rice 5kg (Royal Aroma)", 15, 115), ("Milo 400g", 15, 55), ("Cooking oil 1L (Frytol)", 15, 58)], None),
        ("invoice", "Kwame Darko", dt.date(2026, 11, 14), dt.date(2026, 11, 28), [("Indomie noodles (pack)", 40, 4.5), ("Sardines (Titus)", 20, 15)], None),
    ]
    for kind, cust, issued, due, lines, paid_by in invoices:
        call("POST", "/invoices", json={"kind": kind, "customer_name": cust, "issued_on": issued.isoformat(), "due_on": due and due.isoformat(),
             "lines": [{"description": n, "quantity": q, "unit_price": p} for n, q, p in lines], "paid_by": paid_by})
    print(f"invoices: {len(invoices)}")

    for name, acct, amt, paid_from, dom in (("Shop rent", "rent", 1500, "bank", 1), ("ECG prepaid power", "utilities", 350, "momo_mtn", 5)):
        item = call("POST", "/recurring", json={"name": name, "account": acct, "amount": amt, "paid_from": paid_from, "day_of_month": dom, "start_month": MONTHS[0]})
        for m in MONTHS:
            if item and dt.date(int(m[:4]), int(m[5:]), dom) <= today:
                call("POST", f"/recurring/{item['id']}/decide", json={"month": m, "confirm": True})
    print("recurring: 2, confirmed for each past month")

    for acct, amt in (("transport", 600), ("airtime", 220), ("utilities", 500), ("charges", 80), ("wages", 2100)):
        for m in ("2026-11", "2026-12"):
            call("PUT", "/budgets", json={"month": m, "account": acct, "amount": amt})
    print("budgets: Nov and Dec")

    for cat, acct, amt in (("cash", "Cash box", 1850), ("cash", "MTN MoMo wallet", 4320), ("bank", "GCB current account", 12600),
                           ("inventory", "Stock on hand", 7400), ("fixed_assets", "Fridge, shelves and counter", 9500), ("loans", "Susu group loan", 3000)):
        call("POST", "/financial-position/balances", json={"as_of_date": "2026-11-24", "category": cat, "account_name": acct, "amount": amt})
    print("balances: 6\nDone.")


if __name__ == "__main__":
    main()
