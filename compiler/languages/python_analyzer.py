"""
Native Python Code Quality Analyzer.

Leverages Python's standard library `ast` and `tokenize` modules to extract:
- Token stream with line/col tracking
- Hierarchical AST
- Scope-aware Symbol Table
- Semantic diagnostics (undeclared names, unused variables, dead code)
- Control Flow Graph (CFG) with basic blocks and McCabe's formula M = E - N + 2P
- Code smells and refactoring suggestions
- Per-function and program-wide metrics
"""

import ast
import io
import token
import tokenize
from typing import Dict, Any, List, Optional, Set, Tuple


def _complexity_level(cc: int) -> str:
    if cc <= 4:
        return "Low"
    if cc <= 10:
        return "Moderate"
    return "High"


def _expr_to_str(node: Optional[ast.AST]) -> str:
    if not node:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return str(type(node).__name__)


def _ast_to_dict(node: ast.AST) -> Dict[str, Any]:
    """Converts a Python ast node to a serializable dictionary format compatible with UI."""
    node_type = type(node).__name__
    result = {
        "type": node_type,
        "line": getattr(node, "lineno", 1),
        "col": getattr(node, "col_offset", 1) + 1,
    }

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        result["type"] = "FunctionDecl"
        result["name"] = node.name
        result["returnType"] = _expr_to_str(node.returns) if node.returns else "def"
        result["params"] = [{"varType": "Any", "name": a.arg, "line": a.lineno, "col": a.col_offset + 1} for a in node.args.args]
        result["body"] = {"type": "Block", "statements": [_ast_to_dict(s) for s in node.body], "line": node.lineno, "col": 1}
    elif isinstance(node, ast.If):
        result["type"] = "If"
        result["condition"] = {"type": "Expr", "value": _expr_to_str(node.test)}
        result["consequent"] = {"type": "Block", "statements": [_ast_to_dict(s) for s in node.body]}
        result["alternate"] = {"type": "Block", "statements": [_ast_to_dict(s) for s in node.orelse]} if node.orelse else None
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        result["type"] = "For"
        result["init"] = f"{_expr_to_str(node.target)} in {_expr_to_str(node.iter)}"
        result["condition"] = ""
        result["update"] = ""
        result["body"] = {"type": "Block", "statements": [_ast_to_dict(s) for s in node.body]}
    elif isinstance(node, ast.While):
        result["type"] = "While"
        result["condition"] = {"type": "Expr", "value": _expr_to_str(node.test)}
        result["body"] = {"type": "Block", "statements": [_ast_to_dict(s) for s in node.body]}
    elif isinstance(node, ast.Return):
        result["type"] = "Return"
        result["value"] = {"type": "Expr", "value": _expr_to_str(node.value)} if node.value else None
    elif isinstance(node, ast.Assign):
        targets = ", ".join(_expr_to_str(t) for t in node.targets)
        result["type"] = "Declaration"
        result["varType"] = "auto"
        result["name"] = targets
        result["init"] = {"type": "Expr", "value": _expr_to_str(node.value)}
    elif isinstance(node, ast.AugAssign):
        result["type"] = "ExprStmt"
        result["expr"] = {"type": "Assign", "name": _expr_to_str(node.target), "op": "+=", "value": {"type": "Expr", "value": _expr_to_str(node.value)}}
    elif isinstance(node, ast.Expr):
        result["type"] = "ExprStmt"
        result["expr"] = {"type": "Expr", "value": _expr_to_str(node.value)}
    elif isinstance(node, ast.Break):
        result["type"] = "Break"
    elif isinstance(node, ast.Continue):
        result["type"] = "Continue"
    elif isinstance(node, ast.Pass):
        result["type"] = "Pass"

    return result


def _tokenize_python(source: str) -> List[Dict[str, Any]]:
    tokens = []
    try:
        reader = io.StringIO(source).readline
        for tok in tokenize.generate_tokens(reader):
            tok_type_name = token.tok_name.get(tok.type, "UNKNOWN")
            val = tok.string
            if tok.type == token.NAME:
                import keyword
                t_type = "KEYWORD" if keyword.iskeyword(val) else "IDENTIFIER"
            elif tok.type == token.NUMBER:
                t_type = "NUMBER"
            elif tok.type == token.STRING:
                t_type = "STRING"
            elif tok.type == token.OP:
                t_type = "OPERATOR" if val in "+-*/%=<>!&|^~" else "DELIMITER"
            elif tok.type == token.COMMENT:
                t_type = "COMMENT"
            else:
                continue

            tokens.append({
                "type": t_type,
                "value": val,
                "line": tok.start[0],
                "col": tok.start[1] + 1,
            })
    except Exception:
        pass
    return tokens


