"""
Flask web interface and multi-language API for the Code Quality Analyzer.

Supported Languages: C, C++, Python, Java, JavaScript.
Endpoints:
- GET /: Renders main interactive dashboard
- POST /analyze: Analyzes single source file
- POST /analyze_project: Multi-file project analysis and comparison
"""

import os
from flask import Flask, request, jsonify, render_template
from compiler.multi_language import analyze_multilang, detect_language

app = Flask(__name__)

# Sample cases for EVERY section and language
SAMPLES = {
    # 1. Section: Metrics & Complexity
    "sample_metrics": """int calculate_base(int a, int b) {
    if (a > b) {
        return a - b;
    }
    return b - a;
}

int process_matrix(int n, int threshold) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            if (i == j) {
                sum = sum + i * 2;
            } else if (i > j) {
                if (sum > threshold) {
                    sum = sum - 5;
                } else {
                    sum = sum + 10;
                }
            } else {
                sum = sum + 1;
            }
        }
    }
    return sum;
}

int main() {
    int r1 = calculate_base(10, 20);
    int r2 = process_matrix(5, 50);
    return r1 + r2;
}""",

    # 2. Section: Control Flow Graph (CFG)
    "sample_cfg": """int evaluate_flow(int x, int limit) {
    int count = 0;
    
    if (x > 0) {
        count = count + 10;
    } else {
        count = count - 5;
    }

    while (count < limit) {
        if (count % 2 == 0) {
            count = count + 3;
        } else {
            count = count + 1;
        }
    }

    return count;
}""",

    # 3. Section: Semantic Diagnostics & Error Detection
    "sample_diagnostics": """int compute_sum(int a, int b) {
    int unused_buffer = 100;    // Warning: Unused variable
    undeclared_target = 42;     // Error: Undeclared identifier
    int duplicate = 10;
    int duplicate = 20;         // Error: Redeclaration in same scope
    return a + b;
}

void invalid_return_fn() {
    return 999;                 // Error: Void function returns value
}

int main() {
    int res = compute_sum(5, 10);
    return 0;
}""",

    # 4. Section: Code Smells & Refactoring
    "sample_smells": """int deeply_nested_algorithm(int a, int b, int c, int d, int e) {
    int total = 0;

    // Code Smell: Deep Nesting (>= 4 levels) & High Complexity
    if (a > 0) {
        if (b > 0) {
            if (c > 0) {
                if (d > 0) {
                    if (e > 0) {
                        total = a + b + c + d + e;
                    } else {
                        total = a + b + c + d - 100;
                    }
                }
            }
        }
    }

    // Code Smell: Magic Numbers
    if (total > 500) {
        total = total - 250;
    }

    return total;
    total = total + 99; // Code Smell: Dead / Unreachable Code
}

int main() {
    return deeply_nested_algorithm(1, 2, 3, 4, 5);
}""",

    # 5. Section: Symbol Table & Scoping
    "sample_symbols": """int global_config = 100;

int calculate_scope(int multiplier) {
    int local_val = 50;

    {
        // Variable shadowing in nested block scope
        int local_val = 999;
        local_val = local_val * multiplier;
    }

    local_val = local_val + global_config;
    return local_val;
}

int main() {
    int result = calculate_scope(2);
    return result;
}""",

    # 6. Section: Abstract Syntax Tree (AST)
    "sample_ast": """int parse_expression_demo(int a, int b, int c) {
    int result;
    result = (a + b * c) > (10 - c / 2) && !(a == 0);
    return result ? result * 2 : 0;
}""",

    # 7. Section: Lexical Tokens
    "sample_tokens": """#include <stdio.h>
#define PI 3.14159

// Multi-character operators and token types
void demo_tokens(int *ptr, int arr[]) {
    float rate = 12.5;
    char tag = 'K';
    *ptr += 1;
    if (rate >= 10.0 && tag != 'X') {
        printf("Tokens successfully classified\\n");
    }
}""",

    # 8. Python Language Sample
    "python_sample": """def calculate_metrics(items, threshold):
    total = 0
    unused_debug_counter = 0

    for item in items:
        if item > threshold:
            if item % 2 == 0:
                total += item * 2
            else:
                total += item
        else:
            total += 1

    return total

def main():
    dataset = [2, 5, 8, 12, 15]
    result = calculate_metrics(dataset, 6)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()""",

    # 9. Java Language Sample
    "java_sample": """public class MatrixProcessor {
    public static int processData(int size, int limit) {
        int total = 0;
        for (int i = 0; i < size; i++) {
            if (i < limit) {
                if (i % 2 == 0) {
                    total += i * 2;
                } else {
                    total += i;
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        int result = processData(10, 5);
        System.out.println(result);
    }
}""",

    # 10. JavaScript Language Sample
    "js_sample": """function computeDiscount(cartTotal, isMember) {
    let finalAmount = cartTotal;

    if (cartTotal > 100) {
        if (isMember) {
            finalAmount = cartTotal * 0.8;
        } else {
            finalAmount = cartTotal * 0.9;
        }
    } else {
        if (isMember) {
            finalAmount = cartTotal * 0.95;
        }
    }

    return finalAmount;
}

function runAnalysis() {
    let total = computeDiscount(150, true);
    return total;
}""",

    # 11. C++ Language Sample
    "cpp_sample": """#include <iostream>

class SensorAnalyzer {
public:
    int filterReadings(int val, int threshold) {
        if (val > threshold || val < 0) {
            return -1;
        }
        return val * 2;
    }
};

int main() {
    SensorAnalyzer analyzer;
    int res = analyzer.filterReadings(25, 50);
    return res;
}""",
}


