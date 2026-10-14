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


if __name__ == "__main__":
    unittest.main()
