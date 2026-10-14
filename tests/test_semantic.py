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


if __name__ == "__main__":
    unittest.main()
