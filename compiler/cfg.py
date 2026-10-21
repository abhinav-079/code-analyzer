"""
Control Flow Graph (CFG) generation and analysis for the Code Quality Analyzer.

Constructs basic blocks and directed control-flow edges from the AST.
Computes McCabe's Cyclomatic Complexity from the graph: M = E - N + 2P.
Provides serialization format for interactive graph visualization.
"""

from typing import List, Dict, Any, Optional, Set, Tuple


def _expr_to_str(expr: Optional[Dict[str, Any]]) -> str:
    if not expr:
        return ""
    t = expr.get("type")
    if t == "Number":
        return str(expr.get("value", ""))
    if t == "String":
        return str(expr.get("value", ""))
    if t == "Char":
        return str(expr.get("value", ""))
    if t == "Identifier":
        return str(expr.get("name", ""))
    if t == "BinaryExpr":
        return f"{_expr_to_str(expr.get('left'))} {expr.get('op')} {_expr_to_str(expr.get('right'))}"
    if t == "Assign":
        name = expr.get("name") or _expr_to_str(expr.get("target"))
        return f"{name} {expr.get('op')} {_expr_to_str(expr.get('value'))}"
    if t == "Unary":
        if expr.get("prefix", True):
            return f"{expr.get('op')}{_expr_to_str(expr.get('argument'))}"
        return f"{_expr_to_str(expr.get('argument'))}{expr.get('op')}"
    if t == "PointerDeref":
        return f"*{_expr_to_str(expr.get('argument'))}"
    if t == "AddressOf":
        return f"&{_expr_to_str(expr.get('argument'))}"
    if t == "ArrayAccess":
        return f"{_expr_to_str(expr.get('array'))}[{_expr_to_str(expr.get('index'))}]"
    if t == "Call":
        args = ", ".join(_expr_to_str(a) for a in expr.get("args", []))
        return f"{expr.get('callee')}({args})"
    if t == "Ternary":
        return f"{_expr_to_str(expr.get('condition'))} ? {_expr_to_str(expr.get('consequent'))} : {_expr_to_str(expr.get('alternate'))}"
    if t == "ArrayInit":
        items = ", ".join(_expr_to_str(x) for x in expr.get("items", []))
        return f"{{{items}}}"
    return ""


def _stmt_to_str(stmt: Any) -> str:
    if not stmt:
        return ""
    if isinstance(stmt, list):
        return ", ".join(_stmt_to_str(s) for s in stmt)
    t = stmt.get("type")
    if t == "Declaration":
        init_str = ""
        if stmt.get("init"):
            init_str = f" = {_expr_to_str(stmt.get('init'))}"
        if stmt.get("arraySizes"):
            arr_str = "".join(f"[{_expr_to_str(s)}]" if s else "[]" for s in stmt["arraySizes"])
        elif stmt.get("arraySize"):
            arr_str = f"[{_expr_to_str(stmt.get('arraySize'))}]"
        else:
            arr_str = ""
        return f"{stmt.get('varType')}{arr_str} {stmt.get('name')}{init_str};"
    if t == "ExprStmt":
        return f"{_expr_to_str(stmt.get('expr'))};"
    if t == "Return":
        val = f" {_expr_to_str(stmt.get('value'))}" if stmt.get("value") else ""
        return f"return{val};"
    if t == "Break":
        return "break;"
    if t == "Continue":
        return "continue;"
    return t


class BasicBlock:
    def __init__(self, block_id: str, label: str, block_type: str = "statement", line: int = 1):
        self.id = block_id
        self.label = label
        self.block_type = block_type  # 'entry', 'exit', 'condition', 'statement', 'join'
        self.instructions: List[str] = []
        self.line = line

    def add_instruction(self, inst: str):
        if inst:
            self.instructions.append(inst)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.block_type,
            "instructions": self.instructions,
            "line": self.line,
        }

    def __repr__(self):
        return f"Block({self.id}, {self.label}, {len(self.instructions)} insts)"


