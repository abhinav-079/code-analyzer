import unittest
from compiler.lexer import tokenize
from compiler.parser import Parser
from compiler.semantic import SemanticAnalyzer


class TestSemanticAnalyzer(unittest.TestCase):
    def test_undeclared_variable(self):
        code = """
        int main() {
            y = 10;
            return 0;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        rules = [d["rule"] for d in res["diagnostics"]]
        self.assertIn("undeclared-identifier", rules)

    def test_unused_variable_warning(self):
        code = """
        int calc() {
            int unused_num = 42;
            return 0;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        rules = [d["rule"] for d in res["diagnostics"]]
        self.assertIn("unused-variable", rules)

    def test_redefinition_same_scope(self):
        code = """
        void test() {
            int a = 1;
            int a = 2;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        rules = [d["rule"] for d in res["diagnostics"]]
        self.assertIn("redeclaration", rules)

    def test_return_type_mismatch(self):
        code = """
        void bad_fn() {
            return 5;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        rules = [d["rule"] for d in res["diagnostics"]]
        self.assertIn("return-type-mismatch", rules)

    def test_function_called_with_variables_is_referenced(self):
        code = """
        int calculate_base(int a, int b) {
            return a + b;
        }

        int main() {
            int x = 10;
            int y = 20;
            int res = calculate_base(x, y);
            return res;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        flat = res["symbolTable"]["flatSymbols"]
        calc_fn = [s for s in flat if s["name"] == "calculate_base" and s["kind"] == "function"][0]
        self.assertTrue(calc_fn["isUsed"])
        self.assertGreater(calc_fn["usageCount"], 0)

        # Check variables passed
        x_var = [s for s in flat if s["name"] == "x"][0]
        y_var = [s for s in flat if s["name"] == "y"][0]
        self.assertTrue(x_var["isUsed"])
        self.assertTrue(y_var["isUsed"])

    def test_2d_array_parameters_and_symbol_references(self):
        code = """
        int matrix_calc(int m[2][2], int n) {
            int x = m[0][0];
            return x > n ? x : n;
        }
        int main() {
            int matrix[2][2] = {{1, 2}, {3, 4}};
            int res = matrix_calc(matrix, 2);
            return res;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        self.assertEqual(res["errorCount"], 0)
        self.assertEqual(res["warningCount"], 0)

        flat = res["symbolTable"]["flatSymbols"]
        fn_sym = [s for s in flat if s["name"] == "matrix_calc" and s["kind"] == "function"][0]
        self.assertTrue(fn_sym["isUsed"])
        self.assertEqual(fn_sym["usageCount"], 1)

        matrix_sym = [s for s in flat if s["name"] == "matrix" and s["scopeName"] == "main"][0]
        self.assertTrue(matrix_sym["isUsed"])
        self.assertEqual(matrix_sym["type"], "int[][]")

        m_param = [s for s in flat if s["name"] == "m" and s["scopeName"] == "matrix_calc"][0]
        self.assertTrue(m_param["isUsed"])
        self.assertEqual(m_param["type"], "int[][]")

    def test_cast_expression_type_inference(self):
        code = """
        int main() {
            int usedMemory = 50;
            int totalMemory = 100;
            float utilization = ((float)usedMemory / totalMemory) * 100;
            return 0;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = SemanticAnalyzer(ast).analyze()
        self.assertEqual(res["errorCount"], 0)
        flat = res["symbolTable"]["flatSymbols"]
        used_sym = [s for s in flat if s["name"] == "usedMemory"][0]
        total_sym = [s for s in flat if s["name"] == "totalMemory"][0]
        self.assertTrue(used_sym["isUsed"])
        self.assertTrue(total_sym["isUsed"])


if __name__ == "__main__":
    unittest.main()

