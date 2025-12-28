from typing import Any, Dict, List


def _walk(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    root = plan.get("Plan", plan)
    if not isinstance(root, dict):
        return nodes

    def rec(n: Dict[str, Any]):
        nodes.append(n)
        for ch in n.get("Plans") or []:
            if isinstance(ch, dict):
                rec(ch)

    rec(root)
    return nodes


def diff_plans(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a compact diff between two plan trees.

    Returns:
        { nodes: [ { beforeOp, afterOp, costBefore, costAfter, rowsBefore, rowsAfter } ] }
    """
    b_nodes = _walk(before)
    a_nodes = _walk(after)
    n = min(len(b_nodes), len(a_nodes))
    out: List[Dict[str, Any]] = []
    for i in range(n):
        b = b_nodes[i]
        a = a_nodes[i]
        out.append(
            {
                "beforeOp": b.get("Node Type"),
                "afterOp": a.get("Node Type"),
                "costBefore": (
                    float(f"{(before.get('Plan', before).get('Total Cost', 0.0)):.3f}")
                    if i == 0
                    else None
                ),
                "costAfter": (
                    float(f"{(after.get('Plan', after).get('Total Cost', 0.0)):.3f}")
                    if i == 0
                    else None
                ),
                "rowsBefore": b.get("Plan Rows") or b.get("Actual Rows"),
                "rowsAfter": a.get("Plan Rows") or a.get("Actual Rows"),
            }
        )
    return {"nodes": out}