@app.route("/")
def index():
    return render_template("index.html", samples=SAMPLES)


@app.route("/analyze", methods=["POST"])
def analyze_route():
    data = request.get_json(force=True) or {}
    source = data.get("code", "")
    language = data.get("language")

    try:
        result = analyze_multilang(source, language=language)
        return jsonify(result)
    except Exception as exc:
        if language and language != "auto":
            try:
                fallback = analyze_multilang(source, language=None)
                return jsonify(fallback)
            except Exception:
                pass
        return jsonify({
            "error": str(exc),
            "stage": "analyzer",
        }), 400


@app.route("/analyze_project", methods=["POST"])
def analyze_project_route():
    """Analyzes a multi-file project across any supported programming languages."""
    data = request.get_json(force=True) or {}
    files = data.get("files", [])

    if not files:
        return jsonify({"error": "No files provided"}), 400

    file_results = []
    total_loc = 0
    total_functions = 0
    total_cyclomatic = 0
    total_smells = 0
    all_diagnostics = []

    for f in files:
        fname = f.get("name", "untitled.c")
        fcode = f.get("code", "")
        flang = f.get("language") or detect_language(fcode, fname)

        try:
            res = analyze_multilang(fcode, language=flang, filename=fname)
            res["filename"] = fname
            file_results.append(res)

            total_loc += res["metrics"]["program"]["loc"]
            total_functions += res["metrics"]["program"]["functions"]
            total_cyclomatic += res["metrics"]["program"]["cyclomatic"]
            total_smells += len(res["codeSmells"])
            for d in res["diagnostics"]:
                all_diagnostics.append({**d, "file": fname})

        except Exception as exc:
            file_results.append({
                "filename": fname,
                "error": str(exc),
                "language": flang,
            })

    valid_results = [r for r in file_results if "error" not in r]
    avg_cc = round(total_cyclomatic / total_functions, 1) if total_functions > 0 else 0
    overall_quality = 0
    if valid_results:
        overall_quality = round(sum(r["quality"]["score"] for r in valid_results) / len(valid_results))

    project_summary = {
        "fileCount": len(files),
        "totalLoc": total_loc,
        "totalFunctions": total_functions,
        "totalCyclomatic": total_cyclomatic,
        "averageCyclomatic": avg_cc,
        "totalCodeSmells": total_smells,
        "overallQualityScore": overall_quality,
        "diagnosticsCount": len(all_diagnostics),
    }

    return jsonify({
        "summary": project_summary,
        "files": file_results,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    print(f"Starting Code Quality Analyzer on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
