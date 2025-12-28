"""
Input validation and security checks for QEO.

Provides:
- SQL injection prevention
- Request size limits
- Parameter validation
- Sanitization
"""

import logging
import re

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Maximum sizes
MAX_SQL_LENGTH = 50000  # 50KB for SQL queries
MAX_SQLS_COUNT = 100  # Maximum queries in workload analysis
MAX_REQUEST_SIZE = 1_000_000  # 1MB total request size

# Dangerous SQL patterns (basic detection - not foolproof)
DANGEROUS_PATTERNS = [
    r";\s*(DROP|DELETE|TRUNCATE|UPDATE)\s+",  # Stacked queries with dangerous operations
    r";\s*--",  # Comment injection
    r"xp_cmdshell",  # SQL Server command execution
    r"INTO\s+(OUTFILE|DUMPFILE)",  # File operations
    r"LOAD_FILE",  # MySQL file reading
    r"pg_read_file",  # PostgreSQL file reading
    r"COPY\s+.*\s+FROM",  # PostgreSQL COPY
]

# Compiled patterns for performance
_DANGEROUS_PATTERN_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in DANGEROUS_PATTERNS
]


def validate_sql_length(sql: str) -> None:
    """
    Validate SQL query length.

    Args:
        sql: SQL query to validate

    Raises:
        HTTPException: If SQL exceeds maximum length
    """
    if len(sql) > MAX_SQL_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"SQL query too long. Maximum length is {MAX_SQL_LENGTH} characters.",
        )


def check_dangerous_patterns(sql: str) -> None:
    """
    Check for potentially dangerous SQL patterns.

    Note: This is a basic check and not a replacement for proper parameterization
    and database permissions. QEO only executes EXPLAIN, not actual DML/DDL.

    Args:
        sql: SQL query to check

    Raises:
        HTTPException: If dangerous pattern detected
    """
    for pattern in _DANGEROUS_PATTERN_COMPILED:
        if pattern.search(sql):
            logger.warning(f"Dangerous SQL pattern detected: {pattern.pattern}")
            raise HTTPException(
                status_code=400,
                detail="SQL query contains potentially dangerous operations. "
                "This API only supports SELECT queries for analysis.",
            )


def validate_sql_for_analysis(sql: str) -> None:
    """
    Validate SQL query for analysis.

    Performs:
    - Length check
    - Dangerous pattern detection
    - Basic structure validation

    Args:
        sql: SQL query to validate

    Raises:
        HTTPException: If validation fails
    """
    if not sql or not sql.strip():
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    # Trim whitespace
    sql = sql.strip()

    # Check length
    validate_sql_length(sql)

    # Check for dangerous patterns
    check_dangerous_patterns(sql)


def validate_workload_sqls(sqls: list) -> None:
    """
    Validate list of SQL queries for workload analysis.

    Args:
        sqls: List of SQL queries

    Raises:
        HTTPException: If validation fails
    """
    if not sqls:
        raise HTTPException(
            status_code=400, detail="At least one SQL query is required"
        )

    if len(sqls) > MAX_SQLS_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Too many queries. Maximum is {MAX_SQLS_COUNT} queries per workload.",
        )

    # Validate each query
    for i, sql in enumerate(sqls):
        try:
            validate_sql_for_analysis(sql)
        except HTTPException as e:
            raise HTTPException(
                status_code=400, detail=f"Query #{i+1} validation failed: {e.detail}"
            ) from None


async def validate_request_size(request: Request) -> None:
    """
    Validate request body size.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: If request too large
    """
    content_length = request.headers.get("content-length")

    if content_length:
        content_length = int(content_length)
        if content_length > MAX_REQUEST_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request too large. Maximum size is {MAX_REQUEST_SIZE} bytes.",
            )


def sanitize_sql_for_logging(sql: str, max_length: int = 200) -> str:
    """
    Sanitize SQL for logging by truncating and removing sensitive patterns.

    Args:
        sql: SQL query
        max_length: Maximum length for logging

    Returns:
        Sanitized SQL string
    """
    # Truncate
    if len(sql) > max_length:
        sql = sql[:max_length] + "..."

    # Remove potential sensitive data patterns
    # Replace string literals with placeholder
    sql = re.sub(r"'[^']*'", "'***'", sql)

    # Replace numbers that might be IDs
    sql = re.sub(r"\b\d{6,}\b", "***", sql)

    return sql


def sanitize_error_message(error: str) -> str:
    """
    Sanitize error messages to avoid leaking sensitive information.

    Args:
        error: Original error message

    Returns:
        Sanitized error message
    """
    # Remove file paths
    error = re.sub(r'[A-Za-z]:\\[^\s"]+', "[PATH]", error)
    error = re.sub(r'/[^\s"]+/[^\s"]+', "[PATH]", error)

    # Remove IP addresses
    error = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]", error)

    # Remove potential passwords/keys
    error = re.sub(
        r"password[=:][^\s,;]+", "password=[REDACTED]", error, flags=re.IGNORECASE
    )
    error = re.sub(r"token[=:][^\s,;]+", "token=[REDACTED]", error, flags=re.IGNORECASE)
    error = re.sub(r"key[=:][^\s,;]+", "key=[REDACTED]", error, flags=re.IGNORECASE)

    return error


def validate_parameter_range(
    value: int, min_val: int, max_val: int, param_name: str
) -> None:
    """
    Validate parameter is within acceptable range.

    Args:
        value: Parameter value
        min_val: Minimum acceptable value
        max_val: Maximum acceptable value
        param_name: Parameter name for error message

    Raises:
        HTTPException: If value out of range
    """
    if value < min_val or value > max_val:
        raise HTTPException(
            status_code=400,
            detail=f"{param_name} must be between {min_val} and {max_val}",
        )