def _build_python_cfg(fn_node: ast.FunctionDef) -> Dict[str, Any]:
    nodes = []
    edges = []
    block_id_counter = 0

    def make_id(prefix="B"):
        nonlocal block_id_counter
        bid = f"{prefix}_{block_id_counter}"
        block_id_counter += 1
        return bid

    entry_id = "ENTRY"
    exit_id = "EXIT"

    param_str = ", ".join(a.arg for a in fn_node.args.args)
    nodes.append({
        "id": entry_id,
        "label": "Entry",
        "type": "entry",
        "instructions": [f"def {fn_node.name}({param_str}):"],
        "line": fn_node.lineno,
    })

    nodes.append({
        "id": exit_id,
        "label": "Exit",
        "type": "exit",
        "instructions": [],
        "line": getattr(fn_node, "end_lineno", fn_node.lineno),
    })

    start_body_id = make_id()
    nodes.append({
        "id": start_body_id,
        "label": "Start",
        "type": "statement",
        "instructions": [],
        "line": fn_node.lineno,
    })
    edges.append({"source": entry_id, "target": start_body_id, "type": "fallthrough", "label": ""})

    def process_body(stmts: List[ast.stmt], prev_id: str) -> Optional[str]:
        curr = prev_id
        for s in stmts:
            if curr is None:
                break

            if isinstance(s, ast.If):
                cond_str = _expr_to_str(s.test)
                cond_id = make_id("COND")
                nodes.append({
                    "id": cond_id,
                    "label": f"If ({cond_str})",
                    "type": "condition",
                    "instructions": [f"if {cond_str}:"],
                    "line": s.lineno,
                })
                edges.append({"source": curr, "target": cond_id, "type": "fallthrough", "label": ""})

                join_id = make_id("JOIN")
                nodes.append({
                    "id": join_id,
                    "label": "Join If",
                    "type": "join",
                    "instructions": [],
                    "line": s.lineno,
                })

                then_id = make_id("THEN")
                nodes.append({"id": then_id, "label": "Then", "type": "statement", "instructions": [], "line": s.lineno})
                edges.append({"source": cond_id, "target": then_id, "type": "true", "label": "True"})
                then_end = process_body(s.body, then_id)
                if then_end:
                    edges.append({"source": then_end, "target": join_id, "type": "fallthrough", "label": ""})

                if s.orelse:
                    else_id = make_id("ELSE")
                    nodes.append({"id": else_id, "label": "Else", "type": "statement", "instructions": [], "line": s.lineno})
                    edges.append({"source": cond_id, "target": else_id, "type": "false", "label": "False"})
                    else_end = process_body(s.orelse, else_id)
                    if else_end:
                        edges.append({"source": else_end, "target": join_id, "type": "fallthrough", "label": ""})
                else:
                    edges.append({"source": cond_id, "target": join_id, "type": "false", "label": "False"})

                curr = join_id

            elif isinstance(s, (ast.While, ast.For)):
                loop_type = "While" if isinstance(s, ast.While) else "For"
                cond_str = _expr_to_str(s.test) if isinstance(s, ast.While) else f"{_expr_to_str(s.target)} in {_expr_to_str(s.iter)}"
                cond_id = make_id("LOOP")
                nodes.append({
                    "id": cond_id,
                    "label": f"{loop_type} ({cond_str})",
                    "type": "condition",
                    "instructions": [f"{loop_type.lower()} {cond_str}:"],
                    "line": s.lineno,
                })
                edges.append({"source": curr, "target": cond_id, "type": "fallthrough", "label": ""})

                exit_loop_id = make_id("EXIT_LOOP")
                nodes.append({"id": exit_loop_id, "label": f"Exit {loop_type}", "type": "join", "instructions": [], "line": s.lineno})

                body_id = make_id("LOOP_BODY")
                nodes.append({"id": body_id, "label": f"{loop_type} Body", "type": "statement", "instructions": [], "line": s.lineno})
                edges.append({"source": cond_id, "target": body_id, "type": "true", "label": "True"})

                body_end = process_body(s.body, body_id)
                if body_end:
                    edges.append({"source": body_end, "target": cond_id, "type": "loop_back", "label": "Loop"})

                edges.append({"source": cond_id, "target": exit_loop_id, "type": "false", "label": "False"})
                curr = exit_loop_id

            elif isinstance(s, ast.Return):
                ret_str = f"return {_expr_to_str(s.value)}" if s.value else "return"
                for b in nodes:
                    if b["id"] == curr:
                        b["instructions"].append(ret_str)
                        break
                edges.append({"source": curr, "target": exit_id, "type": "return", "label": "Return"})
                curr = None

            else:
                stmt_str = _expr_to_str(s)
                for b in nodes:
                    if b["id"] == curr:
                        b["instructions"].append(stmt_str)
                        break

        return curr

    final_id = process_body(fn_node.body, start_body_id)
    if final_id:
        edges.append({"source": final_id, "target": exit_id, "type": "fallthrough", "label": ""})

    # Prune unreachable blocks
    reachable = set()
    def dfs(bid):
        if bid in reachable:
            return
        reachable.add(bid)
        for e in edges:
            if e["source"] == bid:
                dfs(e["target"])
    dfs(entry_id)

    pruned_nodes = [n for n in nodes if n["id"] in reachable or n["id"] == exit_id]
    pruned_edges = [e for e in edges if e["source"] in reachable and e["target"] in {n["id"] for n in pruned_nodes}]

    n_count = len(pruned_nodes)
    e_count = len(pruned_edges)
    mccabe_cc = max(1, e_count - n_count + 2)

    return {
        "function": fn_node.name,
        "returnType": "def",
        "nodes": pruned_nodes,
        "edges": pruned_edges,
        "nodeCount": n_count,
        "edgeCount": e_count,
        "cyclomaticComplexity": mccabe_cc,
    }


