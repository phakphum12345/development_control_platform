"""Tests for the opt-in local Runner service supervisor."""
import threading
import unittest

from tools.local_runner_agent.client import RunnerGatewayError
from tools.local_runner_agent.execution import ExecutionError
from tools.local_runner_agent.service import RunnerAgentService


class RunnerAgentServiceTests(unittest.TestCase):
    def test_idle_poll_then_job_processing_stops_without_claiming_more_work(self):
        stop = threading.Event()

        class Pipeline:
            def __init__(self):
                self.results = [None, {"outcome": "succeeded"}, None]
                self.calls = 0

            def run_once(self):
                self.calls += 1
                return self.results.pop(0)

        pipeline = Pipeline()
        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                stop.set()

        result = RunnerAgentService(
            pipeline, poll_interval_seconds=4, wait=wait
        ).run(stop)

        self.assertTrue(result["stopped"])
        self.assertEqual(result["cycles"], 3)
        self.assertEqual(result["jobs_processed"], 1)
        self.assertEqual(result["idle_polls"], 2)
        self.assertEqual(result["outcomes"]["succeeded"], 1)
        self.assertEqual(waits, [4, 4])
        self.assertEqual(pipeline.calls, 3)

    def test_gateway_failures_use_bounded_exponential_backoff(self):
        stop = threading.Event()

        class Pipeline:
            def __init__(self):
                self.results = [
                    RunnerGatewayError("safe transport failure"),
                    RunnerGatewayError("safe transport failure"),
                    None,
                ]

            def run_once(self):
                result = self.results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result

        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 3:
                stop.set()

        result = RunnerAgentService(
            Pipeline(), poll_interval_seconds=5,
            max_backoff_seconds=2, wait=wait,
        ).run(stop)

        self.assertTrue(result["stopped"])
        self.assertEqual(result["gateway_errors"], 2)
        self.assertEqual(waits, [1, 2, 5])

    def test_draining_or_offline_runner_stops_service_without_retry(self):
        stop = threading.Event()

        class Pipeline:
            def run_once(self):
                raise ExecutionError("runner is draining")

        waits = []
        result = RunnerAgentService(
            Pipeline(), wait=lambda seconds: waits.append(seconds)
        ).run(stop)

        self.assertFalse(result["stopped"])
        self.assertEqual(result["reason"], "runner_not_eligible")
        self.assertEqual(result["cycles"], 0)
        self.assertEqual(waits, [])

    def test_invalid_service_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            RunnerAgentService(object(), poll_interval_seconds=0)
        with self.assertRaises(ValueError):
            RunnerAgentService(object(), max_backoff_seconds=301)
        with self.assertRaises(ValueError):
            RunnerAgentService(object()).run(threading.Event(), max_cycles=0)


if __name__ == "__main__":
    unittest.main()
