#!/usr/bin/env python3
"""
Optimized Load Testing Script with Advanced Metrics Collection
Generates mean, p95, p99 latency and throughput data for visualization
"""

import asyncio
import aiohttp
import json
import time
import statistics
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OptimizedLoadTester:
    """Advanced load tester with comprehensive metrics collection."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.results = {}
        self.response_times = []
        self.throughput_data = []
        
    async def simulate_concurrent_users(self, num_users: int = 100, duration: int = 60) -> Dict[str, Any]:
        """Simulate concurrent users performing various operations."""
        logger.info(f"🚀 Starting load test: {num_users} users for {duration} seconds")
        
        # Prepare test data
        test_artifacts = self._generate_test_artifacts(50)
        
        # Create semaphore to control concurrency
        semaphore = asyncio.Semaphore(num_users)
        
        start_time = time.time()
        end_time = start_time + duration
        
        tasks = []
        
        async with aiohttp.ClientSession() as session:
            while time.time() < end_time:
                # Create batch of concurrent tasks
                batch_tasks = []
                for i in range(min(num_users, 20)):  # Process in batches
                    task = asyncio.create_task(
                        self._simulate_user_session(session, semaphore, test_artifacts)
                    )
                    batch_tasks.append(task)
                
                # Execute batch and collect results
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Process results
                for result in batch_results:
                    if isinstance(result, dict):
                        self.response_times.extend(result.get('response_times', []))
                        self.throughput_data.append({
                            'timestamp': time.time(),
                            'requests': len(result.get('response_times', []))
                        })
                
                # Small delay between batches
                await asyncio.sleep(0.1)
        
        total_time = time.time() - start_time
        return self._calculate_metrics(total_time)
    
    async def _simulate_user_session(self, session: aiohttp.ClientSession, 
                                   semaphore: asyncio.Semaphore, 
                                   test_artifacts: List[Dict]) -> Dict[str, Any]:
        """Simulate a single user session with multiple API calls."""
        async with semaphore:
            session_results = {'response_times': []}
            
            try:
                # 1. Get all packages
                response_time = await self._timed_request(session, 'GET', '/packages')
                session_results['response_times'].append(response_time)
                
                # 2. Upload an artifact
                artifact = np.random.choice(test_artifacts)
                response_time = await self._timed_request(
                    session, 'POST', '/artifacts', 
                    json=[{"name": artifact['name'], "types": [artifact['type']]}]
                )
                session_results['response_times'].append(response_time)
                
                # 3. Search by regex
                response_time = await self._timed_request(
                    session, 'POST', '/artifact/byRegEx',
                    json={"RegEx": ".*test.*"}
                )
                session_results['response_times'].append(response_time)
                
                # 4. Get artifact by name
                response_time = await self._timed_request(
                    session, 'GET', f'/artifact/byName/{artifact["name"]}'
                )
                session_results['response_times'].append(response_time)
                
            except Exception as e:
                logger.warning(f"User session error: {e}")
            
            return session_results
    
    async def _timed_request(self, session: aiohttp.ClientSession, 
                           method: str, endpoint: str, **kwargs) -> float:
        """Make a timed HTTP request and return response time in milliseconds."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            async with session.request(method, url, **kwargs) as response:
                await response.read()  # Ensure full response is received
                return (time.time() - start_time) * 1000  # Convert to milliseconds
        except Exception as e:
            logger.warning(f"Request failed {method} {endpoint}: {e}")
            return float('inf')  # Mark as failed
    
    def _generate_test_artifacts(self, count: int) -> List[Dict[str, str]]:
        """Generate test artifacts for load testing."""
        artifacts = []
        types = ['model', 'dataset', 'code']
        
        for i in range(count):
            artifacts.append({
                'name': f'test-artifact-{i}',
                'type': np.random.choice(types),
                'version': f'1.{i // 10}.{i % 10}'
            })
        
        return artifacts
    
    def _calculate_metrics(self, total_time: float) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        # Filter out failed requests (inf values)
        valid_times = [t for t in self.response_times if t != float('inf')]
        
        if not valid_times:
            return {'error': 'No successful requests'}
        
        # Convert to numpy array for percentile calculations
        times_array = np.array(valid_times)
        
        metrics = {
            'total_requests': len(self.response_times),
            'successful_requests': len(valid_times),
            'failed_requests': len(self.response_times) - len(valid_times),
            'total_duration': total_time,
            'throughput_rps': len(valid_times) / total_time,
            
            # Latency Metrics
            'mean_latency': float(np.mean(times_array)),
            'median_latency': float(np.median(times_array)),
            'p95_latency': float(np.percentile(times_array, 95)),
            'p99_latency': float(np.percentile(times_array, 99)),
            'min_latency': float(np.min(times_array)),
            'max_latency': float(np.max(times_array)),
            'std_latency': float(np.std(times_array)),
            
            # Raw data for plotting
            'raw_response_times': valid_times,
            'throughput_timeline': self.throughput_data
        }
        
        return metrics
    
    def generate_performance_graphs(self, metrics: Dict[str, Any], 
                                  output_dir: str = "performance_graphs") -> None:
        """Generate comprehensive performance visualization graphs."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Set style for better-looking graphs
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (12, 8)
        
        # 1. Latency Distribution Histogram
        plt.figure(figsize=(12, 6))
        plt.subplot(1, 2, 1)
        plt.hist(metrics['raw_response_times'], bins=50, alpha=0.7, color='skyblue', edgecolor='black')
        plt.axvline(metrics['mean_latency'], color='red', linestyle='--', label=f'Mean: {metrics["mean_latency"]:.1f}ms')
        plt.axvline(metrics['p95_latency'], color='orange', linestyle='--', label=f'P95: {metrics["p95_latency"]:.1f}ms')
        plt.axvline(metrics['p99_latency'], color='purple', linestyle='--', label=f'P99: {metrics["p99_latency"]:.1f}ms')
        plt.xlabel('Response Time (ms)')
        plt.ylabel('Frequency')
        plt.title('Response Time Distribution')
        plt.legend()
        
        # 2. Latency Box Plot
        plt.subplot(1, 2, 2)
        plt.boxplot(metrics['raw_response_times'], vert=True)
        plt.ylabel('Response Time (ms)')
        plt.title('Response Time Box Plot')
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path / 'latency_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. Throughput Over Time
        if metrics['throughput_timeline']:
            throughput_df = pd.DataFrame(metrics['throughput_timeline'])
            throughput_df['timestamp'] = pd.to_datetime(throughput_df['timestamp'], unit='s')
            
            plt.figure(figsize=(14, 6))
            plt.plot(throughput_df['timestamp'], throughput_df['requests'], marker='o', alpha=0.7)
            plt.xlabel('Time')
            plt.ylabel('Requests per Batch')
            plt.title('Throughput Over Time')
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(output_path / 'throughput_timeline.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 4. Performance Summary Dashboard
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Latency metrics bar chart
        latency_metrics = ['Mean', 'P95', 'P99', 'Max']
        latency_values = [
            metrics['mean_latency'], 
            metrics['p95_latency'], 
            metrics['p99_latency'], 
            metrics['max_latency']
        ]
        bars = ax1.bar(latency_metrics, latency_values, color=['#3498db', '#e74c3c', '#9b59b6', '#e67e22'])
        ax1.set_ylabel('Response Time (ms)')
        ax1.set_title('Latency Metrics Summary')
        
        # Add value labels on bars
        for bar, value in zip(bars, latency_values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(latency_values)*0.01,
                    f'{value:.1f}ms', ha='center', va='bottom')
        
        # Throughput gauge
        ax2.pie([metrics['successful_requests'], metrics['failed_requests']], 
               labels=['Success', 'Failed'], autopct='%1.1f%%',
               colors=['#2ecc71', '#e74c3c'])
        ax2.set_title(f'Request Success Rate\n({metrics["throughput_rps"]:.1f} RPS)')
        
        # Response time scatter plot
        times = metrics['raw_response_times'][:1000]  # Limit for visibility
        ax3.scatter(range(len(times)), times, alpha=0.6, s=10)
        ax3.set_xlabel('Request Number')
        ax3.set_ylabel('Response Time (ms)')
        ax3.set_title('Response Time Scatter (First 1000 requests)')
        
        # Performance summary text
        ax4.axis('off')
        summary_text = f"""
