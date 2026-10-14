# Code Quality Analyzer: Multi-Language Structural & Semantic Analysis Platform

A compiler-based code quality analysis platform supporting **C, C++, Python, Java, and JavaScript**, written from first principles in Python and served via an interactive Flask web application.

```
Source Code (C, C++, Python, Java, JavaScript)
                     │
[1] Lexical Analysis     ──▶  Classified Tokens with Line & Column tracking
                     │
[2] Syntax Analysis      ──▶  Abstract Syntax Tree (AST) with Source Spans
                     │
[3] Symbol Table         ──▶  Scope Hierarchy, Identifier Tracking & First-Use
                     │
[4] Semantic Analysis    ──▶  Type Checking, Undeclared & Unused Detection
                     │
[5] Control Flow Graph   ──▶  Branch-Aware Basic Blocks & McCabe Complexity (E - N + 2P)
                     │
[6] Smell Detection      ──▶  Deep Nesting, Long Functions, Dead Code & Refactoring
                     │
[7] Metrics & Scoring    ──▶  Per-Function Metrics, Most Complex Highlight & 0-100 Quality Score
                     │
[8] Interactive UI       ──▶  Auto-Centering SVG Flowcharts, Multi-File Workspace & Section Demos
```

---

## 1. Project Overview & Deliverables

This repository implements the full compiler analysis pipeline with multi-language extensions:

| Feature Area | Implementation Description | Key Files |
|---|---|---|
| **Multi-Language Support** | Full parsing, CFG, metrics, and smells for **C, C++, Python, Java, and JavaScript**. | `compiler/multi_language.py`, `compiler/languages/python_analyzer.py` |
| **Control Flow Graph (CFG)** | True branch-aware layout with auto-centering SVG `viewBox`, True/False lanes, and McCabe $M = E - N + 2P$. | `compiler/cfg.py`, `static/app.js` |
| **Semantic Diagnostics** | Live detection of undeclared identifiers, unused variables, redeclarations, return mismatches with editor line-jumping. | `compiler/semantic.py`, `static/app.js` |
| **Section Feature Demos** | Interactive showcase toolbar with dedicated test cases for Metrics, CFG, Diagnostics, Smells, Symbols, AST, and Tokens. | `templates/index.html`, `app.py` |
| **Code Smell Detection** | Automated engine detecting Long Functions, Deep Nesting, High CC, Dead Code, Duplicated Logic, and Magic Numbers. | `compiler/code_smells.py` |
| **Scope-Aware Symbol Table** | Hierarchical scope tree tracking variables, parameters, functions, shadowing, and usage counts. | `compiler/symbol_table.py` |
| **Automated Test Suite** | 35 comprehensive automated tests covering all languages and compiler phases. | `tests/`, `run_tests.py` |

---

## 2. Compiler Pipeline Architecture

### Phase 1: Lexical Analysis (`compiler/lexer.py`)
- Emits classified tokens: `KEYWORD`, `IDENTIFIER`, `NUMBER`, `STRING`, `CHAR`, `OPERATOR`, `DELIMITER`, `PREPROCESSOR`, `EOF`.
- Tracks exact source line numbers and column offsets on each `Token`.
- Gracefully handles preprocessor directives (`#include`, `#define`), single-line comments (`//`), and block comments (`/* ... */`).

### Phase 2: Recursive-Descent Parsing (`compiler/parser.py`)
- Parses a practical C subset into an Abstract Syntax Tree (AST) represented as serializable dictionary structures.
- Supports:
  - Function declarations with typed parameters and return types
  - Compound statements and nested block scoping
  - Variable declarations (scalars, pointers, arrays, initializers)
  - Control constructs: `if/else`, `for`, `while`, `do-while`, `switch/case/default`
  - Jump statements: `return`, `break`, `continue`
  - Expressions climbing precedence: assignment, ternary, logical OR/AND, bitwise, relational, additive, multiplicative, unary (`*`, `&`, `!`, `~`, `++`, `--`), postfix (subscript `[]`, function calls, member access).

### Phase 3: Scope-Aware Symbol Table (`compiler/symbol_table.py`)
- Represents lexical scoping via a tree of `Scope` objects (`global`, `function`, `block`).
- Records each `Symbol`:
  - Name, type (`int`, `float`, `char*`, `int[]`, etc.), and kind (`variable`, `parameter`, `function`).
  - Declaration coordinate (`line`, `col`).
  - Reference tracking: every read/write location, total usage count, and first-use timestamp.
- Allows inner scopes to shadow outer variables while preserving distinct symbol identities.

