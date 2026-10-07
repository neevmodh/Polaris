"""Emission factors and their uncertainty, in one auditable place."""

# Scope 2: CEA CO2 Baseline Database v22.0 (Aug 2026), FY2025-26, weighted average, Indian grid
GRID_EF_KG_PER_KWH = 0.675          # tCO2/MWh == kgCO2/kWh
GRID_EF_SIGMA = 0.08                # lognormal sigma used for Monte Carlo (assumption)

# Scope 1: kg CO2 per unit. Diesel: EPA 10.21 kg/US gal / 3.78541 L. Others approximate:
# VERIFY against IPCC 2006 / UK DESNZ before presenting.
FUEL_EF = {
    "diesel_l": 2.70,
    "petrol_l": 2.31,
    "lpg_kg": 2.98,
    "natural_gas_m3": 2.02,
}
FUEL_EF_SIGMA = 0.05

# Scope 3 spend-based: EPA USEEIO v1.3 (data/raw/useeio_v1.3.csv, kg CO2e / 2022 USD).
# These are US factors applied to Indian spend: an approximation, hence the wide sigma.
SPEND_EF_SIGMA = 0.5
USD_TO_INR = 85.0                    # ASSUMPTION: set to the rate you want to state

# Assumed annual decline of grid intensity for projections (Monte Carlo draws around this)
GRID_DECLINE_PER_YEAR = 0.025
