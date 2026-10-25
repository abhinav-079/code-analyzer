"""
Lexical analyzer for the supported C subset.

Converts raw source text into a flat list of Token objects:
KEYWORD, IDENTIFIER, NUMBER, STRING, CHAR, OPERATOR, DELIMITER, PREPROCESSOR, EOF.
Tracks line and column numbers for precise error reporting and diagnostics.
"""

KEYWORDS = {
    # C / C++
    "int", "float", "double", "char", "void", "long", "short", "unsigned", "signed", "const", "sizeof",
    "if", "else", "for", "while", "do", "return",
    "switch", "case", "default", "break", "continue",
    "struct", "class", "namespace", "using", "template", "auto", "bool", "true", "false",
    "public", "private", "protected", "virtual", "new", "delete", "nullptr",
    "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast",
    # Java
    "package", "import", "interface", "extends", "implements", "static", "final",
    "this", "super", "boolean", "String", "null", "throws", "try", "catch", "finally",
    # JavaScript
    "function", "let", "var", "undefined", "async", "await", "typeof", "instanceof",
}

MULTI_CHAR_OPERATORS = {
    "==", "!=", "<=", ">=", "&&", "||", "++", "--",
    "+=", "-=", "*=", "/=", "%=", "->",
    "===", "!==", "::", "=>", "<<", ">>",
}

SINGLE_CHAR_OPERATORS = set("+-*/%=<>!&|^~?.")
DELIMITERS = set("(){}[];,:")


class Token:
    __slots__ = ("type", "value", "line", "col")

    def __init__(self, type_, value, line=1, col=1):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def to_dict(self):
        return {
            "type": self.type,
            "value": self.value,
            "line": self.line,
            "col": self.col,
        }

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, L{self.line}:C{self.col})"


def tokenize(source: str):
    tokens = []
    i, n = 0, len(source)
    line = 1
    col = 1

    def is_alpha(c):
        return c.isalpha() or c == "_"

    def is_alnum(c):
        return c.isalnum() or c == "_"

    while i < n:
        c = source[i]

        # Newlines and whitespace
        if c == "\n":
            line += 1
            col = 1
            i += 1
            continue
        if c in " \t\r":
            col += 1
            i += 1
            continue

        # Preprocessor directive (e.g. #include <stdio.h>, #define MAX 100)
        if c == "#":
            start_col = col
            start_i = i
            while i < n and source[i] != "\n":
                i += 1
                col += 1
            directive_text = source[start_i:i].strip()
            tokens.append(Token("PREPROCESSOR", directive_text, line, start_col))
            continue

        # Single-line comment
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
                col += 1
            continue

        # Block comment
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            start_line = line
            start_col = col
            i += 2
            col += 2
            closed = False
            while i + 1 < n:
                if source[i] == "*" and source[i + 1] == "/":
                    i += 2
                    col += 2
                    closed = True
                    break
                if source[i] == "\n":
                    line += 1
                    col = 1
                    i += 1
                else:
                    i += 1
                    col += 1
            if not closed:
                raise SyntaxError(f"Unterminated block comment starting at line {start_line}, col {start_col}")
            continue

        # Numbers (integer or floating point, hex/octal basics)
        if c.isdigit():
            start_col = col
            start_i = i
            if c == "0" and i + 1 < n and source[i + 1] in "xX":
                i += 2
                col += 2
                while i < n and (source[i].isdigit() or source[i] in "abcdefABCDEF"):
                    i += 1
                    col += 1
            else:
                while i < n and source[i].isdigit():
                    i += 1
                    col += 1
                if i < n and source[i] == ".":
                    i += 1
                    col += 1
                    while i < n and source[i].isdigit():
                        i += 1
                        col += 1
            tokens.append(Token("NUMBER", source[start_i:i], line, start_col))
            continue

        # Identifiers and keywords
        if is_alpha(c):
            start_col = col
            start_i = i
            while i < n and is_alnum(source[i]):
                i += 1
                col += 1
            word = source[start_i:i]
            tok_type = "KEYWORD" if word in KEYWORDS else "IDENTIFIER"
            tokens.append(Token(tok_type, word, line, start_col))
            continue

        # String literals
        if c == '"':
            start_line = line
            start_col = col
            start_i = i
            i += 1
            col += 1
            escaped = False
            while i < n:
                curr = source[i]
                if curr == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                i += 1

                if escaped:
                    escaped = False
                elif curr == "\\":
                    escaped = True
                elif curr == '"':
                    break
            else:
                raise SyntaxError(f"Unterminated string literal at line {start_line}, col {start_col}")
            tokens.append(Token("STRING", source[start_i:i], start_line, start_col))
            continue

        # Character literals
        if c == "'":
            start_line = line
            start_col = col
            start_i = i
            i += 1
            col += 1
            if i < n and source[i] == "\\":
                i += 2
                col += 2
            elif i < n:
                i += 1
                col += 1
            if i < n and source[i] == "'":
                i += 1
                col += 1
                tokens.append(Token("CHAR", source[start_i:i], start_line, start_col))
                continue
            else:
                raise SyntaxError(f"Unterminated character literal at line {start_line}, col {start_col}")

        # Three-character operators (e.g. ===, !==)
        three = source[i:i + 3]
        if three in ("===", "!=="):
            tokens.append(Token("OPERATOR", three, line, col))
            i += 3
            col += 3
            continue

        # Two-character operators
        two = source[i:i + 2]
        if two in MULTI_CHAR_OPERATORS:
            tokens.append(Token("OPERATOR", two, line, col))
            i += 2
            col += 2
            continue

        # Single-character operators
        if c in SINGLE_CHAR_OPERATORS:
            tokens.append(Token("OPERATOR", c, line, col))
            i += 1
            col += 1
            continue

        # Delimiters
        if c in DELIMITERS:
            tokens.append(Token("DELIMITER", c, line, col))
            i += 1
            col += 1
            continue

        raise SyntaxError(f"Unexpected character '{c}' at line {line}, col {col}")

    tokens.append(Token("EOF", "", line, col))
    return tokens