Performance Test Summary
━━━━━━━━━━━━━━━━━━━━━━━━

📊 Total Requests: {metrics['total_requests']:,}
✅ Success Rate: {(metrics['successful_requests']/metrics['total_requests']*100):.1f}%
⚡ Throughput: {metrics['throughput_rps']:.1f} req/sec
⏱️  Duration: {metrics['total_duration']:.1f} seconds

📈 Latency Metrics:
   Mean: {metrics['mean_latency']:.1f} ms
   P95: {metrics['p95_latency']:.1f} ms  
   P99: {metrics['p99_latency']:.1f} ms
   Std Dev: {metrics['std_latency']:.1f} ms

🎯 Performance Grade: {"A" if metrics['p95_latency'] < 200 else "B" if metrics['p95_latency'] < 500 else "C"}
        """
        ax4.text(0.1, 0.5, summary_text, fontsize=12, fontfamily='monospace',
                verticalalignment='center', bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray"))
        
        plt.tight_layout()
        plt.savefig(output_path / 'performance_dashboard.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"📊 Performance graphs saved to {output_path}")
    
    def save_detailed_report(self, metrics: Dict[str, Any], 
                           output_file: str = "performance_results.json") -> None:
        """Save detailed performance metrics to JSON file."""
        # Prepare data for JSON serialization
        report_data = {
            'test_metadata': {
                'timestamp': datetime.now().isoformat(),
                'test_type': 'Optimized Load Test',
                'version': '2.0'
            },
            'summary_metrics': {k: v for k, v in metrics.items() 
                              if k not in ['raw_response_times', 'throughput_timeline']},
            'raw_data_stats': {
                'response_time_samples': len(metrics.get('raw_response_times', [])),
                'throughput_samples': len(metrics.get('throughput_timeline', []))
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"📋 Detailed report saved to {output_file}")


async def main():
    """Main function to run optimized load tests."""
    logger.info("🎯 Starting Optimized Load Test & Graph Generation")
    
    # Initialize tester
    tester = OptimizedLoadTester()
    
    # Run load test
    try:
        metrics = await tester.simulate_concurrent_users(
            num_users=50,  # Start with moderate load
            duration=30    # 30 second test
        )
        
        if 'error' in metrics:
            logger.error(f"Load test failed: {metrics['error']}")
            return
        
        # Generate graphs
        tester.generate_performance_graphs(metrics)
        
        # Save detailed report
        tester.save_detailed_report(metrics)
        
        # Print summary
        print("\n" + "="*60)
        print("🎉 OPTIMIZED LOAD TEST RESULTS")
        print("="*60)
        print(f"📊 Total Requests: {metrics['total_requests']:,}")
        print(f"✅ Success Rate: {(metrics['successful_requests']/metrics['total_requests']*100):.1f}%")
        print(f"⚡ Throughput: {metrics['throughput_rps']:.1f} req/sec")
        print(f"📈 Mean Latency: {metrics['mean_latency']:.1f} ms")
        print(f"📈 P95 Latency: {metrics['p95_latency']:.1f} ms")
        print(f"📈 P99 Latency: {metrics['p99_latency']:.1f} ms")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())