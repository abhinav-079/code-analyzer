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

    # Heuristic analysis
    lines = code.splitlines()
    for line in lines[:25]:
        stripped = line.strip()
        code_part = stripped.split("//")[0].strip()
        if not code_part.startswith("#include") and not code_part.startswith("#define"):
            code_part = code_part.split("#")[0].strip()
        if not code_part:
            continue
        if code_part.startswith("def ") or (code_part.startswith("import ") and not code_part.endswith(";")) or "elif " in code_part:
            return "python"
        if "public class " in code_part or "System.out.print" in code_part or "public static void main" in code_part:
            return "java"
        if code_part.startswith("function ") or "function(" in code_part or "console.log" in code_part or (code_part.startswith("const ") and "=>" in code_part) or code_part.startswith("let "):
            return "javascript"
        if "#include <iostream>" in code_part or "std::" in code_part or "using namespace std" in code_part or "class " in code_part:
            return "cpp"

    return "c"


def analyze_multilang(code: str, language: Optional[str] = None, filename: str = "") -> Dict[str, Any]:
    """
    Analyzes code in C, C++, Python, Java, or JavaScript.
    Produces identical schema for UI rendering (tokens, ast, metrics, symbol table, diagnostics, cfgs, smells, quality).
    """
    lang = (language or detect_language(code, filename)).lower()

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
