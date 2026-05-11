import asyncio
import json
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter
from openai import APIConnectionError, APITimeoutError, RateLimitError, InternalServerError

from app.agent.context import SessionCtx
from app.agent.system_prompt import build_system_prompt
from app.agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS
from app.config import settings
from app.llm.kimi_client import get_client
from app.logging_setup import get_logger
from app.pipeline.events import publish

log = get_logger(__name__)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=2, max=30),
    retry=retry_if_exception_type(
        (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
    ),
    reraise=True,
)
def _chat(messages: list[dict]) -> Any:
    client = get_client()
    return client.chat.completions.create(
        model=settings.openai_model_name,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="required",
        temperature=0.5,
        max_completion_tokens=settings.max_completion_tokens,
        reasoning_effort="high",
    )


def _serialize_assistant_message(msg) -> dict:
    """Persistable form for the messages list (chat completions API shape)."""
    out: dict[str, Any] = {"role": "assistant"}
    if msg.content:
        out["content"] = msg.content
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return out


def _initial_user_message(transcript: dict, direction: str | None, source_duration: float) -> str:
    return json.dumps({
        "source_duration_sec": round(source_duration, 2),
        "user_direction": direction or None,
        "transcript": {
            "text": transcript.get("text", ""),
            "words": transcript.get("words", []),
        },
    }, ensure_ascii=False)


async def _run_tool(ctx: SessionCtx, name: str, arguments: dict) -> dict:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(ctx, **arguments)
    except TypeError as e:
        return {"error": "bad arguments", "detail": str(e)}
    except Exception as e:
        log.exception("tool %s failed", name)
        return {"error": str(e), "type": type(e).__name__}


async def run_agent_loop(ctx: SessionCtx, transcript: dict) -> dict:
    """Run the orchestrator until it calls finalize_reel or hits MAX_AGENT_TURNS.

    Returns dict with at least {"ok": bool, "plan_path": str | None}.
    """
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": _initial_user_message(transcript, ctx.direction, ctx.source_duration_sec)},
    ]
    publish(ctx.session_id, "agent.started", {"max_turns": settings.max_agent_turns})

    finalized = False
    final_plan_path: str | None = None

    for turn_idx in range(settings.max_agent_turns):
        publish(ctx.session_id, "agent.turn", {"turn": turn_idx})

        try:
            resp = await asyncio.to_thread(_chat, messages)
        except Exception as e:
            publish(ctx.session_id, "agent.error", {"error": str(e), "type": type(e).__name__})
            raise

        msg = resp.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning:
            publish(ctx.session_id, "agent.thinking", {"turn": turn_idx, "content": reasoning})
        if msg.content:
            publish(ctx.session_id, "agent.message", {"turn": turn_idx, "content": msg.content})

        messages.append(_serialize_assistant_message(msg))

        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            publish(ctx.session_id, "agent.no_tool_call", {"turn": turn_idx})
            messages.append({
                "role": "user",
                "content": "You must either call a tool or call finalize_reel(plan) to end. Continue.",
            })
            continue

        # Parse + run all tool calls in parallel
        parsed: list[tuple[str, str, dict]] = []  # (call_id, name, args)
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            parsed.append((tc.id, tc.function.name, args))
            publish(ctx.session_id, "agent.tool_call", {
                "turn": turn_idx, "call_id": tc.id, "name": tc.function.name,
                "arguments": args,
            })

        tasks = [_run_tool(ctx, name, args) for _, name, args in parsed]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for (call_id, name, args), result in zip(parsed, results):
            publish(ctx.session_id, "agent.tool_result", {
                "turn": turn_idx, "call_id": call_id, "name": name,
                "result": result,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result),
            })
            if name == "finalize_reel" and isinstance(result, dict) and result.get("ok"):
                finalized = True
                final_plan_path = result.get("plan_path")

        if finalized:
            publish(ctx.session_id, "agent.final", {"plan_path": final_plan_path})
            break

    if not finalized:
        publish(ctx.session_id, "agent.exhausted", {"turns": settings.max_agent_turns})
        raise RuntimeError(
            f"agent did not finalize within {settings.max_agent_turns} turns"
        )

    return {"ok": True, "plan_path": final_plan_path}
