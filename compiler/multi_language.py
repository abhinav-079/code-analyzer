"""
Multi-language analysis dispatcher for Code Quality Analyzer.
Supports C, C++, Python, Java, and JavaScript.
"""

from typing import Dict, Any, Optional
from compiler.lexer import tokenize
from compiler.parser import Parser, ParseError
from compiler.analyzer import analyze, complexity_level
from compiler.languages.python_analyzer import analyze_python_source


def detect_language(code: str, filename: str = "") -> str:
    """Detects programming language from filename extension or code syntax heuristics."""
    fname = filename.lower()
    if fname.endswith(".py"):
        return "python"
    if fname.endswith(".java"):
        return "java"
    if fname.endswith((".js", ".jsx", ".mjs")):
        return "javascript"
    if fname.endswith((".cpp", ".hpp", ".cc", ".cxx")):
        return "cpp"
    if fname.endswith((".c", ".h")):
        return "c"

    # Multi-factor confidence scoring
    scores = {"python": 0, "java": 0, "cpp": 0, "javascript": 0, "c": 0}

    # Python indicators
    if "def " in code or "elif " in code:
        scores["python"] += 5
    if "__name__ == '__main__'" in code or '__name__ == "__main__"' in code:
        scores["python"] += 6
    if "import " in code and not "import java." in code and not ";" in code:
        scores["python"] += 3
    if "print(" in code and not ";" in code:
        scores["python"] += 7
    if "None" in code or "True" in code or "False" in code:
        scores["python"] += 4
    if "len(" in code or "range(" in code or "input(" in code:
        scores["python"] += 4
    if not "{" in code and not "}" in code and not ";" in code:
        scores["python"] += 3

    # Java indicators
    if "System.out." in code or "System.err." in code or "System.out.print" in code:
        scores["java"] += 8
    if "public static void main" in code:
        scores["java"] += 8
    if "import java." in code or "package " in code:
        scores["java"] += 6
    if "String[]" in code or "String " in code:
        scores["java"] += 4
    if "boolean " in code:
        scores["java"] += 3
    if "public class " in code:
        scores["java"] += 5
    if "new Scanner" in code or "new ArrayList" in code or "new HashMap" in code:
        scores["java"] += 5
    if "extends " in code or "implements " in code:
        scores["java"] += 4

    # C++ indicators
    if "#include <iostream>" in code or "#include <vector>" in code or "#include <string>" in code or "#include <algorithm>" in code:
        scores["cpp"] += 8
    if "using namespace std" in code:
        scores["cpp"] += 8
    if "std::" in code:
        scores["cpp"] += 7
    if "cout" in code or "cin" in code or "endl" in code:
        scores["cpp"] += 6
    if "nullptr" in code:
        scores["cpp"] += 4
    if "public:" in code or "private:" in code or "protected:" in code:
        scores["cpp"] += 5
    if "template <" in code or "template<" in code:
        scores["cpp"] += 6
    if "class " in code and scores["java"] == 0:
        scores["cpp"] += 2

    # JavaScript indicators
    if "console.log" in code or "console.error" in code:
        scores["javascript"] += 8
    if "function " in code or "function(" in code:
        scores["javascript"] += 5
    if "=>" in code and ("const " in code or "let " in code or "var " in code):
        scores["javascript"] += 6
    if "===" in code or "!==" in code:
        scores["javascript"] += 5
    if "let " in code or "var " in code:
        scores["javascript"] += 3
    if "document." in code or "window." in code:
        scores["javascript"] += 6

    # C indicators
    if "#include <stdio.h>" in code or "#include <stdlib.h>" in code or "#include <string.h>" in code:
        scores["c"] += 6
    if "printf(" in code or "scanf(" in code:
        scores["c"] += 4
    if "malloc(" in code or "free(" in code:
        scores["c"] += 3

    best_lang = max(scores, key=scores.get)
    if scores[best_lang] > 0:
        return best_lang

    if "class " in code:
        return "java" if ("System." in code or "public " in code) else "cpp"

    return "c"


def analyze_multilang(code: str, language: Optional[str] = None, filename: str = "") -> Dict[str, Any]:
    """
    Analyzes code in C, C++, Python, Java, or JavaScript.
    Produces identical schema for UI rendering (tokens, ast, metrics, symbol table, diagnostics, cfgs, smells, quality).
    """
    if not language or str(language).lower() in ("auto", "none", "null", "autodetect", "auto detect"):
        lang = detect_language(code, filename).lower()
    else:
        lang = str(language).lower()

    if lang == "python":
        result = analyze_python_source(code)
        result["language"] = "python"
        return result

    # C, C++, Java, JavaScript handled by compiler front-end
    tokens = tokenize(code)
    ast = Parser(tokens).parse_program()
    loc = len([line for line in code.splitlines() if line.strip()])
    analysis = analyze(ast, loc)
    analysis["complexityLevel"] = complexity_level(analysis["program"]["cyclomatic"])

    return {
        "language": lang,
        "tokens": [t.to_dict() for t in tokens if t.type != "EOF"],
        "ast": ast,
        "metrics": analysis,
        "symbolTable": analysis["symbolTable"],
        "diagnostics": analysis["diagnostics"],
        "cfgs": analysis["cfgs"],
        "codeSmells": analysis["codeSmells"],
        "quality": analysis["quality"],
    }
