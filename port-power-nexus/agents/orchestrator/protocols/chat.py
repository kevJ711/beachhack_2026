import os
import re
import time
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel
from uagents import Agent, Context, Model, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)


try:
    agent
except NameError:
    agent = Agent(name="Logistics_Orchestrator", store_message_history=True)


chat_protocol = Protocol(spec=chat_protocol_spec)
swarm_protocol = Protocol(name="port_power_swarm", version="0.1.0")

IntentType = Literal["start_auction_for_truck", "get_truck_status", "unknown"]
PENDING_INDEX_KEY = "pending_request_ids"

GRID_AGENT_ADDRESS = os.getenv(
    "GRID_AGENT_ADDRESS",
    "agent1qdrkj8c6caq7tdmk04r3277ekaukfg7ztxncx0alpddflgz995k4xun8nut",
)
TERMINAL_AGENT_ADDRESS = os.getenv(
    "TERMINAL_AGENT_ADDRESS",
    "agent1q2dsyxc0g3482s3cewzss6vf4gakd2r8znask0gpmqrnvm0p5n0fy9gsulk",
)
TRUCK_STATUS_AGENT_ADDRESS = os.getenv("TRUCK_STATUS_AGENT_ADDRESS", "agent://truck-status")
ORCHESTRATOR_HELLO_TEXT = os.getenv(
    "ORCHESTRATOR_HELLO_TEXT", "Hello from Port-Power Nexus"
)
ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS = int(
    os.getenv("ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS", "20")
)

TRUCK_PATTERN = re.compile(r"\btruck[_\-\s]?(\d{1,2})\b", re.IGNORECASE)
AUCTION_KEYWORDS = {"charge", "charging", "slot", "auction", "bid", "cleanest"}
STATUS_KEYWORDS = {"status", "state", "progress", "update"}
SUSTAINABILITY_KEYWORDS = {"sustainable", "renewable", "clean", "cleanest"}


class ParsedCommand(BaseModel):
    intent: IntentType
    target_truck: Optional[str] = None
    requested_goal: Optional[str] = None
    original_text: str


class StartAuctionRequest(Model):
    request_id: str
    truck_id: str
    requested_goal: Optional[str]
    original_text: str
    reply_to: str
    timestamp: datetime


class AuctionStarted(Model):
    request_id: str
    truck_id: str
    status: str
    note: str
    timestamp: datetime


class TruckStatusRequest(Model):
    request_id: str
    truck_id: str
    reply_to: str
    timestamp: datetime


class TruckStatusResponse(Model):
    request_id: str
    truck_id: str
    truck_status: str
    state_of_charge: Optional[float]
    distance_to_port: Optional[float]
    bay: Optional[str]
    timestamp: datetime


class FinalAssignmentResponse(Model):
    request_id: str
    truck_id: str
    status: str
    decision_summary: str
    bay: Optional[str]
    price: Optional[float]
    tx_hash: Optional[str]
    timestamp: datetime


class AgentErrorResponse(Model):
    request_id: str
    source_agent: str
    error_message: str
    timestamp: datetime


def extract_text(msg: ChatMessage) -> str:
    chunks = []
    for item in msg.content:
        if isinstance(item, TextContent):
            chunks.append(item.text)
        elif isinstance(item, EndSessionContent):
            return ""
    return " ".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def strip_agent_mentions(text: str) -> str:
    return " ".join(token for token in text.split() if not token.startswith("@")).strip()


def create_text_chat(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


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


def parse_command(message: str) -> ParsedCommand:
    lowered = message.lower()
    truck_id = normalize_truck_id(message)
    goal = extract_goal(message)

    if truck_id and any(word in lowered for word in STATUS_KEYWORDS):
        return ParsedCommand(
            intent="get_truck_status",
            target_truck=truck_id,
            requested_goal=goal,
            original_text=message,
        )

    if truck_id and any(word in lowered for word in AUCTION_KEYWORDS):
        return ParsedCommand(
            intent="start_auction_for_truck",
            target_truck=truck_id,
            requested_goal=goal,
            original_text=message,
        )

    return ParsedCommand(
        intent="unknown",
        target_truck=truck_id,
        requested_goal=goal,
        original_text=message,
    )


def is_handshake(message: str) -> bool:
    return message.strip().lower() in {"hello", "hi", "ping", "test", "handshake"}


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
            f"The auction request for {command.target_truck} was dispatched, but the Grid Agent "
            "did not return a final assignment before the timeout window closed."
        )
    if command.intent == "get_truck_status":
        return (
            f"The status request for {command.target_truck} was dispatched, but the truck status "
            "agent did not answer before the timeout window closed."
        )
    return "The orchestrator timed out waiting for a downstream swarm response."