### Phase 4: Semantic Analysis (`compiler/semantic.py`)
- Validates program semantics beyond syntactic grammar:
  - **Undeclared Identifiers**: Flags variables used without prior declaration in the active scope chain.
  - **Unused Variables**: Flags local variables or parameters declared but never referenced.
  - **Scope Redeclarations**: Forbids duplicate definitions of the same identifier in the same scope.
  - **Type Compatibility**: Checks assignment types, return types (e.g. non-void functions returning values), and argument counts against known signatures and C standard library functions (`printf`, `scanf`, `malloc`, etc.).
  - **Unreachable Code**: Identifies dead statements placed after unconditional `return`, `break`, or `continue`.

### Phase 5: Control Flow Graph (CFG) (`compiler/cfg.py`)
- Converts function ASTs into directed graphs consisting of `BasicBlock` nodes and `CFGEdge` links.
- Classifies blocks: `ENTRY`, `EXIT`, `CONDITION`, `STATEMENT`, `JOIN`.
- Classifies edges: `fallthrough`, `true`, `false`, `loop_back`, `return`, `break`, `continue`.
- Computes McCabe's Cyclomatic Complexity:
  $$M = E - N + 2P$$
  where $E = \text{edges}$, $N = \text{nodes}$, and $P = 1$ (single connected component).
- Verifies graph-based complexity against AST decision-point complexity.

### Phase 6: Code Smell Detection & Automated Refactoring (`compiler/code_smells.py`)
- Evaluates code against industry maintainability rules:
  1. **Long Function**: Flags functions exceeding 25 lines with Extract Method recommendations.
  2. **Deep Nesting**: Flags control structures nested $\ge 3$ levels deep with Guard Clause & Early Return refactorings.
  3. **High Cyclomatic Complexity**: Flags functions with $CC > 10$ with Decision Decomposition advice.
  4. **Dead / Unreachable Code**: Highlights unreachable code blocks for removal.
  5. **Unused Variables**: Recommends removing unreferenced declarations.
  6. **Duplicated Logic**: Identifies repeated statement sequences across branches.
  7. **Magic Numbers**: Flags hardcoded numeric literals with `#define` constant recommendations.

### Phase 7: Quality Scoring & Aggregate Metrics (`compiler/analyzer.py`)
- Generates a holistic 0–100 Maintainability Score and letter grade (`A`, `B`, `C`, `D`, `F`).
- Highlights the **Most Complex Function** across the codebase.
- Aggregates lines of code, decision points, loops, variables, and average complexity per function.

---

## 3. Project Structure

```
code_quality_analyzer/
├── app.py                      Flask API & UI server
├── requirements.txt            Dependencies (Flask >= 3.0)
├── run_tests.py                Automated test runner
├── compiler/
│   ├── __init__.py             Public module interface
│   ├── lexer.py                Lexer with line/col tracking & preprocessor support
│   ├── parser.py               Recursive-descent parser (switches, arrays, pointers)
│   ├── symbol_table.py         Scope hierarchy & symbol usage tracker
│   ├── semantic.py             Semantic analyzer & diagnostic checks
│   ├── cfg.py                  Control Flow Graph builder & McCabe CC calculator
│   ├── code_smells.py          Code smells detector & refactoring advisor
│   ├── analyzer.py             Metrics orchestrator & quality scoring
│   ├── moderate.c              Sample C program (moderate complexity)
│   └── high_complex.c          Sample C program (high complexity, nested branches)
├── templates/
│   └── index.html              Dashboard shell with 10 interactive tabs
├── static/
│   ├── style.css               Dark theme UI, SVG visualizers, card layouts
│   └── app.js                  Interactive SVG graph engine, multi-file manager
└── tests/
    ├── __init__.py
    ├── test_lexer.py           Lexer unit tests
    ├── test_parser.py          Parser unit tests
    ├── test_symbol_table.py    Symbol table scoping tests
    ├── test_semantic.py        Semantic analysis tests
    ├── test_cfg.py             CFG basic block & McCabe formula tests
    ├── test_code_smells.py     Code smell detection tests
    └── test_api.py             Flask API endpoint tests
```

---

## 4. Quick Start

### Installation

