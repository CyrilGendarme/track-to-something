"""Performance monitoring utility for analyzing bottlenecks.

This utility provides easy access to performance statistics and helps identify
bottlenecks in the audio processing pipeline.

Usage:
    # In your main application
    from src.engine import get_performance_monitor
    
    perf = get_performance_monitor()
    
    # ... run audio pipeline ...
    
    # Log summary when done
    perf.log_summary(limit=10)
    
    # Or programmatically access stats
    stft_stats = perf.get_stats("process:stft")
    print(f"STFT processing: {stft_stats.avg_ms:.2f}ms avg")
"""

from src.engine.performance import get_performance_monitor, PerformanceMonitor
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def print_performance_report(limit: int = 15) -> None:
    """Print a comprehensive performance report.
    
    Args:
        limit: Number of slowest operations to show
    """
    perf = get_performance_monitor()
    perf.log_summary(limit=limit)


def print_operation_summary(operation: str) -> None:
    """Print stats for a specific operation.
    
    Args:
        operation: Operation name (e.g., "process:stft")
    """
    perf = get_performance_monitor()
    perf.log_operation(operation)


def get_bottleneck_analysis() -> dict:
    """Analyze performance data to identify bottlenecks.
    
    Returns:
        Dictionary with bottleneck insights
    """
    perf = get_performance_monitor()
    
    if not perf.stats:
        return {"error": "No performance data recorded"}
    
    # Find slowest operations
    sorted_stats = sorted(
        perf.stats.values(),
        key=lambda s: s.avg_ms,
        reverse=True
    )
    
    total_time = sum(s.total_ms for s in perf.stats.values())
    
    analysis = {
        "total_operations": len(perf.stats),
        "total_time_ms": total_time,
        "slowest_operations": [
            {
                "name": s.operation,
                "avg_ms": round(s.avg_ms, 2),
                "max_ms": round(s.max_ms, 2),
                "count": s.count,
                "percent_of_total": round(100 * s.total_ms / total_time, 1),
            }
            for s in sorted_stats[:5]
        ],
        "operations_above_30ms": [
            {
                "name": s.operation,
                "avg_ms": round(s.avg_ms, 2),
                "count": s.count,
            }
            for s in sorted_stats if s.avg_ms > 30
        ],
    }
    
    return analysis


def show_bottleneck_insights() -> None:
    """Show detailed bottleneck analysis with recommendations."""
    analysis = get_bottleneck_analysis()
    
    if "error" in analysis:
        logger.error(analysis["error"])
        return
    
    logger.info("=" * 70)
    logger.info("[BOTTLENECK ANALYSIS]")
    logger.info("=" * 70)
    logger.info(f"Total operations tracked: {analysis['total_operations']}")
    logger.info(f"Total processing time: {analysis['total_time_ms']:.2f}ms")
    logger.info("")
    
    logger.info("TOP 5 SLOWEST OPERATIONS:")
    for i, op in enumerate(analysis["slowest_operations"], 1):
        logger.info(
            f"  {i}. {op['name']:30s} | "
            f"avg={op['avg_ms']:7.2f}ms | "
            f"max={op['max_ms']:7.2f}ms | "
            f"{op['percent_of_total']:5.1f}% of total"
        )
    
    if analysis["operations_above_30ms"]:
        logger.info("")
        logger.info("OPERATIONS ABOVE 30ms (POTENTIALLY PROBLEMATIC):")
        for op in analysis["operations_above_30ms"]:
            logger.warning(
                f"  ⚠ {op['name']:30s} | "
                f"avg={op['avg_ms']:7.2f}ms | "
                f"n={op['count']}"
            )
        logger.warning("")
        logger.warning("RECOMMENDATIONS:")
        logger.warning("  - Profile these operations with a debugger")
        logger.warning("  - Look for synchronous I/O or expensive computations")
        logger.warning("  - Consider moving to async/separate threads")
        logger.warning("  - Use caching for repeated calculations")
    
    logger.info("=" * 70)


if __name__ == "__main__":
    # Example: Import and use
    perf = get_performance_monitor()
    
    if perf.stats:
        # Show detailed analysis
        show_bottleneck_insights()
        
        # Also show full summary
        print()
        perf.log_summary(limit=20)
    else:
        logger.info("No performance data available. Run the audio pipeline first.")
        logger.info("")
        logger.info("Example usage:")
        logger.info("  from src.engine import get_performance_monitor")
        logger.info("  perf = get_performance_monitor()")
        logger.info("  # ... run pipeline ...")
        logger.info("  perf.log_summary()")
