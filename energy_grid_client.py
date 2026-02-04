import hashlib
import time
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from collections import deque
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

@dataclass
class Config:
    base_url: str = "http://localhost:3000"
    endpoint: str = "/device/real/query"
    token: str = "interview_token_123"
    batch_size: int = 10
    rate_limit_seconds: float = 1.0
    max_retries: int = 3
    retry_backoff: float = 2.0  
    timeout: int = 30



class SignatureGenerator:
    
    def __init__(self, token: str):
        self.token = token
    
    def generate(self, url: str, timestamp: int) -> str:
        
        payload = f"{url}{self.token}{timestamp}"
        return hashlib.md5(payload.encode()).hexdigest()


class RateLimiter:
    
    def __init__(self, min_interval: float = 1.0):
        self.min_interval = min_interval
        self.last_request_time: float = 0
        self._buffer = 0.05  # 50ms buffer for safety
    
    def wait(self) -> None:
        now = time.time()
        elapsed = now - self.last_request_time
        required_wait = self.min_interval + self._buffer
        
        if elapsed < required_wait:
            sleep_time = required_wait - elapsed
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def reset(self) -> None:
        self.last_request_time = 0



class EnergyGridAPIClient:
    
    def __init__(self, config: Config):
        self.config = config
        self.signer = SignatureGenerator(config.token)
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        session = requests.Session()
        
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=1,
            pool_maxsize=1
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _build_headers(self) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        signature = self.signer.generate(self.config.endpoint, timestamp)
        
        return {
            "Content-Type": "application/json",
            "timestamp": timestamp,
            "signature": signature
        }
    
    def query_devices(self, serial_numbers: List[str]) -> requests.Response:
       
        url = f"{self.config.base_url}{self.config.endpoint}"
        headers = self._build_headers()
        payload = {"sn_list": serial_numbers}
        
        return self.session.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.config.timeout
        )
    
    def close(self) -> None:
        self.session.close()


@dataclass
class BatchResult:
    batch_index: int
    serial_numbers: List[str]
    data: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    attempts: int = 0


