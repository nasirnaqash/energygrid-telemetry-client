import hashlib
import time
import json
from unittest.mock import Mock, patch, MagicMock
import sys

from energy_grid_client import (
    Config,
    SignatureGenerator,
    RateLimiter,
    BatchProcessor,
    DataAggregator,
    BatchResult,
    AggregatedReport,
    EnergyGridDataAggregator,
)


def test_signature_generator():
    print("Testing SignatureGenerator...")
    
    signer = SignatureGenerator("interview_token_123")
    
    # Test case 1: 
    url = "/device/real/query"
    timestamp = "1704067200000"  # Example timestamp
    
    signature = signer.generate(url, timestamp)
    
    payload = f"{url}interview_token_123{timestamp}"
    expected = hashlib.md5(payload.encode()).hexdigest()
    
    assert signature == expected, f"Signature mismatch: {signature} != {expected}"
    print(f"  Signature generation correct: {signature}")
    
    # Test case 2
    sig1 = signer.generate("/path1", "100")
    sig2 = signer.generate("/path2", "100")
    sig3 = signer.generate("/path1", "200")
    
    assert sig1 != sig2, "Different paths should produce different signatures"
    assert sig1 != sig3, "Different timestamps should produce different signatures"
    print("  Different inputs produce unique signatures")
    
    print("  SignatureGenerator tests passed!\n")


def test_rate_limiter():
    print("Testing RateLimiter...")
    
    limiter = RateLimiter(min_interval=0.1)  
    
    start = time.time()
    limiter.wait()
    elapsed1 = time.time() - start
    
    assert elapsed1 < 0.1, f"First call should not wait, took {elapsed1:.3f}s"
    print(f"  ✓ First call completed quickly ({elapsed1:.3f}s)")
    
    start = time.time()
    limiter.wait()
    elapsed2 = time.time() - start
    
    assert elapsed2 >= 0.1, f"Second call should wait at least 0.1s, waited {elapsed2:.3f}s"
    print(f"  Second call properly waited ({elapsed2:.3f}s)")
    
    # Reset and verify
    limiter.reset()
    start = time.time()
    limiter.wait()
    elapsed3 = time.time() - start
    
    assert elapsed3 < 0.1, "After reset, should not wait"
    print("  Reset works correctly")
    
    print("  RateLimiter tests passed!\n")


def test_batch_creation():
    print("Testing batch creation...")
    
    items = [f"SN-{i:03d}" for i in range(25)]
    
    batches = BatchProcessor.create_batches(items, batch_size=10)
    
    assert len(batches) == 3, f"Expected 3 batches, got {len(batches)}"
    assert len(batches[0]) == 10, "First batch should have 10 items"
    assert len(batches[1]) == 10, "Second batch should have 10 items"
    assert len(batches[2]) == 5, "Third batch should have 5 items"
    
    flattened = [item for batch in batches for item in batch]
    assert flattened == items, "Batching should preserve all items"
    
    print(f"  25 items correctly split into 3 batches: [10, 10, 5]")
    print("  Batch creation tests passed!\n")


def test_serial_number_generation():
    print("Testing serial number generation...")
    
    sns = EnergyGridDataAggregator.generate_serial_numbers(500)
    
    assert len(sns) == 500, f"Expected 500 SNs, got {len(sns)}"
    assert sns[0] == "SN-000", f"First SN should be SN-000, got {sns[0]}"
    assert sns[499] == "SN-499", f"Last SN should be SN-499, got {sns[499]}"
    assert len(set(sns)) == 500, "All SNs should be unique"
    
    print(f"  Generated 500 unique serial numbers (SN-000 to SN-499)")
    print("  Serial number generation tests passed!\n")


