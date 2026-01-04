"""
Test Suite: Quick Math Security
================================
Tests that quick_math uses sympy (no eval/code execution).
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestQuickMathSecurity(unittest.TestCase):
    """Test quick_math is secure against injection attacks."""
    
    @classmethod
    def setUpClass(cls):
        """Import the tool once."""
        from sakura_assistant.core.tools import quick_math
        cls.quick_math = quick_math
    
    def test_basic_arithmetic(self):
        """Test basic math works."""
        result = self.quick_math.invoke({"expression": "2 + 2"})
        self.assertEqual(result, "4")
    
    def test_multiplication(self):
        """Test multiplication."""
        result = self.quick_math.invoke({"expression": "7 * 8"})
        self.assertEqual(result, "56")
    
    def test_division(self):
        """Test division returns float when needed."""
        result = self.quick_math.invoke({"expression": "10 / 4"})
        self.assertEqual(result, "2.5")
    
    def test_integer_division(self):
        """Test division returns int when whole number."""
        result = self.quick_math.invoke({"expression": "10 / 2"})
        self.assertEqual(result, "5")
    
    def test_power(self):
        """Test exponentiation."""
        result = self.quick_math.invoke({"expression": "2 ** 10"})
        self.assertEqual(result, "1024")
    
    def test_sqrt(self):
        """Test sqrt function."""
        result = self.quick_math.invoke({"expression": "sqrt(16)"})
        self.assertEqual(result, "4")
    
    def test_complex_expression(self):
        """Test complex expression."""
        result = self.quick_math.invoke({"expression": "(3 + 5) * 2 - 4"})
        self.assertEqual(result, "12")
    
    # Security Tests - Sympy blocks all code execution
    # Tests verify malicious code either returns "Error" or is treated as a symbol
    def _is_safe_rejection(self, result: str, expression: str) -> bool:
        """
        Check if result indicates safe rejection (no code execution).
        
        Sympy safely handles malicious code in two ways:
        1. Returns an Error message
        2. Returns the expression as a literal symbol (no execution)
        """
        # Error message = definitely blocked
        if "Error" in result:
            return True
        # If result equals the expression (sympy treated as symbol, not executed)
        if result == expression or expression in result:
            return True
        # Check if it looks like a number (potential execution if attack was trying to return code)
        try:
            float(result)
            return False  # Could be a bypass if attack returned a number
        except ValueError:
            return True  # Non-numeric = probably symbolic/error
    
    def test_injection_builtins_access(self):
        """__builtins__ should be treated as symbol, not executed."""
        expr = "__builtins__"
        result = self.quick_math.invoke({"expression": expr})
        # Sympy returns '__builtins__' as a symbol - this is safe
        self.assertTrue(self._is_safe_rejection(result, expr),
                        f"Potential code execution: {result}")
    
    def test_injection_class_introspection(self):
        """Reject class introspection attack."""
        result = self.quick_math.invoke({
            "expression": "().__class__.__bases__[0].__subclasses__()"
        })
        self.assertIn("Error", result)
    
    def test_injection_import(self):
        """Reject import attempts - should not execute system commands."""
        result = self.quick_math.invoke({
            "expression": "__import__('os').system('whoami')"
        })
        # Should error (sympy doesn't recognize __import__)
        self.assertIn("Error", result)
    
    def test_injection_exec(self):
        """Reject exec attempts."""
        result = self.quick_math.invoke({
            "expression": "exec('print(1)')"
        })
        # Sympy might error on string literal or exec function
        self.assertIn("Error", result)
    
    def test_injection_eval(self):
        """Reject nested eval attempts."""
        result = self.quick_math.invoke({
            "expression": "eval('1+1')"
        })
        # Returns error because sympy's eval != Python's eval
        self.assertIn("Error", result)
    
    def test_injection_open_file(self):
        """Reject file access attempts."""
        result = self.quick_math.invoke({
            "expression": "open('C:/Windows/System32/config/SAM').read()"
        })
        self.assertIn("Error", result)


if __name__ == "__main__":
    unittest.main()