class CFGEdge:
    def __init__(self, source_id: str, target_id: str, edge_type: str = "fallthrough", label: str = ""):
        self.source = source_id
        self.target = target_id
        self.edge_type = edge_type  # 'fallthrough', 'true', 'false', 'loop_back', 'return', 'break', 'continue'
        self.label = label or edge_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type,
            "label": self.label,
        }

    def __repr__(self):
        return f"Edge({self.source} -> {self.target} [{self.label}])"


class FunctionCFG:
    def __init__(self, function_name: str, return_type: str, params: List[Dict[str, Any]]):
        self.function_name = function_name
        self.return_type = return_type
        self.params = params
        self.blocks: Dict[str, BasicBlock] = {}
        self.edges: List[CFGEdge] = []
        self._block_counter = 0

        # Create standard Entry and Exit blocks
        self.entry_block = self.create_block("ENTRY", "Entry", block_type="entry")
        param_str = ", ".join(f"{p['varType']} {p['name']}" for p in params)
        self.entry_block.add_instruction(f"{return_type} {function_name}({param_str})")

        self.exit_block = self.create_block("EXIT", "Exit", block_type="exit")

    def next_id(self, prefix: str = "B") -> str:
        idx = self._block_counter
        self._block_counter += 1
        return f"{prefix}_{idx}"

    def create_block(self, block_id: Optional[str] = None, label: str = "", block_type: str = "statement", line: int = 1) -> BasicBlock:
        if block_id is None:
            block_id = self.next_id()
        if not label:
            label = block_id
        block = BasicBlock(block_id, label, block_type, line)
        self.blocks[block_id] = block
        return block

    def add_edge(self, source_id: str, target_id: str, edge_type: str = "fallthrough", label: str = ""):
        # Avoid duplicate identical edges
        for e in self.edges:
            if e.source == source_id and e.target == target_id and e.edge_type == edge_type:
                return
        self.edges.append(CFGEdge(source_id, target_id, edge_type, label))

    def compute_cyclomatic_complexity(self) -> int:
        """
        McCabe formula: M = E - N + 2P
        E = edges, N = nodes, P = 1 (single function component)
        """
        n = len(self.blocks)
        e = len(self.edges)
        p = 1
        # McCabe complexity for single component
        cc = e - n + (2 * p)
        return max(1, cc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "function": self.function_name,
            "returnType": self.return_type,
            "nodes": [b.to_dict() for b in self.blocks.values()],
            "edges": [e.to_dict() for e in self.edges],
            "nodeCount": len(self.blocks),
            "edgeCount": len(self.edges),
            "cyclomaticComplexity": self.compute_cyclomatic_complexity(),
        }


