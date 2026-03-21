import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from uagents import Agent, Context, Model
from uagents.types import DeliveryStatus

from shared.config import load_orchestrator_settings
from shared.models import (
    AgentErrorResponse,
    FinalAssignmentResponse,
    StartAuctionRequest,
    TruckStatusRequest,
    TruckStatusResponse,
)


IntentType = Literal["start_auction_for_truck", "get_truck_status", "unknown"]

TRUCK_PATTERN = re.compile(r"\btruck[_\-\s]?(\d{1,2})\b", re.IGNORECASE)
AUCTION_KEYWORDS = {"charge", "charging", "slot", "auction", "bid", "cleanest"}
STATUS_KEYWORDS = {"status", "state", "progress", "update"}
SUSTAINABILITY_KEYWORDS = {"sustainable", "renewable", "clean", "cleanest"}


class OrchestratorChatMessage(Model):
    message: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None


class OrchestratorChatResponse(Model):
    message: str
    status: str = "ok"


@dataclass(frozen=True)
class ParsedCommand:
    intent: IntentType
    target_truck: Optional[str]
    requested_goal: Optional[str]
    original_text: str


SETTINGS = load_orchestrator_settings()

orchestrator_agent = Agent(
    name="Logistics_Orchestrator",
    seed="logistics_orchestrator_seed",
    port=8010,
    mailbox=True,
)


def parse_command(message: str) -> ParsedCommand:
    lowered = message.lower()
    truck_id = normalize_truck_id(message)
    goal = extract_goal(message)

    if truck_id and any(word in lowered for word in STATUS_KEYWORDS):
        return ParsedCommand("get_truck_status", truck_id, goal, message)

    if truck_id and any(word in lowered for word in AUCTION_KEYWORDS):
        return ParsedCommand("start_auction_for_truck", truck_id, goal, message)

    return ParsedCommand("unknown", truck_id, goal, message)


def normalize_truck_id(message: str) -> Optional[str]:
    match = TRUCK_PATTERN.search(message)
    if not match:
        return None
    return f"Truck_{int(match.group(1)):02d}"


def extract_goal(message: str) -> Optional[str]:
    lowered = message.lower()
    if any(word in lowered for word in SUSTAINABILITY_KEYWORDS):
        return "sustainable_charging"
    if any(word in lowered for word in {"fast", "urgent", "priority"}):
        return "priority_dispatch"
    if any(word in lowered for word in AUCTION_KEYWORDS):
        return "charge_slot"
    return None


def format_unknown_response(command: ParsedCommand) -> str:
    truck_hint = (
        f" I recognized {command.target_truck}, but I still need a charging or status request."
        if command.target_truck
        else ""
    )
    return (
        "I can coordinate charging requests for the Port-Power Nexus swarm."
        f"{truck_hint} Try: \"what is the status of Truck_02\" or "
        "\"find the cleanest charging slot for Truck_07\"."
    )


def format_assignment_response(
    response: FinalAssignmentResponse, requested_goal: Optional[str]
) -> str:
    goal = requested_goal or "general_dispatch"
    parts = [
        f"Truck: {response.truck_id}",
        f"Interpreted goal: {goal}",
        f"Status: {response.status}",
        f"Reasoning: {response.decision_summary}",
    ]
    if response.bay:
        parts.append(f"Assigned bay: {response.bay}")
    if response.price is not None:
        parts.append(f"Clearing price: ${response.price:.2f}")
    if response.tx_hash:
        parts.append(f"TX hash: {response.tx_hash}")
    return "\n".join(parts)


def format_truck_status_response(response: TruckStatusResponse) -> str:
    parts = [
        f"Truck: {response.truck_id}",
        f"Status: {response.truck_status}",
    ]
    if response.state_of_charge is not None:
        parts.append(f"State of charge: {response.state_of_charge}%")
    if response.distance_to_port is not None:
        parts.append(f"Distance to port: {response.distance_to_port} miles")
    if response.bay:
        parts.append(f"Assigned bay: {response.bay}")
    return "\n".join(parts)


def format_error_response(response: AgentErrorResponse) -> str:
    return (
        f"The swarm reported a failure from {response.source_agent}. "
        f"Details: {response.error_message}"
    )


