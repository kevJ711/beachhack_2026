from uagents import Model
from typing import Optional
from datetime import datetime


class GridSignal(Model):
    """Grid → Trucks: broadcast current grid conditions."""
    price: float              # current auction price $/kWh
    grid_stress: str          # "low", "medium", "high"
    renewable_pct: float      # % of power from renewables
    timestamp: datetime


class PowerBid(Model):
    """Truck → Terminal: a bid to charge."""
    truck_id: str
    battery_level: float      # current battery level 0.0–100.0
    requested_kwh: float
    bid_price: float          # $/kWh the truck offers
    reasoning: str            # LLM explanation string
    timestamp: datetime


class BidResponse(Model):
    """Terminal → Truck: outcome of the bid."""
    accepted: bool
    bay: Optional[str]
    price_confirmed: float
    queue_position: int
