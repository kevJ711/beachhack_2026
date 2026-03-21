import os
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel
from uagents import Agent, Context, Protocol
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


protocol = Protocol(spec=chat_protocol_spec)

IntentType = Literal["start_auction_for_truck", "get_truck_status", "unknown"]

GRID_AGENT_ADDRESS = os.getenv("GRID_AGENT_ADDRESS", "agent://grid")
TERMINAL_AGENT_ADDRESS = os.getenv(
    "TERMINAL_AGENT_ADDRESS",
    "agent1q2dsyxc0g3482s3cewzss6vf4gakd2r8znask0gpmqrnvm0p5n0fy9gsulk",
)
TRUCK_STATUS_AGENT_ADDRESS = os.getenv("TRUCK_STATUS_AGENT_ADDRESS", "agent://truck-status")
AMAZON_TRUCK_AGENT_ADDRESS = os.getenv(
    "AMAZON_TRUCK_AGENT_ADDRESS",
    "agent1qt64xcals30mgjk0vgjykjen7j6wq0m3mp4ny0k5ymnpkaeadmxtqz3hp36",
)
FEDEX_TRUCK_AGENT_ADDRESS = os.getenv(
    "FEDEX_TRUCK_AGENT_ADDRESS",
    "agent1q0n4pnt8c25efcfzj3v9fwxp6fqw6lmn0yy279czrsem9hzvftgz7n4nmsq",
)
UPS_TRUCK_AGENT_ADDRESS = os.getenv(
    "UPS_TRUCK_AGENT_ADDRESS",
    "agent1qtelk9cdqsacsyz6re8edxugphks6z6cgaynn0q5w87m9h3x0zrqxxyslsx",
)


class ParsedCommand(BaseModel):
    intent: IntentType
    target_truck: Optional[str] = None
    requested_goal: Optional[str] = None
    original_text: str


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
    lowered = message.lower()
    marker = "truck"
    index = lowered.find(marker)
    if index == -1:
        return None
    suffix = lowered[index + len(marker) :]
    digits = []
    for char in suffix:
        if char.isdigit():
            digits.append(char)
        elif digits:
            break
    if not digits:
        return None
    return f"Truck_{int(''.join(digits)):02d}"


def extract_goal(message: str) -> Optional[str]:
    lowered = message.lower()
    if any(word in lowered for word in ["sustainable", "renewable", "clean", "cleanest"]):
        return "sustainable_charging"
    if any(word in lowered for word in ["fast", "urgent", "priority"]):
        return "priority_dispatch"
    if any(word in lowered for word in ["charge", "charging", "slot", "auction", "bid"]):
        return "charge_slot"
    return None


def parse_command(message: str) -> ParsedCommand:
    lowered = message.lower()
    truck_id = normalize_truck_id(message)
    goal = extract_goal(message)

    if truck_id and any(word in lowered for word in ["status", "state", "progress", "update"]):
        return ParsedCommand(
            intent="get_truck_status",
            target_truck=truck_id,
            requested_goal=goal,
            original_text=message,
        )

    if truck_id and any(
        word in lowered for word in ["charge", "charging", "slot", "auction", "bid", "cleanest"]
    ):
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


def process_user_message(text: str) -> str:
    cleaned_text = strip_agent_mentions(text)

    if is_handshake(cleaned_text):
        return "Hello from Port-Power Nexus"

    command = parse_command(cleaned_text)
    if command.intent == "unknown" or not command.target_truck:
        return format_unknown_response(command)

    if command.intent == "get_truck_status":
        return (
            f"I've prepared a truck-status request for {command.target_truck}. "
            f"Once the status agent is live at {TRUCK_STATUS_AGENT_ADDRESS}, "
            "I will return the current charging state."
        )

    return (
        f"I've prepared an auction request for {command.target_truck}. "
        f"Once the Grid Agent is live at {GRID_AGENT_ADDRESS}, I will coordinate with "
        f"Terminal at {TERMINAL_AGENT_ADDRESS} and the truck swarm "
        f"({AMAZON_TRUCK_AGENT_ADDRESS}, {FEDEX_TRUCK_AGENT_ADDRESS}, {UPS_TRUCK_AGENT_ADDRESS}) "
        "to return the reasoning, assigned bay, and TX hash."
    )


@protocol.on_message(ChatMessage)
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

    reply = process_user_message(text)
    await ctx.send(sender, create_text_chat(reply))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(
        f"ack_received sender={sender} msg_id={msg.acknowledged_msg_id}"
    )


agent.include(protocol, publish_manifest=True)
