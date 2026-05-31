from __future__ import annotations

from api.services import ai_service, context_builder, model_policy, prompt_registry, usage_meter


async def master_chat(*, message: str, user_id: str) -> dict[str, object]:
    ai_service.ensure_runtime_layout()
    prompt = prompt_registry.load_prompt("master_prompt.md")
    model = model_policy.select_model("owner")
    conversation = ai_service.get_or_create_conversation("master", tenant_id=None, user_id=user_id)
    usage_summary = usage_meter.global_usage_summary()
    context = context_builder.build_master_context(
        message=message,
        usage=usage_summary,
        context_limit=model_policy.max_context_messages("owner"),
    )
    input_tokens = ai_service.estimate_tokens(prompt, message, context)
    ai_service.append_conversation_message(conversation["id"], "user", message, input_tokens=input_tokens)
    response_text = ai_service.render_master_response(message=message, context=context)
    output_tokens = ai_service.estimate_tokens(response_text)
    usage = usage_meter.record_master_usage(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    ai_service.append_conversation_message(conversation["id"], "assistant", response_text, output_tokens=output_tokens, cost_estimate=usage["quote"]["estimated_openai_cost_usd"])
    ai_service.log_audit(
        "master",
        "ai_chat",
        tenant_id=None,
        user_id=user_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=usage["quote"]["estimated_openai_cost_usd"],
        credits_charged=0,
        status_value="success",
    )
    return {
        "conversation_id": conversation["id"],
        "model": model,
        "response": response_text,
        "prompt_name": "master_prompt.md",
        "usage": usage["event"],
        "context": {
            "master_memory_items": len(context.get("master_memory", [])),
            "shared_learning_items": len(context.get("learning_items", [])),
        },
    }