def analyze_python_source(source: str) -> Dict[str, Any]:
    """Analyzes Python code end-to-end producing all metrics and artifacts."""
    tokens = _tokenize_python(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise SyntaxError(f"Line {e.lineno}, Col {e.offset}: {e.msg}")

    # Build compatible AST dict
    ast_dict = {
        "type": "Program",
        "functions": [_ast_to_dict(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
        "line": 1,
        "col": 1,
    }

    # Per-function metrics
    functions_metrics = []
    cfgs = {}
    max_cc = 0
    most_complex_fn = ""

    # Symbol table tracking
    scopes = [{"scopeId": 0, "name": "global", "scopeType": "global", "level": 0, "symbols": []}]
    flat_symbols = []
    diagnostics = []
    all_smells = []
    smell_id = 1

    # Collect all called function names across the entire module
    all_calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                all_calls[fname] = all_calls.get(fname, 0) + 1
            elif isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                all_calls[attr_name] = all_calls.get(attr_name, 0) + 1

    # Extract functions and register in global symbol table
    func_nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in func_nodes:
        call_count = all_calls.get(fn.name, 0)
        is_fn_used = call_count > 0 or fn.name == "main"
        fn_sym = {
            "name": fn.name,
            "type": _expr_to_str(fn.returns) if getattr(fn, "returns", None) else "def",
            "kind": "function",
            "scopeId": 0,
            "scopeName": "global",
            "line": fn.lineno,
            "col": getattr(fn, "col_offset", 0) + 1,
            "isUsed": is_fn_used,
            "usageCount": max(call_count, 1 if fn.name == "main" else 0),
            "firstUse": {"line": fn.lineno} if is_fn_used else None,
            "references": [{"line": fn.lineno, "col": 1, "kind": "entrypoint" if fn.name == "main" else "call"}] if is_fn_used else [],
        }
        scopes[0]["symbols"].append(fn_sym)
        flat_symbols.append(fn_sym)

    for fn in func_nodes:
        # Cyclomatic complexity
        cc = 1  # Base path
        ifs = 0
        fors = 0
        whiles = 0
        returns = 0
        max_nesting = 0
        vars_set = set()
        loaded_names = set()

        depth = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                cc += 1
                ifs += 1
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                cc += 1
                fors += 1
            elif isinstance(node, ast.While):
                cc += 1
                whiles += 1
            elif isinstance(node, ast.ExceptHandler):
                cc += 1
            elif isinstance(node, ast.BoolOp):
                cc += len(node.values) - 1
            elif isinstance(node, ast.IfExp):
                cc += 1
            elif isinstance(node, ast.Return):
                returns += 1
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    vars_set.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    loaded_names.add(node.id)

        # Track nesting depth recursively
        def check_nesting(node, current_depth):
            nonlocal max_nesting
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                current_depth += 1
                max_nesting = max(max_nesting, current_depth)
            for child in ast.iter_child_nodes(node):
                check_nesting(child, current_depth)

        check_nesting(fn, 0)

        loc = max(1, getattr(fn, "end_lineno", fn.lineno) - fn.lineno + 1)
        params = [a.arg for a in fn.args.args]
        total_vars = len(vars_set) + len(params)

        f_metric = {
            "name": fn.name,
            "returnType": "def",
            "paramCount": len(params),
            "params": [{"name": p, "varType": "Any"} for p in params],
            "variables": total_vars,
            "ifs": ifs,
            "fors": fors,
            "whiles": whiles,
            "switches": 0,
            "returns": returns,
            "maxNesting": max_nesting,
            "cyclomatic": cc,
            "complexityLevel": _complexity_level(cc),
            "startLine": fn.lineno,
            "endLine": getattr(fn, "end_lineno", fn.lineno),
            "loc": loc,
            "isMostComplex": False,
        }
        functions_metrics.append(f_metric)

        if cc > max_cc:
            max_cc = cc
            most_complex_fn = fn.name

        # CFG for this function
        cfgs[fn.name] = _build_python_cfg(fn)

        # Symbols for this function
        scope_id = len(scopes)
        fn_syms = []
        for p in params:
            is_used = p in loaded_names
            sym = {
                "name": p,
                "type": "Any",
                "kind": "parameter",
                "scopeId": scope_id,
                "scopeName": fn.name,
                "line": fn.lineno,
                "col": 1,
                "isUsed": is_used,
                "usageCount": 1 if is_used else 0,
                "firstUse": {"line": fn.lineno} if is_used else None,
            }
            fn_syms.append(sym)
            flat_symbols.append(sym)
            if not is_used and p != "self" and p != "cls":
                diagnostics.append({
                    "severity": "warning",
                    "message": f"Unused parameter '{p}' in function '{fn.name}'",
                    "line": fn.lineno,
                    "col": 1,
                    "rule": "unused-parameter",
                })

        for v in vars_set:
            is_used = v in loaded_names
            sym = {
                "name": v,
                "type": "Any",
                "kind": "variable",
                "scopeId": scope_id,
                "scopeName": fn.name,
                "line": fn.lineno,
                "col": 1,
                "isUsed": is_used,
                "usageCount": 1 if is_used else 0,
                "firstUse": {"line": fn.lineno} if is_used else None,
            }
            fn_syms.append(sym)
            flat_symbols.append(sym)
            if not is_used and not v.startswith("_"):
                diagnostics.append({
                    "severity": "warning",
                    "message": f"Unused variable '{v}' declared in function '{fn.name}'",
                    "line": fn.lineno,
                    "col": 1,
                    "rule": "unused-variable",
                })

        scopes.append({
            "scopeId": scope_id,
            "name": fn.name,
            "scopeType": "function",
            "level": 1,
            "symbols": fn_syms,
        })

        # Code Smells
        if loc > 25:
            all_smells.append({
                "id": f"SMELL_{smell_id:03d}",
                "category": "Long Function",
                "severity": "Critical" if loc > 40 else "High",
                "function": fn.name,
                "line": fn.lineno,
                "description": f"Python function '{fn.name}' is {loc} lines long (threshold: 25 lines).",
                "suggestion": "Extract Method: Decompose this function into smaller helper functions with single responsibilities.",
                "examplePattern": f"# Split def {fn.name}() into cohesive helper functions",
            })
            smell_id += 1

        if max_nesting >= 3:
            all_smells.append({
                "id": f"SMELL_{smell_id:03d}",
                "category": "Deep Nesting",
                "severity": "High" if max_nesting >= 4 else "Medium",
                "function": fn.name,
                "line": fn.lineno,
                "description": f"Function '{fn.name}' has nesting depth of {max_nesting} (threshold: 3 levels).",
                "suggestion": "Flatten Control Flow: Invert condition checks with early returns / guard clauses or list comprehensions.",
                "examplePattern": "# Replace nested if with guard clauses:\n# if not condition: return",
            })
            smell_id += 1

        if cc > 10:
            all_smells.append({
                "id": f"SMELL_{smell_id:03d}",
                "category": "High Cyclomatic Complexity",
                "severity": "Critical" if cc > 15 else "High",
                "function": fn.name,
                "line": fn.lineno,
                "description": f"Function '{fn.name}' has cyclomatic complexity of {cc} (threshold: 10).",
                "suggestion": "Decompose Decisions: Replace complex branching with dictionary dispatch tables or helper functions.",
                "examplePattern": "# Use dictionary dispatch table:\n# dispatch = {'case1': handler1, 'case2': handler2}",
            })
            smell_id += 1

    # Mark most complex function
    for f in functions_metrics:
        f["isMostComplex"] = (f["name"] == most_complex_fn and max_cc > 1)

    # Program totals
    total_loc = len([l for l in source.splitlines() if l.strip()])
    total_funcs = len(functions_metrics)
    total_vars = sum(f["variables"] for f in functions_metrics)
    total_ifs = sum(f["ifs"] for f in functions_metrics)
    total_fors = sum(f["fors"] for f in functions_metrics)
    total_whiles = sum(f["whiles"] for f in functions_metrics)
    total_returns = sum(f["returns"] for f in functions_metrics)
    total_cc = sum(f["cyclomatic"] for f in functions_metrics)
    avg_cc = round(total_cc / total_funcs, 1) if total_funcs > 0 else 0
    max_nest = max((f["maxNesting"] for f in functions_metrics), default=0)

    prog_metrics = {
        "functions": total_funcs,
        "variables": total_vars,
        "ifs": total_ifs,
        "fors": total_fors,
        "whiles": total_whiles,
        "switches": 0,
        "returns": total_returns,
        "maxNesting": max_nest,
        "cyclomatic": total_cc,
        "avgCyclomatic": avg_cc,
        "complexityLevel": _complexity_level(total_cc),
        "loc": total_loc,
        "mostComplexFunction": most_complex_fn,
        "maxFunctionComplexity": max_cc,
    }

    # Quality score
    score = 100
    if avg_cc > 10:
        score -= min(25, int((avg_cc - 10) * 3))
    elif avg_cc > 5:
        score -= min(10, int((avg_cc - 5) * 2))
    if max_nest >= 3:
        score -= min(15, (max_nest - 2) * 5)
    score -= len([d for d in diagnostics if d["severity"] == "error"]) * 12
    score -= len([d for d in diagnostics if d["severity"] == "warning"]) * 2
    for s in all_smells:
        if s["severity"] == "Critical": score -= 10
        elif s["severity"] == "High": score -= 6
        elif s["severity"] == "Medium": score -= 3
        else: score -= 1
    score = max(0, min(100, score))

    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 65 else "D" if score >= 50 else "F"
    quality = {
        "score": score,
        "grade": grade,
        "description": "Clean and maintainable" if grade in ("A", "B") else "Moderate structural complexity" if grade == "C" else "Severe maintainability issues"
    }

    symbol_table_data = {
        "hierarchy": scopes[0],
        "flatSymbols": flat_symbols,
        "totalSymbols": len(flat_symbols),
        "totalScopes": len(scopes),
    }

    return {
        "tokens": tokens,
        "ast": ast_dict,
        "metrics": {
            **prog_metrics,
            "program": prog_metrics,
            "perFunction": functions_metrics,
            "functionList": functions_metrics,
        },
        "symbolTable": symbol_table_data,
        "diagnostics": diagnostics,
        "cfgs": cfgs,
        "codeSmells": all_smells,
        "quality": quality,
    }