def is_failed_delivery(status: object) -> bool:
    delivery_status = getattr(status, "status", None)
    if delivery_status is None:
        return True
    return str(delivery_status).lower().endswith("failed")


def _pending_key(request_id: str) -> str:
    return f"pending_request:{request_id}"


def save_pending_request(ctx: Context, request_id: str, sender: str, command: ParsedCommand) -> None:
    pending = {
        "request_id": request_id,
        "sender": sender,
        "intent": command.intent,
        "target_truck": command.target_truck,
        "requested_goal": command.requested_goal,
        "original_text": command.original_text,
        "created_at": time.time(),
        "expires_at": time.time() + ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS,
        "stage": "dispatched",
    }
    ctx.storage.set(_pending_key(request_id), pending)
    pending_ids = ctx.storage.get(PENDING_INDEX_KEY) or []
    if request_id not in pending_ids:
        pending_ids.append(request_id)
        ctx.storage.set(PENDING_INDEX_KEY, pending_ids)


def get_pending_request(ctx: Context, request_id: str) -> Optional[dict]:
    return ctx.storage.get(_pending_key(request_id))


def update_pending_stage(ctx: Context, request_id: str, stage: str) -> None:
    pending = get_pending_request(ctx, request_id)
    if not pending:
        return
    pending["stage"] = stage
    ctx.storage.set(_pending_key(request_id), pending)


def remove_pending_request(ctx: Context, request_id: str) -> None:
    ctx.storage.remove(_pending_key(request_id))
    pending_ids = ctx.storage.get(PENDING_INDEX_KEY) or []
    if request_id in pending_ids:
        pending_ids.remove(request_id)
        ctx.storage.set(PENDING_INDEX_KEY, pending_ids)


def parsed_command_from_pending(pending: dict) -> ParsedCommand:
    return ParsedCommand(
        intent=pending["intent"],
        target_truck=pending.get("target_truck"),
        requested_goal=pending.get("requested_goal"),
        original_text=pending.get("original_text", ""),
    )


async def route_command(ctx: Context, sender: str, command: ParsedCommand) -> str:
    if command.intent == "unknown" or not command.target_truck:
        return format_unknown_response(command)

    if command.intent == "get_truck_status":
        request_id = str(uuid4())
        request = TruckStatusRequest(
            request_id=request_id,
            truck_id=command.target_truck,
            reply_to=ctx.agent.address,
            timestamp=datetime.utcnow(),
        )
        status = await ctx.send(
            TRUCK_STATUS_AGENT_ADDRESS,
            request,
            timeout=ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS,
        )
        if is_failed_delivery(status):
            return (
                f"I could not reach the truck status agent for {command.target_truck}. "
                f"Details: {status.detail}."
            )
        save_pending_request(ctx, request_id, sender, command)
        return (
            f"I've dispatched a truck status request for {command.target_truck}. "
            "I will return the latest charging state as soon as the swarm responds."
        )

    request_id = str(uuid4())
    request = StartAuctionRequest(
        request_id=request_id,
        truck_id=command.target_truck,
        requested_goal=command.requested_goal,
        original_text=command.original_text,
        reply_to=ctx.agent.address,
        timestamp=datetime.utcnow(),
    )
    status = await ctx.send(
        GRID_AGENT_ADDRESS,
        request,
        timeout=ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS,
    )
    if is_failed_delivery(status):
        return (
            f"I could not reach the Grid Agent for {command.target_truck}. "
            f"Details: {status.detail}."
        )
    save_pending_request(ctx, request_id, sender, command)
    return (
        f"I've dispatched an auction request for {command.target_truck}. "
        "I will return the reasoning, assigned bay, and TX hash as soon as the swarm responds."
    )


