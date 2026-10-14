"""
Semantic analysis module for the Code Quality Analyzer.

Performs:
- Scope-aware symbol table construction
- Undeclared identifier and function detection
- Variable redeclaration checking
- Unused variable and parameter detection
- Basic type checking (assignments, return types, function call arity)
- Unreachable code detection
"""

from typing import List, Dict, Any, Optional
from .symbol_table import SymbolTable, Symbol

BUILTIN_FUNCTIONS = {
    "printf": {"returnType": "int", "variadic": True},
    "scanf": {"returnType": "int", "variadic": True},
    "puts": {"returnType": "int", "params": ["char*"]},
    "getchar": {"returnType": "int", "params": []},
    "putchar": {"returnType": "int", "params": ["int"]},
    "malloc": {"returnType": "void*", "params": ["int"]},
    "free": {"returnType": "void", "params": ["void*"]},
    "exit": {"returnType": "void", "params": ["int"]},
    "strlen": {"returnType": "int", "params": ["char*"]},
    "strcpy": {"returnType": "char*", "params": ["char*", "char*"]},
    "strcmp": {"returnType": "int", "params": ["char*", "char*"]},
    "abs": {"returnType": "int", "params": ["int"]},
    "sqrt": {"returnType": "double", "params": ["double"]},
    "pow": {"returnType": "double", "params": ["double", "double"]},
    "memset": {"returnType": "void*", "params": ["void*", "int", "int"]},
    "memcpy": {"returnType": "void*", "params": ["void*", "void*", "int"]},
}


class Diagnostic:
    def __init__(self, severity: str, message: str, line: int = 1, col: int = 1, rule: str = ""):
        self.severity = severity  # 'error', 'warning', 'info'
        self.message = message
        self.line = line
        self.col = col
        self.rule = rule

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "rule": self.rule,
        }

    def __repr__(self):
        return f"[{self.severity.upper()}] Line {self.line}:{self.col} - {self.message}"


