# Air Quality Retail Impact Dashboard

> Real-time PM2.5 air quality data mapped to retail footfall elasticity — showing how poor air quality directly reduces shopper traffic and revenue across 10 global retail districts.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![OpenAQ](https://img.shields.io/badge/Data-OpenAQ_v3-00b4d8)
![License](https://img.shields.io/badge/License-MIT-green)

## 🌐 Live Dashboard

**[https://sirohids.github.io/air-retail-impact/](https://sirohids.github.io/air-retail-impact/)**

---

## What It Does

Fetches real-time PM2.5 readings from [OpenAQ v3](https://openaq.org) for 10 global high-street retail districts, applies a footfall elasticity model based on WHO guidelines, and outputs:

| PM2.5 Level | Retail Impact |
|---|---|
| ≤ 15 µg/m³ (WHO safe) | Normal footfall |
| 15–100 µg/m³ | −5% footfall (Slight Decrease) |
| 100–250 µg/m³ | −20% footfall (Significant Avoidance) |
| > 250 µg/m³ | −50% footfall (Retail Standstill) |

## Dashboard Features

- **KPI Summary** — cities monitored, cities above WHO limit, avg footfall loss, worst-affected district
- **Footfall Loss Bar Chart** — all 10 cities ranked by retail impact severity
- **Risk Distribution Donut** — breakdown of High / Medium / Low risk cities
- **PM2.5 vs Retail Impact Scatter** — visual correlation between air quality and footfall decline
- **Recovery Forecast Chart** — current PM2.5 vs 10% air-quality improvement scenario
- **24-Hour PM2.5 Trend** — hourly readings for top monitored cities
- **Full City Table** — PM2.5, footfall progress bars, revenue risk, and forecasts

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run the pipeline (you will be prompted for an OpenAQ API key)
python air_retail_impact.py
```

Get a free API key at [explore.openaq.org/register](https://explore.openaq.org/register).

The pipeline writes `retail_risk.json` — the dashboard reads this file. Commit the updated JSON and push to refresh the live dashboard.

## Cities Monitored

London · Delhi · New York · Beijing · Mumbai · Lahore · Dhaka · Bangkok · Cairo · Mexico City
