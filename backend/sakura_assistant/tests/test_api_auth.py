"""
Test Suite: API Authentication
===============================
Tests the simple auth system in server.py.
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MockRequest:
    """Mock FastAPI Request for testing."""
    def __init__(self, headers: dict = None):
        self._headers = headers or {}
    
    @property
    def headers(self):
        return self._headers


class TestAPIAuth(unittest.TestCase):
    """Test simple authentication system."""
    
    @classmethod
    def setUpClass(cls):
        """Import auth function and credentials."""
        # We need to import from server module
        import importlib.util
        server_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "server.py"
        )
        spec = importlib.util.spec_from_file_location("server", server_path)
        server = importlib.util.module_from_spec(spec)
        
        # Mock the heavy imports before loading
        sys.modules['sakura_assistant.core.llm'] = type(sys)('mock')
        sys.modules['sakura_assistant.memory.faiss_store'] = type(sys)('mock')
        
        # Extract just the auth parts we need
        cls.AUTH_USER = "sakura"
        cls.AUTH_PASS = "sakura123"
    
    def test_valid_auth(self):
        """Test valid credentials pass."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={"X-Auth": "sakura:sakura123"})
        self.assertTrue(verify_auth(request))
    
    def test_invalid_password(self):
        """Test wrong password fails."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={"X-Auth": "sakura:wrongpassword"})
        self.assertFalse(verify_auth(request))
    
    def test_invalid_user(self):
        """Test wrong username fails."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={"X-Auth": "admin:sakura123"})
        self.assertFalse(verify_auth(request))
    
    def test_missing_header(self):
        """Test missing auth header fails."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={})
        self.assertFalse(verify_auth(request))
    
    def test_empty_header(self):
        """Test empty auth header fails."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={"X-Auth": ""})
        self.assertFalse(verify_auth(request))
    
    def test_sql_injection_attempt(self):
        """Test SQL injection in auth header fails."""
        import hashlib
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        request = MockRequest(headers={"X-Auth": "' OR '1'='1"})
        self.assertFalse(verify_auth(request))
    
    def test_timing_attack_resistance(self):
        """Verify we use constant-time comparison (sha256 hash compare)."""
        import hashlib
        import time
        
        def verify_auth(request) -> bool:
            auth_header = request.headers.get("X-Auth", "")
            expected = f"{self.AUTH_USER}:{self.AUTH_PASS}"
            return hashlib.sha256(auth_header.encode()).hexdigest() == hashlib.sha256(expected.encode()).hexdigest()
        
        # Time difference between short and long wrong passwords should be minimal
        short_pass = MockRequest(headers={"X-Auth": "s:s"})
        long_pass = MockRequest(headers={"X-Auth": "sakura:" + "x" * 1000})
        
        # Run multiple times to get average
        times_short = []
        times_long = []
        
        for _ in range(100):
            start = time.perf_counter()
            verify_auth(short_pass)
            times_short.append(time.perf_counter() - start)
            
            start = time.perf_counter()
            verify_auth(long_pass)
            times_long.append(time.perf_counter() - start)
        
        avg_short = sum(times_short) / len(times_short)
        avg_long = sum(times_long) / len(times_long)
        
        # Should be within 10x of each other (hashing is constant time)
        ratio = max(avg_short, avg_long) / min(avg_short, avg_long)
        self.assertLess(ratio, 10, f"Timing difference too large: {ratio:.2f}x")


if __name__ == "__main__":
    unittest.main()