class BatchProcessor:
 
    def __init__(self, client: EnergyGridAPIClient, config: Config):
        self.client = client
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit_seconds)
    
    @staticmethod
    def create_batches(items: List[str], batch_size: int) -> List[List[str]]:
        return [
            items[i:i + batch_size] 
            for i in range(0, len(items), batch_size)
        ]
    
    def _process_single_batch(
        self, 
        batch: List[str], 
        batch_index: int
    ) -> BatchResult:
       
        result = BatchResult(
            batch_index=batch_index,
            serial_numbers=batch
        )
        
        for attempt in range(self.config.max_retries):
            result.attempts = attempt + 1
            
            try:
                self.rate_limiter.wait()
                
                response = self.client.query_devices(batch)
                
                if response.status_code == 200:
                    data = response.json()
                    result.data = data.get("data", [])
                    result.success = True
                    return result
                
                elif response.status_code == 429:
                    wait_time = self.config.retry_backoff ** attempt
                    print(f"  Rate limited on batch {batch_index}, "
                          f"waiting {wait_time:.1f}s (attempt {attempt + 1})")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code == 401:
                    result.error = f"Authentication failed: {response.text}"
                    return result
                
                else:
                    result.error = f"HTTP {response.status_code}: {response.text}"
                    return result
                    
            except requests.exceptions.RequestException as e:
                result.error = f"Network error: {str(e)}"
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_backoff ** attempt
                    print(f"   Network error on batch {batch_index}, "
                          f"retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue
        
        if not result.success and not result.error:
            result.error = "Max retries exceeded"
        
        return result
    
    def process_all_batches(
        self, 
        serial_numbers: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[BatchResult]:
       
        batches = self.create_batches(serial_numbers, self.config.batch_size)
        results: List[BatchResult] = []
        
        total_batches = len(batches)
        print(f"\n Processing {len(serial_numbers)} devices in {total_batches} batches")
        print(f"   Rate limit: {self.config.rate_limit_seconds}s between requests")
        print(f"   Batch size: {self.config.batch_size} devices\n")
        
        for idx, batch in enumerate(batches):
            result = self._process_single_batch(batch, idx)
            results.append(result)
            
            # Progress output
            status = "ok" if result.success else "failed"
            print(f"  [{idx + 1:3}/{total_batches}] {status} "
                  f"Batch {idx}: {len(batch)} devices "
                  f"(attempts: {result.attempts})")
            
            if progress_callback:
                progress_callback(idx + 1, total_batches, result)
        
        return results


@dataclass
class AggregatedReport:
    total_devices: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    total_power_kw: float = 0.0
    average_power_kw: float = 0.0
    devices: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "total_devices": self.total_devices,
                "successful_queries": self.successful_queries,
                "failed_queries": self.failed_queries,
                "online_devices": self.online_devices,
                "offline_devices": self.offline_devices,
                "total_power_kw": round(self.total_power_kw, 2),
                "average_power_kw": round(self.average_power_kw, 2),
                "execution_time_seconds": round(self.execution_time_seconds, 2)
            },
            "devices": self.devices,
            "errors": self.errors
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class DataAggregator:
    
    @staticmethod
    def aggregate(
        batch_results: List[BatchResult], 
        execution_time: float
    ) -> AggregatedReport:
       
        report = AggregatedReport()
        report.execution_time_seconds = execution_time
        
        all_devices: List[Dict[str, Any]] = []
        total_power = 0.0
        
        for batch in batch_results:
            if batch.success:
                for device in batch.data:
                    all_devices.append(device)
                    
                    # Count status
                    if device.get("status") == "Online":
                        report.online_devices += 1
                    else:
                        report.offline_devices += 1
                    
                    power_str = device.get("power", "0 kW")
                    try:
                        power_val = float(power_str.replace(" kW", ""))
                        total_power += power_val
                    except ValueError:
                        pass
                
                report.successful_queries += len(batch.data)
            else:
                report.failed_queries += len(batch.serial_numbers)
                report.errors.append({
                    "batch_index": batch.batch_index,
                    "serial_numbers": batch.serial_numbers,
                    "error": batch.error,
                    "attempts": batch.attempts
                })
        
        report.total_devices = report.successful_queries + report.failed_queries
        report.devices = all_devices
        report.total_power_kw = total_power
        
        if report.successful_queries > 0:
            report.average_power_kw = total_power / report.successful_queries
        
        return report


class EnergyGridDataAggregator:
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.client = EnergyGridAPIClient(self.config)
        self.processor = BatchProcessor(self.client, self.config)
        self.aggregator = DataAggregator()
    
    @staticmethod
    def generate_serial_numbers(count: int = 500) -> List[str]:
        return [f"SN-{i:03d}" for i in range(count)]
    
    def run(self, serial_numbers: Optional[List[str]] = None) -> AggregatedReport:
        if serial_numbers is None:
            serial_numbers = self.generate_serial_numbers()
        
        print("=" * 60)
        print("EnergyGrid Data Aggregator")
        print("=" * 60)
        print(f"\nTarget: {self.config.base_url}{self.config.endpoint}")
        print(f"Devices to query: {len(serial_numbers)}")
        
        start_time = time.time()
        
        try:
            batch_results = self.processor.process_all_batches(serial_numbers)
            
            execution_time = time.time() - start_time
            report = self.aggregator.aggregate(batch_results, execution_time)
            
            self._print_summary(report)
            
            return report
            
        finally:
            self.client.close()
    
    def _print_summary(self, report: AggregatedReport) -> None:
        print("\n" + "=" * 60)
        print("AGGREGATION SUMMARY")
        print("=" * 60)
        print(f"  Total devices queried:  {report.total_devices}")
        print(f"  Successful queries:     {report.successful_queries}")
        print(f"  Failed queries:         {report.failed_queries}")
        print(f"  Online devices:         {report.online_devices}")
        print(f"  Offline devices:        {report.offline_devices}")
        print(f"  Total power output:     {report.total_power_kw:.2f} kW")
        print(f"  Average power/device:   {report.average_power_kw:.2f} kW")
        print(f"  Execution time:         {report.execution_time_seconds:.2f} seconds")
        
        if report.errors:
            print(f"\n {len(report.errors)} batches failed:")
            for err in report.errors[:5]:  # Show first 5 errors
                print(f"    - Batch {err['batch_index']}: {err['error']}")
            if len(report.errors) > 5:
                print(f"    ... and {len(report.errors) - 5} more")
        
        print("=" * 60)



def main():
    aggregator = EnergyGridDataAggregator()
    
    report = aggregator.run()
    
    # Save full report to file
    output_file = "telemetry_report.json"
    with open(output_file, "w") as f:
        f.write(report.to_json())
    
    print(f"\nFull report saved to: {output_file}")
    
    return report


if __name__ == "__main__":
    main()