def format_timeout_response(command: ParsedCommand) -> str:
    if command.intent == "start_auction_for_truck":
        return (
            f"I sent the auction request for {command.target_truck}, but the swarm did not "
            "return a final assignment before the timeout window closed."
        )
    if command.intent == "get_truck_status":
        return (
            f"I requested the latest status for {command.target_truck}, but the status agent "
            "did not answer before the timeout window closed."
        )
    return "The orchestrator timed out waiting for a downstream swarm response."


async def route_command(ctx: Context, command: ParsedCommand) -> str:
    if command.intent == "unknown" or not command.target_truck:
        return format_unknown_response(command)

    if command.intent == "get_truck_status":
        request = TruckStatusRequest(
            request_id=str(uuid4()),
            truck_id=command.target_truck,
            reply_to=ctx.agent.address,
            timestamp=datetime.utcnow(),
        )
        status = await ctx.send(
            SETTINGS.addresses.truck_status_agent,
            request,
            sync=False,
            timeout=SETTINGS.outbound_timeout_seconds,
        )
        if status.status == DeliveryStatus.FAILED:
            return (
                f"I could not reach the truck status agent for {command.target_truck}. "
                f"Details: {status.detail}."
            )
        return (
            f"I've asked the swarm for the latest status of {command.target_truck}. "
            "I will return the current charging state when the truck agent responds."
        )

    request = StartAuctionRequest(
        request_id=str(uuid4()),
        truck_id=command.target_truck,
        requested_goal=command.requested_goal,
        original_text=command.original_text,
        reply_to=ctx.agent.address,
        timestamp=datetime.utcnow(),
    )
    status = await ctx.send(
        SETTINGS.addresses.grid_agent,
        request,
        sync=False,
        timeout=SETTINGS.outbound_timeout_seconds,
    )
    if status.status == DeliveryStatus.FAILED:
        return (
            f"I could not reach the Grid Agent for {command.target_truck}. "
            f"Details: {status.detail}."
        )
    return (
        f"I've asked the Grid Agent to start an auction for {command.target_truck}. "
        "I will format the bay assignment, reasoning, and TX hash as soon as the swarm replies."
    )


@orchestrator_agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(
        f"Orchestrator started address={orchestrator_agent.address} "
        f"grid={SETTINGS.addresses.grid_agent} "
        f"terminal={SETTINGS.addresses.terminal_agent} "
        f"truck_status={SETTINGS.addresses.truck_status_agent} "
        f"amazon={SETTINGS.addresses.amazon_truck_agent} "
        f"fedex={SETTINGS.addresses.fedex_truck_agent} "
        f"ups={SETTINGS.addresses.ups_truck_agent}"
    )


@orchestrator_agent.on_message(model=OrchestratorChatMessage, replies={OrchestratorChatResponse}, allow_unverified=True)
async def handle_chat(ctx: Context, sender: str, msg: OrchestratorChatMessage):
    cleaned = " ".join(token for token in msg.message.split() if not token.startswith("@")).strip()
    if cleaned.lower() in {"hello", "hi", "ping", "test", "handshake"}:
        await ctx.send(sender, OrchestratorChatResponse(message=SETTINGS.hello_text))
        return

    command = parse_command(cleaned)
    reply = await route_command(ctx, command)
    await ctx.send(sender, OrchestratorChatResponse(message=reply))


@orchestrator_agent.on_message(model=TruckStatusResponse, allow_unverified=True)
async def handle_truck_status_response(ctx: Context, sender: str, msg: TruckStatusResponse):
    ctx.logger.info(
        f"truck_status_response sender={sender} truck={msg.truck_id} status={msg.truck_status}"
    )


@orchestrator_agent.on_message(model=FinalAssignmentResponse, allow_unverified=True)
async def handle_final_assignment(ctx: Context, sender: str, msg: FinalAssignmentResponse):
    ctx.logger.info(
        f"final_assignment sender={sender} truck={msg.truck_id} status={msg.status}"
    )


@orchestrator_agent.on_message(model=AgentErrorResponse, allow_unverified=True)
async def handle_agent_error(ctx: Context, sender: str, msg: AgentErrorResponse):
    ctx.logger.info(
        f"agent_error sender={sender} source={msg.source_agent} detail={msg.error_message}"
    )


if __name__ == "__main__":
    orchestrator_agent.run()
