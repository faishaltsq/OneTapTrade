from typing import Any, Optional


def format_tv_context(chart: Optional[dict], studies: Optional[list], lines: Optional[list],
                      labels: Optional[list], tables: Optional[list], boxes: Optional[list],
                      symbol: str) -> dict:
    result: dict[str, Any] = {
        "tv_available": False,
        "tv_chart_context": {},
    }

    if chart is None:
        return result

    result["tv_available"] = True

    ctx: dict[str, Any] = {
        "symbol": chart.get("symbol", symbol),
        "timeframe": chart.get("timeframe", ""),
        "visible_indicators": [
            {"name": ind.get("name", ""), "id": ind.get("id", "")}
            for ind in (chart.get("indicators") or [])
        ],
    }

    if studies:
        ctx["indicators_values"] = [
            {"name": s.get("name", ""), "values": s.get("values", {})}
            for s in studies if isinstance(s, dict)
        ]

    if lines:
        all_price_lines = [l for l in lines if isinstance(l, dict) and l.get("price", 0) > 0]
        ctx["pine_levels"] = {
            "support": sorted(
                [l["price"] for l in all_price_lines if "support" in (l.get("text") or "").lower()],
                reverse=True,
            )[:5],
            "resistance": sorted(
                [l["price"] for l in all_price_lines if "resistance" in (l.get("text") or "").lower()],
            )[:5],
            "all_levels": [
                {"price": l["price"], "text": l.get("text", "")}
                for l in all_price_lines[:10]
            ],
        }

    if labels:
        ctx["pine_annotations"] = [
            {"text": lbl.get("text", ""), "price": lbl.get("price")}
            for lbl in labels if isinstance(lbl, dict)
        ][:20]

    if boxes:
        ctx["price_zones"] = [
            {"high": b.get("high", 0), "low": b.get("low", 0)}
            for b in boxes if isinstance(b, dict)
        ][:10]

    if tables:
        ctx["data_tables"] = [
            {"name": t.get("name", ""), "rows_count": len(t.get("rows") or [])}
            for t in tables if isinstance(t, dict)
        ][:5]

    result["tv_chart_context"] = ctx
    return result
