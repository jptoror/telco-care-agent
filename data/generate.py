"""Synthetic data for "Conecta", a fictional telco.

Produces CSV tables (customers, plans, invoices, invoice_lines, usage_daily,
zones, outages, devices) under data/out/. Seeded customers C1001-C1008 carry
hand-crafted situations used by the demo and the eval suite; the rest is
random background population.

    python data/generate.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "out"
rng = random.Random(42)

PERIODS = ["2026-08", "2026-09", "2026-10"]

PLANS = [
    # plan_id, name, kind, monthly_fee, data_gb, speed_mbps, roaming_included
    ("MOB-S", "Movil 10GB", "mobile", 15.00, 10, 0, "false"),
    ("MOB-M", "Movil 30GB", "mobile", 25.00, 30, 0, "false"),
    ("MOB-L", "Movil Ilimitado", "mobile", 45.00, 999, 0, "true"),
    ("HOME-100", "Hogar 100 Mbps", "home", 30.00, 0, 100, "false"),
    ("HOME-300", "Hogar 300 Mbps", "home", 45.00, 0, 300, "false"),
    ("HOME-1000", "Hogar 1 Gbps", "home", 70.00, 0, 1000, "false"),
]
PLAN = {p[0]: p for p in PLANS}

ZONES = [
    ("Z-NORTE", "Ciudad Norte"), ("Z-CENTRO", "Ciudad Centro"),
    ("Z-SUR", "Ciudad Sur"), ("Z-COSTA", "Bahia Costa"), ("Z-ISLA", "Isla Grande"),
]

FIRST = ["Ana", "Carlos", "Maria", "Luis", "Laura", "Jorge", "Sofia", "Diego", "Valentina", "Andres",
         "Camila", "Mateo", "Isabella", "Santiago", "Lucia", "John", "Grace", "Michael", "Sarah", "Kevin"]
LAST = ["Gomez", "Rodriguez", "Martinez", "Lopez", "Perez", "Garcia", "Sanchez", "Ramirez", "Torres",
        "Flores", "Smith", "Brown", "Williams", "Clarke", "Morgan"]

TAX_RATE = 0.10


def money(x: float) -> str:
    return f"{x:.2f}"


class Writer:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def add(self, table: str, **row):
        self.tables.setdefault(table, []).append(row)

    def flush(self):
        OUT.mkdir(parents=True, exist_ok=True)
        for name, rows in self.tables.items():
            with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"{name:14s} {len(rows):6d} rows")


W = Writer()
line_seq = iter(range(1, 10**7))


def invoice(cust_id: str, period: str, lines: list[tuple[str, str, float, str]], paid_on: str | None):
    """lines: (concept_code, description, amount, ref_date)."""
    inv_id = f"INV-{cust_id}-{period.replace('-', '')}"
    y, m = map(int, period.split("-"))
    issue = date(y, m, 1)
    due = issue + timedelta(days=15)
    subtotal = round(sum(l[2] for l in lines), 2)
    tax = round(subtotal * TAX_RATE, 2)
    for code, desc, amount, ref in lines + [("TAX", "Impuestos (10%)", tax, issue.isoformat())]:
        W.add("invoice_lines", line_id=f"L{next(line_seq):07d}", invoice_id=inv_id, concept_code=code,
              description=desc, amount=money(amount), ref_date=ref)
    status = "PAID" if paid_on else ("OPEN" if period == PERIODS[-1] else "OVERDUE")
    W.add("invoices", invoice_id=inv_id, customer_id=cust_id, period=period, issue_date=issue.isoformat(),
          due_date=due.isoformat(), subtotal=money(subtotal), tax=money(tax), total=money(subtotal + tax),
          status=status, paid_on=paid_on or "")
    return inv_id


def plan_line(plan_id: str, period: str):
    p = PLAN[plan_id]
    return ("PLAN_FEE", f"Cargo fijo {p[1]}", p[3], f"{period}-01")


def usage(cust_id: str, start: date, days: int, daily_mb: tuple[int, int], roaming: dict | None = None):
    for i in range(days):
        d = start + timedelta(days=i)
        r_mb, country = 0, ""
        if roaming and roaming["from"] <= d <= roaming["to"]:
            r_mb, country = rng.randint(*roaming["mb"]), roaming["country"]
        W.add("usage_daily", customer_id=cust_id, date=d.isoformat(), data_mb=rng.randint(*daily_mb),
              roaming_mb=r_mb, roaming_country=country)


def customer(cid, name, zone, plan, lang, since, segment="residential"):
    W.add("customers", customer_id=cid, full_name=name, zone_id=zone, plan_id=plan, language=lang,
          customer_since=since, segment=segment, phone=f"+1-555-{rng.randint(1000000, 9999999)}")


def device(cid, status, signal, last_seen, kind="modem"):
    W.add("devices", device_id=f"DEV-{cid}", customer_id=cid, kind=kind, status=status,
          signal_dbm=signal, last_seen=last_seen, firmware="4.2.1")


def regular_invoices(cid, plan, periods=PERIODS, extra=None):
    for per in periods:
        lines = [plan_line(plan, per)] + (extra.get(per, []) if extra else [])
        y, m = map(int, per.split("-"))
        paid = None if per == PERIODS[-1] else date(y, m, rng.randint(3, 14)).isoformat()
        invoice(cid, per, lines, paid)


# ------------------------------------------------------------------ catalog
for p in PLANS:
    W.add("plans", plan_id=p[0], name=p[1], kind=p[2], monthly_fee=money(p[3]), data_gb=p[4],
          speed_mbps=p[5], roaming_included=p[6])
for z in ZONES:
    W.add("zones", zone_id=z[0], name=z[1])

# Active outage in Z-SUR (fiber cut), resolved one in Z-NORTE.
W.add("outages", outage_id="OUT-2210", zone_id="Z-SUR", started_at="2026-10-17T06:40:00-05:00",
      eta="2026-10-17T18:00:00-05:00", ended_at="", status="ACTIVE", cause="Corte de fibra troncal",
      affected="home")
W.add("outages", outage_id="OUT-2187", zone_id="Z-NORTE", started_at="2026-10-09T13:00:00-05:00",
      eta="", ended_at="2026-10-09T16:20:00-05:00", status="RESOLVED", cause="Mantenimiento",
      affected="home")

# ------------------------------------------------------------------ seeded cases
OCT = date(2026, 10, 1)

# C1001: plan fee charged twice in October -> credit eligible (billing error).
customer("C1001", "Ana Gomez", "Z-CENTRO", "MOB-L", "es", "2021-03-14")
regular_invoices("C1001", "MOB-L", extra={"2026-10": [plan_line("MOB-L", "2026-10")]})
usage("C1001", date(2026, 8, 1), 77, (300, 900))

# C1002: legit roaming charges after a trip to Miami (plan has no roaming) -> no credit.
customer("C1002", "John Clarke", "Z-COSTA", "MOB-M", "en", "2023-07-02")
regular_invoices("C1002", "MOB-M", extra={"2026-10": [
    ("ROAMING", "Roaming datos USA (2.1 GB, 26-30 sep)", 63.00, "2026-09-30"),
    ("ROAMING", "Roaming llamadas USA (42 min)", 8.40, "2026-09-30")]})
usage("C1002", date(2026, 8, 1), 77, (200, 700),
      roaming={"from": date(2026, 9, 26), "to": date(2026, 9, 30), "mb": (380, 480), "country": "US"})

# C1003: home internet slow / down -> active outage in Z-SUR.
customer("C1003", "Maria Lopez", "Z-SUR", "HOME-300", "es", "2019-11-20")
regular_invoices("C1003", "HOME-300")
device("C1003", "OFFLINE", -99, "2026-10-17T06:41:12-05:00")

# C1004: modem offline, no outage -> remote reboot fixes it.
customer("C1004", "Carlos Ramirez", "Z-CENTRO", "HOME-100", "es", "2022-01-09")
regular_invoices("C1004", "HOME-100")
device("C1004", "DEGRADED", -81, "2026-10-17T08:02:45-05:00")

# C1005: pays for 1 Gbps but uses little -> recommend a cheaper plan; change needs confirmation.
customer("C1005", "Laura Torres", "Z-NORTE", "HOME-1000", "es", "2020-05-30")
regular_invoices("C1005", "HOME-1000")
device("C1005", "ONLINE", -52, "2026-10-17T09:10:00-05:00")
usage("C1005", date(2026, 8, 1), 77, (1500, 4000))

# C1006: unrecognized premium SMS subscription, first dispute -> credit eligible by policy.
customer("C1006", "Diego Sanchez", "Z-ISLA", "MOB-S", "es", "2024-02-11")
regular_invoices("C1006", "MOB-S", extra={"2026-10": [
    ("PREMIUM_SMS", "Suscripcion SMS premium 'TriviaMax'", 4.99, "2026-09-12"),
    ("PREMIUM_SMS", "Suscripcion SMS premium 'TriviaMax'", 4.99, "2026-09-19"),
    ("PREMIUM_SMS", "Suscripcion SMS premium 'TriviaMax'", 4.99, "2026-09-26")]})
usage("C1006", date(2026, 8, 1), 77, (100, 400))

# C1007: September paid late -> late fee in October is legit.
customer("C1007", "Grace Morgan", "Z-COSTA", "MOB-M", "en", "2018-09-01")
for per, paid, extra in [("2026-08", "2026-08-10", []), ("2026-09", "2026-09-27", []),
                         ("2026-10", None, [("LATE_FEE", "Recargo por pago tardio factura 2026-09", 5.00,
                                             "2026-09-27")])]:
    invoice("C1007", per, [plan_line("MOB-M", per)] + extra, paid)

# C1008: plan upgraded mid-September -> proration on October invoice (legit).
customer("C1008", "Luis Perez", "Z-NORTE", "HOME-300", "es", "2021-12-12")
regular_invoices("C1008", "HOME-100", periods=["2026-08", "2026-09"])
invoice("C1008", "2026-10", [plan_line("HOME-300", "2026-10"),
                             ("PRORATION", "Prorrateo cambio a Hogar 300 Mbps (16-30 sep)", 7.50, "2026-09-16")],
        None)
device("C1008", "ONLINE", -48, "2026-10-17T09:30:00-05:00")

# ------------------------------------------------------------------ background population
for n in range(2000, 2190):
    cid = f"C{n}"
    plan = rng.choice(PLANS)[0]
    zone = rng.choice(ZONES)[0]
    lang = "en" if zone in ("Z-COSTA", "Z-ISLA") and rng.random() < 0.6 else "es"
    customer(cid, f"{rng.choice(FIRST)} {rng.choice(LAST)}", zone, plan, lang,
             (date(2016, 1, 1) + timedelta(days=rng.randint(0, 3500))).isoformat(),
             segment=rng.choice(["residential"] * 4 + ["smb"]))
    extra = {}
    if rng.random() < 0.15:
        extra["2026-10"] = [("DATA_PACK", "Paquete adicional 5GB", 7.00, "2026-09-20")]
    regular_invoices(cid, plan, extra=extra)
    if PLAN[plan][2] == "home":
        st = "OFFLINE" if zone == "Z-SUR" and rng.random() < 0.7 else rng.choice(["ONLINE"] * 9 + ["DEGRADED"])
        device(cid, st, rng.randint(-95, -45), "2026-10-17T09:00:00-05:00")
    else:
        usage(cid, OCT, 16, (100, 1500))

W.flush()
