#!/usr/bin/env python3
"""
Real Performance Analysis with Live Server
Generates actual performance metrics and visualizations from running Flask server
"""

import requests
import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealPerformanceAnalyzer:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.response_times = []
        self.results = {}
        
    def verify_server(self):
        """Verify server is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ Server is accessible and running")
                return True
            else:
                logger.error(f"❌ Server returned status: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Server not accessible: {e}")
            return False
    
    def run_real_load_test(self, num_requests=200, max_workers=20):
        """Run actual load test against live server."""
        logger.info(f"🚀 Starting real load test: {num_requests} requests, {max_workers} workers")
        
        # Test endpoints with real API calls
        test_endpoints = [
            ("/health", "GET", None),
            ("/openapi", "GET", None),
            ("/artifacts", "POST", [{"name": "test-package"}]),
            ("/artifact/byRegEx", "POST", {"RegEx": "test.*"}),
            ("/artifact/byName/test-package", "GET", None),
        ]
        
        results = {
            "response_times": [],
            "success_count": 0,
            "failure_count": 0,
            "endpoint_results": {}
        }
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all requests
            futures = []
            for i in range(num_requests):
                endpoint_data = test_endpoints[i % len(test_endpoints)]
                future = executor.submit(self._make_real_request, *endpoint_data)
                futures.append((future, endpoint_data[0]))
            
            # Collect results
            for future, endpoint in futures:
                result = future.result()
                if result:
                    results["response_times"].append(result["response_time"])
                    results["success_count"] += 1
                    
                    # Track per-endpoint metrics
                    if endpoint not in results["endpoint_results"]:
                        results["endpoint_results"][endpoint] = []
                    results["endpoint_results"][endpoint].append(result["response_time"])
                else:
                    results["failure_count"] += 1
        
        total_time = time.time() - start_time
        
        # Calculate comprehensive metrics
        if results["response_times"]:
            times = np.array(results["response_times"])
            
            metrics = {
                "test_duration": total_time,
                "total_requests": results["success_count"] + results["failure_count"],
                "successful_requests": results["success_count"],
                "failed_requests": results["failure_count"],
                "success_rate": (results["success_count"] / (results["success_count"] + results["failure_count"])) * 100,
                "throughput": results["success_count"] / total_time,
                
                # Latency metrics
                "mean_latency": float(np.mean(times)),
                "median_latency": float(np.median(times)),
                "p95_latency": float(np.percentile(times, 95)),
                "p99_latency": float(np.percentile(times, 99)),
                "min_latency": float(np.min(times)),
                "max_latency": float(np.max(times)),
                "std_latency": float(np.std(times)),
                
                # Raw data for graphing
                "raw_response_times": results["response_times"],
                "endpoint_breakdown": {}
            }
            
            # Calculate per-endpoint metrics
            for endpoint, times_list in results["endpoint_results"].items():
                if times_list:
                    endpoint_times = np.array(times_list)
                    metrics["endpoint_breakdown"][endpoint] = {
                        "count": len(times_list),
                        "mean": float(np.mean(endpoint_times)),
                        "p95": float(np.percentile(endpoint_times, 95)),
                        "p99": float(np.percentile(endpoint_times, 99))
                    }
            
            return metrics
        else:
            return {"error": "No successful requests"}
    
    def _make_real_request(self, endpoint, method, json_data):
        """Make actual HTTP request and measure response time."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=json_data, timeout=10)
            
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            if response.status_code < 400:
                return {
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "endpoint": endpoint
                }
            else:
                logger.warning(f"HTTP error {response.status_code} for {endpoint}")
                return None
                
        except Exception as e:
            logger.warning(f"Request failed for {endpoint}: {e}")
            return None
    
    def generate_real_performance_graphs(self, metrics, output_dir="performance_graphs"):
        """Generate real performance visualization graphs."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Set matplotlib backend and style
        import matplotlib
        matplotlib.use('Agg')
        sns.set_style("whitegrid")
        
        # 1. Main Performance Dashboard
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Latency metrics bar chart
        latency_metrics = ['Mean', 'Median', 'P95', 'P99', 'Max']
        latency_values = [
            metrics['mean_latency'],
            metrics['median_latency'],
            metrics['p95_latency'],
            metrics['p99_latency'],
            metrics['max_latency']
        ]
        
        colors = ['#3498db', '#2ecc71', '#e74c3c', '#9b59b6', '#e67e22']
        bars = ax1.bar(latency_metrics, latency_values, color=colors, alpha=0.8)
        ax1.set_ylabel('Response Time (ms)')
        ax1.set_title('Real Latency Metrics (Live Server)')
        ax1.grid(True, alpha=0.3)
        
        # Add value labels
        for bar, value in zip(bars, latency_values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(latency_values)*0.01,
                    f'{value:.1f}ms', ha='center', va='bottom', fontsize=9)
        
        # Response time distribution histogram
        ax2.hist(metrics['raw_response_times'], bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        ax2.axvline(metrics['mean_latency'], color='red', linestyle='--', linewidth=2,
                   label=f'Mean: {metrics["mean_latency"]:.1f}ms')
        ax2.axvline(metrics['p95_latency'], color='orange', linestyle='--', linewidth=2,
                   label=f'P95: {metrics["p95_latency"]:.1f}ms')
        ax2.axvline(metrics['p99_latency'], color='purple', linestyle='--', linewidth=2,
                   label=f'P99: {metrics["p99_latency"]:.1f}ms')
        ax2.set_xlabel('Response Time (ms)')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Real Response Time Distribution')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Endpoint performance comparison
        if metrics.get('endpoint_breakdown'):
            endpoints = list(metrics['endpoint_breakdown'].keys())
            endpoint_means = [metrics['endpoint_breakdown'][ep]['mean'] for ep in endpoints]
            endpoint_p95s = [metrics['endpoint_breakdown'][ep]['p95'] for ep in endpoints]
            
            x = np.arange(len(endpoints))
            width = 0.35
            
            ax3.bar(x - width/2, endpoint_means, width, label='Mean', alpha=0.8, color='#3498db')
            ax3.bar(x + width/2, endpoint_p95s, width, label='P95', alpha=0.8, color='#e74c3c')
            
            ax3.set_xlabel('API Endpoints')
            ax3.set_ylabel('Response Time (ms)')
            ax3.set_title('Per-Endpoint Performance (Real Data)')
            ax3.set_xticks(x)
            ax3.set_xticklabels([ep.replace('/', '') or 'root' for ep in endpoints], rotation=45)
            ax3.legend()
            ax3.grid(True, alpha=0.3)
        
        # Performance summary box
        ax4.axis('off')
        summary_text = f"""
