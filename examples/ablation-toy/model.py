"""Toy levelized cost of storage (USD/kWh-throughput) — illustrative only, numbers are not research findings."""


def model(p):
    capex = p["capex"]            # USD/kWh installed
    cycles = p["cycles"]          # full cycles over life
    rte = p["rte"]                # round-trip efficiency
    power = p["power_price"]      # USD/kWh charging energy
    om = p["om"]                  # O&M as share of capex over life
    return capex * (1 + om) / cycles + power / rte
