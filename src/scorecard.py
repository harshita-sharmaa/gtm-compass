"""Score each go-to-market channel and test a budget shift.

Reads data/channel_spend.csv and data/leads.csv, then writes to outputs/:
  channel_scorecard.csv  leads, customers, CAC, payback and LTV:CAC per channel
  segment_summary.csv    win rate and contract value per customer segment
  budget_scenario.csv    customers and revenue before and after moving budget
plus two charts. Assumptions are the constants below.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"

GROSS_MARGIN = 0.80
ANNUAL_CHURN = {"SMB": 0.40, "Mid-market": 0.25, "Enterprise": 0.15}  # share of customers lost per year
HEALTHY_LTV_CAC = 3.0     # common rule of thumb: a channel should return 3x what it costs
SCALE_LTV_CAC = 5.0       # channels above this are candidates for more budget
SHIFT_SHARE = 0.50        # share of the weakest channel's budget to move
EFFICIENCY_HAIRCUT = 0.30  # extra budget in a channel is assumed 30% less efficient than today's

VERDICT_COLORS = {"Scale": "#0ca30c", "Keep": "#2a78d6", "Fix or cut": "#d03b3b"}
BLUE, INK, MUTED, GRID, SURFACE = "#2a78d6", "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": "#c3c2b7",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "text.color": INK,
        "axes.labelcolor": "#52514e",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "font.size": 10,
    }
)


def build_scorecard(spend, leads):
    won = leads[leads["won"] == 1].copy()
    # Lifetime value of a customer = yearly margin x expected years as a customer (1 / churn)
    won["lifetime_value"] = won["annual_contract_value"] * GROSS_MARGIN / won["segment"].map(ANNUAL_CHURN)

    card = pd.DataFrame({
        "spend": spend.groupby("channel")["spend"].sum(),
        "leads": leads.groupby("channel").size(),
        "qualified": leads.groupby("channel")["qualified"].sum(),
        "customers": won.groupby("channel").size(),
        "new_annual_revenue": won.groupby("channel")["annual_contract_value"].sum(),
        "avg_contract_value": won.groupby("channel")["annual_contract_value"].mean(),
        "avg_lifetime_value": won.groupby("channel")["lifetime_value"].mean(),
    })
    card["lead_to_customer_pct"] = 100 * card["customers"] / card["leads"]
    card["cost_per_lead"] = card["spend"] / card["leads"]
    card["cac"] = card["spend"] / card["customers"]
    card["payback_months"] = card["cac"] / (card["avg_contract_value"] * GROSS_MARGIN / 12)
    card["ltv_to_cac"] = card["avg_lifetime_value"] / card["cac"]
    card["share_of_leads_pct"] = 100 * card["leads"] / card["leads"].sum()
    card["share_of_customers_pct"] = 100 * card["customers"] / card["customers"].sum()
    card["verdict"] = "Keep"
    card.loc[card["ltv_to_cac"] >= SCALE_LTV_CAC, "verdict"] = "Scale"
    card.loc[card["ltv_to_cac"] < HEALTHY_LTV_CAC, "verdict"] = "Fix or cut"
    return card.sort_values("ltv_to_cac", ascending=False)


def build_segment_summary(leads):
    won = leads[leads["won"] == 1]
    seg = pd.DataFrame({
        "leads": leads.groupby("segment").size(),
        "customers": won.groupby("segment").size(),
        "avg_contract_value": won.groupby("segment")["annual_contract_value"].mean(),
        "new_annual_revenue": won.groupby("segment")["annual_contract_value"].sum(),
    })
    seg["lead_to_customer_pct"] = 100 * seg["customers"] / seg["leads"]
    seg["share_of_customers_pct"] = 100 * seg["customers"] / seg["customers"].sum()
    seg["share_of_revenue_pct"] = 100 * seg["new_annual_revenue"] / seg["new_annual_revenue"].sum()
    return seg.sort_values("new_annual_revenue", ascending=False)


def build_budget_scenario(card):
    """Move part of the weakest channel's budget into the two strongest, split evenly."""
    weakest = card["ltv_to_cac"].idxmin()
    strongest = list(card.index[:2])
    moved = card.loc[weakest, "spend"] * SHIFT_SHARE

    scenario = card[["spend", "customers", "new_annual_revenue", "cac", "avg_contract_value"]].copy()
    scenario["spend_after"] = scenario["spend"]
    scenario.loc[weakest, "spend_after"] -= moved
    scenario.loc[strongest, "spend_after"] += moved / len(strongest)

    change = scenario["spend_after"] - scenario["spend"]
    # Removed budget loses customers at today's CAC; added budget wins them at a worse CAC
    cac_for_change = scenario["cac"].where(change <= 0, scenario["cac"] / (1 - EFFICIENCY_HAIRCUT))
    scenario["customers_after"] = scenario["customers"] + change / cac_for_change
    scenario["new_annual_revenue_after"] = scenario["customers_after"] * scenario["avg_contract_value"]
    scenario = scenario.drop(columns=["cac", "avg_contract_value"])
    return scenario, weakest, strongest, moved


