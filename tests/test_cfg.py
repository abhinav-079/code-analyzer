import unittest
from compiler.lexer import tokenize
from compiler.parser import Parser
from compiler.cfg import build_program_cfgs


class TestCFG(unittest.TestCase):
    def test_cfg_basic_blocks_and_mccabe(self):
        code = """
        int evaluate(int a) {
            if (a > 10) {
                return 1;
            } else {
                return 0;
            }
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        cfgs = build_program_cfgs(ast)
        self.assertIn("evaluate", cfgs)
        cfg = cfgs["evaluate"]

        # McCabe formula: M = E - N + 2P
        e = cfg["edgeCount"]
        n = cfg["nodeCount"]
        expected_cc = e - n + 2
        self.assertEqual(cfg["cyclomaticComplexity"], expected_cc)
        self.assertEqual(cfg["cyclomaticComplexity"], 2)

    def test_cfg_loop_cycle(self):
        code = """
        int sum_to_n(int n) {
            int sum = 0;
            while (n > 0) {
                sum = sum + n;
                n--;
            }
            return sum;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        cfgs = build_program_cfgs(ast)
        cfg = cfgs["sum_to_n"]

        # Check for loop_back edge
        loop_edges = [edge for edge in cfg["edges"] if edge["type"] == "loop_back"]
        self.assertTrue(len(loop_edges) >= 1)
        # 1 base path + 1 while = 2
        self.assertEqual(cfg["cyclomaticComplexity"], 2)

    def test_cfg_ternary_expression(self):
        code = """
        int max(int a, int b) {
            return a > b ? a : b;
        }
        int sign(int x) {
            int s = x > 0 ? 1 : 0;
            return s;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        cfgs = build_program_cfgs(ast)

        # 1. Ternary return
        cfg_max = cfgs["max"]
        self.assertEqual(cfg_max["cyclomaticComplexity"], 2)
        true_edges = [e for e in cfg_max["edges"] if e["type"] == "true"]
        false_edges = [e for e in cfg_max["edges"] if e["type"] == "false"]
        self.assertEqual(len(true_edges), 1)
        self.assertEqual(len(false_edges), 1)

        # 2. Ternary declaration assignment
        cfg_sign = cfgs["sign"]
        self.assertEqual(cfg_sign["cyclomaticComplexity"], 2)
        node_types = [n["type"] for n in cfg_sign["nodes"]]
        self.assertIn("condition", node_types)
        self.assertIn("join", node_types)

    def test_cfg_nested_ternary(self):
        code = """
        int clamp(int v, int low, int high) {
            return v < low ? low : (v > high ? high : v);
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        cfgs = build_program_cfgs(ast)
        cfg_clamp = cfgs["clamp"]
        self.assertEqual(cfg_clamp["cyclomaticComplexity"], 3)


if __name__ == "__main__":
    unittest.main()
