# Sakura V13 Python Sandbox
# Lightweight code execution environment for Code Interpreter tool
# Security: No network, 512MB RAM, non-root user
FROM python:3.11-slim

# Pre-install common data science packages (reduces execution time)
RUN pip install --no-cache-dir \
    pandas==2.1.0 \
    numpy==1.24.0 \
    matplotlib==3.7.0 \
    seaborn==0.12.0 \
    scipy==1.11.0 \
    sympy==1.12

# Create non-root user for security
RUN useradd -m -u 1000 sandbox
USER sandbox
WORKDIR /code

# Default entrypoint
CMD ["python"]
