# Hail Flood Early Warning System

A flood early-warning system for Hail City, Saudi Arabia, that combines real-time rainfall data from Open-Meteo and RainViewer, OSM street network analysis, satellite-based water detection via Sentinel Hub, and machine learning risk prediction to provide actionable flood risk intelligence.

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy the environment template and fill in your Sentinel Hub credentials:
   ```bash
   copy .env.template .env
   ```

4. Run the application:
   ```bash
   streamlit run app.py
   ```

## Machine Learning Component — Honest Scope

The ML layer is trained on a small real dataset (~20 confirmed flood dates spanning 29 known geographic low points, ~300 rows total) and currently functions as a pattern-confirmation layer rather than an independent predictor, since elevation and proximity dominate both the training labels and the available features.

- The rule-based `risk_engine` is the primary and authoritative decision source for all risk assessments.
- ML predictions can only escalate the risk level (to avoid under-warning); they can never downgrade a rule-based determination.
- All ML predictions carry an `"interpretation": "pattern_confirmation"` field in API responses, clearly labeling their role in the UI.
- As the system operates and the `alerts` table accumulates real outcomes over time, retraining on that operational data is the recommended path toward a more independently predictive model.

## Pages

- **Dashboard** — Overview of current weather conditions, radar imagery, and overall risk level.
- **Risk Map** — Interactive folium map displaying flood risk zones across Hail City.
- **Report** — Generates a downloadable report summarizing the current risk assessment.
- **History** — Timeline view of past alerts, events, and risk scores.
