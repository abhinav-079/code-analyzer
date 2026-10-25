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
import builtins
import io
import token
import tokenize
import textwrap
from typing import Dict, Any, List, Optional, Set, Tuple

PYTHON_BUILTINS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__",
    "True", "False", "None", "self", "cls"
}


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


def _build_python_cfg_from_stmts(name: str, param_str: str, stmts: List[ast.stmt], start_line: int, end_line: int) -> Dict[str, Any]:
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

    entry_inst = [f"def {name}({param_str}):"] if param_str or name not in ("<module>", "main") else [f"execution of {name}"]
    nodes.append({
        "id": entry_id,
        "label": "Entry",
        "type": "entry",
        "instructions": entry_inst,
        "line": start_line,
    })

    nodes.append({
        "id": exit_id,
        "label": "Exit",
        "type": "exit",
        "instructions": [],
        "line": end_line,
    })

    start_body_id = make_id()
    nodes.append({
        "id": start_body_id,
        "label": "Start",
        "type": "statement",
        "instructions": [],
        "line": start_line,
    })
    edges.append({"source": entry_id, "target": start_body_id, "type": "fallthrough", "label": ""})

    def process_body(body_stmts: List[ast.stmt], prev_id: str) -> Optional[str]:
        curr = prev_id
        for s in body_stmts:
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

    final_id = process_body(stmts, start_body_id)
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
        "function": name,
        "returnType": "def",
        "nodes": pruned_nodes,
        "edges": pruned_edges,
        "nodeCount": n_count,
        "edgeCount": e_count,
        "cyclomaticComplexity": mccabe_cc,
    }


def _build_python_cfg(fn_node: ast.FunctionDef) -> Dict[str, Any]:
    param_str = ", ".join(a.arg for a in fn_node.args.args)
    return _build_python_cfg_from_stmts(
        fn_node.name,
        param_str,
        fn_node.body,
        fn_node.lineno,
        getattr(fn_node, "end_lineno", fn_node.lineno),
    )