class CFGBuilder:
    def __init__(self, fn_ast: Dict[str, Any]):
        self.fn_ast = fn_ast
        self.cfg = FunctionCFG(
            fn_ast["name"],
            fn_ast.get("returnType", "void"),
            fn_ast.get("params", [])
        )
        # Context stacks for break/continue targets
        self.break_targets: List[str] = []
        self.continue_targets: List[str] = []

    def build(self) -> FunctionCFG:
        first_body_block = self.cfg.create_block(label="Start", line=self.fn_ast.get("line", 1))
        self.cfg.add_edge(self.cfg.entry_block.id, first_body_block.id, "fallthrough", "")

        curr_block = first_body_block
        body = self.fn_ast.get("body", {})
        final_block = self._build_statements(body.get("statements", []), curr_block)

        # Connect end of function to Exit if not already terminated by return
        if final_block and final_block.id != self.cfg.exit_block.id:
            self.cfg.add_edge(final_block.id, self.cfg.exit_block.id, "fallthrough", "")

        # Clean up isolated blocks without predecessors (except Entry)
        self._prune_unreachable_blocks()

        return self.cfg

    def _prune_unreachable_blocks(self):
        reachable = set()

        def dfs(node_id):
            if node_id in reachable:
                return
            reachable.add(node_id)
            for e in self.cfg.edges:
                if e.source == node_id:
                    dfs(e.target)

        dfs(self.cfg.entry_block.id)

        # Remove unreachable blocks and their incident edges
        self.cfg.blocks = {bid: b for bid, b in self.cfg.blocks.items() if bid in reachable or bid == self.cfg.exit_block.id}
        self.cfg.edges = [e for e in self.cfg.edges if e.source in reachable and e.target in self.cfg.blocks]

    def _build_statements(self, stmts: List[Dict[str, Any]], current_block: Optional[BasicBlock]) -> Optional[BasicBlock]:
        curr = current_block
        for stmt in stmts:
            if curr is None:
                break
            curr = self._build_statement(stmt, curr)
        return curr

    def _find_ternary(self, expr: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not expr or not isinstance(expr, dict):
            return None
        if expr.get("type") == "Ternary":
            return expr
        for v in expr.values():
            if isinstance(v, dict):
                res = self._find_ternary(v)
                if res:
                    return res
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        res = self._find_ternary(item)
                        if res:
                            return res
        return None

    def _replace_ternary(self, expr: Any, target: Dict[str, Any], replacement: Any) -> Any:
        if not isinstance(expr, dict):
            if isinstance(expr, list):
                return [self._replace_ternary(item, target, replacement) for item in expr]
            return expr
        if expr is target:
            return replacement
        res = {}
        for k, v in expr.items():
            if isinstance(v, dict):
                res[k] = self._replace_ternary(v, target, replacement)
            elif isinstance(v, list):
                res[k] = [self._replace_ternary(item, target, replacement) for item in v]
            else:
                res[k] = v
        return res

    def _build_statement(self, stmt: Any, current_block: BasicBlock) -> Optional[BasicBlock]:
        if not stmt:
            return current_block
        if isinstance(stmt, list):
            return self._build_statements(stmt, current_block)
        t = stmt.get("type")
        line = stmt.get("line", 1)

        # Check for Ternary expressions in statements (Return, Declaration, ExprStmt)
        ternary = None
        if t == "Return" and stmt.get("value"):
            ternary = self._find_ternary(stmt["value"])
        elif t == "Declaration" and stmt.get("init"):
            ternary = self._find_ternary(stmt["init"])
        elif t == "ExprStmt" and stmt.get("expr"):
            ternary = self._find_ternary(stmt["expr"])

        if ternary:
            cond_str = _expr_to_str(ternary.get("condition"))
            cond_block = self.cfg.create_block(label=f"Ternary ({cond_str})", block_type="condition", line=line)
            cond_block.add_instruction(f"if ({cond_str})")
            self.cfg.add_edge(current_block.id, cond_block.id, "fallthrough", "")

            then_block = self.cfg.create_block(label="Ternary True", line=line)
            self.cfg.add_edge(cond_block.id, then_block.id, "true", "True")

            else_block = self.cfg.create_block(label="Ternary False", line=line)
            self.cfg.add_edge(cond_block.id, else_block.id, "false", "False")

            if t == "Return":
                then_val = self._replace_ternary(stmt["value"], ternary, ternary.get("consequent"))
                then_stmt = {"type": "Return", "value": then_val, "line": line}
                self._build_statement(then_stmt, then_block)

                else_val = self._replace_ternary(stmt["value"], ternary, ternary.get("alternate"))
                else_stmt = {"type": "Return", "value": else_val, "line": line}
                self._build_statement(else_stmt, else_block)
                return None
            else:
                join_block = self.cfg.create_block(label="Join Ternary", block_type="join", line=line)

                then_stmt = self._replace_ternary(stmt, ternary, ternary.get("consequent"))
                then_end = self._build_statement(then_stmt, then_block)
                if then_end:
                    self.cfg.add_edge(then_end.id, join_block.id, "fallthrough", "")

                else_stmt = self._replace_ternary(stmt, ternary, ternary.get("alternate"))
                else_end = self._build_statement(else_stmt, else_block)
                if else_end:
                    self.cfg.add_edge(else_end.id, join_block.id, "fallthrough", "")

                return join_block

        if t in ("Declaration", "ExprStmt"):
            current_block.add_instruction(_stmt_to_str(stmt))
            return current_block

        if t == "Block":
            return self._build_statements(stmt.get("statements", []), current_block)

        if t == "If":
            cond_str = _expr_to_str(stmt.get("condition"))
            cond_block = self.cfg.create_block(label=f"If ({cond_str})", block_type="condition", line=line)
            cond_block.add_instruction(f"if ({cond_str})")
            self.cfg.add_edge(current_block.id, cond_block.id, "fallthrough", "")

            join_block = self.cfg.create_block(label="Join If", block_type="join", line=line)

            # Then branch
            then_start = self.cfg.create_block(label="Then", line=line)
            self.cfg.add_edge(cond_block.id, then_start.id, "true", "True")
            then_end = self._build_substatement(stmt.get("consequent"), then_start)
            if then_end:
                self.cfg.add_edge(then_end.id, join_block.id, "fallthrough", "")

            # Else branch
            if stmt.get("alternate"):
                else_start = self.cfg.create_block(label="Else", line=line)
                self.cfg.add_edge(cond_block.id, else_start.id, "false", "False")
                else_end = self._build_substatement(stmt.get("alternate"), else_start)
                if else_end:
                    self.cfg.add_edge(else_end.id, join_block.id, "fallthrough", "")
            else:
                self.cfg.add_edge(cond_block.id, join_block.id, "false", "False")

            return join_block

        if t == "While":
            cond_str = _expr_to_str(stmt.get("condition"))
            cond_block = self.cfg.create_block(label=f"While ({cond_str})", block_type="condition", line=line)
            cond_block.add_instruction(f"while ({cond_str})")
            self.cfg.add_edge(current_block.id, cond_block.id, "fallthrough", "")

            exit_block = self.cfg.create_block(label="Exit While", block_type="join", line=line)

            # Push context for break/continue
            self.break_targets.append(exit_block.id)
            self.continue_targets.append(cond_block.id)

            body_start = self.cfg.create_block(label="While Body", line=line)
            self.cfg.add_edge(cond_block.id, body_start.id, "true", "True")
            body_end = self._build_substatement(stmt.get("body"), body_start)
            if body_end:
                self.cfg.add_edge(body_end.id, cond_block.id, "loop_back", "Loop")

            self.cfg.add_edge(cond_block.id, exit_block.id, "false", "False")

            self.break_targets.pop()
            self.continue_targets.pop()
            return exit_block

        if t == "For":
            # For init
            if stmt.get("init"):
                current_block.add_instruction(_stmt_to_str(stmt["init"]))

            cond_str = _expr_to_str(stmt.get("condition")) if stmt.get("condition") else "1"
            cond_block = self.cfg.create_block(label=f"For Cond ({cond_str})", block_type="condition", line=line)
            cond_block.add_instruction(f"for condition: {cond_str}")
            self.cfg.add_edge(current_block.id, cond_block.id, "fallthrough", "")

            update_block = self.cfg.create_block(label="For Update", line=line)
            if stmt.get("update"):
                update_block.add_instruction(_expr_to_str(stmt["update"]) + ";")
            self.cfg.add_edge(update_block.id, cond_block.id, "loop_back", "Loop")

            exit_block = self.cfg.create_block(label="Exit For", block_type="join", line=line)

            self.break_targets.append(exit_block.id)
            self.continue_targets.append(update_block.id)

            body_start = self.cfg.create_block(label="For Body", line=line)
            self.cfg.add_edge(cond_block.id, body_start.id, "true", "True")
            body_end = self._build_substatement(stmt.get("body"), body_start)
            if body_end:
                self.cfg.add_edge(body_end.id, update_block.id, "fallthrough", "")

            self.cfg.add_edge(cond_block.id, exit_block.id, "false", "False")

            self.break_targets.pop()
            self.continue_targets.pop()
            return exit_block

        if t == "DoWhile":
            cond_str = _expr_to_str(stmt.get("condition"))
            body_start = self.cfg.create_block(label="Do Body", line=line)
            self.cfg.add_edge(current_block.id, body_start.id, "fallthrough", "")

            cond_block = self.cfg.create_block(label=f"Do Cond ({cond_str})", block_type="condition", line=line)
            cond_block.add_instruction(f"while ({cond_str})")

            exit_block = self.cfg.create_block(label="Exit Do", block_type="join", line=line)

            self.break_targets.append(exit_block.id)
            self.continue_targets.append(cond_block.id)

            body_end = self._build_substatement(stmt.get("body"), body_start)
            if body_end:
                self.cfg.add_edge(body_end.id, cond_block.id, "fallthrough", "")

            self.cfg.add_edge(cond_block.id, body_start.id, "true", "Loop")
            self.cfg.add_edge(cond_block.id, exit_block.id, "false", "False")

            self.break_targets.pop()
            self.continue_targets.pop()
            return exit_block

        if t == "Switch":
            disc_str = _expr_to_str(stmt.get("discriminant"))
            switch_block = self.cfg.create_block(label=f"Switch ({disc_str})", block_type="condition", line=line)
            switch_block.add_instruction(f"switch ({disc_str})")
            self.cfg.add_edge(current_block.id, switch_block.id, "fallthrough", "")

            join_block = self.cfg.create_block(label="Exit Switch", block_type="join", line=line)
            self.break_targets.append(join_block.id)

            prev_case_end = None
            has_default = False

            for case in stmt.get("cases", []):
                case_test = _expr_to_str(case.get("test")) if case.get("test") else "default"
                if case.get("type") == "Default":
                    has_default = True
                case_block = self.cfg.create_block(label=f"Case {case_test}", line=case.get("line", line))
                self.cfg.add_edge(switch_block.id, case_block.id, "true", f"== {case_test}")

                if prev_case_end:
                    self.cfg.add_edge(prev_case_end.id, case_block.id, "fallthrough", "fallthrough")

                case_end = self._build_statements(case.get("consequent", []), case_block)
                prev_case_end = case_end

            if prev_case_end:
                self.cfg.add_edge(prev_case_end.id, join_block.id, "fallthrough", "")

            if not has_default:
                self.cfg.add_edge(switch_block.id, join_block.id, "false", "no match")

            self.break_targets.pop()
            return join_block

        if t == "Return":
            current_block.add_instruction(_stmt_to_str(stmt))
            self.cfg.add_edge(current_block.id, self.cfg.exit_block.id, "return", "Return")
            return None  # Dead code afterwards in this basic block

        if t == "Break":
            current_block.add_instruction("break;")
            if self.break_targets:
                self.cfg.add_edge(current_block.id, self.break_targets[-1], "break", "Break")
            return None

        if t == "Continue":
            current_block.add_instruction("continue;")
            if self.continue_targets:
                self.cfg.add_edge(current_block.id, self.continue_targets[-1], "continue", "Continue")
            return None

        return current_block

    def _build_substatement(self, stmt: Optional[Dict[str, Any]], start_block: BasicBlock) -> Optional[BasicBlock]:
        if not stmt:
            return start_block
        if stmt.get("type") == "Block":
            return self._build_statements(stmt.get("statements", []), start_block)
        return self._build_statement(stmt, start_block)


def build_program_cfgs(ast: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build CFGs for all functions in the program AST."""
    cfgs = {}
    for fn in ast.get("functions", []):
        fn_name = fn["name"]
        builder = CFGBuilder(fn)
        cfg = builder.build()
        cfgs[fn_name] = cfg.to_dict()
    return cfgs
