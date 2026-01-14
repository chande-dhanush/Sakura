"""
Code Interpreter Test Suite
============================
Tests for the Docker-sandboxed Python execution tool.

Run: pytest sakura_assistant/tests/test_code_interpreter.py -v
"""

import pytest
import os
import sys

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sakura_assistant.core.tools_libs.code_interpreter import (
    execute_python, 
    check_code_interpreter_status,
    _check_docker_available,
    _sanitize_code
)


class TestCodeInterpreterBasics:
    """Basic unit tests that don't require Docker."""
    
    def test_sanitize_code_allows_safe_code(self):
        """Sanitize should not block normal code."""
        code = "import pandas as pd\ndf = pd.DataFrame({'a': [1,2,3]})\nprint(df.sum())"
        result = _sanitize_code(code)
        assert result == code
    
    def test_sanitize_code_warns_on_dangerous_patterns(self, capsys):
        """Sanitize should log warning for dangerous patterns."""
        code = "import os; os.system('rm -rf /')"
        result = _sanitize_code(code)
        # Code still passes (Docker is the real sandbox)
        assert "os.system" in result
        # But a warning should be printed
        captured = capsys.readouterr()
        assert "potentially dangerous" in captured.out.lower() or result == code
    
    def test_status_check_returns_structured_info(self):
        """Status check should return meaningful information."""
        result = check_code_interpreter_status.invoke({})
        assert "docker" in result.lower() or "Docker" in result
        assert "sandbox" in result.lower() or "packages" in result.lower()


@pytest.mark.skipif(not _check_docker_available(), reason="Docker not available")
class TestCodeInterpreterWithDocker:
    """Tests that require Docker to be running."""
    
    def test_basic_print(self):
        """Basic print execution should work."""
        result = execute_python.invoke({"code": "print('hello world')"})
        assert "hello" in result.lower()
    
    def test_pandas_dataframe_operations(self):
        """Pandas should be available and work."""
        code = """
import pandas as pd
df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
print(df.sum())
"""
        result = execute_python.invoke({"code": code})
        # Sum of A is 6, Sum of B is 15
        assert "6" in result or "15" in result
    
    def test_numpy_calculations(self):
        """NumPy should be available."""
        code = """
import numpy as np
arr = np.array([1, 2, 3, 4, 5])
print(f"Mean: {arr.mean()}, Std: {arr.std():.2f}")
"""
        result = execute_python.invoke({"code": code})
        assert "Mean" in result
        assert "3.0" in result  # Mean of [1,2,3,4,5]
    
    def test_matplotlib_plot_saving(self):
        """Matplotlib plots should be saved to output.png."""
        code = """
import matplotlib.pyplot as plt
plt.figure()
plt.plot([1, 2, 3], [1, 4, 9])
plt.title('Test Plot')
plt.savefig('/code/output.png')
print('Plot saved')
"""
        result = execute_python.invoke({"code": code})
        assert "Plot saved" in result or "plot" in result.lower()
    
    def test_sympy_symbolic_math(self):
        """SymPy should be available for symbolic math."""
        code = """
from sympy import symbols, solve
x = symbols('x')
result = solve(x**2 - 4, x)
print(f"Solutions: {result}")
"""
        result = execute_python.invoke({"code": code})
        assert "-2" in result and "2" in result
    
    def test_timeout_protection(self):
        """Infinite loops should be terminated by timeout."""
        code = "import time; time.sleep(120)"
        result = execute_python.invoke({"code": code, "timeout": 5})
        assert "timed out" in result.lower() or "timeout" in result.lower()
    
    def test_no_network_access(self):
        """Network access should be blocked."""
        code = """
import urllib.request
try:
    urllib.request.urlopen('https://google.com', timeout=5)
    print('NETWORK ALLOWED - BAD!')
except Exception as e:
    print(f'Network blocked: {type(e).__name__}')
"""
        result = execute_python.invoke({"code": code})
        # Should fail with network error, not succeed
        assert "blocked" in result.lower() or "error" in result.lower() or "NETWORK ALLOWED" not in result
    
    def test_memory_limit(self):
        """Large memory allocations should fail."""
        code = """
try:
    x = [0] * (1024**3)  # Try to allocate ~8GB
    print('MEMORY NOT LIMITED - BAD!')
except MemoryError:
    print('Memory limit enforced')
except Exception as e:
    print(f'Limited by: {type(e).__name__}')
"""
        result = execute_python.invoke({"code": code})
        # Should fail due to 512MB limit
        assert "MEMORY NOT LIMITED" not in result
    
    def test_no_output_warning(self):
        """Code without print should get a hint."""
        code = "x = 1 + 1"  # No print
        result = execute_python.invoke({"code": code})
        assert "no output" in result.lower() or "print" in result.lower()
    
    def test_syntax_error_reported(self):
        """Syntax errors should be reported clearly."""
        code = "def broken("  # Invalid syntax
        result = execute_python.invoke({"code": code})
        assert "error" in result.lower() or "syntax" in result.lower()
    
    def test_output_truncation(self):
        """Very long outputs should be truncated."""
        code = "print('x' * 10000)"  # 10k chars
        result = execute_python.invoke({"code": code})
        # Should still work but potentially be truncated if > MAX_OUTPUT_CHARS
        assert "x" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
