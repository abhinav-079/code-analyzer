"""
Recursive-descent parser for the expanded C subset.

Supports:
- Function definitions with typed parameters and return types
- Block scoping and nested compound statements
- Variable declarations (scalars, pointers, arrays, optional initializers)
- Control structures: if/else, for, while, do-while, switch/case/default
- Jump statements: return, break, continue
- Expressions: assignment, ternary, logical, relational, arithmetic, bitwise,
  unary (+, -, !, ~, *, &), postfix (++, --, array subscript, calls, member access)
- Preprocessor directives at top level (skipped gracefully)
- Line and column tracking on all AST nodes
"""

TYPE_KEYWORDS = {
    "int", "float", "double", "char", "void", "long", "short", "unsigned", "signed", "const",
    "bool", "boolean", "String", "auto", "let", "var", "size_t",
}
MODIFIERS = {
    "public", "private", "protected", "static", "final", "virtual",
    "inline", "async", "export", "override", "synchronized",
}
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%="}


class ParseError(Exception):
    def __init__(self, message, line=None, col=None):
        self.message = message
        self.line = line
        self.col = col
        if line is not None and col is not None:
            super().__init__(f"Line {line}, Col {col}: {message}")
        elif line is not None:
            super().__init__(f"Line {line}: {message}")
        else:
            super().__init__(message)