🎯 REAL PERFORMANCE TEST RESULTS
{'='*45}

📊 Test Configuration:
   Total Requests: {metrics['total_requests']:,}
   Test Duration: {metrics['test_duration']:.1f} seconds
   
✅ Success Metrics:
   Success Rate: {metrics['success_rate']:.1f}%
   Successful Requests: {metrics['successful_requests']:,}
   Failed Requests: {metrics['failed_requests']}
   
⚡ Throughput:
   Requests/Second: {metrics['throughput']:.1f} RPS
   
📈 Latency Analysis:
   Mean Response: {metrics['mean_latency']:.1f} ms
   Median Response: {metrics['median_latency']:.1f} ms
   95th Percentile: {metrics['p95_latency']:.1f} ms
   99th Percentile: {metrics['p99_latency']:.1f} ms
   Standard Deviation: {metrics['std_latency']:.1f} ms
   
🎯 Performance Grade: {"A" if metrics['p95_latency'] < 200 else "B" if metrics['p95_latency'] < 500 else "C"}

📅 Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        ax4.text(0.05, 0.95, summary_text, fontsize=9, fontfamily='monospace',
                verticalalignment='top', transform=ax4.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8f9fa", edgecolor="#dee2e6"))
        
        plt.tight_layout()
        plt.savefig(output_path / 'real_performance_dashboard.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Response time scatter plot over time
        plt.figure(figsize=(14, 6))
        times = metrics['raw_response_times'][:500]  # Limit for clarity
        plt.scatter(range(len(times)), times, alpha=0.6, s=20, c='#3498db')
        plt.axhline(metrics['mean_latency'], color='red', linestyle='--', 
                   label=f'Mean: {metrics["mean_latency"]:.1f}ms')
        plt.axhline(metrics['p95_latency'], color='orange', linestyle='--',
                   label=f'P95: {metrics["p95_latency"]:.1f}ms')
        plt.xlabel('Request Number (Sequential)')
        plt.ylabel('Response Time (ms)')
        plt.title('Real Response Times Over Sequential Requests')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / 'response_time_timeline.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. Box plot for detailed analysis
        plt.figure(figsize=(10, 6))
        plt.boxplot(metrics['raw_response_times'], vert=True, patch_artist=True,
                   boxprops=dict(facecolor='lightblue', alpha=0.7),
                   medianprops=dict(color='red', linewidth=2))
        plt.ylabel('Response Time (ms)')
        plt.title('Real Response Time Distribution (Box Plot)')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / 'response_time_boxplot.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"📊 Real performance graphs saved to {output_path}")
        return output_path
    
    def save_real_results(self, metrics, filename="real_performance_results.json"):
        """Save real performance results to JSON."""
        report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_type": "Real Load Test Against Live Server",
                "server_url": self.base_url,
                "version": "1.0"
            },
            "performance_metrics": {k: v for k, v in metrics.items() if k != 'raw_response_times'},
            "data_summary": {
                "raw_data_points": len(metrics.get('raw_response_times', [])),
                "endpoints_tested": len(metrics.get('endpoint_breakdown', {}))
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📋 Real results saved to {filename}")


def main():
    """Run real performance analysis."""
    print("🎯 REAL PERFORMANCE ANALYSIS - LIVE SERVER")
    print("=" * 60)
    
    analyzer = RealPerformanceAnalyzer()
    
    # Verify server is running
    if not analyzer.verify_server():
        print("❌ Flask server is not accessible. Please start the server first.")
        return 1
    
    try:
        # Run real load test
        print("🔄 Running real load test against live server...")
        metrics = analyzer.run_real_load_test(num_requests=300, max_workers=30)
        
        if 'error' in metrics:
            print(f"❌ Load test failed: {metrics['error']}")
            return 1
        
        # Generate real graphs
        print("📊 Generating real performance graphs...")
        output_dir = analyzer.generate_real_performance_graphs(metrics)
        
        # Save results
        analyzer.save_real_results(metrics)
        
        # Display results
        print("\\n🎉 REAL PERFORMANCE ANALYSIS COMPLETE!")
        print("=" * 60)
        print(f"📊 Total Requests: {metrics['total_requests']:,}")
        print(f"✅ Success Rate: {metrics['success_rate']:.1f}%")
        print(f"⚡ Throughput: {metrics['throughput']:.1f} requests/second")
        print(f"📈 Mean Latency: {metrics['mean_latency']:.1f} ms")
        print(f"📈 P95 Latency: {metrics['p95_latency']:.1f} ms") 
        print(f"📈 P99 Latency: {metrics['p99_latency']:.1f} ms")
        
        print("\\n📁 Generated Files:")
        print(f"   📊 {output_dir}/real_performance_dashboard.png")
        print(f"   📊 {output_dir}/response_time_timeline.png")
        print(f"   📊 {output_dir}/response_time_boxplot.png")
        print(f"   📋 real_performance_results.json")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())