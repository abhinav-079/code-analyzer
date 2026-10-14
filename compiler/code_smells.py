"""
Code smell detection and automated refactoring recommendations engine.

Analyzes AST, per-function metrics, symbol usage, and structural patterns to identify:
- Long Functions (excessive lines of code)
- Deep Nesting (exceeding nesting thresholds)
- High Cyclomatic Complexity (complex decision trees)
- Dead / Unreachable Code (statements after return/break)
- Unused Variables and Parameters
- Duplicated Logic (repeated statement patterns)
- Too Many Parameters (high arity)
- Magic Numbers (hardcoded numeric literals in logic)
"""

from typing import List, Dict, Any, Optional, Set
import hashlib


class CodeSmell:
    def __init__(
        self,
        smell_id: str,
        category: str,
        severity: str,
        function: str,
        line: int,
        description: str,
        suggestion: str,
        example_pattern: str = "",
    ):
        self.id = smell_id
        self.category = category
        self.severity = severity  # 'Critical', 'High', 'Medium', 'Low'
        self.function = function
        self.line = line
        self.description = description
        self.suggestion = suggestion
        self.example_pattern = example_pattern

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "function": self.function,
            "line": self.line,
            "description": self.description,
            "suggestion": self.suggestion,
            "examplePattern": self.example_pattern,
        }


