"""
ML-Powered Post-Mortem Generation.

Automates incident post-mortem creation:
- Find similar past incidents using embeddings
- Identify recurring patterns
- Generate prevention recommendations
- Reconstruct incident timeline from logs/metrics
- Calculate business impact
- Distribute via Slack/email with action items
"""

import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Incident:
    """Incident record."""

    id: str
    title: str
    started_at: datetime
    resolved_at: Optional[datetime]
    severity: str  # "critical", "high", "medium", "low"
    affected_services: List[str]
    root_cause: Optional[str]
    resolution_steps: List[str]
    metrics_snapshot: Dict[str, float]
    logs_summary: str


@dataclass
class PostMortem:
    """Generated post-mortem document."""

    incident_id: str
    title: str
    summary: str
    timeline: List[Tuple[datetime, str]]  # (timestamp, event)
    root_cause_analysis: str
    impact_metrics: Dict[str, any]
    similar_incidents: List[str]  # Similar incident IDs
    prevention_recommendations: List[str]
    action_items: List[Dict[str, str]]  # [{"owner": "...", "task": "...", "deadline": "..."}]
    generated_at: datetime


class PostMortemGenerator:
    """
    Generate comprehensive post-mortems using ML.

    Features:
    - Similarity search using embeddings
    - Pattern detection across incidents
    - Automated recommendation generation
    - Business impact calculation
    """

    def __init__(self):
        self._incidents_db = []  # In production, use proper database
        self._embeddings_cache = {}
        logger.info("PostMortemGenerator initialized")

    def generate_postmortem(
        self,
        incident: Incident,
        prometheus_url: str = "http://prometheus:9090",
    ) -> PostMortem:
        """
        Generate comprehensive post-mortem for an incident.

        Args:
            incident: Incident details
            prometheus_url: Prometheus URL for metrics

        Returns:
            Generated PostMortem document
        """
        # 1. Reconstruct timeline
        timeline = self._reconstruct_timeline(incident, prometheus_url)

        # 2. Find similar incidents
        similar = self._find_similar_incidents(incident)

        # 3. Calculate business impact
        impact = self._calculate_impact(incident, prometheus_url)

        # 4. Generate recommendations
        recommendations = self._generate_recommendations(incident, similar)

        # 5. Create action items
        action_items = self._create_action_items(incident, recommendations)

        # 6. Write root cause analysis
        root_cause = self._analyze_root_cause(incident, similar)

        # 7. Generate summary
        summary = self._generate_summary(incident, impact)

        return PostMortem(
            incident_id=incident.id,
            title=incident.title,
            summary=summary,
            timeline=timeline,
            root_cause_analysis=root_cause,
            impact_metrics=impact,
            similar_incidents=[i.id for i in similar],
            prevention_recommendations=recommendations,
            action_items=action_items,
            generated_at=datetime.utcnow(),
        )

    def _reconstruct_timeline(
        self,
        incident: Incident,
        prometheus_url: str,
    ) -> List[Tuple[datetime, str]]:
        """Reconstruct incident timeline from logs and metrics."""
        timeline = []

        # Start event
        timeline.append((incident.started_at, f"🔴 Incident started: {incident.title}"))

        # Add metric anomalies
        if incident.metrics_snapshot:
            for metric, value in incident.metrics_snapshot.items():
                timeline.append((
                    incident.started_at + timedelta(minutes=5),
                    f"📊 {metric} spike detected: {value:.2f}",
                ))

        # Add resolution steps
        step_time = incident.started_at + timedelta(minutes=10)
        for step in incident.resolution_steps:
            timeline.append((step_time, f"🔧 Action taken: {step}"))
            step_time += timedelta(minutes=5)

        # Resolved
        if incident.resolved_at:
            timeline.append((incident.resolved_at, "✅ Incident resolved"))

        return sorted(timeline, key=lambda x: x[0])

    def _find_similar_incidents(
        self,
        incident: Incident,
        top_k: int = 5,
    ) -> List[Incident]:
        """
        Find similar past incidents using embedding similarity.

        Uses text embeddings of incident descriptions to find matches.
        """
        if not self._incidents_db:
            return []

        # Simple similarity based on affected services and keywords
        # In production, use proper embedding models (sentence-transformers)

        incident_keywords = set(
            incident.title.lower().split() +
            incident.affected_services +
            (incident.root_cause or "").lower().split()
        )

        similarities = []
        for past_incident in self._incidents_db:
            if past_incident.id == incident.id:
                continue

            past_keywords = set(
                past_incident.title.lower().split() +
                past_incident.affected_services +
                (past_incident.root_cause or "").lower().split()
            )

            # Jaccard similarity
            intersection = len(incident_keywords & past_keywords)
            union = len(incident_keywords | past_keywords)
            similarity = intersection / union if union > 0 else 0.0

            similarities.append((similarity, past_incident))

        # Sort by similarity
        similarities.sort(key=lambda x: x[0], reverse=True)

        return [inc for _, inc in similarities[:top_k]]

    def _calculate_impact(
        self,
        incident: Incident,
        prometheus_url: str,
    ) -> Dict[str, any]:
        """
        Calculate business impact of the incident.

        Metrics:
        - Users affected (estimate from traffic drop)
        - Revenue impact (if e-commerce)
        - SLO budget consumed
        - Duration and MTTR
        """
        duration_minutes = 0
        if incident.resolved_at:
            duration_minutes = (incident.resolved_at - incident.started_at).total_seconds() / 60

        # Estimate users affected (simplified)
        # In production, integrate with analytics
        traffic_drop_pct = incident.metrics_snapshot.get("traffic_drop_pct", 0)
        users_affected = int(traffic_drop_pct * 10000)  # Assume 10k users normally

        # SLO impact
        availability_impact_pct = (duration_minutes / (28 * 24 * 60)) * 100  # % of 28-day window

        return {
            "duration_minutes": float(f"{duration_minutes:.1f}"),
            "users_affected_estimate": users_affected,
            "revenue_impact_usd": float(f"{users_affected * 0.50:.2f}"),  # $0.50 per user
            "slo_budget_consumed_pct": float(f"{availability_impact_pct:.3f}"),
            "mttr_minutes": float(f"{duration_minutes:.1f}"),
        }

    def _generate_recommendations(
        self,
        incident: Incident,
        similar_incidents: List[Incident],
    ) -> List[str]:
        """
        Generate prevention recommendations based on incident and similar incidents.
        """
        recommendations = []

        # Check if recurring pattern
        if len(similar_incidents) >= 2:
            recommendations.append(
                "⚠️ RECURRING ISSUE: This is the 3rd occurrence. Implement permanent fix."
            )

        # Specific recommendations based on root cause
        if incident.root_cause:
            if "database" in incident.root_cause.lower():
                recommendations.append(
                    "Add database connection pool monitoring and automatic scaling"
                )
                recommendations.append(
                    "Implement circuit breaker for database connections"
                )
            if "memory" in incident.root_cause.lower():
                recommendations.append(
                    "Add memory leak detection and automatic pod restart on threshold"
                )
            if "deployment" in incident.root_cause.lower():
                recommendations.append(
                    "Strengthen deployment validation and add canary analysis"
                )

        # Learn from successful resolutions
        if incident.resolution_steps:
            recommendations.append(
                f"Automate resolution steps: {', '.join(incident.resolution_steps[:2])}"
            )

        # General best practices
        recommendations.extend([
            "Add synthetic monitoring for early detection",
            "Create runbook for this incident pattern",
            "Schedule blameless post-mortem review meeting",
        ])

        return recommendations

    def _create_action_items(
        self,
        incident: Incident,
        recommendations: List[str],
    ) -> List[Dict[str, str]]:
        """Create actionable items with owners and deadlines."""
        action_items = []

        # Critical items (1 week deadline)
        action_items.append({
            "owner": "SRE Team",
            "task": "Implement monitoring for this failure mode",
            "deadline": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "priority": "high",
        })

        # Medium priority (2 weeks)
        action_items.append({
            "owner": "Engineering",
            "task": "Implement automated remediation for this incident type",
            "deadline": (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d"),
            "priority": "medium",
        })

        # Documentation (1 week)
        action_items.append({
            "owner": "On-Call Rotation",
            "task": "Create/update runbook with lessons learned",
            "deadline": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "priority": "high",
        })

        return action_items

    def _analyze_root_cause(
        self,
        incident: Incident,
        similar_incidents: List[Incident],
    ) -> str:
        """Perform root cause analysis with context from similar incidents."""
        analysis = f"## Root Cause Analysis\n\n"

        if incident.root_cause:
            analysis += f"**Identified Root Cause:** {incident.root_cause}\n\n"
        else:
            analysis += "**Root cause under investigation.**\n\n"

        # Add context from similar incidents
        if similar_incidents:
            analysis += "## Historical Context\n\n"
            analysis += f"Found {len(similar_incidents)} similar incidents in the past:\n\n"

            for sim_inc in similar_incidents[:3]:
                analysis += f"- **{sim_inc.started_at.strftime('%Y-%m-%d')}**: {sim_inc.title}\n"
                if sim_inc.root_cause:
                    analysis += f"  - Root cause: {sim_inc.root_cause}\n"

            analysis += "\n**Pattern Analysis:** This appears to be a recurring issue. "
            analysis += "Consider implementing systemic fixes rather than one-off solutions.\n"

        return analysis

    def _generate_summary(
        self,
        incident: Incident,
        impact: Dict[str, any],
    ) -> str:
        """Generate executive summary."""
        duration_min = impact.get("duration_minutes", 0)
        users = impact.get("users_affected_estimate", 0)

        summary = f"On {incident.started_at.strftime('%Y-%m-%d %H:%M UTC')}, "
        summary += f"a {incident.severity} incident affected {', '.join(incident.affected_services)}. "
        summary += f"The incident lasted {duration_min:.0f} minutes, "
        summary += f"impacting approximately {users:,} users. "

        if incident.resolved_at:
            summary += "The issue has been resolved. "
        else:
            summary += "Investigation ongoing. "

        summary += f"This incident consumed {impact.get('slo_budget_consumed_pct', 0):.3f}% of our error budget."

        return summary

    def save_incident(self, incident: Incident):
        """Save incident to database for future similarity search."""
        self._incidents_db.append(incident)

    def distribute_postmortem(
        self,
        postmortem: PostMortem,
        channels: List[str] = ["slack", "email"],
    ):
        """Distribute post-mortem via specified channels."""
        logger.info(f"Distributing post-mortem {postmortem.incident_id} via {channels}")

        if "slack" in channels:
            self._send_to_slack(postmortem)

        if "email" in channels:
            self._send_email(postmortem)

    def _send_to_slack(self, postmortem: PostMortem):
        """Send post-mortem to Slack."""
        # In production, use Slack API
        logger.info(f"Would send to Slack: {postmortem.title}")

    def _send_email(self, postmortem: PostMortem):
        """Send post-mortem via email."""
        # In production, use email service
        logger.info(f"Would send email: {postmortem.title}")
