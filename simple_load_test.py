#!/usr/bin/env python3
"""
Direct Load Testing Script - Simplified Version
Generates performance metrics and visualizations
"""

import json
import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from pathlib import Path
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleLoadTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.response_times = []
        self.success_count = 0
        self.failure_count = 0
    
    def make_request(self, endpoint, method="GET", json_data=None):
        """Make a single HTTP request and measure response time."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=json_data, timeout=10)
            
            response_time = (time.time() - start_time) * 1000  # ms
            
            if response.status_code < 400:
                self.success_count += 1
                return response_time
            else:
                self.failure_count += 1
                return None
                
        except Exception as e:
            self.failure_count += 1
            logger.warning(f"Request failed: {e}")
            return None
    
    def simulate_user_load(self, num_requests=100):
        """Simulate load by making multiple concurrent requests."""
        logger.info(f"Starting load test with {num_requests} requests...")
        
        # Define test endpoints
        endpoints = [
            ("/health", "GET"),
            ("/packages", "GET"),  
            ("/artifacts", "POST", [{"name": "test-pkg"}]),
            ("/artifact/byRegEx", "POST", {"RegEx": ".*"}),
        ]
        
        # Use ThreadPoolExecutor for concurrent requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            
            for i in range(num_requests):
                # Randomly select endpoint
                endpoint_data = endpoints[i % len(endpoints)]
                endpoint = endpoint_data[0]
                method = endpoint_data[1]
                json_data = endpoint_data[2] if len(endpoint_data) > 2 else None
                
                future = executor.submit(self.make_request, endpoint, method, json_data)
                futures.append(future)
            
            # Collect results
            for future in as_completed(futures):
                response_time = future.result()
                if response_time is not None:
                    self.response_times.append(response_time)
        
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        """Calculate performance metrics from collected data."""
        if not self.response_times:
            return {"error": "No successful requests"}
        
        times = np.array(self.response_times)
        total_requests = self.success_count + self.failure_count
        
        return {
            "total_requests": total_requests,
            "successful_requests": self.success_count,
            "failed_requests": self.failure_count,
            "success_rate": (self.success_count / total_requests) * 100,
            "mean_latency": float(np.mean(times)),
            "median_latency": float(np.median(times)),
            "p95_latency": float(np.percentile(times, 95)),
            "p99_latency": float(np.percentile(times, 99)),
            "min_latency": float(np.min(times)),
            "max_latency": float(np.max(times)),
            "std_latency": float(np.std(times)),
            "raw_times": self.response_times
        }
    
    def generate_graphs(self, metrics, output_dir="performance_graphs"):
        """Generate performance visualization graphs."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Set style
        sns.set_style("whitegrid")
        
        # 1. Latency Metrics Dashboard
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Bar chart of key latency metrics
        metrics_names = ['Mean', 'P95', 'P99', 'Max']
        metrics_values = [
            metrics['mean_latency'],
            metrics['p95_latency'], 
            metrics['p99_latency'],
            metrics['max_latency']
        ]
        
        bars = ax1.bar(metrics_names, metrics_values, 
                      color=['#3498db', '#e74c3c', '#9b59b6', '#e67e22'])
        ax1.set_ylabel('Response Time (ms)')
        ax1.set_title('Key Latency Metrics')
        
        # Add value labels
        for bar, value in zip(bars, metrics_values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(metrics_values)*0.01,
                    f'{value:.1f}ms', ha='center', va='bottom')
        
        # Histogram of response times
        ax2.hist(metrics['raw_times'], bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        ax2.axvline(metrics['mean_latency'], color='red', linestyle='--', 
                   label=f'Mean: {metrics["mean_latency"]:.1f}ms')
        ax2.axvline(metrics['p95_latency'], color='orange', linestyle='--',
                   label=f'P95: {metrics["p95_latency"]:.1f}ms')
        ax2.set_xlabel('Response Time (ms)')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Response Time Distribution')
        ax2.legend()
        
        # Success rate pie chart
        ax3.pie([metrics['successful_requests'], metrics['failed_requests']],
               labels=['Success', 'Failed'], autopct='%1.1f%%',
               colors=['#2ecc71', '#e74c3c'])
        ax3.set_title(f'Request Success Rate\\n({metrics["success_rate"]:.1f}%)')
        
        # Performance summary
        ax4.axis('off')
        summary_text = f"""
PERFORMANCE TEST RESULTS
{"="*30}

📊 Total Requests: {metrics['total_requests']:,}
✅ Success Rate: {metrics['success_rate']:.1f}%
❌ Failed Requests: {metrics['failed_requests']}

⏱️ LATENCY METRICS:
   Mean: {metrics['mean_latency']:.1f} ms
   Median: {metrics['median_latency']:.1f} ms
   P95: {metrics['p95_latency']:.1f} ms
   P99: {metrics['p99_latency']:.1f} ms
   Min: {metrics['min_latency']:.1f} ms
   Max: {metrics['max_latency']:.1f} ms
   Std Dev: {metrics['std_latency']:.1f} ms

🎯 Performance Grade: {"A" if metrics['p95_latency'] < 200 else "B" if metrics['p95_latency'] < 500 else "C"}

Test Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        ax4.text(0.05, 0.95, summary_text, fontsize=10, fontfamily='monospace',
                verticalalignment='top', transform=ax4.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f0f0"))
        
        plt.tight_layout()
        plt.savefig(output_path / 'performance_dashboard.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Box plot for detailed latency analysis
        plt.figure(figsize=(10, 6))
        plt.boxplot(metrics['raw_times'], vert=True, patch_artist=True,
                   boxprops=dict(facecolor='lightblue', alpha=0.7))
        plt.ylabel('Response Time (ms)')
        plt.title('Response Time Distribution (Box Plot)')
        plt.grid(True, alpha=0.3)
        plt.savefig(output_path / 'latency_boxplot.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"📊 Graphs saved to {output_path}")
    
    def save_results(self, metrics, filename="performance_results.json"):
        """Save detailed results to JSON file."""
        results = {
            "test_metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_type": "Optimized Load Test",
                "version": "1.0"
            },
            "metrics": {k: v for k, v in metrics.items() if k != 'raw_times'},
            "sample_count": len(metrics.get('raw_times', []))
        }
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📋 Results saved to {filename}")


def main():
    """Run the performance test."""
    print("🎯 Starting Optimized Load Test & Graph Generation")
    print("=" * 50)
    
    # Initialize tester
    tester = SimpleLoadTester()
    
    try:
        # Run test
        metrics = tester.simulate_user_load(num_requests=200)
        
        if "error" in metrics:
            print(f"❌ Test failed: {metrics['error']}")
            return
        
        # Generate visualizations
        tester.generate_graphs(metrics)
        
        # Save detailed results
        tester.save_results(metrics)
        
        # Print summary
        print("\\n🎉 TEST COMPLETED!")
        print("=" * 50)
        print(f"📊 Total Requests: {metrics['total_requests']}")
        print(f"✅ Success Rate: {metrics['success_rate']:.1f}%")
        print(f"📈 Mean Latency: {metrics['mean_latency']:.1f} ms")
        print(f"📈 P95 Latency: {metrics['p95_latency']:.1f} ms")
        print(f"📈 P99 Latency: {metrics['p99_latency']:.1f} ms")
        print("=" * 50)
        print("📊 Check 'performance_graphs/' for visualizations")
        print("📋 Check 'performance_results.json' for detailed data")
        
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        raise


if __name__ == "__main__":
    main()