def chart_scorecard(card):
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    bars = ax.barh(card.index, card["ltv_to_cac"], color=card["verdict"].map(VERDICT_COLORS), height=0.6)
    ax.bar_label(bars, labels=[f"{r:.1f}x  CAC ${c:,.0f}" for r, c in zip(card["ltv_to_cac"], card["cac"])],
                 padding=5, color=INK)
    ax.axvline(HEALTHY_LTV_CAC, color=MUTED, linestyle="--", linewidth=1)
    ax.text(HEALTHY_LTV_CAC, len(card) - 1.5, " 3x target", color=MUTED, fontsize=8, va="center")
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, card["ltv_to_cac"].max() * 1.3)
    ax.set_xlabel("Lifetime value per $1 spent to win a customer (LTV:CAC)")
    ax.set_title("Channel scorecard: return on acquisition spend")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "channel_scorecard.png", dpi=160)
    plt.close(fig)


def chart_shares(card):
    by_leads = card.sort_values("share_of_leads_pct")
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    y = range(len(by_leads))
    ax.barh([i + 0.2 for i in y], by_leads["share_of_leads_pct"], height=0.38, color="#c3c2b7", label="Share of leads")
    ax.barh([i - 0.2 for i in y], by_leads["share_of_customers_pct"], height=0.38, color=BLUE,
            label="Share of customers")
    ax.set_yticks(list(y))
    ax.set_yticklabels(by_leads.index)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("% of total")
    ax.set_title("Lead volume is not customer volume")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "leads_vs_customers.png", dpi=160)
    plt.close(fig)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    spend = pd.read_csv(DATA_DIR / "channel_spend.csv")
    leads = pd.read_csv(DATA_DIR / "leads.csv")

    card = build_scorecard(spend, leads)
    segments = build_segment_summary(leads)
    scenario, weakest, strongest, moved = build_budget_scenario(card)

    card.round(2).to_csv(OUT_DIR / "channel_scorecard.csv")
    segments.round(2).to_csv(OUT_DIR / "segment_summary.csv")
    scenario.round(1).to_csv(OUT_DIR / "budget_scenario.csv")
    chart_scorecard(card)
    chart_shares(card)

    show = card[["spend", "leads", "customers", "lead_to_customer_pct", "cac", "payback_months",
                 "ltv_to_cac", "verdict"]]
    print(show.round(1).to_string())
    print()
    print(segments.round(1).to_string())

    before, after = scenario["customers"].sum(), scenario["customers_after"].sum()
    rev_before, rev_after = scenario["new_annual_revenue"].sum(), scenario["new_annual_revenue_after"].sum()
    print(f"\nBlended CAC: ${card['spend'].sum() / card['customers'].sum():,.0f}")
    print(f"Scenario: move ${moved:,.0f} ({SHIFT_SHARE:.0%} of {weakest}) into {' and '.join(strongest)}")
    print(f"  Customers: {before:,.0f} -> {after:,.0f} ({100 * (after / before - 1):+.1f}%)")
    print(f"  New annual revenue: ${rev_before:,.0f} -> ${rev_after:,.0f} ({100 * (rev_after / rev_before - 1):+.1f}%)")
    print(f"  Total spend unchanged at ${scenario['spend_after'].sum():,.0f}")
    print(f"Outputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