def analyze_python_source(source: str) -> Dict[str, Any]:
    """Analyzes Python code end-to-end producing all metrics, symbol table and semantic diagnostics."""
    tokens = _tokenize_python(source)

    try:
        tree = ast.parse(source)
    except (SyntaxError, IndentationError):
        try:
            tree = ast.parse(textwrap.dedent(source))
        except SyntaxError as e:
            # Return structured error diagnostic rather than crashing
            diag = {
                "severity": "error",
                "message": f"SyntaxError: {e.msg}",
                "line": e.lineno or 1,
                "col": e.offset or 1,
                "rule": "syntax-error",
            }
            total_loc = len([l for l in source.splitlines() if l.strip()])
            prog_metrics = {
                "functions": 0, "variables": 0, "ifs": 0, "fors": 0, "whiles": 0, "switches": 0, "returns": 0,
                "maxNesting": 0, "cyclomatic": 1, "avgCyclomatic": 1.0, "complexityLevel": "Low",
                "loc": total_loc, "mostComplexFunction": "", "maxFunctionComplexity": 0,
            }
            return {
                "tokens": tokens,
                "ast": {"type": "Program", "functions": [], "line": 1, "col": 1},
                "metrics": {**prog_metrics, "program": prog_metrics, "perFunction": [], "functionList": []},
                "symbolTable": {"hierarchy": {"scopeId": 0, "name": "global", "scopeType": "global", "level": 0, "symbols": []}, "flatSymbols": [], "totalSymbols": 0, "totalScopes": 1},
                "diagnostics": [diag],
                "cfgs": {},
                "codeSmells": [],
                "quality": {"score": 0, "grade": "F", "description": "Critical syntax error: code cannot be parsed"},
            }

    # Extract top-level statements vs functions/classes
    func_nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    top_level_stmts = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]

    # Build compatible AST dict
    ast_functions = [_ast_to_dict(n) for n in func_nodes]
    if top_level_stmts:
        top_name = "main" if not any(f.name in ("main", "Main") for f in func_nodes) else "<module>"
        first_line = top_level_stmts[0].lineno if hasattr(top_level_stmts[0], "lineno") else 1
        ast_functions.insert(0, {
            "type": "FunctionDecl",
            "name": top_name,
            "returnType": "void",
            "params": [],
            "body": {"type": "Block", "statements": [_ast_to_dict(s) for s in top_level_stmts], "line": first_line, "col": 1},
            "line": first_line,
            "col": 1,
        })

    ast_dict = {
        "type": "Program",
        "functions": ast_functions,
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

    # Global symbol registry
    global_syms = {}

    # Register imports
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                mname = alias.asname or alias.name
                global_syms[mname] = {
                    "name": mname, "type": "module", "kind": "import",
                    "scopeId": 0, "scopeName": "global",
                    "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1,
                    "isUsed": False, "usageCount": 0, "firstUse": None, "references": []
                }
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                mname = alias.asname or alias.name
                global_syms[mname] = {
                    "name": mname, "type": "Any", "kind": "import",
                    "scopeId": 0, "scopeName": "global",
                    "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1,
                    "isUsed": False, "usageCount": 0, "firstUse": None, "references": []
                }

    # Register classes
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            global_syms[node.name] = {
                "name": node.name, "type": "class", "kind": "class",
                "scopeId": 0, "scopeName": "global",
                "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1,
                "isUsed": False, "usageCount": 0, "firstUse": None, "references": []
            }

    # Register functions
    for fn in func_nodes:
        global_syms[fn.name] = {
            "name": fn.name,
            "type": _expr_to_str(fn.returns) if getattr(fn, "returns", None) else "def",
            "kind": "function",
            "scopeId": 0, "scopeName": "global",
            "line": fn.lineno, "col": getattr(fn, "col_offset", 0) + 1,
            "isUsed": (fn.name == "main"),
            "usageCount": 1 if fn.name == "main" else 0,
            "firstUse": {"line": fn.lineno} if fn.name == "main" else None,
            "references": [{"line": fn.lineno, "col": 1, "kind": "entrypoint"}] if fn.name == "main" else []
        }

    # Register module-level variables
    for node in top_level_stmts:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = []
            if isinstance(node, ast.Assign): targets = node.targets
            elif isinstance(node, ast.AugAssign): targets = [node.target]
            elif isinstance(node, ast.AnnAssign): targets = [node.target]
            for tgt in targets:
                for n in ast.walk(tgt):
                    if isinstance(n, ast.Name):
                        vname = n.id
                        vtype = "Any"
                        val = getattr(node, "value", None)
                        if isinstance(val, ast.Constant):
                            vtype = type(val.value).__name__
                        elif isinstance(val, ast.List): vtype = "list"
                        elif isinstance(val, ast.Dict): vtype = "dict"
                        elif isinstance(val, ast.Set): vtype = "set"
                        elif isinstance(val, ast.Tuple): vtype = "tuple"
                        if vname not in global_syms:
                            global_syms[vname] = {
                                "name": vname, "type": vtype, "kind": "variable",
                                "scopeId": 0, "scopeName": "global",
                                "line": n.lineno, "col": getattr(n, "col_offset", 0) + 1,
                                "isUsed": False, "usageCount": 0, "firstUse": None, "references": []
                            }

    # Analyze Top-Level Statements (if any)
    if top_level_stmts:
        top_cc = 1
        top_ifs = 0
        top_fors = 0
        top_whiles = 0
        top_max_nesting = 0
        top_vars_set = set()

        for stmt in top_level_stmts:
            for node in ast.walk(stmt):
                if isinstance(node, ast.If):
                    top_cc += 1
                    top_ifs += 1
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    top_cc += 1
                    top_fors += 1
                elif isinstance(node, ast.While):
                    top_cc += 1
                    top_whiles += 1
                elif isinstance(node, ast.ExceptHandler):
                    top_cc += 1
                elif isinstance(node, ast.BoolOp):
                    top_cc += len(node.values) - 1
                elif isinstance(node, ast.IfExp):
                    top_cc += 1
                elif isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Store):
                        top_vars_set.add(node.id)
                    elif isinstance(node.ctx, ast.Load):
                        # Loaded name check
                        nid = node.id
                        if nid in global_syms:
                            global_syms[nid]["isUsed"] = True
                            global_syms[nid]["usageCount"] += 1
                            if not global_syms[nid]["firstUse"]:
                                global_syms[nid]["firstUse"] = {"line": node.lineno}
                            global_syms[nid]["references"].append({
                                "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1, "kind": "read"
                            })
                        elif nid in PYTHON_BUILTINS:
                            pass
                        else:
                            diagnostics.append({
                                "severity": "error",
                                "message": f"Use of undeclared identifier '{nid}'",
                                "line": node.lineno,
                                "col": getattr(node, "col_offset", 0) + 1,
                                "rule": "undeclared-identifier",
                            })

        top_name = "main" if not any(f.name in ("main", "Main") for f in func_nodes) else "<module>"
        first_line = top_level_stmts[0].lineno
        last_line = getattr(top_level_stmts[-1], "end_lineno", top_level_stmts[-1].lineno)
        top_metric = {
            "name": top_name,
            "returnType": "void",
            "paramCount": 0,
            "params": [],
            "variables": len(top_vars_set),
            "ifs": top_ifs,
            "fors": top_fors,
            "whiles": top_whiles,
            "switches": 0,
            "returns": 0,
            "maxNesting": top_max_nesting,
            "cyclomatic": top_cc,
            "complexityLevel": _complexity_level(top_cc),
            "startLine": first_line,
            "endLine": last_line,
            "loc": max(1, last_line - first_line + 1),
            "isMostComplex": False,
        }
        functions_metrics.append(top_metric)
        cfgs[top_name] = _build_python_cfg_from_stmts(top_name, "", top_level_stmts, first_line, last_line)
        if top_cc > max_cc:
            max_cc = top_cc
            most_complex_fn = top_name

    # Analyze Each Explicit Function
    for fn in func_nodes:
        cc = 1
        ifs = 0
        fors = 0
        whiles = 0
        returns = 0
        max_nesting = 0
        vars_set = set()
        fn_syms = {}

        scope_id = len(scopes)

        # Register parameters
        for a in fn.args.args:
            fn_syms[a.arg] = {
                "name": a.arg,
                "type": "Any",
                "kind": "parameter",
                "scopeId": scope_id,
                "scopeName": fn.name,
                "line": a.lineno,
                "col": getattr(a, "col_offset", 0) + 1,
                "isUsed": False,
                "usageCount": 0,
                "firstUse": None,
                "references": [],
            }

        # Track AST nodes inside function
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
                nid = node.id
                if isinstance(node.ctx, ast.Store):
                    vars_set.add(nid)
                    if nid not in fn_syms:
                        fn_syms[nid] = {
                            "name": nid,
                            "type": "Any",
                            "kind": "variable",
                            "scopeId": scope_id,
                            "scopeName": fn.name,
                            "line": node.lineno,
                            "col": getattr(node, "col_offset", 0) + 1,
                            "isUsed": False,
                            "usageCount": 0,
                            "firstUse": None,
                            "references": [],
                        }
                elif isinstance(node.ctx, ast.Load):
                    if nid in fn_syms:
                        fn_syms[nid]["isUsed"] = True
                        fn_syms[nid]["usageCount"] += 1
                        if not fn_syms[nid]["firstUse"]:
                            fn_syms[nid]["firstUse"] = {"line": node.lineno}
                        fn_syms[nid]["references"].append({
                            "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1, "kind": "read"
                        })
                    elif nid in global_syms:
                        global_syms[nid]["isUsed"] = True
                        global_syms[nid]["usageCount"] += 1
                        if not global_syms[nid]["firstUse"]:
                            global_syms[nid]["firstUse"] = {"line": node.lineno}
                        global_syms[nid]["references"].append({
                            "line": node.lineno, "col": getattr(node, "col_offset", 0) + 1, "kind": "read"
                        })
                    elif nid in PYTHON_BUILTINS:
                        pass
                    else:
                        diagnostics.append({
                            "severity": "error",
                            "message": f"Use of undeclared identifier '{nid}'",
                            "line": node.lineno,
                            "col": getattr(node, "col_offset", 0) + 1,
                            "rule": "undeclared-identifier",
                        })

        # Function nesting calculation
        def check_nesting(node, current_depth):
            nonlocal max_nesting
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                current_depth += 1
                max_nesting = max(max_nesting, current_depth)
            for child in ast.iter_child_nodes(node):
                check_nesting(child, current_depth)

        check_nesting(fn, 0)

        loc = max(1, getattr(fn, "end_lineno", fn.lineno) - fn.lineno + 1)
        params_list = [a.arg for a in fn.args.args]
        total_vars = len(vars_set) + len(params_list)

        f_metric = {
            "name": fn.name,
            "returnType": "def",
            "paramCount": len(params_list),
            "params": [{"name": p, "varType": "Any"} for p in params_list],
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
        cfgs[fn.name] = _build_python_cfg(fn)

        if cc > max_cc:
            max_cc = cc
            most_complex_fn = fn.name

        # Scope symbols and diagnostics for function
        fn_sym_list = list(fn_syms.values())
        for sym in fn_sym_list:
            flat_symbols.append(sym)
            if not sym["isUsed"]:
                if sym["kind"] == "parameter" and sym["name"] not in ("self", "cls"):
                    diagnostics.append({
                        "severity": "warning",
                        "message": f"Unused parameter '{sym['name']}' declared in function '{fn.name}'",
                        "line": sym["line"],
                        "col": sym["col"],
                        "rule": "unused-parameter",
                    })
                elif sym["kind"] == "variable" and not sym["name"].startswith("_"):
                    diagnostics.append({
                        "severity": "warning",
                        "message": f"Unused variable '{sym['name']}' declared in function '{fn.name}'",
                        "line": sym["line"],
                        "col": sym["col"],
                        "rule": "unused-variable",
                    })

        scopes.append({
            "scopeId": scope_id,
            "name": fn.name,
            "scopeType": "function",
            "level": 1,
            "symbols": fn_sym_list,
        })

    # Global symbols reporting
    for sym in global_syms.values():
        flat_symbols.append(sym)
        scopes[0]["symbols"].append(sym)
        if not sym["isUsed"]:
            if sym["kind"] == "variable" and not sym["name"].startswith("_"):
                diagnostics.append({
                    "severity": "warning",
                    "message": f"Unused variable '{sym['name']}' declared in global scope",
                    "line": sym["line"],
                    "col": sym["col"],
                    "rule": "unused-variable",
                })
            elif sym["kind"] == "function" and sym["name"] not in ("main", "<module>"):
                diagnostics.append({
                    "severity": "warning",
                    "message": f"Unused function '{sym['name']}' declared in global scope",
                    "line": sym["line"],
                    "col": sym["col"],
                    "rule": "unused-function",
                })

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
    avg_cc = round(total_cc / total_funcs, 1) if total_funcs > 0 else 1.0
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
        "cyclomatic": total_cc if total_cc > 0 else 1,
        "avgCyclomatic": avg_cc,
        "complexityLevel": _complexity_level(total_cc if total_cc > 0 else 1),
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
    score -= len([d for d in diagnostics if d["severity"] == "error"]) * 15
    score -= len([d for d in diagnostics if d["severity"] == "warning"]) * 3
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
