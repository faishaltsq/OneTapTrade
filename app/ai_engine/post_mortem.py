import json
from typing import Optional

from app.config import settings
from app.logger import logger


def run_post_mortem(trade: dict, ai_decision_data: dict = None) -> dict | None:
    if not settings.deepseek_api_key:
        logger.warning("DeepSeek API key not configured — skip post-mortem")
        return None

    from openai import OpenAI

    client = OpenAI(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        timeout=30,
    )

    symbol = trade.get("symbol", "UNKNOWN")
    side = trade.get("side", "?")
    entry_price = trade.get("entry_price")
    sl = trade.get("stop_loss")
    tp = trade.get("take_profit")
    close_price = trade.get("close_price")
    profit = trade.get("profit", 0)

    pnl_r = None
    if entry_price and sl and profit is not None:
        try:
            risk = abs(float(entry_price) - float(sl))
            if risk > 0:
                pnl_r = float(profit) / risk
        except (ValueError, TypeError):
            pass

    structure_snapshot = {}
    ai_reasoning = ""
    ai_score = None
    if ai_decision_data:
        structure_snapshot = ai_decision_data.get("input_json", {}).get("smc", {})
        output = ai_decision_data.get("output_json", {})
        ai_reasoning = output.get("main_reason", "")
        ai_score = output.get("confidence")

    prompt = f"""Kamu adalah analis SMC senior yang bertugas melakukan post-mortem terhadap signal trading yang gagal (loss).

Definisi SMC:
- BOS: close menembus swing high/low searah trend, konfirmasi kontinuasi.
- CHoCH: close menembus swing high/low berlawanan trend, indikasi reversal struktur.
- Order Block: candle/zona terakhir sebelum pergerakan impulsif penyebab BOS/CHoCH.
- FVG: gap antara candle 1 dan 3 akibat pergerakan impulsif candle 2.
- Liquidity Sweep: stop hunt di swing high/low diikuti rejection cepat.

Data setup trading yang menghasilkan LOSS:

### Kondisi struktur SMC saat entry:
{json.dumps(structure_snapshot, indent=2)[:1000]}

### Reasoning AI saat memberi sinyal:
{ai_reasoning}

### Skor confluence AI:
{ai_score}

### Hasil aktual:
- Outcome: LOSS
- PnL: {pnl_r}R
- Entry: {entry_price}
- SL: {sl}
- TP: {tp}
- Close: {close_price}

Tugas: Analisa kegagalan dan berikan diagnosis.

Output HARUS JSON valid saja:
{{
  "primary_failure_element": "elemen struktural utama penyebab kegagalan",
  "failure_reason": "diagnosis 1-2 kalimat kenapa elemen tersebut menyebabkan kegagalan",
  "secondary_factors": ["elemen tambahan, kosongkan jika tidak ada"],
  "actionable_rule": "satu kalimat aturan konkret untuk mencegah pola serupa",
  "confidence": "high/medium/low",
  "confidence_note": "alasan tingkat confidence"
}}"""

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        raw = response.choices[0].message.content or ""
        from app.ai_engine.decision_parser import extract_json_from_response
        result = extract_json_from_response(raw)
        logger.info(f"Post-mortem done for {symbol}: {result.get('primary_failure_element', 'N/A')}")
        return result
    except Exception as e:
        logger.error(f"Post-mortem failed for {symbol}: {e}")
        return None


def process_loss_trade(trade: dict) -> None:
    trade_id = trade.get("id")
    ai_decision_id = trade.get("ai_decision_id")
    symbol = trade.get("symbol", "UNKNOWN")

    if not trade_id:
        return

    if trade.get("post_mortem_done"):
        logger.debug(f"Post-mortem already done for trade {trade_id}")
        return

    ai_decision_data = None
    if ai_decision_id:
        try:
            from app.database.repositories import get_failure_cases
            supabase = None
            from app.database.supabase_client import get_supabase
            supabase = get_supabase()
            if supabase:
                result = supabase.table("ai_decisions").select("*").eq("id", ai_decision_id).limit(1).execute()
                if result.data:
                    ai_decision_data = result.data[0]
        except Exception:
            pass

    diagnosis = run_post_mortem(trade, ai_decision_data)

    if diagnosis:
        try:
            from app.database.repositories import save_failure_case, mark_trade_post_mortem

            save_failure_case({
                "trade_id": trade_id,
                "ai_decision_id": ai_decision_id,
                "symbol": symbol,
                "side": trade.get("side"),
                "entry_price": trade.get("entry_price"),
                "stop_loss": trade.get("stop_loss"),
                "take_profit": trade.get("take_profit"),
                "close_price": trade.get("close_price"),
                "pnl_r": diagnosis.get("pnl_r"),
                "structure_snapshot": ai_decision_data.get("input_json", {}).get("smc", {}) if ai_decision_data else {},
                "ai_reasoning": diagnosis.get("main_reason", ""),
                "ai_confluence_score": ai_decision_data.get("output_json", {}).get("confidence") if ai_decision_data else None,
                "primary_failure_element": diagnosis.get("primary_failure_element", ""),
                "failure_reason": diagnosis.get("failure_reason", ""),
                "secondary_factors": diagnosis.get("secondary_factors", []),
                "actionable_rule": diagnosis.get("actionable_rule", ""),
                "confidence": diagnosis.get("confidence", "medium"),
                "confidence_note": diagnosis.get("confidence_note", ""),
            })

            mark_trade_post_mortem(trade_id, failure_reason=diagnosis.get("failure_reason", ""))
            logger.info(f"Failure case saved for {symbol} trade {trade_id}")
        except Exception as e:
            logger.error(f"Failed to save failure case: {e}")