def test_data_aggregator():
    print("Testing DataAggregator...")
    
    batch_results = [
        BatchResult(
            batch_index=0,
            serial_numbers=["SN-000", "SN-001"],
            data=[
                {"sn": "SN-000", "power": "2.50 kW", "status": "Online"},
                {"sn": "SN-001", "power": "1.50 kW", "status": "Offline"},
            ],
            success=True,
            attempts=1
        ),
        BatchResult(
            batch_index=1,
            serial_numbers=["SN-002", "SN-003"],
            data=[
                {"sn": "SN-002", "power": "3.00 kW", "status": "Online"},
                {"sn": "SN-003", "power": "2.00 kW", "status": "Online"},
            ],
            success=True,
            attempts=1
        ),
        BatchResult(
            batch_index=2,
            serial_numbers=["SN-004", "SN-005"],
            data=[],
            success=False,
            error="Network error",
            attempts=3
        )
    ]
    
    report = DataAggregator.aggregate(batch_results, execution_time=5.0)
    
    assert report.total_devices == 6, f"Expected 6 total devices, got {report.total_devices}"
    assert report.successful_queries == 4, f"Expected 4 successful, got {report.successful_queries}"
    assert report.failed_queries == 2, f"Expected 2 failed, got {report.failed_queries}"
    assert report.online_devices == 3, f"Expected 3 online, got {report.online_devices}"
    assert report.offline_devices == 1, f"Expected 1 offline, got {report.offline_devices}"
    assert abs(report.total_power_kw - 9.0) < 0.01, f"Expected 9.0 kW total, got {report.total_power_kw}"
    assert abs(report.average_power_kw - 2.25) < 0.01, f"Expected 2.25 kW average, got {report.average_power_kw}"
    assert len(report.errors) == 1, f"Expected 1 error entry, got {len(report.errors)}"
    
    print("  Correct device counts (6 total, 4 success, 2 failed)")
    print("  Correct status counts (3 online, 1 offline)")
    print("  Correct power calculations (9.0 kW total, 2.25 kW avg)")
    print("  Error tracking working correctly")
    
    json_output = report.to_json()
    parsed = json.loads(json_output)
    assert "summary" in parsed, "JSON should contain summary"
    assert "devices" in parsed, "JSON should contain devices"
    
    print("  JSON serialization working")
    print("  DataAggregator tests passed!\n")


def test_config():
    print("Testing Config...")
    
    config = Config()
    
    assert config.base_url == "http://localhost:3000"
    assert config.endpoint == "/device/real/query"
    assert config.token == "interview_token_123"
    assert config.batch_size == 10
    assert config.rate_limit_seconds == 1.0
    assert config.max_retries == 3
    
    print("  All default config values correct")
    print("  Config tests passed!\n")


def test_integration_mocked():
    print("Testing full integration (mocked HTTP)...")
    
    # mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"sn": f"SN-{i:03d}", "power": "2.50 kW", "status": "Online"}
            for i in range(10)
        ]
    }
    
    with patch('energy_grid_client.requests.Session') as MockSession:
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_response
        MockSession.return_value = mock_session_instance
        
        config = Config(rate_limit_seconds=0.01)  
        aggregator = EnergyGridDataAggregator(config)
        
        aggregator.processor.rate_limiter = RateLimiter(min_interval=0.01)
        
        serial_numbers = aggregator.generate_serial_numbers(20)
        report = aggregator.run(serial_numbers)
        
        assert report.successful_queries == 20, f"Expected 20 successful, got {report.successful_queries}"
        assert report.failed_queries == 0, f"Expected 0 failed, got {report.failed_queries}"
        
        assert mock_session_instance.post.call_count == 2, "Should make 2 API calls"
        
    print("  Mocked integration completed successfully")
    print("  Correct number of API calls made")
    print("  Integration tests passed!\n")


def run_all_tests():
    print("=" * 60)
    print("EnergyGrid Data Aggregator - Unit Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_config,
        test_signature_generator,
        test_rate_limiter,
        test_batch_creation,
        test_serial_number_generation,
        test_data_aggregator,
        test_integration_mocked,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
