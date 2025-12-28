"""
Query correction module for detecting and fixing SQL syntax errors and common mistakes.

Provides:
- Syntax error detection and suggestions
- Common mistake detection (typos, missing keywords)
- Auto-correction suggestions
- Query validation and repair
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlglot import ParseError, TokenError, parse_one
from sqlglot.errors import ErrorLevel


class QueryError:
    """Represents a query error with correction suggestions."""

    def __init__(
        self,
        error_type: str,
        message: str,
        position: Optional[Tuple[int, int]] = None,
        original: Optional[str] = None,
        corrected: Optional[str] = None,
        confidence: float = 0.0,
        explanation: Optional[str] = None,
    ):
        self.error_type = error_type
        self.message = message
        self.position = position  # (line, column)
        self.original = original
        self.corrected = corrected
        self.confidence = confidence
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "position": self.position,
            "original": self.original,
            "corrected": self.corrected,
            "confidence": self.confidence,
            "explanation": self.explanation,
        }


class QueryCorrector:
    """Main class for query correction and validation."""

    # Common SQL keyword typos and corrections
    KEYWORD_TYPOS = {
        "selct": "SELECT",
        "form": "FROM",
        "wher": "WHERE",
        "wherer": "WHERE",
        "ordr": "ORDER",
        "oder": "ORDER",
        "grup": "GROUP",
        "havng": "HAVING",
        "havig": "HAVING",
        "joinn": "JOIN",
        "innner": "INNER",
        "lefft": "LEFT",
        "rigth": "RIGHT",
        "on": "ON",  # Common but valid, check context
        "limt": "LIMIT",
        "limmit": "LIMIT",
        "offsett": "OFFSET",
        "distinct": "DISTINCT",  # Common but valid
        "distnct": "DISTINCT",
        "unioon": "UNION",
        "unoin": "UNION",
    }

    # Common function name typos
    FUNCTION_TYPOS = {
        "cout": "COUNT",
        "coutn": "COUNT",
        "summ": "SUM",
        "avrg": "AVG",
        "averge": "AVG",
        "maxx": "MAX",
        "minn": "MIN",
        "uppper": "UPPER",
        "lowwer": "LOWER",
        "lenght": "LENGTH",
        "lengt": "LENGTH",
        "substrng": "SUBSTRING",
        "substr": "SUBSTRING",
        "datte": "DATE",
        "datte_trunc": "DATE_TRUNC",
    }

    def __init__(self):
        self.errors: List[QueryError] = []

    def correct_query(self, sql: str) -> Dict[str, Any]:
        """
        Analyze and correct a SQL query.

        Returns:
            Dict with:
            - corrected: Corrected SQL (if corrections found)
            - errors: List of errors found
            - suggestions: List of correction suggestions
            - is_valid: Whether query is syntactically valid
        """
        self.errors = []
        original_sql = sql

        # Step 1: Try to parse the query
        try:
            parse_one(sql, error_level=ErrorLevel.RAISE)
            is_valid = True
        except (ParseError, TokenError) as e:
            is_valid = False
            self._analyze_parse_error(sql, e)

        # Step 2: Check for common typos even if parse succeeds
        corrected_sql = self._fix_common_typos(sql)

        # Step 3: Validate corrected query
        if corrected_sql != sql:
            try:
                parse_one(corrected_sql, error_level=ErrorLevel.RAISE)
                # If corrected version parses, add suggestion
                self.errors.append(
                    QueryError(
                        error_type="typo",
                        message="Query contains typos that were corrected",
                        corrected=corrected_sql,
                        confidence=0.8,
                        explanation="Common keyword/function typos were detected and corrected",
                    )
                )
            except (ParseError, TokenError):
                pass  # Correction didn't help

        # Step 4: Check for common mistakes
        self._check_common_mistakes(sql)

        # Step 5: Check for missing clauses
        self._check_missing_clauses(sql)

        return {
            "original": original_sql,
            "corrected": corrected_sql if corrected_sql != sql else None,
            "is_valid": is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "suggestions": self._generate_suggestions(),
            "can_auto_correct": any(
                e.corrected for e in self.errors if e.confidence > 0.7
            ),
        }

    def _analyze_parse_error(self, sql: str, error: Exception) -> None:
        """Analyze parse error and suggest fixes."""
        error_msg = str(error)

        # Check for missing keyword patterns
        if "expecting" in error_msg.lower():
            # Try to extract what was expected
            match = re.search(r"expecting\s+['\"]?(\w+)", error_msg, re.IGNORECASE)
            if match:
                expected = match.group(1).upper()
                self.errors.append(
                    QueryError(
                        error_type="missing_keyword",
                        message=f"Expected keyword: {expected}",
                        explanation=f"The parser expected '{expected}' but found something else",
                    )
                )

        # Check for syntax errors around specific keywords
        if "unexpected" in error_msg.lower():
            match = re.search(r"unexpected\s+['\"]?(\w+)", error_msg, re.IGNORECASE)
            if match:
                unexpected = match.group(1)
                # Check if it's a typo
                if unexpected.lower() in self.KEYWORD_TYPOS:
                    corrected = self.KEYWORD_TYPOS[unexpected.lower()]
                    self.errors.append(
                        QueryError(
                            error_type="typo",
                            message=f"Typo detected: '{unexpected}' should be '{corrected}'",
                            original=unexpected,
                            corrected=corrected,
                            confidence=0.9,
                            explanation=f"'{unexpected}' appears to be a typo for '{corrected}'",
                        )
                    )

        # Check for unclosed quotes/parentheses
        if "unclosed" in error_msg.lower() or "unterminated" in error_msg.lower():
            self.errors.append(
                QueryError(
                    error_type="syntax",
                    message="Unclosed quotes or parentheses detected",
                    explanation="Check for missing closing quotes (') or parentheses ())",
                )
            )

    def _fix_common_typos(self, sql: str) -> str:
        """Fix common typos in SQL query."""
        corrected = sql

        # Fix keyword typos (case-insensitive, whole word)
        for typo, correct in self.KEYWORD_TYPOS.items():
            # Use word boundaries to avoid partial matches
            pattern = r"\b" + re.escape(typo) + r"\b"
            corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)

        # Fix function name typos
        for typo, correct in self.FUNCTION_TYPOS.items():
            pattern = r"\b" + re.escape(typo) + r"\s*\("
            corrected = re.sub(pattern, correct + "(", corrected, flags=re.IGNORECASE)

        return corrected

    def _check_common_mistakes(self, sql: str) -> None:
        """Check for common SQL mistakes."""
        sql_upper = sql.upper()

        # Check for SELECT without FROM (unless it's SELECT constant)
        if re.search(r"\bSELECT\b", sql_upper) and not re.search(
            r"\bFROM\b", sql_upper
        ):
            # Check if it's a constant SELECT (SELECT 1, SELECT NOW(), etc.)
            if not re.search(
                r"SELECT\s+(?:[\d\'\"]|NOW\(\)|CURRENT_DATE|CURRENT_TIMESTAMP)",
                sql_upper,
            ):
                self.errors.append(
                    QueryError(
                        error_type="missing_clause",
                        message="SELECT statement missing FROM clause",
                        explanation="Most SELECT statements require a FROM clause. Use 'SELECT 1' for constants.",
                    )
                )

        # Check for WHERE without condition
        if re.search(r"\bWHERE\s*$", sql_upper) or re.search(
            r"\bWHERE\s+(?:ORDER|GROUP|LIMIT|;|\Z)", sql_upper
        ):
            self.errors.append(
                QueryError(
                    error_type="syntax",
                    message="WHERE clause missing condition",
                    explanation="WHERE clause must be followed by a condition (e.g., WHERE id = 1)",
                )
            )

        # Check for JOIN without ON
        if re.search(r"\b(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\b", sql_upper):
            # Count JOINs and ONs
            join_count = len(
                re.findall(r"\b(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\b", sql_upper)
            )
            on_count = len(re.findall(r"\bON\b", sql_upper))
            if join_count > on_count:
                self.errors.append(
                    QueryError(
                        error_type="missing_clause",
                        message=f"JOIN statement(s) missing ON clause ({join_count} JOINs, {on_count} ONs)",
                        explanation="Each JOIN must have an ON clause specifying the join condition",
                    )
                )

        # Check for GROUP BY without aggregate functions
        if re.search(r"\bGROUP\s+BY\b", sql_upper) and not re.search(
            r"\b(?:COUNT|SUM|AVG|MAX|MIN|STRING_AGG|ARRAY_AGG)\s*\(", sql_upper
        ):
            self.errors.append(
                QueryError(
                    error_type="logic",
                    message="GROUP BY used without aggregate functions",
                    explanation="GROUP BY is typically used with aggregate functions (COUNT, SUM, AVG, etc.)",
                )
            )

        # Check for HAVING without GROUP BY
        if re.search(r"\bHAVING\b", sql_upper) and not re.search(
            r"\bGROUP\s+BY\b", sql_upper
        ):
            self.errors.append(
                QueryError(
                    error_type="logic",
                    message="HAVING clause used without GROUP BY",
                    explanation="HAVING can only be used with GROUP BY",
                )
            )

    def _check_missing_clauses(self, sql: str) -> None:
        """Check for missing important clauses."""
        sql_upper = sql.upper()

        # Check for UPDATE/DELETE without WHERE (dangerous!)
        if re.search(r"\bUPDATE\s+\w+\s+SET\b", sql_upper) and not re.search(
            r"\bWHERE\b", sql_upper
        ):
            self.errors.append(
                QueryError(
                    error_type="safety",
                    message="UPDATE statement missing WHERE clause",
                    explanation="UPDATE without WHERE will update all rows. Add a WHERE clause to limit the update.",
                    confidence=1.0,
                )
            )

        if re.search(r"\bDELETE\s+FROM\s+\w+", sql_upper) and not re.search(
            r"\bWHERE\b", sql_upper
        ):
            self.errors.append(
                QueryError(
                    error_type="safety",
                    message="DELETE statement missing WHERE clause",
                    explanation="DELETE without WHERE will delete all rows. Add a WHERE clause to limit the deletion.",
                    confidence=1.0,
                )
            )

    def _generate_suggestions(self) -> List[Dict[str, Any]]:
        """Generate correction suggestions from errors."""
        suggestions = []

        for error in self.errors:
            if error.corrected:
                suggestions.append(
                    {
                        "type": "correction",
                        "error": error.error_type,
                        "message": error.message,
                        "fix": error.corrected,
                        "confidence": error.confidence,
                        "explanation": error.explanation,
                    }
                )
            else:
                suggestions.append(
                    {
                        "type": "suggestion",
                        "error": error.error_type,
                        "message": error.message,
                        "explanation": error.explanation,
                    }
                )

        return suggestions


def correct_query(sql: str) -> Dict[str, Any]:
    """
    Convenience function to correct a SQL query.

    Args:
        sql: SQL query string to correct

    Returns:
        Dict with correction results
    """
    corrector = QueryCorrector()
    return corrector.correct_query(sql)
