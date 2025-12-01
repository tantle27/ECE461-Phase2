#!/usr/bin/env python3
"""
Complete Performance Analysis Generator
Creates actual graphs, metrics, and detailed analysis files
"""

import json
import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from datetime import datetime
from pathlib import Path
import requests
import subprocess
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PerformanceAnalyzer:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.results = {}
        self.flask_process = None
        
    def start_flask_server(self):
        """Start Flask server for testing."""
        logger.info("🚀 Starting Flask server...")
        try:
            env = os.environ.copy()
            env["FLASK_APP"] = "app.app"
            env["FLASK_ENV"] = "development"
            
            self.flask_process = subprocess.Popen(
                [sys.executable, "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            
            # Wait for server to start
            for i in range(30):  # 30 second timeout
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=2)
                    if response.status_code == 200:
                        logger.info("✅ Flask server started successfully")
                        return True
                except requests.exceptions.RequestException:
                    time.sleep(1)
            
            logger.error("❌ Flask server failed to start")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error starting Flask server: {e}")
            return False
    
    def stop_flask_server(self):
        """Stop Flask server."""
        if self.flask_process:
            logger.info("🛑 Stopping Flask server...")
            self.flask_process.terminate()
            try:
                self.flask_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.flask_process.kill()
    
    def run_comprehensive_load_test(self):
        """Run comprehensive load tests and collect metrics."""
        logger.info("📊 Starting comprehensive load tests...")
        
        # Test configurations
        test_scenarios = [
            {"name": "Light Load", "users": 10, "duration": 30},
            {"name": "Normal Load", "users": 50, "duration": 60},
            {"name": "Heavy Load", "users": 100, "duration": 30},
        ]
        
        all_results = {}
        
        for scenario in test_scenarios:
            logger.info(f"🔬 Running {scenario['name']} test...")
            results = self._run_load_scenario(scenario)
            all_results[scenario['name']] = results
            
            # Brief pause between tests
            time.sleep(5)
        
        return all_results
    
    def _run_load_scenario(self, scenario):
        """Run a single load test scenario."""
        response_times = []
        success_count = 0
        failure_count = 0
        
        # API endpoints to test
        endpoints = [
            ("/health", "GET", None),
            ("/packages", "GET", None),
            ("/artifacts", "POST", [{"name": "test-pkg"}]),
            ("/artifact/byRegEx", "POST", {"RegEx": ".*"}),
            ("/artifact/byName/test-pkg", "GET", None),
        ]
        
        start_time = time.time()
        end_time = start_time + scenario['duration']
        
        with ThreadPoolExecutor(max_workers=scenario['users']) as executor:
            futures = []
            
            while time.time() < end_time:
                # Submit batch of requests
                for _ in range(min(scenario['users'], 10)):  # Batch size
                    endpoint_data = endpoints[len(futures) % len(endpoints)]
                    future = executor.submit(self._make_timed_request, *endpoint_data)
                    futures.append(future)
                
                # Collect completed results
                completed_futures = [f for f in futures if f.done()]
                for future in completed_futures:
                    result = future.result()
                    if result and result > 0:
                        response_times.append(result)
                        success_count += 1
                    else:
                        failure_count += 1
                    futures.remove(future)
                
                time.sleep(0.1)  # Small delay
        
        # Wait for remaining futures
        for future in futures:
            result = future.result()
            if result and result > 0:
                response_times.append(result)
                success_count += 1
            else:
                failure_count += 1
        
        # Calculate metrics
        if response_times:
            times_array = np.array(response_times)
            return {
                "total_requests": success_count + failure_count,
                "successful_requests": success_count,
                "failed_requests": failure_count,
                "success_rate": (success_count / (success_count + failure_count)) * 100,
                "mean_latency": float(np.mean(times_array)),
                "median_latency": float(np.median(times_array)),
                "p95_latency": float(np.percentile(times_array, 95)),
                "p99_latency": float(np.percentile(times_array, 99)),
                "min_latency": float(np.min(times_array)),
                "max_latency": float(np.max(times_array)),
                "std_latency": float(np.std(times_array)),
                "raw_times": response_times[:1000],  # Limit for file size
                "throughput": success_count / scenario['duration']
            }
        else:
            return {"error": "No successful requests"}
    
    def _make_timed_request(self, endpoint, method, json_data):
        """Make a timed HTTP request."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=json_data, timeout=10)
            
            response_time = (time.time() - start_time) * 1000  # ms
            
            if response.status_code < 400:
                return response_time
            else:
                return None
                
        except Exception:
            return None
    
    def generate_performance_graphs(self, test_results, output_dir="performance_graphs"):
        """Generate comprehensive performance graphs."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Set matplotlib backend for headless operation
        import matplotlib
        matplotlib.use('Agg')
        
        # Set style
        sns.set_style("whitegrid")
        plt.rcParams.update({'font.size': 10})
        
        # 1. Latency Comparison Across Load Scenarios
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # Prepare data for comparison
        scenarios = []
        mean_latencies = []
        p95_latencies = []
        p99_latencies = []
        throughputs = []
        
        for scenario_name, results in test_results.items():
            if 'error' not in results:
                scenarios.append(scenario_name)
                mean_latencies.append(results['mean_latency'])
                p95_latencies.append(results['p95_latency'])
                p99_latencies.append(results['p99_latency'])
                throughputs.append(results['throughput'])
        
        # Latency comparison bar chart
        x = np.arange(len(scenarios))
        width = 0.25
        
        axes[0,0].bar(x - width, mean_latencies, width, label='Mean', alpha=0.8, color='#3498db')
        axes[0,0].bar(x, p95_latencies, width, label='P95', alpha=0.8, color='#e74c3c')
        axes[0,0].bar(x + width, p99_latencies, width, label='P99', alpha=0.8, color='#9b59b6')
        
        axes[0,0].set_xlabel('Test Scenarios')
        axes[0,0].set_ylabel('Response Time (ms)')
        axes[0,0].set_title('Latency Metrics Comparison')
        axes[0,0].set_xticks(x)
        axes[0,0].set_xticklabels(scenarios)
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # Throughput comparison
        bars = axes[0,1].bar(scenarios, throughputs, color=['#2ecc71', '#f39c12', '#e74c3c'])
        axes[0,1].set_ylabel('Requests per Second')
        axes[0,1].set_title('Throughput Comparison')
        axes[0,1].grid(True, alpha=0.3)
        
        # Add value labels on bars
        for bar, value in zip(bars, throughputs):
            axes[0,1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(throughputs)*0.01,
                          f'{value:.1f}', ha='center', va='bottom')
        
        # Response time distribution (using Normal Load data)
        normal_load_data = test_results.get("Normal Load", {})
        if 'raw_times' in normal_load_data:
            axes[1,0].hist(normal_load_data['raw_times'], bins=30, alpha=0.7, 
                          color='skyblue', edgecolor='black')
            axes[1,0].axvline(normal_load_data['mean_latency'], color='red', 
                             linestyle='--', label=f'Mean: {normal_load_data["mean_latency"]:.1f}ms')
            axes[1,0].axvline(normal_load_data['p95_latency'], color='orange', 
                             linestyle='--', label=f'P95: {normal_load_data["p95_latency"]:.1f}ms')
            axes[1,0].set_xlabel('Response Time (ms)')
            axes[1,0].set_ylabel('Frequency')
            axes[1,0].set_title('Response Time Distribution (Normal Load)')
            axes[1,0].legend()
            axes[1,0].grid(True, alpha=0.3)
        
        # Performance summary table
        axes[1,1].axis('off')
        summary_data = []
        for scenario_name, results in test_results.items():
            if 'error' not in results:
                summary_data.append([
                    scenario_name,
                    f"{results['success_rate']:.1f}%",
                    f"{results['mean_latency']:.1f}ms",
                    f"{results['p95_latency']:.1f}ms",
                    f"{results['throughput']:.1f} RPS"
                ])
        
        table = axes[1,1].table(cellText=summary_data,
                               colLabels=['Scenario', 'Success Rate', 'Mean', 'P95', 'Throughput'],
                               cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        axes[1,1].set_title('Performance Summary Table')
        
        plt.tight_layout()
        plt.savefig(output_path / 'comprehensive_performance_analysis.png', 
                   dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Individual scenario detailed graphs
        for scenario_name, results in test_results.items():
            if 'error' not in results and 'raw_times' in results:
                fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
                
                # Histogram
                ax1.hist(results['raw_times'], bins=25, alpha=0.7, color='lightblue', edgecolor='black')
                ax1.axvline(results['mean_latency'], color='red', linestyle='--', 
                           label=f'Mean: {results["mean_latency"]:.1f}ms')
                ax1.axvline(results['p95_latency'], color='orange', linestyle='--',
                           label=f'P95: {results["p95_latency"]:.1f}ms')
                ax1.set_xlabel('Response Time (ms)')
                ax1.set_ylabel('Frequency')
                ax1.set_title(f'{scenario_name} - Response Time Distribution')
                ax1.legend()
                ax1.grid(True, alpha=0.3)
                
                # Box plot
                ax2.boxplot(results['raw_times'], vert=True, patch_artist=True,
                           boxprops=dict(facecolor='lightgreen', alpha=0.7))
                ax2.set_ylabel('Response Time (ms)')
                ax2.set_title(f'{scenario_name} - Box Plot')
                ax2.grid(True, alpha=0.3)
                
                # Time series (simulated)
                times = results['raw_times'][:200]  # Limit for visualization
                ax3.plot(range(len(times)), times, alpha=0.7, color='blue')
                ax3.set_xlabel('Request Number')
                ax3.set_ylabel('Response Time (ms)')
                ax3.set_title(f'{scenario_name} - Response Time Over Requests')
                ax3.grid(True, alpha=0.3)
                
                # Metrics summary
                ax4.axis('off')
                metrics_text = f"""
{scenario_name} Performance Metrics
{'='*40}

📊 Total Requests: {results['total_requests']:,}
✅ Success Rate: {results['success_rate']:.1f}%
⚡ Throughput: {results['throughput']:.1f} req/sec

📈 Latency Statistics:
   Mean: {results['mean_latency']:.1f} ms
   Median: {results['median_latency']:.1f} ms
   P95: {results['p95_latency']:.1f} ms
   P99: {results['p99_latency']:.1f} ms
   Min: {results['min_latency']:.1f} ms
   Max: {results['max_latency']:.1f} ms
   Std Dev: {results['std_latency']:.1f} ms

🎯 Performance Grade: {"A" if results['p95_latency'] < 200 else "B" if results['p95_latency'] < 500 else "C"}
                """
                
                ax4.text(0.05, 0.95, metrics_text, fontsize=9, fontfamily='monospace',
                        verticalalignment='top', transform=ax4.transAxes,
                        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8f9fa"))
                
                plt.tight_layout()
                safe_name = scenario_name.lower().replace(' ', '_')
                plt.savefig(output_path / f'{safe_name}_detailed_analysis.png', 
                           dpi=300, bbox_inches='tight')
                plt.close()
        
        logger.info(f"📊 Performance graphs saved to {output_path}")
    
    def save_detailed_results(self, test_results, filename="performance_analysis_results.json"):
        """Save comprehensive results to JSON."""
        report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_type": "Comprehensive Load Testing",
                "version": "2.0",
                "generated_by": "ECE461-Phase2 Performance Analyzer"
            },
            "summary": {
                "scenarios_tested": len(test_results),
                "total_duration_estimate": "~2 minutes",
                "analysis_type": "Multi-scenario load testing with latency and throughput analysis"
            },
            "detailed_results": test_results,
            "recommendations": self._generate_recommendations(test_results)
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📋 Detailed results saved to {filename}")
    
    def _generate_recommendations(self, test_results):
        """Generate performance recommendations based on results."""
        recommendations = []
        
        for scenario_name, results in test_results.items():
            if 'error' not in results:
                if results['p95_latency'] > 500:
                    recommendations.append(f"🔴 {scenario_name}: P95 latency ({results['p95_latency']:.1f}ms) exceeds 500ms threshold - Critical optimization needed")
                elif results['p95_latency'] > 200:
                    recommendations.append(f"🟡 {scenario_name}: P95 latency ({results['p95_latency']:.1f}ms) above 200ms - Consider optimization")
                else:
                    recommendations.append(f"🟢 {scenario_name}: Good performance (P95: {results['p95_latency']:.1f}ms)")
                
                if results['success_rate'] < 95:
                    recommendations.append(f"🔴 {scenario_name}: Low success rate ({results['success_rate']:.1f}%) - Investigate error handling")
        
        return recommendations


def main():
    """Main execution function."""
    print("🎯 ECE461-Phase2 Comprehensive Performance Analysis")
    print("=" * 60)
    
    analyzer = PerformanceAnalyzer()
    
    try:
        # Start Flask server
        if not analyzer.start_flask_server():
            print("❌ Failed to start Flask server. Exiting...")
            return 1
        
        # Run comprehensive tests
        test_results = analyzer.run_comprehensive_load_test()
        
        # Generate graphs and analysis
        analyzer.generate_performance_graphs(test_results)
        analyzer.save_detailed_results(test_results)
        
        # Print summary
        print("\\n🎉 COMPREHENSIVE PERFORMANCE ANALYSIS COMPLETE!")
        print("=" * 60)
        
        for scenario_name, results in test_results.items():
            if 'error' not in results:
                print(f"\\n📊 {scenario_name}:")
                print(f"   Success Rate: {results['success_rate']:.1f}%")
                print(f"   Mean Latency: {results['mean_latency']:.1f} ms")
                print(f"   P95 Latency: {results['p95_latency']:.1f} ms")
                print(f"   Throughput: {results['throughput']:.1f} req/sec")
        
        print("\\n📁 Generated Files:")
        print("   📊 performance_graphs/comprehensive_performance_analysis.png")
        print("   📊 performance_graphs/*_detailed_analysis.png")
        print("   📋 performance_analysis_results.json")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1
    
    finally:
        analyzer.stop_flask_server()


if __name__ == "__main__":
    sys.exit(main())