class CodeSmellDetector:
    def __init__(
        self,
        ast: Dict[str, Any],
        function_metrics: List[Dict[str, Any]],
        symbol_table_data: Dict[str, Any],
        diagnostics: List[Dict[str, Any]],
    ):
        self.ast = ast
        self.function_metrics = {m["name"]: m for m in function_metrics}
        self.symbol_table_data = symbol_table_data
        self.diagnostics = diagnostics
        self.smells: List[CodeSmell] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"SMELL_{self._counter:03d}"

    def detect(self) -> List[Dict[str, Any]]:
        self._check_metrics_smells()
        self._check_unused_variables()
        self._check_dead_code()
        self._check_duplicated_logic()
        self._check_magic_numbers()

        return [s.to_dict() for s in self.smells]

    def _check_metrics_smells(self):
        for fn in self.ast.get("functions", []):
            name = fn["name"]
            metrics = self.function_metrics.get(name, {})
            fn_line = fn.get("line", 1)

            # 1. Long Function
            loc = metrics.get("loc", 0)
            if loc > 25:
                sev = "Critical" if loc > 45 else "High"
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Long Function",
                    sev,
                    name,
                    fn_line,
                    f"Function '{name}' is {loc} lines long (threshold: 25 lines).",
                    "Apply Extract Method: Decompose into smaller, specialized helper functions where each handles a single distinct task.",
                    "// Refactor by extracting coherent blocks into helper functions:\n// e.g. void compute_step_one(...) { ... }",
                ))

            # 2. Deep Nesting
            nesting = metrics.get("maxNesting", 0)
            if nesting >= 3:
                sev = "High" if nesting >= 4 else "Medium"
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Deep Nesting",
                    sev,
                    name,
                    fn_line,
                    f"Function '{name}' has a maximum nesting depth of {nesting} (threshold: 3 levels).",
                    "Apply Guard Clauses & Early Returns: Invert conditions and return early to flatten indented branch pyramids.",
                    "// Replace:\n// if (condition) { /* deep block */ }\n// With:\n// if (!condition) return; /* flat flow */",
                ))

            # 3. High Cyclomatic Complexity
            cc = metrics.get("cyclomatic", 1)
            if cc > 10:
                sev = "Critical" if cc > 15 else "High"
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "High Cyclomatic Complexity",
                    sev,
                    name,
                    fn_line,
                    f"Function '{name}' has a cyclomatic complexity of {cc} (threshold: 10).",
                    "Decompose Decision Tree: Split independent decision pathways into separate functions, or replace switch/cascades with lookup tables.",
                    "// Split complex decision points into isolated predicate functions.",
                ))

            # 4. Too Many Parameters
            param_count = len(fn.get("params", []))
            if param_count > 4:
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Too Many Parameters",
                    "Low",
                    name,
                    fn_line,
                    f"Function '{name}' accepts {param_count} parameters (recommended max: 4).",
                    "Introduce Parameter Object: Group related parameters into a C struct to simplify call sites and decouple arguments.",
                    "// e.g. struct Options { int a; int b; ... };\n// void func(struct Options *opts);",
                ))

    def _check_unused_variables(self):
        for sym in self.symbol_table_data.get("flatSymbols", []):
            if sym.get("kind") in ("variable", "parameter") and not sym.get("isUsed"):
                if sym.get("scopeName") == "main" and sym.get("kind") == "parameter":
                    continue
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Unused Variable",
                    "Low",
                    sym.get("scopeName", "unknown"),
                    sym.get("line", 1),
                    f"{sym.get('kind').capitalize()} '{sym.get('name')}' is declared but never read or referenced.",
                    "Remove Unused Identifier: Delete this unused declaration to clean up the symbol table and eliminate dead storage.",
                    f"// Remove '{sym.get('name')}' declaration",
                ))

    def _check_dead_code(self):
        for d in self.diagnostics:
            if d.get("rule") == "unreachable-code":
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Dead / Unreachable Code",
                    "Medium",
                    "function",
                    d.get("line", 1),
                    d.get("message", "Unreachable code detected"),
                    "Remove Dead Code: Delete the unreachable statements following return, break, or continue.",
                    "// Remove statements after return/break",
                ))

    def _check_duplicated_logic(self):
        """Identifies duplicate non-trivial statements or condition expressions across the AST."""
        statement_hashes: Dict[str, List[Tuple[str, int, str]]] = {}

        def hash_node(node: Dict[str, Any]) -> str:
            # Deterministic representation ignoring line/col
            t = node.get("type")
            if t in ("Number", "String", "Identifier"):
                return f"{t}:{node.get('value') or node.get('name')}"
            if t == "BinaryExpr":
                return f"Bin:{node.get('op')}({hash_node(node.get('left'))},{hash_node(node.get('right'))})"
            if t == "Assign":
                return f"Assign:{node.get('name') or node.get('op')}={hash_node(node.get('value'))}"
            if t == "Call":
                args = ",".join(hash_node(a) for a in node.get("args", []))
                return f"Call:{node.get('callee')}({args})"
            if t == "ExprStmt":
                return f"ExprStmt:{hash_node(node.get('expr'))}"
            return t or ""

        for fn in self.ast.get("functions", []):
            fn_name = fn["name"]

            def visit_stmts(stmts):
                for s in stmts:
                    t = s.get("type")
                    if t in ("ExprStmt", "Declaration", "Assign"):
                        h = hash_node(s)
                        if len(h) > 8:  # Non-trivial statement
                            if h not in statement_hashes:
                                statement_hashes[h] = []
                            statement_hashes[h].append((fn_name, s.get("line", 1), t))
                    elif t == "If":
                        visit_stmts([s.get("consequent")])
                        if s.get("alternate"):
                            visit_stmts([s.get("alternate")])
                    elif t in ("While", "For", "DoWhile"):
                        visit_stmts([s.get("body")])
                    elif t == "Block":
                        visit_stmts(s.get("statements", []))

            visit_stmts(fn.get("body", {}).get("statements", []))

        # Check statements that appear 3 or more times
        reported_hashes = set()
        for h, occurrences in statement_hashes.items():
            if len(occurrences) >= 3 and h not in reported_hashes:
                reported_hashes.add(h)
                fn_name, line, stmt_type = occurrences[0]
                lines_str = ", ".join(f"L{occ[1]}" for occ in occurrences[:4])
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Duplicated Logic",
                    "Medium",
                    fn_name,
                    line,
                    f"Identical logic block detected {len(occurrences)} times ({lines_str}).",
                    "Extract Helper Function / Macro: Consolidate repeated statements into a single reusable helper function or loop construct.",
                    "// Extract repeated logic into a shared helper function",
                ))

    def _check_magic_numbers(self):
        """Detects arbitrary numeric literals (not 0, 1, -1) hardcoded in expressions."""
        magic_numbers: Dict[str, List[Tuple[str, int]]] = {}

        def visit(node, fn_name):
            if not isinstance(node, dict):
                return
            t = node.get("type")
            if t == "Number":
                val = str(node.get("value", ""))
                # Filter out standard 0, 1, 2, -1
                if val not in ("0", "1", "2", "-1", "0.0", "1.0"):
                    if val not in magic_numbers:
                        magic_numbers[val] = []
                    magic_numbers[val].append((fn_name, node.get("line", 1)))
            for v in node.values():
                if isinstance(v, dict):
                    visit(v, fn_name)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            visit(item, fn_name)

        for fn in self.ast.get("functions", []):
            visit(fn.get("body"), fn["name"])

        # Report magic numbers that occur
        for num, occurrences in magic_numbers.items():
            if len(occurrences) >= 2:
                fn_name, line = occurrences[0]
                self.smells.append(CodeSmell(
                    self._next_id(),
                    "Magic Number",
                    "Low",
                    fn_name,
                    line,
                    f"Magic number '{num}' is hardcoded across {len(occurrences)} places.",
                    f"Define Named Constant: Replace hardcoded literal '{num}' with a meaningful `#define CONST_NAME {num}` or `const` variable.",
                    f"#define MAX_LIMIT {num}  // Replace literal with constant",
                ))
