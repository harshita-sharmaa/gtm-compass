"""Generate a synthetic go-to-market dataset for a made-up B2B software product.

Writes two files to data/: monthly marketing and sales spend per channel, and
one row per lead with its channel, customer segment and how far it got
(lead, qualified, won). The data is simulated with a fixed seed. Each channel
is given its own cost per lead, conversion rates and segment mix so the
scorecard has real differences to find.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 21
MONTHS = pd.period_range("2025-07", "2026-06", freq="M")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CHANNELS = {
    # channel: monthly spend, cost per lead, P(qualified), P(won | qualified), segment mix (SMB, Mid-market, Enterprise)
    "Paid Social": (30000, 60, 0.10, 0.07, (0.85, 0.13, 0.02)),
    "Paid Search": (25000, 125, 0.25, 0.10, (0.60, 0.33, 0.07)),
    "Content / SEO": (12000, 80, 0.20, 0.10, (0.55, 0.37, 0.08)),
    "Webinars & Events": (20000, 250, 0.26, 0.10, (0.25, 0.55, 0.20)),
    "Outbound Sales": (28000, 310, 0.20, 0.085, (0.05, 0.45, 0.50)),
    "Referrals & Partners": (8000, 160, 0.32, 0.12, (0.35, 0.45, 0.20)),
}
SEGMENTS = ["SMB", "Mid-market", "Enterprise"]
TYPICAL_CONTRACT = {"SMB": 3000, "Mid-market": 12000, "Enterprise": 40000}  # annual contract value, USD


def main():
    rng = np.random.default_rng(SEED)
    spend_rows, lead_frames = [], []

    for channel, (base_spend, cost_per_lead, p_qualified, p_won, mix) in CHANNELS.items():
        for month in MONTHS:
            spend = round(base_spend * rng.normal(1.0, 0.06), -2)
            spend_rows.append({"month": str(month), "channel": channel, "spend": spend})

            n = rng.poisson(spend / cost_per_lead)
            segment = rng.choice(SEGMENTS, size=n, p=mix)
            qualified = rng.random(n) < p_qualified
            won = qualified & (rng.random(n) < p_won)
            contract = np.array([TYPICAL_CONTRACT[s] for s in segment]) * rng.lognormal(0, 0.25, n)
            day = rng.integers(1, month.days_in_month + 1, n)
            lead_frames.append(pd.DataFrame({
                "created_date": [f"{month}-{d:02d}" for d in day],
                "channel": channel,
                "segment": segment,
                "qualified": qualified.astype(int),
                "won": won.astype(int),
                "annual_contract_value": np.where(won, np.round(contract, -2), 0).astype(int),
            }))

    spend = pd.DataFrame(spend_rows)
    leads = pd.concat(lead_frames, ignore_index=True).sort_values("created_date").reset_index(drop=True)
    leads.insert(0, "lead_id", np.arange(1, len(leads) + 1))

    DATA_DIR.mkdir(exist_ok=True)
    spend.to_csv(DATA_DIR / "channel_spend.csv", index=False)
    leads.to_csv(DATA_DIR / "leads.csv", index=False)
    print(f"Wrote {len(spend)} spend rows and {len(leads):,} leads to {DATA_DIR}")


if __name__ == "__main__":
    main()
