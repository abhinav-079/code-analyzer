"""
Structural and semantic metrics analyzer for the Code Quality Analyzer.

Coordinates:
- Per-function structural metrics (cyclomatic complexity, nesting depth, LOC, declarations)
- Identification of the most complex function
- Program-level aggregated metrics
- Semantic analysis & Symbol table integration
- Control Flow Graph (CFG) generation & McCabe complexity verification
- Code smell detection & refactoring recommendations
- Holistic code quality score & grading
"""

from typing import Dict, Any, List, Optional
from .semantic import SemanticAnalyzer
from .cfg import build_program_cfgs
from .code_smells import CodeSmellDetector


def _count_logical_operators(expr: Optional[Dict[str, Any]]) -> int:
    """Count &&/|| occurrences inside an expression subtree."""
    if not expr:
        return 0
    t = expr.get("type")
    if t == "BinaryExpr":
        self_count = 1 if expr.get("op") in ("&&", "||") else 0
        return self_count + _count_logical_operators(expr.get("left")) + _count_logical_operators(expr.get("right"))
    if t == "Unary":
        return _count_logical_operators(expr.get("argument"))
    if t == "Assign":
        return _count_logical_operators(expr.get("value"))
    if t == "Call":
        return sum(_count_logical_operators(a) for a in expr.get("args", []))
    if t == "Cast":
        return _count_logical_operators(expr.get("argument"))
    if t == "Sizeof":
        arg = expr.get("argument")
        return _count_logical_operators(arg) if isinstance(arg, dict) else 0
    if t == "Ternary":
        return (
            _count_logical_operators(expr.get("condition"))
            + _count_logical_operators(expr.get("consequent"))
            + _count_logical_operators(expr.get("alternate"))
        )
    return 0