class SemanticAnalyzer:
    def __init__(self, ast: Dict[str, Any]):
        self.ast = ast
        self.symbol_table = SymbolTable()
        self.diagnostics: List[Diagnostic] = []
        self.current_function: Optional[Dict[str, Any]] = None
        self.function_signatures: Dict[str, Dict[str, Any]] = {}

    def analyze(self) -> Dict[str, Any]:
        self._collect_function_signatures()
        self._analyze_globals()

        for fn in self.ast.get("functions", []):
            self._analyze_function(fn)

        self._check_unused_symbols()

        return {
            "symbolTable": self.symbol_table.to_dict(),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "errorCount": len([d for d in self.diagnostics if d.severity == "error"]),
            "warningCount": len([d for d in self.diagnostics if d.severity == "warning"]),
        }

    def _collect_function_signatures(self):
        for fn in self.ast.get("functions", []):
            name = fn["name"]
            ret_type = fn["returnType"]
            params = fn.get("params", [])
            line = fn.get("line", 1)
            col = fn.get("col", 1)

            if name in self.function_signatures:
                self.diagnostics.append(Diagnostic(
                    "error",
                    f"Redefinition of function '{name}' (previously defined)",
                    line, col, "redefinition"
                ))
            else:
                self.function_signatures[name] = {
                    "returnType": ret_type,
                    "params": params,
                    "line": line,
                    "col": col,
                }
                # Also define in global symbol table
                self.symbol_table.define(name, ret_type, "function", line, col)

    def _analyze_globals(self):
        for g_decl in self.ast.get("globals", []):
            self._analyze_declaration(g_decl)

    def _analyze_function(self, fn: Dict[str, Any]):
        self.current_function = fn
        name = fn["name"]
        fn_line = fn.get("line", 1)
        fn_col = fn.get("col", 1)

        # Enter function scope
        self.symbol_table.enter_scope(name, scope_type="function")

        # Define parameters in function scope
        for param in fn.get("params", []):
            p_name = param["name"]
            p_type = param["varType"]
            p_line = param.get("line", fn_line)
            p_col = param.get("col", fn_col)

            sym, ok = self.symbol_table.define(p_name, p_type, "parameter", p_line, p_col)
            if not ok:
                self.diagnostics.append(Diagnostic(
                    "error",
                    f"Duplicate parameter name '{p_name}' in function '{name}'",
                    p_line, p_col, "duplicate-parameter"
                ))

        # Analyze function body
        body = fn.get("body", {})
        self._analyze_block(body, create_scope=False)

        # Check if non-void function has a return statement
        if fn["returnType"] != "void" and name != "main":
            has_return = self._has_return_statement(body)
            if not has_return:
                self.diagnostics.append(Diagnostic(
                    "warning",
                    f"Non-void function '{name}' may reach end of non-void function without returning a value",
                    fn_line, fn_col, "missing-return"
                ))

        self.symbol_table.exit_scope()
        self.current_function = None

    def _has_return_statement(self, block: Dict[str, Any]) -> bool:
        if not block:
            return False
        for stmt in block.get("statements", []):
            if stmt.get("type") == "Return":
                return True
            if stmt.get("type") == "If":
                conseq_has = self._has_return_statement(stmt.get("consequent")) if stmt.get("consequent", {}).get("type") == "Block" else (stmt.get("consequent", {}).get("type") == "Return")
                alt_has = False
                if stmt.get("alternate"):
                    alt_has = self._has_return_statement(stmt.get("alternate")) if stmt.get("alternate", {}).get("type") == "Block" else (stmt.get("alternate", {}).get("type") == "Return")
                if conseq_has and alt_has:
                    return True
        return False

    def _analyze_block(self, block: Dict[str, Any], create_scope: bool = True):
        if not block:
            return
        if create_scope:
            self.symbol_table.enter_scope(f"block_L{block.get('line', 1)}", scope_type="block")

        statements = block.get("statements", [])
        unreachable = False

        for stmt in statements:
            if unreachable:
                self.diagnostics.append(Diagnostic(
                    "warning",
                    f"Unreachable statement detected: {stmt.get('type')}",
                    stmt.get("line", 1), stmt.get("col", 1), "unreachable-code"
                ))

            self._analyze_statement(stmt)

            # If return or break or continue, subsequent statements in this block are unreachable
            if stmt.get("type") in ("Return", "Break", "Continue"):
                unreachable = True

        if create_scope:
            self.symbol_table.exit_scope()

    def _analyze_statement(self, stmt: Dict[str, Any]):
        if not stmt:
            return
        t = stmt.get("type")

        if t == "Declaration":
            self._analyze_declaration(stmt)

        elif t == "Block":
            self._analyze_block(stmt, create_scope=True)

        elif t == "If":
            self._analyze_expression(stmt.get("condition"))
            consequent = stmt.get("consequent")
            if consequent:
                if consequent.get("type") == "Block":
                    self._analyze_block(consequent, create_scope=True)
                else:
                    self._analyze_statement(consequent)
            alternate = stmt.get("alternate")
            if alternate:
                if alternate.get("type") == "Block":
                    self._analyze_block(alternate, create_scope=True)
                else:
                    self._analyze_statement(alternate)

        elif t == "For":
            self.symbol_table.enter_scope(f"for_L{stmt.get('line', 1)}", scope_type="block")
            if stmt.get("init"):
                self._analyze_statement(stmt["init"])
            if stmt.get("condition"):
                self._analyze_expression(stmt["condition"])
            if stmt.get("update"):
                self._analyze_expression(stmt["update"])
            body = stmt.get("body")
            if body:
                if body.get("type") == "Block":
                    self._analyze_block(body, create_scope=False)
                else:
                    self._analyze_statement(body)
            self.symbol_table.exit_scope()

        elif t == "While":
            self._analyze_expression(stmt.get("condition"))
            body = stmt.get("body")
            if body:
                if body.get("type") == "Block":
                    self._analyze_block(body, create_scope=True)
                else:
                    self._analyze_statement(body)

        elif t == "DoWhile":
            body = stmt.get("body")
            if body:
                if body.get("type") == "Block":
                    self._analyze_block(body, create_scope=True)
                else:
                    self._analyze_statement(body)
            self._analyze_expression(stmt.get("condition"))

        elif t == "Switch":
            self._analyze_expression(stmt.get("discriminant"))
            for case in stmt.get("cases", []):
                if case.get("test"):
                    self._analyze_expression(case["test"])
                for s in case.get("consequent", []):
                    self._analyze_statement(s)

        elif t == "Return":
            val = stmt.get("value")
            fn_ret_type = self.current_function.get("returnType") if self.current_function else "void"
            if val is not None:
                val_type = self._analyze_expression(val)
                if fn_ret_type == "void":
                    self.diagnostics.append(Diagnostic(
                        "error",
                        "Void function should not return a value",
                        stmt.get("line", 1), stmt.get("col", 1), "return-type-mismatch"
                    ))
                elif val_type and val_type != "unknown" and val_type != fn_ret_type:
                    # Allow numeric conversions between int/float/double/char
                    num_types = {"int", "float", "double", "char", "short", "long"}
                    if not (val_type in num_types and fn_ret_type in num_types):
                        self.diagnostics.append(Diagnostic(
                            "warning",
                            f"Return type mismatch: expected '{fn_ret_type}', got '{val_type}'",
                            stmt.get("line", 1), stmt.get("col", 1), "return-type-mismatch"
                        ))
            else:
                if fn_ret_type != "void":
                    self.diagnostics.append(Diagnostic(
                        "error",
                        f"Non-void function '{self.current_function.get('name')}' must return a value of type '{fn_ret_type}'",
                        stmt.get("line", 1), stmt.get("col", 1), "return-empty"
                    ))

        elif t == "ExprStmt":
            self._analyze_expression(stmt.get("expr"))

    def _analyze_declaration(self, decl: Dict[str, Any]):
        name = decl["name"]
        var_type = decl["varType"]
        line = decl.get("line", 1)
        col = decl.get("col", 1)

        sym, ok = self.symbol_table.define(name, var_type, "variable", line, col)
        if not ok:
            prev_line = sym.line if sym else "unknown"
            self.diagnostics.append(Diagnostic(
                "error",
                f"Redeclaration of variable '{name}' in the same scope (previously defined at line {prev_line})",
                line, col, "redeclaration"
            ))

        if decl.get("init"):
            init_node = decl["init"]
            if init_node.get("type") == "ArrayInit":
                for item in init_node.get("items", []):
                    self._analyze_expression(item)
            else:
                init_type = self._analyze_expression(init_node)
                if init_type and init_type != "unknown":
                    num_types = {"int", "float", "double", "char", "short", "long"}
                    if not (var_type in num_types and init_type in num_types):
                        if var_type != init_type and not ("*" in var_type and init_type == "void*"):
                            self.diagnostics.append(Diagnostic(
                                "warning",
                                f"Type mismatch in initialization of '{name}': declared '{var_type}', assigned '{init_type}'",
                                line, col, "type-mismatch"
                            ))

    def _analyze_expression(self, expr: Optional[Dict[str, Any]]) -> str:
        """Analyzes an expression and attempts to infer its result type."""
        if not expr:
            return "unknown"
        t = expr.get("type")
        line = expr.get("line", 1)
        col = expr.get("col", 1)

        if t == "Number":
            val = expr.get("value", "")
            return "float" if "." in val else "int"

        if t == "String":
            return "char*"

        if t == "Char":
            return "char"

        if t == "Identifier":
            name = expr.get("name")
            sym = self.symbol_table.lookup(name)
            if sym is None:
                # Check if it's a known function or builtin
                if name not in self.function_signatures and name not in BUILTIN_FUNCTIONS:
                    self.diagnostics.append(Diagnostic(
                        "error",
                        f"Use of undeclared identifier '{name}'",
                        line, col, "undeclared-identifier"
                    ))
                return "unknown"
            else:
                self.symbol_table.record_usage(name, line, col, "read")
                return sym.var_type

        if t == "Assign":
            target = expr.get("target")
            target_name = expr.get("name")
            target_type = "unknown"

            if target_name:
                sym = self.symbol_table.lookup(target_name)
                if sym is None:
                    self.diagnostics.append(Diagnostic(
                        "error",
                        f"Assignment to undeclared identifier '{target_name}'",
                        line, col, "undeclared-identifier"
                    ))
                else:
                    self.symbol_table.record_usage(target_name, line, col, "write")
                    target_type = sym.var_type
            elif target:
                target_type = self._analyze_expression(target)

            val_type = self._analyze_expression(expr.get("value"))

            if target_type != "unknown" and val_type != "unknown":
                num_types = {"int", "float", "double", "char", "short", "long"}
                if not (target_type in num_types and val_type in num_types):
                    if target_type != val_type and not ("*" in target_type and val_type == "void*"):
                        self.diagnostics.append(Diagnostic(
                            "warning",
                            f"Type mismatch in assignment: assigning '{val_type}' to '{target_type}'",
                            line, col, "type-mismatch"
                        ))
            return target_type

        if t == "BinaryExpr":
            op = expr.get("op")
            left_type = self._analyze_expression(expr.get("left"))
            right_type = self._analyze_expression(expr.get("right"))

            # Logical and relational operators evaluate to int (0 or 1)
            if op in ("&&", "||", "==", "!=", "<", ">", "<=", ">="):
                return "int"

            # Arithmetic operators
            if left_type == "double" or right_type == "double":
                return "double"
            if left_type == "float" or right_type == "float":
                return "float"
            return left_type if left_type != "unknown" else "int"

        if t == "Unary":
            op = expr.get("op")
            arg_type = self._analyze_expression(expr.get("argument"))
            if op == "!":
                return "int"
            return arg_type

        if t == "PointerDeref":
            arg_type = self._analyze_expression(expr.get("argument"))
            if arg_type.endswith("*"):
                return arg_type[:-1]
            return "unknown"

        if t == "AddressOf":
            arg_type = self._analyze_expression(expr.get("argument"))
            return f"{arg_type}*" if arg_type != "unknown" else "unknown"

        if t == "ArrayAccess":
            arr_type = self._analyze_expression(expr.get("array"))
            self._analyze_expression(expr.get("index"))
            if arr_type.endswith("[]"):
                return arr_type[:-2]
            if arr_type.endswith("*"):
                return arr_type[:-1]
            return "unknown"

        if t == "Call":
            callee = expr.get("callee")
            args = expr.get("args", [])
            arg_types = [self._analyze_expression(a) for a in args]

            # Check builtins
            if callee in BUILTIN_FUNCTIONS:
                b_info = BUILTIN_FUNCTIONS[callee]
                if not b_info.get("variadic") and "params" in b_info:
                    expected_params = b_info["params"]
                    if len(args) != len(expected_params):
                        self.diagnostics.append(Diagnostic(
                            "warning",
                            f"Function '{callee}' expects {len(expected_params)} arguments, but {len(args)} were provided",
                            line, col, "argument-count-mismatch"
                        ))
                return b_info["returnType"]

            # Check user functions
            if callee in self.function_signatures:
                fn_info = self.function_signatures[callee]
                expected_params = fn_info["params"]
                if len(args) != len(expected_params):
                    self.diagnostics.append(Diagnostic(
                        "error",
                        f"Function '{callee}' expects {len(expected_params)} arguments, but {len(args)} were provided",
                        line, col, "argument-count-mismatch"
                    ))
                return fn_info["returnType"]

            # Undeclared function call
            self.diagnostics.append(Diagnostic(
                "warning",
                f"Implicit declaration of function '{callee}'",
                line, col, "implicit-function-declaration"
            ))
            return "int"

        if t == "Ternary":
            self._analyze_expression(expr.get("condition"))
            c_type = self._analyze_expression(expr.get("consequent"))
            a_type = self._analyze_expression(expr.get("alternate"))
            return c_type if c_type != "unknown" else a_type

        return "unknown"

    def _check_unused_symbols(self):
        for sym in self.symbol_table.get_all_symbols():
            if sym.kind in ("variable", "parameter") and not sym.is_used:
                # Main function argc/argv parameters often unused, skip if parameter of main
                if sym.scope_name == "main" and sym.kind == "parameter":
                    continue
                self.diagnostics.append(Diagnostic(
                    "warning",
                    f"Unused {sym.kind} '{sym.name}' declared in {sym.scope_name}",
                    sym.line, sym.col, f"unused-{sym.kind}"
                ))