class Parser:
    def __init__(self, tokens):
        # Ignore EOF and top-level preprocessor directives during token ingestion
        self.toks = [t for t in tokens if t.type not in ("EOF", "PREPROCESSOR")]
        self.pos = 0

    # -- token helpers -----------------------------------------------
    def peek(self, offset=0):
        idx = self.pos + offset
        if idx < len(self.toks):
            return self.toks[idx]
        from .lexer import Token
        last_line = self.toks[-1].line if self.toks else 1
        last_col = self.toks[-1].col if self.toks else 1
        return Token("EOF", "", last_line, last_col)

    def skip_modifiers(self):
        while self.pos < len(self.toks) and self.toks[self.pos].type == "KEYWORD" and self.toks[self.pos].value in MODIFIERS:
            self.pos += 1

    def is_type(self):
        t = self.peek()
        if t.type == "KEYWORD" and (t.value in TYPE_KEYWORDS or t.value in ("struct", "class")):
            return True
        if t.type == "IDENTIFIER":
            next1 = self.peek(1)
            if next1.type == "IDENTIFIER" or next1.value in ("*", "&"):
                return True
            if next1.value == "[" and self.peek(2).value == "]":
                return True
        return False

    def at(self, type_, value=None):
        t = self.peek()
        return t.type == type_ and (value is None or t.value == value)

    def expect(self, type_, value=None):
        if not self.at(type_, value):
            t = self.peek()
            expected_desc = value if value is not None else type_
            found_desc = f"'{t.value}'" if t.value else t.type
            raise ParseError(f"Expected {expected_desc} but found {found_desc}", t.line, t.col)
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def advance(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    # -- type parser helper ------------------------------------------
    def parse_full_type(self):
        self.skip_modifiers()
        tok = self.peek()
        if tok.type == "KEYWORD" and tok.value in ("struct", "class"):
            self.advance()
            name = self.expect("IDENTIFIER").value
            base_type = f"{tok.value} {name}"
        elif tok.type == "KEYWORD":
            base_type = self.advance().value
        elif tok.type == "IDENTIFIER":
            base_type = self.advance().value
        else:
            base_type = "void"

        # Compound types like "unsigned int", "long long", "long double"
        while self.at("KEYWORD") and self.peek().value in ("int", "long", "short", "char", "double", "float"):
            base_type += " " + self.advance().value
        while self.at("KEYWORD", "const"):
            self.advance()

        # Pointers and references (*, &)
        while self.at("OPERATOR", "*") or self.at("OPERATOR", "&") or self.at("KEYWORD", "const"):
            p_tok = self.advance()
            if p_tok.value in ("*", "&"):
                base_type += p_tok.value
        # Array brackets in type e.g. int[], int[][], int[10][20]
        while self.at("DELIMITER", "["):
            self.advance()
            while not self.at("DELIMITER", "]") and not self.at("EOF"):
                self.advance()
            self.expect("DELIMITER", "]")
            base_type += "[]"
        return base_type

    def looks_like_cast(self):
        if not self.at("DELIMITER", "("):
            return False
        look = 1
        # Skip leading qualifiers like const, unsigned, signed, struct, class
        while self.pos + look < len(self.toks) and self.toks[self.pos + look].value in (
            "const", "unsigned", "signed", "struct", "class"
        ):
            look += 1
        if self.pos + look >= len(self.toks):
            return False
        first_tok = self.toks[self.pos + look]
        # Must be a type keyword or identifier
        if not ((first_tok.type == "KEYWORD" and first_tok.value in TYPE_KEYWORDS) or first_tok.type == "IDENTIFIER"):
            return False
        look += 1
        # Second word in compound types like "unsigned int", "struct Foo"
        if self.pos + look < len(self.toks) and self.toks[self.pos + look].type in ("KEYWORD", "IDENTIFIER"):
            if self.toks[self.pos + look].value in TYPE_KEYWORDS or first_tok.value in ("struct", "class"):
                look += 1
        # Pointers, references, array brackets
        while self.pos + look < len(self.toks) and self.toks[self.pos + look].value in ("*", "&", "[", "]", "const"):
            look += 1
        if self.pos + look >= len(self.toks) or self.toks[self.pos + look].value != ")":
            return False

        # If the type token was a built-in type keyword (like float, int, char, double, void, etc.),
        # (float) CANNOT be a valid parenthesized expression value in C/C++/Java. It is always a cast!
        if first_tok.type == "KEYWORD" and first_tok.value in TYPE_KEYWORDS:
            return True

        # If it was an identifier (e.g. (MyType)x or (x) + 1):
        # We look at the token right after ')'
        after_pos = self.pos + look + 1
        if after_pos >= len(self.toks):
            return False
        after_tok = self.toks[after_pos]
        if after_tok.value in (";", ",", "]", "}", ")") or (after_tok.type == "OPERATOR" and after_tok.value not in ("*", "&", "+", "-", "!", "~", "++", "--")):
            return False
        return True

    def looks_like_function(self):
        lookahead = 0
        while self.pos + lookahead < len(self.toks) and (
            self.toks[self.pos + lookahead].value in TYPE_KEYWORDS
            or self.toks[self.pos + lookahead].value in MODIFIERS
            or self.toks[self.pos + lookahead].value in ("*", "&", "struct", "class")
        ):
            lookahead += 1
        if self.pos + lookahead < len(self.toks) and self.toks[self.pos + lookahead].type == "IDENTIFIER":
            if self.pos + lookahead + 1 < len(self.toks) and self.toks[self.pos + lookahead + 1].type == "IDENTIFIER":
                lookahead += 1
        return (
            self.pos + lookahead < len(self.toks)
            and self.toks[self.pos + lookahead].type == "IDENTIFIER"
            and self.pos + lookahead + 1 < len(self.toks)
            and self.toks[self.pos + lookahead + 1].value == "("
        )

    # -- grammar -------------------------------------------------------
    def parse_program(self):
        functions = []
        global_declarations = []
        while self.pos < len(self.toks):
            # Skip package, import, using statements
            if self.at("KEYWORD", "package") or self.at("KEYWORD", "import") or self.at("KEYWORD", "using"):
                while not self.at("DELIMITER", ";") and not self.at("EOF"):
                    self.advance()
                if self.at("DELIMITER", ";"):
                    self.advance()
                continue

            # Skip modifiers
            self.skip_modifiers()
            if self.pos >= len(self.toks):
                break

            # Class definition (Java / C++)
            if self.at("KEYWORD", "class") or self.at("KEYWORD", "interface"):
                class_fns = self.parse_class()
                functions.extend(class_fns)
                continue

            # JavaScript 'function'
            if self.at("KEYWORD", "function"):
                fn = self.parse_js_function()
                if fn:
                    functions.append(fn)
                continue

            # Check for function or global declaration
            if self.looks_like_function():
                fn = self.parse_function()
                if fn:
                    functions.append(fn)
            elif self.is_type():
                decl_stmts = self.parse_declaration()
                if isinstance(decl_stmts, list):
                    global_declarations.extend(decl_stmts)
                elif decl_stmts:
                    global_declarations.append(decl_stmts)
            else:
                self.advance()

        return {
            "type": "Program",
            "functions": functions,
            "globals": global_declarations,
            "line": 1,
            "col": 1,
        }

    def parse_class(self):
        tok_class = self.advance()
        class_name = self.expect("IDENTIFIER").value
        while not self.at("DELIMITER", "{") and not self.at("EOF"):
            self.advance()
        self.expect("DELIMITER", "{")

        class_functions = []
        while not self.at("DELIMITER", "}") and not self.at("EOF"):
            self.skip_modifiers()
            if self.at("DELIMITER", "}") or self.at("EOF"):
                break

            # Access specifiers in C++ (public:, private:, protected:)
            if self.at("KEYWORD") and self.peek().value in ("public", "private", "protected") and self.peek(1).value == ":":
                self.advance()
                self.advance()
                continue

            if self.at("KEYWORD", "function"):
                fn = self.parse_js_function(prefix=class_name)
                if fn:
                    class_functions.append(fn)
            elif self.looks_like_function():
                fn = self.parse_function(prefix=class_name)
                if fn:
                    class_functions.append(fn)
            elif self.is_type():
                self.parse_declaration()
            else:
                # Constructor or method without explicit type: Name(...) { ... }
                if self.at("IDENTIFIER") and self.peek(1).value == "(":
                    method_name = self.advance().value
                    self.expect("DELIMITER", "(")
                    params = []
                    while not self.at("DELIMITER", ")") and not self.at("EOF"):
                        p_type = self.parse_full_type() if self.is_type() else "any"
                        p_name = self.expect("IDENTIFIER").value if self.at("IDENTIFIER") else f"arg_{len(params)}"
                        params.append({"varType": p_type, "name": p_name, "line": tok_class.line, "col": 1})
                        if self.at("DELIMITER", ","):
                            self.advance()
                    self.expect("DELIMITER", ")")
                    body = self.parse_block()
                    class_functions.append({
                        "type": "FunctionDecl",
                        "name": f"{class_name}.{method_name}",
                        "returnType": "void",
                        "params": params,
                        "body": body,
                        "line": tok_class.line,
                        "col": tok_class.col,
                    })
                else:
                    self.advance()

        self.expect("DELIMITER", "}")
        if self.at("DELIMITER", ";"):
            self.advance()
        return class_functions

    def parse_js_function(self, prefix=""):
        tok_start = self.expect("KEYWORD", "function")
        name = self.expect("IDENTIFIER").value if self.at("IDENTIFIER") else "anonymous"
        if prefix:
            name = f"{prefix}.{name}"
        self.expect("DELIMITER", "(")
        params = []
        while not self.at("DELIMITER", ")") and not self.at("EOF"):
            p_name = self.expect("IDENTIFIER").value
            params.append({"varType": "any", "name": p_name, "line": tok_start.line, "col": 1})
            if self.at("DELIMITER", ","):
                self.advance()
        self.expect("DELIMITER", ")")
        body = self.parse_block()
        return {
            "type": "FunctionDecl",
            "name": name,
            "returnType": "function",
            "params": params,
            "body": body,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_function(self, prefix=""):
        tok_start = self.peek()
        return_type = self.parse_full_type()
        name_tok = self.expect("IDENTIFIER")
        name = f"{prefix}.{name_tok.value}" if prefix else name_tok.value
        self.expect("DELIMITER", "(")
        params = []
        while not self.at("DELIMITER", ")"):
            p_tok = self.peek()
            p_type = self.parse_full_type()
            # If void with no param name
            if p_type == "void" and self.at("DELIMITER", ")"):
                break
            p_name = self.expect("IDENTIFIER").value
            while self.at("DELIMITER", "["):
                self.advance()
                if not self.at("DELIMITER", "]"):
                    self.parse_expr()
                self.expect("DELIMITER", "]")
                p_type += "[]"
            params.append({
                "varType": p_type,
                "name": p_name,
                "line": p_tok.line,
                "col": p_tok.col,
            })
            if self.at("DELIMITER", ","):
                self.advance()
        self.expect("DELIMITER", ")")

        # Check for function prototype (ends with ;) vs definition (has body {)
        if self.at("DELIMITER", ";"):
            self.advance()
            return None  # Ignore standalone prototype declaration

        body = self.parse_block()
        return {
            "type": "FunctionDecl",
            "name": name,
            "returnType": return_type,
            "params": params,
            "body": body,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_block(self):
        tok_start = self.expect("DELIMITER", "{")
        statements = []
        while not self.at("DELIMITER", "}") and not self.at("EOF"):
            stmt = self.parse_statement()
            if isinstance(stmt, list):
                statements.extend(stmt)
            elif stmt is not None:
                statements.append(stmt)
        self.expect("DELIMITER", "}")
        return {
            "type": "Block",
            "statements": statements,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_statement(self):
        tok = self.peek()
        if self.at("DELIMITER", "{"):
            return self.parse_block()
        if self.at("KEYWORD", "if"):
            return self.parse_if()
        if self.at("KEYWORD", "for"):
            return self.parse_for()
        if self.at("KEYWORD", "while"):
            return self.parse_while()
        if self.at("KEYWORD", "do"):
            return self.parse_do_while()
        if self.at("KEYWORD", "switch"):
            return self.parse_switch()
        if self.at("KEYWORD", "break"):
            self.advance()
            self.expect("DELIMITER", ";")
            return {"type": "Break", "line": tok.line, "col": tok.col}
        if self.at("KEYWORD", "continue"):
            self.advance()
            self.expect("DELIMITER", ";")
            return {"type": "Continue", "line": tok.line, "col": tok.col}
        if self.at("KEYWORD", "return"):
            return self.parse_return()
        if self.is_type():
            return self.parse_declaration()
        return self.parse_expr_statement()

    def parse_declaration(self):
        tok_start = self.peek()
        base_type = self.parse_full_type()
        declarations = []

        while True:
            # Check for pointer qualifier on variable
            var_type = base_type
            while self.at("OPERATOR", "*"):
                self.advance()
                var_type += "*"

            name_tok = self.expect("IDENTIFIER")
            name = name_tok.value
            array_sizes = []

            # Multi-dimensional array declaration e.g. int arr[10][20];
            while self.at("DELIMITER", "["):
                self.advance()
                dim_size = None
                if not self.at("DELIMITER", "]"):
                    dim_size = self.parse_expr()
                self.expect("DELIMITER", "]")
                var_type += "[]"
                array_sizes.append(dim_size)

            array_size = array_sizes[0] if array_sizes else None

            init = None
            if self.at("OPERATOR", "="):
                self.advance()
                # Initializer can be expression or array list { ... }
                if self.at("DELIMITER", "{"):
                    init = self.parse_array_init()
                else:
                    init = self.parse_expr()

            declarations.append({
                "type": "Declaration",
                "varType": var_type,
                "name": name,
                "init": init,
                "arraySize": array_size,
                "arraySizes": array_sizes,
                "line": name_tok.line,
                "col": name_tok.col,
            })

            if self.at("DELIMITER", ","):
                self.advance()
            else:
                break

        self.expect("DELIMITER", ";")
        return declarations if len(declarations) > 1 else declarations[0]

    def parse_array_init(self):
        tok_start = self.expect("DELIMITER", "{")
        items = []
        while not self.at("DELIMITER", "}") and not self.at("EOF"):
            if self.at("DELIMITER", "{"):
                items.append(self.parse_array_init())
            else:
                items.append(self.parse_expr())
            if self.at("DELIMITER", ","):
                self.advance()
            elif not self.at("DELIMITER", "}"):
                break
        self.expect("DELIMITER", "}")
        return {
            "type": "ArrayInit",
            "items": items,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_if(self):
        tok_start = self.expect("KEYWORD", "if")
        self.expect("DELIMITER", "(")
        condition = self.parse_expr()
        self.expect("DELIMITER", ")")
        consequent = self.parse_statement()
        alternate = None
        if self.at("KEYWORD", "else"):
            self.advance()
            alternate = self.parse_statement()
        return {
            "type": "If",
            "condition": condition,
            "consequent": consequent,
            "alternate": alternate,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_for(self):
        tok_start = self.expect("KEYWORD", "for")
        self.expect("DELIMITER", "(")
        init = None
        if self.is_type():
            init = self.parse_declaration()
        elif not self.at("DELIMITER", ";"):
            init = {"type": "ExprStmt", "expr": self.parse_expr(), "line": tok_start.line, "col": tok_start.col}
            self.expect("DELIMITER", ";")
        else:
            self.advance()
        condition = None
        if not self.at("DELIMITER", ";"):
            condition = self.parse_expr()
        self.expect("DELIMITER", ";")
        update = None
        if not self.at("DELIMITER", ")"):
            update = self.parse_expr()
        self.expect("DELIMITER", ")")
        body = self.parse_statement()
        return {
            "type": "For",
            "init": init,
            "condition": condition,
            "update": update,
            "body": body,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_while(self):
        tok_start = self.expect("KEYWORD", "while")
        self.expect("DELIMITER", "(")
        condition = self.parse_expr()
        self.expect("DELIMITER", ")")
        body = self.parse_statement()
        return {
            "type": "While",
            "condition": condition,
            "body": body,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_do_while(self):
        tok_start = self.expect("KEYWORD", "do")
        body = self.parse_statement()
        self.expect("KEYWORD", "while")
        self.expect("DELIMITER", "(")
        condition = self.parse_expr()
        self.expect("DELIMITER", ")")
        self.expect("DELIMITER", ";")
        return {
            "type": "DoWhile",
            "condition": condition,
            "body": body,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_switch(self):
        tok_start = self.expect("KEYWORD", "switch")
        self.expect("DELIMITER", "(")
        discriminant = self.parse_expr()
        self.expect("DELIMITER", ")")
        self.expect("DELIMITER", "{")
        cases = []

        while not self.at("DELIMITER", "}") and not self.at("EOF"):
            case_tok = self.peek()
            if self.at("KEYWORD", "case"):
                self.advance()
                test_expr = self.parse_expr()
                self.expect("DELIMITER", ":")
                consequent = []
                while not self.at("KEYWORD", "case") and not self.at("KEYWORD", "default") and not self.at("DELIMITER", "}"):
                    c_stmt = self.parse_statement()
                    if isinstance(c_stmt, list):
                        consequent.extend(c_stmt)
                    elif c_stmt:
                        consequent.append(c_stmt)
                cases.append({
                    "type": "Case",
                    "test": test_expr,
                    "consequent": consequent,
                    "line": case_tok.line,
                    "col": case_tok.col,
                })
            elif self.at("KEYWORD", "default"):
                self.advance()
                self.expect("DELIMITER", ":")
                consequent = []
                while not self.at("KEYWORD", "case") and not self.at("KEYWORD", "default") and not self.at("DELIMITER", "}"):
                    c_stmt = self.parse_statement()
                    if isinstance(c_stmt, list):
                        consequent.extend(c_stmt)
                    elif c_stmt:
                        consequent.append(c_stmt)
                cases.append({
                    "type": "Default",
                    "consequent": consequent,
                    "line": case_tok.line,
                    "col": case_tok.col,
                })
            else:
                tok_err = self.peek()
                raise ParseError(f"Expected 'case' or 'default' inside switch, found '{tok_err.value}'", tok_err.line, tok_err.col)

        self.expect("DELIMITER", "}")
        return {
            "type": "Switch",
            "discriminant": discriminant,
            "cases": cases,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_return(self):
        tok_start = self.expect("KEYWORD", "return")
        value = None
        if not self.at("DELIMITER", ";"):
            value = self.parse_expr()
        self.expect("DELIMITER", ";")
        return {
            "type": "Return",
            "value": value,
            "line": tok_start.line,
            "col": tok_start.col,
        }

    def parse_expr_statement(self):
        expr = self.parse_expr()
        self.expect("DELIMITER", ";")
        return {
            "type": "ExprStmt",
            "expr": expr,
            "line": expr.get("line", 1),
            "col": expr.get("col", 1),
        }

    # -- expressions (precedence climbing) ------------------------------
    def parse_expr(self):
        return self.parse_assignment()

    def parse_assignment(self):
        # Lookahead for lvalue assignment (ID or array or pointer)
        left = self.parse_ternary()
        if self.at("OPERATOR") and self.peek().value in ASSIGN_OPS:
            op_tok = self.advance()
            val = self.parse_assignment()
            return {
                "type": "Assign",
                "target": left,
                "name": left.get("name") if left.get("type") == "Identifier" else None,
                "op": op_tok.value,
                "value": val,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_ternary(self):
        left = self.parse_logical_or()
        if self.at("OPERATOR", "?"):
            q_tok = self.advance()
            consequent = self.parse_expr()
            self.expect("DELIMITER", ":")
            alternate = self.parse_ternary()
            return {
                "type": "Ternary",
                "condition": left,
                "consequent": consequent,
                "alternate": alternate,
                "line": q_tok.line,
                "col": q_tok.col,
            }
        return left

    def parse_logical_or(self):
        left = self.parse_logical_and()
        while self.at("OPERATOR", "||"):
            op_tok = self.advance()
            right = self.parse_logical_and()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_logical_and(self):
        left = self.parse_bitwise_or()
        while self.at("OPERATOR", "&&"):
            op_tok = self.advance()
            right = self.parse_bitwise_or()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_bitwise_or(self):
        left = self.parse_bitwise_xor()
        while self.at("OPERATOR", "|"):
            op_tok = self.advance()
            right = self.parse_bitwise_xor()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_bitwise_xor(self):
        left = self.parse_bitwise_and()
        while self.at("OPERATOR", "^"):
            op_tok = self.advance()
            right = self.parse_bitwise_and()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_bitwise_and(self):
        left = self.parse_equality()
        while self.at("OPERATOR", "&"):
            op_tok = self.advance()
            right = self.parse_equality()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_equality(self):
        left = self.parse_relational()
        while self.at("OPERATOR", "==") or self.at("OPERATOR", "!="):
            op_tok = self.advance()
            right = self.parse_relational()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_relational(self):
        left = self.parse_additive()
        while any(self.at("OPERATOR", o) for o in ("<", ">", "<=", ">=")):
            op_tok = self.advance()
            right = self.parse_additive()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.at("OPERATOR", "+") or self.at("OPERATOR", "-"):
            op_tok = self.advance()
            right = self.parse_multiplicative()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while any(self.at("OPERATOR", o) for o in ("*", "/", "%")):
            op_tok = self.advance()
            right = self.parse_unary()
            left = {
                "type": "BinaryExpr",
                "op": op_tok.value,
                "left": left,
                "right": right,
                "line": op_tok.line,
                "col": op_tok.col,
            }
        return left

    def parse_unary(self):
        tok = self.peek()
        # Pointer dereference *ptr
        if self.at("OPERATOR", "*"):
            self.advance()
            return {
                "type": "PointerDeref",
                "argument": self.parse_unary(),
                "line": tok.line,
                "col": tok.col,
            }
        # Address-of &var
        if self.at("OPERATOR", "&"):
            self.advance()
            return {
                "type": "AddressOf",
                "argument": self.parse_unary(),
                "line": tok.line,
                "col": tok.col,
            }
        # Standard prefix unaries
        if any(self.at("OPERATOR", o) for o in ("-", "+", "!", "~", "++", "--")):
            op_tok = self.advance()
            return {
                "type": "Unary",
                "op": op_tok.value,
                "argument": self.parse_unary(),
                "prefix": True,
                "line": op_tok.line,
                "col": op_tok.col,
            }

        # sizeof operator: sizeof(int), sizeof(expr)
        if self.at("KEYWORD", "sizeof"):
            sz_tok = self.advance()
            self.expect("DELIMITER", "(")
            if self.is_type():
                arg = self.parse_full_type()
            else:
                arg = self.parse_expr()
            self.expect("DELIMITER", ")")
            return {
                "type": "Sizeof",
                "argument": arg,
                "line": sz_tok.line,
                "col": sz_tok.col,
            }

        # C++ explicit casts: static_cast<Type>(expr)
        if self.at("KEYWORD") and self.peek().value in ("static_cast", "reinterpret_cast", "const_cast", "dynamic_cast"):
            cast_tok = self.advance()
            self.expect("OPERATOR", "<")
            cast_type = self.parse_full_type()
            self.expect("OPERATOR", ">")
            self.expect("DELIMITER", "(")
            arg = self.parse_expr()
            self.expect("DELIMITER", ")")
            return {
                "type": "Cast",
                "castKind": cast_tok.value,
                "targetType": cast_type,
                "argument": arg,
                "line": cast_tok.line,
                "col": cast_tok.col,
            }

        # C/C++/Java type cast: (type)expr e.g. (float)usedMemory, (int)x, (void*)ptr
        if self.looks_like_cast():
            cast_start = self.advance()  # consume '('
            cast_type = self.parse_full_type()
            self.expect("DELIMITER", ")")
            arg = self.parse_unary()
            return {
                "type": "Cast",
                "targetType": cast_type,
                "argument": arg,
                "line": cast_start.line,
                "col": cast_start.col,
            }

        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            # Postfix ++ or --
            if self.at("OPERATOR", "++") or self.at("OPERATOR", "--"):
                op_tok = self.advance()
                node = {
                    "type": "Unary",
                    "op": op_tok.value,
                    "argument": node,
                    "prefix": False,
                    "line": op_tok.line,
                    "col": op_tok.col,
                }
            # Array subscript: node[index]
            elif self.at("DELIMITER", "["):
                bracket_tok = self.advance()
                index_expr = self.parse_expr()
                self.expect("DELIMITER", "]")
                node = {
                    "type": "ArrayAccess",
                    "array": node,
                    "index": index_expr,
                    "line": bracket_tok.line,
                    "col": bracket_tok.col,
                }
            # Member access: node.member or node->member or node::member
            elif self.at("OPERATOR", ".") or self.at("OPERATOR", "->") or self.at("OPERATOR", "::"):
                op_tok = self.advance()
                member_tok = self.expect("IDENTIFIER")
                node = {
                    "type": "MemberAccess",
                    "object": node,
                    "op": op_tok.value,
                    "member": member_tok.value,
                    "line": op_tok.line,
                    "col": op_tok.col,
                }
            # Function or method call: node(args...)
            elif self.at("DELIMITER", "("):
                call_tok = self.advance()
                args = []
                while not self.at("DELIMITER", ")") and not self.at("EOF"):
                    args.append(self.parse_expr())
                    if self.at("DELIMITER", ","):
                        self.advance()
                self.expect("DELIMITER", ")")
                callee_str = node.get("name") or node.get("member") or "call"
                node = {
                    "type": "Call",
                    "callee": callee_str,
                    "target": node,
                    "args": args,
                    "line": call_tok.line,
                    "col": call_tok.col,
                }
            else:
                break
        return node

    def parse_primary(self):
        t = self.peek()
        # new ClassName(...)
        if t.type == "KEYWORD" and t.value == "new":
            new_tok = self.advance()
            callee_name = self.expect("IDENTIFIER").value
            args = []
            if self.at("DELIMITER", "("):
                self.advance()
                while not self.at("DELIMITER", ")") and not self.at("EOF"):
                    args.append(self.parse_expr())
                    if self.at("DELIMITER", ","):
                        self.advance()
                self.expect("DELIMITER", ")")
            return {
                "type": "Call",
                "callee": f"new {callee_name}",
                "args": args,
                "line": new_tok.line,
                "col": new_tok.col,
            }

        # Literals and special keywords
        if t.type == "KEYWORD" and t.value in ("true", "false", "null", "undefined", "this", "nullptr"):
            self.advance()
            return {"type": "Identifier", "name": t.value, "line": t.line, "col": t.col}

        if t.type == "NUMBER":
            self.advance()
            return {"type": "Number", "value": t.value, "line": t.line, "col": t.col}
        if t.type == "STRING":
            self.advance()
            return {"type": "String", "value": t.value, "line": t.line, "col": t.col}
        if t.type == "CHAR":
            self.advance()
            return {"type": "Char", "value": t.value, "line": t.line, "col": t.col}
        if t.type == "IDENTIFIER":
            self.advance()
            # Function call e.g. printf(...)
            if self.at("DELIMITER", "("):
                call_tok = self.advance()
                args = []
                while not self.at("DELIMITER", ")") and not self.at("EOF"):
                    args.append(self.parse_expr())
                    if self.at("DELIMITER", ","):
                        self.advance()
                self.expect("DELIMITER", ")")
                return {
                    "type": "Call",
                    "callee": t.value,
                    "args": args,
                    "line": t.line,
                    "col": t.col,
                }
            return {"type": "Identifier", "name": t.value, "line": t.line, "col": t.col}
        if self.at("DELIMITER", "("):
            self.advance()
            e = self.parse_expr()
            self.expect("DELIMITER", ")")
            return e

        if self.at("DELIMITER", "{"):
            return self.parse_array_init()

        if self.at("DELIMITER", "["):
            bracket_tok = self.advance()
            items = []
            while not self.at("DELIMITER", "]") and not self.at("EOF"):
                items.append(self.parse_expr())
                if self.at("DELIMITER", ","):
                    self.advance()
                elif not self.at("DELIMITER", "]"):
                    break
            self.expect("DELIMITER", "]")
            return {
                "type": "ArrayInit",
                "items": items,
                "line": bracket_tok.line,
                "col": bracket_tok.col,
            }

        raise ParseError(f"Unexpected token '{t.value or t.type}' in expression", t.line, t.col)
