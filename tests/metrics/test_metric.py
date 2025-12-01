import asyncio
import unittest

from src.metrics.metric import Metric


class DummyMetric(Metric):
    async def calculate(self, metric_input):
        return metric_input


class BrokenMetric(Metric):
    """A metric that accidentally calls super().calculate() to test the abstract method body."""

    async def calculate(self, metric_input):
        # This will call the abstract method body
        await super().calculate(metric_input)
        return 0.0


class IncompleteMetric(Metric):
    # This class doesn't implement calculate to test the abstract method
    pass


class TestMetricBase(unittest.TestCase):
    def test_abstract_method(self):
        with self.assertRaises(TypeError):
            Metric()

    def test_subclass_implements_calculate(self):
        async def run_test():
            dummy = DummyMetric()
            result = await dummy.calculate(42)
            return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertEqual(result, 42)
        finally:
            loop.close()

    def test_incomplete_subclass_cannot_be_instantiated(self):
        """Test that a subclass that doesn't implement calculate cannot be instantiated."""
        with self.assertRaises(TypeError):
            IncompleteMetric()

    def test_abstract_method_signature(self):
        """Test that the abstract method has correct signature."""
        # This ensures the abstract method definition is covered
        import inspect

        sig = inspect.signature(Metric.calculate)
        self.assertIn("metric_input", sig.parameters)
        self.assertEqual(len(sig.parameters), 2)  # self + metric_input

    def test_abstract_method_body_coverage(self):
        """Test to ensure the abstract method body is covered."""

        async def run_test():
            broken = BrokenMetric()
            # This should call the abstract method's pass statement
            result = await broken.calculate(42)
            return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertEqual(result, 0.0)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