@chat_protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.utcnow(),
            acknowledged_msg_id=msg.msg_id,
        ),
    )

    text = extract_text(msg)
    if not text:
        await ctx.send(sender, create_text_chat("Session closed."))
        return

    cleaned_text = strip_agent_mentions(text)
    command = parse_command(cleaned_text)
    ctx.logger.info(
        "hosted_chat_received "
        f"sender={sender} "
        f"text={text!r} "
        f"cleaned_text={cleaned_text!r} "
        f"intent={command.intent} "
        f"truck={command.target_truck} "
        f"goal={command.requested_goal}"
    )

    if is_handshake(cleaned_text):
        await ctx.send(sender, create_text_chat(ORCHESTRATOR_HELLO_TEXT))
        return

    reply = await route_command(ctx, sender, command)
    await ctx.send(sender, create_text_chat(reply))


@swarm_protocol.on_message(AuctionStarted)
async def handle_auction_started(ctx: Context, sender: str, msg: AuctionStarted):
    pending = get_pending_request(ctx, msg.request_id)
    ctx.logger.info(
        f"auction_started sender={sender} truck={msg.truck_id} status={msg.status}"
    )
    if not pending:
        return
    update_pending_stage(ctx, msg.request_id, "auction_started")
    await ctx.send(
        pending["sender"],
        create_text_chat(f"Auction started for {msg.truck_id}. {msg.note}"),
    )


@swarm_protocol.on_message(TruckStatusResponse)
async def handle_truck_status_response(ctx: Context, sender: str, msg: TruckStatusResponse):
    pending = get_pending_request(ctx, msg.request_id)
    ctx.logger.info(
        f"truck_status_response sender={sender} truck={msg.truck_id} status={msg.truck_status}"
    )
    if not pending:
        return
    await ctx.send(pending["sender"], create_text_chat(format_truck_status_response(msg)))
    remove_pending_request(ctx, msg.request_id)


@swarm_protocol.on_message(FinalAssignmentResponse)
async def handle_final_assignment(ctx: Context, sender: str, msg: FinalAssignmentResponse):
    pending = get_pending_request(ctx, msg.request_id)
    ctx.logger.info(
        f"final_assignment sender={sender} truck={msg.truck_id} status={msg.status}"
    )
    if not pending:
        return
    command = parsed_command_from_pending(pending)
    await ctx.send(
        pending["sender"],
        create_text_chat(format_assignment_response(msg, command.requested_goal)),
    )
    remove_pending_request(ctx, msg.request_id)


@swarm_protocol.on_message(AgentErrorResponse)
async def handle_agent_error(ctx: Context, sender: str, msg: AgentErrorResponse):
    pending = get_pending_request(ctx, msg.request_id)
    ctx.logger.info(
        f"agent_error sender={sender} source={msg.source_agent} detail={msg.error_message}"
    )
    if not pending:
        return
    await ctx.send(pending["sender"], create_text_chat(format_error_response(msg)))
    remove_pending_request(ctx, msg.request_id)


@chat_protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"ack_received sender={sender} msg_id={msg.acknowledged_msg_id}")


@swarm_protocol.on_interval(period=5.0)
async def timeout_pending_requests(ctx: Context):
    pending_ids = list(ctx.storage.get(PENDING_INDEX_KEY) or [])
    now = time.time()
    for request_id in pending_ids:
        pending = get_pending_request(ctx, request_id)
        if not pending:
            remove_pending_request(ctx, request_id)
            continue
        if pending.get("expires_at", now + 1) > now:
            continue
        command = parsed_command_from_pending(pending)
        await ctx.send(
            pending["sender"],
            create_text_chat(format_timeout_response(command)),
        )
        remove_pending_request(ctx, request_id)


agent.include(chat_protocol, publish_manifest=True)
agent.include(swarm_protocol, publish_manifest=True)