def _count_ternary_complexity(expr: Optional[Dict[str, Any]]) -> int:
    """Calculates cyclomatic complexity contribution of Ternary expressions (1 per decision + logical operators in condition)."""
    if not expr or not isinstance(expr, dict):
        return 0
    t = expr.get("type")
    count = 0
    if t == "Ternary":
        count += 1 + _count_logical_operators(expr.get("condition"))
        count += _count_ternary_complexity(expr.get("condition"))
        count += _count_ternary_complexity(expr.get("consequent"))
        count += _count_ternary_complexity(expr.get("alternate"))
        return count

    for k, v in expr.items():
        if isinstance(v, dict):
            count += _count_ternary_complexity(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    count += _count_ternary_complexity(item)
    return count


def complexity_level(cyclomatic: int) -> str:
    if cyclomatic <= 4:
        return "Low"
    if cyclomatic <= 10:
        return "Moderate"
    return "High"


def _get_max_line(node: Any) -> int:
    """Finds the maximum line number referenced in a node subtree."""
    if not isinstance(node, dict):
        return 0
    max_l = node.get("line", 0)
    for v in node.values():
        if isinstance(v, dict):
            max_l = max(max_l, _get_max_line(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    max_l = max(max_l, _get_max_line(item))
    return max_l


def analyze_function(fn: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts structural metrics for a single function."""
    metrics = {
        "name": fn["name"],
        "returnType": fn.get("returnType", "void"),
        "paramCount": len(fn.get("params", [])),
        "params": fn.get("params", []),
        "variables": len(fn.get("params", [])),
        "ifs": 0,
        "fors": 0,
        "whiles": 0,
        "switches": 0,
        "returns": 0,
        "maxNesting": 0,
        "cyclomatic": 1,  # Base path = 1
        "startLine": fn.get("line", 1),
        "endLine": max(fn.get("line", 1), _get_max_line(fn.get("body", {}))),
    }
    metrics["loc"] = max(1, metrics["endLine"] - metrics["startLine"] + 1)

    depth = 0

    def visit(node):
        nonlocal depth
        if not node:
            return
        if isinstance(node, list):
            for stmt in node:
                visit(stmt)
            return
        t = node.get("type")

        if t == "Block":
            for stmt in node.get("statements", []):
                visit(stmt)

        elif t == "Declaration":
            metrics["variables"] += 1
            if node.get("init"):
                metrics["cyclomatic"] += _count_ternary_complexity(node["init"])

        elif t == "ExprStmt":
            if node.get("expr"):
                metrics["cyclomatic"] += _count_ternary_complexity(node["expr"])

        elif t == "If":
            metrics["ifs"] += 1
            metrics["cyclomatic"] += 1 + _count_logical_operators(node.get("condition")) + _count_ternary_complexity(node.get("condition"))
            depth += 1
            metrics["maxNesting"] = max(metrics["maxNesting"], depth)
            visit(node.get("consequent"))
            if node.get("alternate"):
                visit(node.get("alternate"))
            depth -= 1

        elif t == "For":
            metrics["fors"] += 1
            metrics["cyclomatic"] += 1 + _count_logical_operators(node.get("condition")) + _count_ternary_complexity(node.get("condition"))
            if node.get("init"):
                visit(node["init"])
            if node.get("update"):
                metrics["cyclomatic"] += _count_ternary_complexity(node["update"])
            depth += 1
            metrics["maxNesting"] = max(metrics["maxNesting"], depth)
            visit(node.get("body"))
            depth -= 1

        elif t == "While" or t == "DoWhile":
            metrics["whiles"] += 1
            metrics["cyclomatic"] += 1 + _count_logical_operators(node.get("condition")) + _count_ternary_complexity(node.get("condition"))
            depth += 1
            metrics["maxNesting"] = max(metrics["maxNesting"], depth)
            visit(node.get("body"))
            depth -= 1

        elif t == "Switch":
            metrics["switches"] += 1
            # In switch, each case is an alternate path (+1 per case)
            cases = node.get("cases", [])
            case_count = sum(1 for c in cases if c.get("type") == "Case")
            metrics["cyclomatic"] += case_count
            depth += 1
            metrics["maxNesting"] = max(metrics["maxNesting"], depth)
            for c in cases:
                for s in c.get("consequent", []):
                    visit(s)
            depth -= 1

        elif t == "Return":
            metrics["returns"] += 1
            if node.get("value"):
                metrics["cyclomatic"] += _count_ternary_complexity(node["value"])

    visit(fn.get("body", {}))
    metrics["complexityLevel"] = complexity_level(metrics["cyclomatic"])
    return metrics


def calculate_quality_score(
    program_metrics: Dict[str, Any],
    smells: List[Dict[str, Any]],
    diagnostics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculates overall maintainability and quality score (0 - 100)."""
    score = 100

    # Complexity penalty
    avg_cc = program_metrics.get("avgCyclomatic", 1)
    if avg_cc > 10:
        score -= min(25, int((avg_cc - 10) * 3))
    elif avg_cc > 5:
        score -= min(10, int((avg_cc - 5) * 2))

    # Nesting penalty
    max_nest = program_metrics.get("maxNesting", 0)
    if max_nest >= 3:
        score -= min(15, (max_nest - 2) * 5)

    # Diagnostic penalties
    error_count = sum(1 for d in diagnostics if d.get("severity") == "error")
    warning_count = sum(1 for d in diagnostics if d.get("severity") == "warning")
    score -= error_count * 12
    score -= warning_count * 2

    # Smell penalties by severity
    for s in smells:
        sev = s.get("severity")
        if sev == "Critical":
            score -= 10
        elif sev == "High":
            score -= 6
        elif sev == "Medium":
            score -= 3
        elif sev == "Low":
            score -= 1

    score = max(0, min(100, score))

    if score >= 90:
        grade = "A"
        grade_desc = "Excellent: Clean, modular, well-structured code."
    elif score >= 80:
        grade = "B"
        grade_desc = "Good: Minor refactoring opportunities or mild complexity."
    elif score >= 65:
        grade = "C"
        grade_desc = "Moderate: Code has noticeable nesting, complexity, or smells."
    elif score >= 50:
        grade = "D"
        grade_desc = "Poor: Significant structural issues and refactoring needed."
    else:
        grade = "F"
        grade_desc = "Critical: High complexity, errors, and severe maintainability smells."

    return {
        "score": score,
        "grade": grade,
        "description": grade_desc,
    }


def analyze(ast: Dict[str, Any], loc: int) -> Dict[str, Any]:
    """
    Performs complete end-to-end analysis on the parsed AST:
    - Per-function metrics and most complex function detection
    - Program aggregate metrics
    - Semantic analysis & Symbol table
    - Control Flow Graphs for all functions
    - Code smell detection & refactoring recommendations
    - Overall quality score
    """
    # 1. Per-function metrics
    functions_metrics: List[Dict[str, Any]] = []
    max_cc = -1
    most_complex_fn_name = ""

    for fn in ast.get("functions", []):
        f_m = analyze_function(fn)
        functions_metrics.append(f_m)
        if f_m["cyclomatic"] > max_cc:
            max_cc = f_m["cyclomatic"]
            most_complex_fn_name = f_m["name"]

    # Mark the most complex function
    for f_m in functions_metrics:
        f_m["isMostComplex"] = (f_m["name"] == most_complex_fn_name and max_cc > 1)

    # 2. Program-level aggregation
    total_funcs = len(functions_metrics)
    total_vars = sum(f["variables"] for f in functions_metrics) + len(ast.get("globals", []))
    total_ifs = sum(f["ifs"] for f in functions_metrics)
    total_fors = sum(f["fors"] for f in functions_metrics)
    total_whiles = sum(f["whiles"] for f in functions_metrics)
    total_switches = sum(f["switches"] for f in functions_metrics)
    total_returns = sum(f["returns"] for f in functions_metrics)
    max_nesting = max((f["maxNesting"] for f in functions_metrics), default=0)
    total_cyclomatic = sum(f["cyclomatic"] for f in functions_metrics)
    avg_cyclomatic = round(total_cyclomatic / total_funcs, 1) if total_funcs > 0 else 0

    program_metrics = {
        "functions": total_funcs,
        "variables": total_vars,
        "ifs": total_ifs,
        "fors": total_fors,
        "whiles": total_whiles,
        "switches": total_switches,
        "returns": total_returns,
        "maxNesting": max_nesting,
        "cyclomatic": total_cyclomatic,
        "avgCyclomatic": avg_cyclomatic,
        "complexityLevel": complexity_level(total_cyclomatic),
        "loc": loc,
        "mostComplexFunction": most_complex_fn_name,
        "maxFunctionComplexity": max_cc if max_cc >= 0 else 0,
    }

    # 3. Semantic Analysis & Symbol Table
    semantic_analyzer = SemanticAnalyzer(ast)
    semantic_result = semantic_analyzer.analyze()

    # 4. Control Flow Graph (CFG) generation
    cfgs = build_program_cfgs(ast)

    # 5. Code Smell Detection & Automated Refactoring
    detector = CodeSmellDetector(
        ast=ast,
        function_metrics=functions_metrics,
        symbol_table_data=semantic_result["symbolTable"],
        diagnostics=semantic_result["diagnostics"],
    )
    smells = detector.detect()

    # 6. Overall Quality Score
    quality = calculate_quality_score(program_metrics, smells, semantic_result["diagnostics"])

    return {
        **program_metrics,
        "program": program_metrics,
        "perFunction": functions_metrics,
        "functionList": functions_metrics,
        "symbolTable": semantic_result["symbolTable"],
        "diagnostics": semantic_result["diagnostics"],
        "cfgs": cfgs,
        "codeSmells": smells,
        "quality": quality,
    }
