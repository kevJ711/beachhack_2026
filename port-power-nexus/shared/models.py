from uagents import Model
from typing import Optional
from datetime import datetime


class GridSignal(Model):
    """Grid → Trucks: broadcast current grid conditions."""
    auction_id: str
    current_price: float      # current auction price $/kWh
    start_price: float
    min_price: float
    renewable_pct: float      # % of power from renewables
    grid_stress: float        # 0.0–1.0
    ca_iso_zone: str
    timestamp: str


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


class StartAuctionRequest(Model):
    """Orchestrator → Grid: begin an auction for a specific truck."""
    request_id: str
    truck_id: str
    requested_goal: Optional[str]
    original_text: str
    reply_to: str
    timestamp: datetime


class AuctionStarted(Model):
    """Grid → Orchestrator: confirms the auction loop has started."""
    request_id: str
    truck_id: str
    status: str
    note: str
    timestamp: datetime


class TruckStatusRequest(Model):
    """Orchestrator → Truck directory / truck agent: ask for current status."""
    request_id: str
    truck_id: str
    reply_to: str
    timestamp: datetime


class TruckStatusResponse(Model):
    """Truck / status service → Orchestrator: current truck state."""
    request_id: str
    truck_id: str
    truck_status: str
    state_of_charge: Optional[float]
    distance_to_port: Optional[float]
    bay: Optional[str]
    timestamp: datetime


class FinalAssignmentResponse(Model):
    """Grid / Terminal → Orchestrator: final result to present in ASI:One."""
    request_id: str
    truck_id: str
    status: str
    decision_summary: str
    bay: Optional[str]
    price: Optional[float]
    tx_hash: Optional[str]
    timestamp: datetime


class AgentErrorResponse(Model):
    """Any downstream agent → Orchestrator: explicit failure payload."""
    request_id: str
    source_agent: str
    error_message: str
    timestamp: datetime