```bash
# Activate existing virtual environment or create a new one
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Web Application

```bash
python app.py
```

Open your browser to:
```
http://127.0.0.1:5001
```

The application loads with a pre-analyzed demo program ready for presentation.

### Running the Automated Test Suite

```bash
python run_tests.py
```

All 29 tests execute across the compiler phases and verify zero regressions.

---

## 5. REST API Documentation

### Single File Analysis: `POST /analyze`
**Request Body**:
```json
{
  "code": "int main() { int x = 10; return x; }"
}
```
**Response JSON**:
- `tokens`: List of classified tokens with line and column positions.
- `ast`: Full Abstract Syntax Tree.
- `metrics`: Per-function metrics (`perFunction`), program totals (`program`), and most complex function flag.
- `symbolTable`: Scope tree and flat identifier symbol records with usage counters.
- `diagnostics`: Semantic error and warning messages with line numbers.
- `cfgs`: Directed graph basic blocks and edges for each function.
- `codeSmells`: Detected anti-patterns with severity and refactoring advice.
- `quality`: Overall score (0–100), letter grade (`A`–`F`), and description.

### Multi-File Project Analysis: `POST /analyze_project`
**Request Body**:
```json
{
  "files": [
    { "name": "main.c", "code": "int main() { return 0; }" },
    { "name": "calc.c", "code": "int add(int a, int b) { return a + b; }" }
  ]
}
```
**Response JSON**:
- `summary`: Project-wide LOC, function count, total cyclomatic complexity, average CC, total smells, and overall project grade.
- `files`: Array of individual file analysis results for cross-file comparison.

---

## 6. Project Review 2 / Final Presentation Guide

When demonstrating this project to reviewers or faculty:

1. **Compiler Pipeline Overview**:
   - Point out the 9-stage animated pipeline banner at the top (`Source` &rarr; `Lexer` &rarr; `Parser` &rarr; `AST` &rarr; `Symbol Table` &rarr; `Semantics` &rarr; `CFG` &rarr; `Code Smells` &rarr; `Report`).
   - Emphasize that **no external parsing library (like ANTLR, Clang, or tree-sitter) was used**; every stage is crafted from first principles in standard Python.

2. **Demonstrating Language Extensions**:
   - Select the `Sample: Switch + Pointers + Array` from the dropdown.
   - Show how the parser validates pointer dereferencing (`*buffer`), arrays (`items[0]`), and `switch/case/default` constructs.

3. **Demonstrating Symbol Table & Scoping**:
   - Open the **Symbol Table** tab. Show how variables in different scopes (e.g. `main` vs helper functions) are tracked independently with declaration coordinates and reference counts.

4. **Demonstrating Semantic Diagnostics**:
   - Type an undeclared variable (`z = 5;`) or an unused variable (`int unused = 0;`).
   - Open the **Diagnostics** tab to show live compiler warnings and errors with line and column jumps.

5. **Demonstrating Control Flow Graphs & McCabe's Formula**:
   - Open the **Control Flow Graph** tab.
   - Inspect the interactive flowchart: Entry (teal), Conditions (amber), Basic Blocks (slate), and Exit (purple).
   - Point to the formula verification chip: $M = E - N + 2P$ dynamically matching the decision-point cyclomatic complexity.

6. **Demonstrating Code Smell Detection & Refactoring**:
   - Select `Sample: Code Smells & Refactoring Demo` or `Sample: Multi-Function High Complexity`.
   - Open the **Code Smells** tab. Show the highlighted anti-patterns (Deep Nesting, Long Function, Dead Code) along with actionable refactoring advice (Guard Clauses, Extract Method).

7. **Demonstrating Multi-File Projects & History**:
   - Toggle **Project Mode** to demonstrate multi-file analysis and comparative grading across translation units.
   - Show the **History** tab tracking previous runs and quality score evolutions over time.

---

## 7. Production Deployment & Report Export

### Exporting & Downloading Reports
In the **Quality Report** tab:
- **Download Report (.txt)**: Generates and downloads a clean, formatted plain-text inspection report containing all 4 metric sections, complexity breakdown, and actionable refactoring advice.
- **Download JSON**: Downloads structured compiler output containing tokens, AST, CFGs, symbol table, diagnostics, and metrics for CI/CD integration.
- **Copy Report**: Copies the full report to your clipboard for instant sharing.

### Deployment Options

#### 1. Local Network / Production Server
Run the production server bound to all interfaces:
```bash
./deploy.sh
# Choose option 1
```
Or directly via Python:
```bash
export HOST=0.0.0.0
export PORT=5001
./.venv/bin/python app.py
```

#### 2. Docker & Docker Compose
Build and run the containerized application:
```bash
docker compose up --build -d
```
Access at `http://localhost:5001`.

#### 3. 1-Click Free Cloud Deployment (Render / Railway / Fly.io)
1. Initialize a git repository and push your project to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Code Quality Analyzer"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```
2. **On Render (Recommended)**:
   - Log into [Render](https://render.com) and create a **Web Service**.
   - Connect your GitHub repository.
   - Render automatically reads [`render.yaml`](file:///Users/shanmukha/Downloads/code_quality_analyzer/render.yaml) or configure:
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn wsgi:app`
   - Your app will be live on a public HTTPS URL (e.g., `https://code-quality-analyzer.onrender.com`).
3. **On Railway**:
   - Create a new project from your GitHub repo; Railway automatically uses [`Procfile`](file:///Users/shanmukha/Downloads/code_quality_analyzer/Procfile).

