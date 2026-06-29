#!/usr/bin/env python3
"""
Lumora — financial model and path to $100k/month.

Pure-Python, no dependencies. Run it to print the model and (re)write
financial-model.csv. All assumptions are explicit and editable at the top.

    python3 financial_model.py
"""

import csv
import os

# ---------------------------------------------------------------------------
# ASSUMPTIONS  (edit these — everything else is derived)
# ---------------------------------------------------------------------------

AOV = 42.00                 # blended average order value ($), engineered via
                            # price ladder ($19-$97) + order bump + 1 upsell.
GROSS_MARGIN = 0.92         # contribution after Stripe (~3%), refunds (~3%),
                            # delivery/email COGS (~1%). Digital => very high.
REPEAT_RATE = 0.15          # share of orders from returning customers.
CAC = 15.00                 # blended cost to acquire one PAID customer ($).
OPEX_BASE = 400.0           # month-1 fixed costs (tools, email, hosting).
OPEX_MAX = 3500.0           # steady-state fixed costs (contractor, design, app fees).

# Monthly ORDERS trajectory — a realistic compounding ramp from a soft launch.
# This is the single growth input; revenue/profit are derived from it.
ORDERS = [120, 260, 460, 720, 1050, 1450, 1850, 2250, 2450, 2600, 2750, 2900]

# Paid-acquisition share of NEW customers, growing as we scale ad spend.
PAID_SHARE = [0.30, 0.33, 0.36, 0.40, 0.43, 0.45, 0.47, 0.48, 0.49, 0.50, 0.50, 0.50]

# ---------------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------------

def opex_for(month_index, n_months):
    """Fixed costs scale linearly from base to max as the business grows."""
    if n_months == 1:
        return OPEX_MAX
    frac = month_index / (n_months - 1)
    return round(OPEX_BASE + (OPEX_MAX - OPEX_BASE) * frac, 2)


def build_rows():
    rows = []
    cumulative_net = 0.0
    n = len(ORDERS)
    for i, orders in enumerate(ORDERS):
        revenue = orders * AOV
        gross_profit = revenue * GROSS_MARGIN
        new_customers = orders * (1 - REPEAT_RATE)
        paid_customers = new_customers * PAID_SHARE[i]
        ad_spend = paid_customers * CAC
        opex = opex_for(i, n)
        net = gross_profit - ad_spend - opex
        cumulative_net += net
        blended_cac = ad_spend / new_customers if new_customers else 0
        rows.append({
            "month": i + 1,
            "orders": orders,
            "revenue": round(revenue, 2),
            "gross_profit": round(gross_profit, 2),
            "ad_spend": round(ad_spend, 2),
            "opex": round(opex, 2),
            "net_profit": round(net, 2),
            "cumulative_net": round(cumulative_net, 2),
            "blended_cac_all": round(blended_cac, 2),
        })
    return rows


def ltv():
    orders_per_customer = 1 + REPEAT_RATE / (1 - REPEAT_RATE)  # ~1.18
    return AOV * orders_per_customer * GROSS_MARGIN


def main():
    rows = build_rows()
    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(here, "financial-model.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Pretty print
    hdr = (f"{'Mo':>3} {'Orders':>7} {'Revenue':>11} {'GrossProfit':>12} "
           f"{'AdSpend':>10} {'Opex':>8} {'Net':>11} {'CumNet':>12}")
    print("\nLUMORA — 12-MONTH MODEL (AOV ${:.0f}, gross margin {:.0%})".format(AOV, GROSS_MARGIN))
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['month']:>3} {r['orders']:>7} "
              f"${r['revenue']:>10,.0f} ${r['gross_profit']:>11,.0f} "
              f"${r['ad_spend']:>9,.0f} ${r['opex']:>7,.0f} "
              f"${r['net_profit']:>10,.0f} ${r['cumulative_net']:>11,.0f}")
    print("=" * len(hdr))

    # Key metrics
    customer_ltv = ltv()
    first_100k = next((r["month"] for r in rows if r["revenue"] >= 100_000), None)
    year_rev = sum(r["revenue"] for r in rows)
    year_net = rows[-1]["cumulative_net"]
    run_rate = rows[-1]["revenue"] * 12

    print("\nUNIT ECONOMICS & TARGETS")
    print("-" * 40)
    print(f"  AOV                         ${AOV:,.2f}")
    print(f"  Contribution / order        ${AOV*GROSS_MARGIN:,.2f}")
    print(f"  Customer LTV (contribution) ${customer_ltv:,.2f}")
    print(f"  Target CAC                  ${CAC:,.2f}")
    print(f"  LTV:CAC                      {customer_ltv/CAC:,.1f} : 1   (target >= 3:1)")
    print(f"  Orders/mo for $100k         {round(100_000/AOV):,}  (~{round(100_000/AOV/30)}/day)")
    print(f"  Sessions/mo for $100k       {round(100_000/AOV/0.026):,}  (@2.6% conv)")
    print()
    print(f"  Month revenue first hits $100k:  Month {first_100k}")
    print(f"  Exit run-rate (mo12 x12):        ${run_rate:,.0f}/yr")
    print(f"  Year-1 gross revenue:            ${year_rev:,.0f}")
    print(f"  Year-1 cumulative net profit:    ${year_net:,.0f}")
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
