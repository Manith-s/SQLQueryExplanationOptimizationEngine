"""
Background Task System for Query Profiler

Periodically analyzes stored query profiles to identify optimization opportunities
and generate automated performance reports with recommendations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.core.config import settings
from app.core.profiler import get_profiler

logger = logging.getLogger(__name__)


class ProfilerBackgroundTasks:
    """
    Manages background tasks for automated profiler analysis.
    """

    def __init__(self):
        self.running = False
        self.task = None
        self.profiler = get_profiler()
        self.analysis_results: List[Dict[str, Any]] = []

    async def start(self):
        """Start the background analysis task."""
        if self.running:
            logger.warning("Background tasks already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._run_periodic_analysis())
        logger.info("Profiler background tasks started")

    async def stop(self):
        """Stop the background analysis task."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Profiler background tasks stopped")

    async def _run_periodic_analysis(self):
        """
        Run periodic analysis at configured intervals.
        """
        while self.running:
            try:
                await self._perform_analysis()
                await asyncio.sleep(settings.PROFILER_BACKGROUND_ANALYSIS_INTERVAL_S)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic analysis: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _perform_analysis(self):
        """
        Perform comprehensive analysis of stored profiles.
        """
        logger.info("Starting periodic profiler analysis")

        try:
            # Get all query summaries from last 24 hours
            summaries = await asyncio.to_thread(
                self.profiler.get_all_query_summaries,
                hours=24,
                limit=100
            )

            analysis_batch = []

            for summary in summaries:
                try:
                    # Get detailed statistics
                    stats = await asyncio.to_thread(
                        self.profiler.get_query_statistics,
                        query_hash=summary["query_hash"],
                        hours=24
                    )

                    # Analyze and generate recommendations
                    recommendations = self._generate_recommendations(summary, stats)

                    if recommendations:
                        analysis_batch.append({
                            "query_hash": summary["query_hash"],
                            "query_text": summary["query_text"],
                            "analysis_time": datetime.now().isoformat(),
                            "recommendations": recommendations
                        })

                        # Store recommendations in database
                        await self._store_recommendations(
                            summary["query_hash"],
                            recommendations
                        )

                except Exception as e:
                    logger.error(f"Error analyzing query {summary['query_hash']}: {e}")

            self.analysis_results = analysis_batch
            logger.info(f"Analysis complete. Generated {len(analysis_batch)} reports")

            # Clean up old data
            if datetime.now().hour == 2:  # Run cleanup at 2 AM
                deleted = await asyncio.to_thread(
                    self.profiler.cleanup_old_data,
                    days=settings.PROFILER_CLEANUP_DAYS
                )
                logger.info(f"Cleaned up {deleted} old profiling records")

        except Exception as e:
            logger.error(f"Error in periodic analysis: {e}", exc_info=True)

    def _generate_recommendations(
        self,
        summary: Dict[str, Any],
        stats: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate optimization recommendations based on query statistics.

        Args:
            summary: Query summary data
            stats: Detailed statistics

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        # Check for high execution time
        if summary.get("avg_time_ms", 0) > 1000:
            recommendations.append({
                "type": "performance",
                "priority": 3,
                "title": "High Average Execution Time",
                "description": f"Query has an average execution time of {summary['avg_time_ms']:.2f}ms, "
                               f"which exceeds the recommended threshold of 1000ms.",
                "action": "Consider adding indexes on frequently filtered columns or rewriting the query for better performance."
            })

        # Check for high variance (inconsistent performance)
        exec_time = stats.get("execution_time", {})
        if exec_time:
            std_dev = exec_time.get("std_dev")
            mean = exec_time.get("mean")

            if std_dev and mean:
                cv = (std_dev / mean) * 100  # Coefficient of variation
                if cv > 50:  # More than 50% variation
                    recommendations.append({
                        "type": "stability",
                        "priority": 2,
                        "title": "Inconsistent Performance",
                        "description": f"Query execution time varies significantly (coefficient of variation: {cv:.1f}%). "
                                       f"This suggests cache effects or resource contention.",
                        "action": "Investigate database cache behavior, concurrent query load, and consider query optimization."
                    })

        # Check for degrading performance trend
        trend = stats.get("trend", {})
        if trend.get("direction") == "degrading" and abs(trend.get("change_pct", 0)) > 20:
            recommendations.append({
                "type": "degradation",
                "priority": 3,
                "title": "Performance Degradation Detected",
                "description": f"Query performance has degraded by {trend['change_pct']:.1f}% recently. "
                               f"This may indicate growing data volume or changing execution plans.",
                "action": "Review recent data growth, analyze execution plan changes, and consider index maintenance (VACUUM, ANALYZE)."
            })

        # Check for cache inefficiency
        cache_stats = stats.get("cache_hit_rate", {})
        if cache_stats:
            mean_cache_rate = cache_stats.get("mean")
            if mean_cache_rate and mean_cache_rate < 80:
                recommendations.append({
                    "type": "cache",
                    "priority": 2,
                    "title": "Low Cache Hit Rate",
                    "description": f"Average cache hit rate is only {mean_cache_rate:.1f}%. "
                                   f"This suggests inefficient buffer usage.",
                    "action": "Consider increasing shared_buffers, optimizing query to reduce data scanned, or adding covering indexes."
                })

        # Check for high execution count (potential caching candidate)
        if summary.get("execution_count", 0) > 100:
            recommendations.append({
                "type": "optimization",
                "priority": 1,
                "title": "Frequently Executed Query",
                "description": f"Query has been executed {summary['execution_count']} times in 24 hours. "
                               f"Consider application-level caching.",
                "action": "Implement application-level caching (Redis, Memcached) for this frequently accessed query."
            })

        # Sort by priority (higher first)
        recommendations.sort(key=lambda r: r["priority"], reverse=True)

        return recommendations

    async def _store_recommendations(
        self,
        query_hash: str,
        recommendations: List[Dict[str, Any]]
    ):
        """
        Store recommendations in the profiler database.

        Args:
            query_hash: Query hash identifier
            recommendations: List of recommendations
        """
        try:
            import json

            for rec in recommendations:
                with self.profiler._get_connection() as conn:
                    # Check if similar recommendation already exists (within last 24 hours)
                    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

                    existing = conn.execute("""
                        SELECT id FROM optimization_recommendations
                        WHERE query_hash = ?
                          AND recommendation_type = ?
                          AND created_at > ?
                    """, (query_hash, rec["type"], cutoff)).fetchone()

                    if not existing:
                        conn.execute("""
                            INSERT INTO optimization_recommendations (
                                query_hash, recommendation_type, description,
                                priority, metrics
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (
                            query_hash,
                            rec["type"],
                            f"{rec['title']}: {rec['description']} Action: {rec['action']}",
                            rec["priority"],
                            json.dumps({
                                "title": rec["title"],
                                "action": rec["action"]
                            })
                        ))
                        conn.commit()

        except Exception as e:
            logger.error(f"Error storing recommendations: {e}")

    def get_recent_analysis(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent analysis results.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of analysis result dictionaries
        """
        return self.analysis_results[:limit]

    async def run_manual_analysis(self, query_hash: str) -> Dict[str, Any]:
        """
        Run manual analysis for a specific query.

        Args:
            query_hash: Query hash to analyze

        Returns:
            Analysis result dictionary
        """
        try:
            stats = await asyncio.to_thread(
                self.profiler.get_query_statistics,
                query_hash=query_hash,
                hours=168  # 1 week
            )

            if stats.get("sample_count", 0) == 0:
                return {
                    "status": "error",
                    "message": "No data found for this query"
                }

            # Get summary info
            summaries = await asyncio.to_thread(
                self.profiler.get_all_query_summaries,
                hours=168,
                limit=1000
            )

            summary = next(
                (s for s in summaries if s["query_hash"] == query_hash),
                None
            )

            if not summary:
                return {
                    "status": "error",
                    "message": "Query not found in summaries"
                }

            # Generate recommendations
            recommendations = self._generate_recommendations(summary, stats)

            # Store recommendations
            await self._store_recommendations(query_hash, recommendations)

            return {
                "status": "success",
                "query_hash": query_hash,
                "analysis_time": datetime.now().isoformat(),
                "statistics": stats,
                "recommendations": recommendations
            }

        except Exception as e:
            logger.error(f"Error in manual analysis: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }


# Global background tasks instance
_background_tasks: ProfilerBackgroundTasks = None


def get_background_tasks() -> ProfilerBackgroundTasks:
    """Get or create the global background tasks instance."""
    global _background_tasks
    if _background_tasks is None:
        _background_tasks = ProfilerBackgroundTasks()
    return _background_tasks
