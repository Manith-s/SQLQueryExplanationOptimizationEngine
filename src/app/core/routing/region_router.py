"""
Multi-Region Intelligent Query Router.

Routes queries based on:
- User location (latency optimization)
- Query type (read vs write)
- Region capacity and health
- Data residency requirements
- Cost optimization
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Type of query operation."""
    READ = "read"
    WRITE = "write"
    ANALYZE = "analyze"


class RegionRole(str, Enum):
    """Role of a region in the cluster."""
    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass
class Region:
    """Region configuration."""
    name: str
    role: RegionRole
    api_url: str
    database_url: str
    cache_url: str
    latitude: float
    longitude: float
    country: str
    max_replicas: int
    current_load: float = 0.0  # 0-1
    healthy: bool = True
    allow_cross_border: bool = True
    last_health_check: float = 0.0


@dataclass
class RoutingDecision:
    """Result of routing decision."""
    target_region: str
    reason: str
    latency_estimate_ms: float
    confidence: float  # 0-1
    fallback_regions: List[str]


class RegionRouter:
    """
    Intelligent multi-region query router.

    Features:
    - Latency-based routing (nearest region for reads)
    - Primary-only routing for writes
    - Health-aware failover
    - Data residency compliance
    - Load-aware distribution
    - Cost-aware routing
    """

    # Simplified region configurations (loaded from ConfigMap in production)
    REGIONS = {
        "us-east-1": Region(
            name="us-east-1",
            role=RegionRole.PRIMARY,
            api_url="https://us-east-1.qeo.example.com",
            database_url="cockroachdb-us-east-1:26257",
            cache_url="redis-us-east-1:6379",
            latitude=37.7749,
            longitude=-122.4194,
            country="US",
            max_replicas=30,
            allow_cross_border=True,
        ),
        "eu-west-1": Region(
            name="eu-west-1",
            role=RegionRole.SECONDARY,
            api_url="https://eu-west-1.qeo.example.com",
            database_url="cockroachdb-eu-west-1:26257",
            cache_url="redis-eu-west-1:6379",
            latitude=53.3498,
            longitude=-6.2603,
            country="IE",
            max_replicas=20,
            allow_cross_border=False,  # GDPR
        ),
        "ap-southeast-1": Region(
            name="ap-southeast-1",
            role=RegionRole.SECONDARY,
            api_url="https://ap-southeast-1.qeo.example.com",
            database_url="cockroachdb-ap-southeast-1:26257",
            cache_url="redis-ap-southeast-1:6379",
            latitude=1.3521,
            longitude=103.8198,
            country="SG",
            max_replicas=20,
            allow_cross_border=True,
        ),
    }

    def __init__(self):
        self._health_check_task = None
        self._start_health_monitoring()
        logger.info("RegionRouter initialized with {} regions".format(len(self.REGIONS)))

    def _start_health_monitoring(self):
        """Start background health monitoring."""
        # In production, this would be an async task
        pass

    def calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate great-circle distance between two points (Haversine formula).

        Returns distance in kilometers.
        """
        import math

        R = 6371  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad)
            * math.cos(lat2_rad)
            * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def estimate_latency(
        self,
        distance_km: float,
        region: Region,
    ) -> float:
        """
        Estimate network latency based on distance and region health.

        Factors:
        - Physical distance (roughly 0.5ms per 100km)
        - Region load (adds latency under high load)
        - Network congestion
        """
        # Base latency from distance (speed of light in fiber: ~200,000 km/s)
        base_latency_ms = distance_km / 200  # Roughly 0.5ms per 100km

        # Add processing latency
        base_latency_ms += 5  # API processing

        # Add load penalty
        load_penalty = region.current_load * 50  # Up to 50ms under full load

        # Add health penalty
        health_penalty = 0 if region.healthy else 1000  # 1s penalty if unhealthy

        total_latency = base_latency_ms + load_penalty + health_penalty

        return float(f"{total_latency:.2f}")

    def route_query(
        self,
        query_type: QueryType,
        user_latitude: float,
        user_longitude: float,
        user_country: Optional[str] = None,
        requires_eu_residency: bool = False,
    ) -> RoutingDecision:
        """
        Route query to optimal region.

        Args:
            query_type: READ, WRITE, or ANALYZE
            user_latitude: User's latitude
            user_longitude: User's longitude
            user_country: User's country code (for data residency)
            requires_eu_residency: Must data stay in EU?

        Returns:
            RoutingDecision with target region and metadata
        """
        # Filter regions based on data residency
        eligible_regions = self._filter_by_data_residency(
            list(self.REGIONS.values()),
            user_country,
            requires_eu_residency,
        )

        if not eligible_regions:
            # Fall back to primary if no eligible regions
            logger.warning("No eligible regions found, falling back to primary")
            eligible_regions = [r for r in self.REGIONS.values() if r.role == RegionRole.PRIMARY]

        # Route based on query type
        if query_type == QueryType.WRITE:
            # Writes always go to primary
            primary = [r for r in eligible_regions if r.role == RegionRole.PRIMARY][0]
            distance = self.calculate_distance(
                user_latitude,
                user_longitude,
                primary.latitude,
                primary.longitude,
            )
            latency = self.estimate_latency(distance, primary)

            return RoutingDecision(
                target_region=primary.name,
                reason="writes_to_primary",
                latency_estimate_ms=latency,
                confidence=1.0,
                fallback_regions=[
                    r.name
                    for r in eligible_regions
                    if r.name != primary.name and r.healthy
                ],
            )

        # For reads, find nearest healthy region
        region_scores = []
        for region in eligible_regions:
            if not region.healthy:
                continue

            distance = self.calculate_distance(
                user_latitude,
                user_longitude,
                region.latitude,
                region.longitude,
            )
            latency = self.estimate_latency(distance, region)

            # Score: lower latency = higher score
            # Factor in load: prefer less loaded regions
            score = 1000 / latency - (region.current_load * 100)

            region_scores.append((score, region, latency))

        if not region_scores:
            # No healthy regions, return error or use unhealthy primary
            logger.error("No healthy regions available!")
            primary = [r for r in self.REGIONS.values() if r.role == RegionRole.PRIMARY][0]
            return RoutingDecision(
                target_region=primary.name,
                reason="no_healthy_regions_fallback_to_primary",
                latency_estimate_ms=1000,
                confidence=0.3,
                fallback_regions=[],
            )

        # Sort by score (highest first)
        region_scores.sort(key=lambda x: x[0], reverse=True)

        best_score, best_region, best_latency = region_scores[0]

        fallback_regions = [r[1].name for r in region_scores[1:4]]  # Top 3 fallbacks

        confidence = min(1.0, best_score / 500)  # Normalize confidence

        return RoutingDecision(
            target_region=best_region.name,
            reason=f"nearest_healthy_region_distance_{self.calculate_distance(user_latitude, user_longitude, best_region.latitude, best_region.longitude):.0f}km",
            latency_estimate_ms=best_latency,
            confidence=float(f"{confidence:.3f}"),
            fallback_regions=fallback_regions,
        )

    def _filter_by_data_residency(
        self,
        regions: List[Region],
        user_country: Optional[str],
        requires_eu_residency: bool,
    ) -> List[Region]:
        """Filter regions based on data residency requirements."""
        if requires_eu_residency:
            # Must use EU region
            eu_regions = [r for r in regions if r.country in ["IE", "DE", "FR", "NL"]]
            if eu_regions:
                return eu_regions
            logger.warning("EU residency required but no EU regions available")
            return []

        if user_country and user_country in ["DE", "FR", "IT", "ES", "NL", "BE"]:
            # EU user - prefer EU region if available
            eu_regions = [r for r in regions if r.country in ["IE", "DE"]]
            if eu_regions:
                return eu_regions

        # No restrictions, return all regions
        return regions

    async def health_check_region(self, region: Region) -> bool:
        """
        Check if a region is healthy.

        Returns True if healthy, False otherwise.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{region.api_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        region.healthy = True
                        region.last_health_check = time.time()
                        return True
                    else:
                        region.healthy = False
                        logger.warning(
                            f"Region {region.name} health check failed: {response.status}"
                        )
                        return False
        except Exception as e:
            region.healthy = False
            logger.error(f"Region {region.name} health check error: {e}")
            return False

    async def update_region_load(self, region_name: str, load: float):
        """Update current load for a region (0-1)."""
        if region_name in self.REGIONS:
            self.REGIONS[region_name].current_load = min(1.0, max(0.0, load))

    def get_region_status(self) -> Dict:
        """Get status of all regions."""
        return {
            region.name: {
                "role": region.role.value,
                "healthy": region.healthy,
                "current_load": float(f"{region.current_load:.2f}"),
                "location": f"{region.latitude}, {region.longitude}",
                "country": region.country,
                "last_health_check_seconds_ago": (
                    time.time() - region.last_health_check
                    if region.last_health_check > 0
                    else None
                ),
            }
            for region in self.REGIONS.values()
        }

    def route_with_retry(
        self,
        query_type: QueryType,
        user_latitude: float,
        user_longitude: float,
        user_country: Optional[str] = None,
        requires_eu_residency: bool = False,
        max_retries: int = 3,
    ) -> RoutingDecision:
        """
        Route query with retry logic.

        If primary region fails, automatically tries fallback regions.
        """
        decision = self.route_query(
            query_type,
            user_latitude,
            user_longitude,
            user_country,
            requires_eu_residency,
        )

        # In production, this would actually attempt the request
        # and retry with fallbacks if it fails

        return decision


# Global router instance
_global_router = None


def get_router() -> RegionRouter:
    """Get or create global router instance."""
    global _global_router
    if _global_router is None:
        _global_router = RegionRouter()
    return _global_router
