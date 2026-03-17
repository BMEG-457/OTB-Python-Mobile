"""Unit tests for app/processing/pipeline.py.

Tests the ProcessingPipeline class and the get_pipeline/clear_pipelines registry.
Run with:
    python -m unittest tests.test_pipeline
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from app.processing.pipeline import ProcessingPipeline, get_pipeline, clear_pipelines


class TestProcessingPipeline(unittest.TestCase):

    def setUp(self):
        self.pipeline = ProcessingPipeline()

    def test_empty_pipeline_returns_input_unchanged(self):
        data = np.ones((8, 100))
        result = self.pipeline.run(data)
        np.testing.assert_array_equal(result, data)

    def test_single_stage_applied(self):
        self.pipeline.add_stage(lambda x: x * 2)
        data = np.ones((4, 50))
        result = self.pipeline.run(data)
        np.testing.assert_allclose(result, 2.0)

    def test_multiple_stages_applied_in_order(self):
        # Stage 1: multiply by 2, Stage 2: add 1 → result = input*2 + 1
        self.pipeline.add_stage(lambda x: x * 2)
        self.pipeline.add_stage(lambda x: x + 1)
        data = np.ones((2, 10))
        result = self.pipeline.run(data)
        np.testing.assert_allclose(result, 3.0)

    def test_stage_receives_previous_output(self):
        # Second stage should see the output of the first
        seen = []
        self.pipeline.add_stage(lambda x: x + 10)
        self.pipeline.add_stage(lambda x: (seen.append(x.copy()), x)[1])
        data = np.zeros((1, 5))
        self.pipeline.run(data)
        np.testing.assert_allclose(seen[0], 10.0)

    def test_stages_list_grows_on_add(self):
        self.assertEqual(len(self.pipeline.stages), 0)
        self.pipeline.add_stage(lambda x: x)
        self.assertEqual(len(self.pipeline.stages), 1)
        self.pipeline.add_stage(lambda x: x)
        self.assertEqual(len(self.pipeline.stages), 2)

    def test_run_preserves_dtype(self):
        self.pipeline.add_stage(lambda x: x)
        data = np.ones((4, 100), dtype=np.float32)
        result = self.pipeline.run(data)
        self.assertEqual(result.dtype, np.float32)


class TestPipelineRegistry(unittest.TestCase):

    def setUp(self):
        clear_pipelines()

    def tearDown(self):
        clear_pipelines()

    def test_get_pipeline_creates_on_first_call(self):
        p = get_pipeline('test')
        self.assertIsNotNone(p)
        self.assertIsInstance(p, ProcessingPipeline)

    def test_get_pipeline_returns_same_instance(self):
        p1 = get_pipeline('test')
        p2 = get_pipeline('test')
        self.assertIs(p1, p2)

    def test_different_names_return_different_instances(self):
        p1 = get_pipeline('a')
        p2 = get_pipeline('b')
        self.assertIsNot(p1, p2)

    def test_clear_pipelines_removes_all(self):
        get_pipeline('x')
        get_pipeline('y')
        clear_pipelines()
        # After clearing, get_pipeline creates a new (empty) instance
        p = get_pipeline('x')
        self.assertEqual(len(p.stages), 0)

    def test_stages_added_via_registry_are_run(self):
        get_pipeline('filtered').add_stage(lambda x: x * 3)
        data = np.ones((2, 10))
        result = get_pipeline('filtered').run(data)
        np.testing.assert_allclose(result, 3.0)

    def test_pipelines_are_independent(self):
        get_pipeline('p1').add_stage(lambda x: x + 1)
        get_pipeline('p2').add_stage(lambda x: x + 100)
        data = np.zeros((1, 5))
        r1 = get_pipeline('p1').run(data)
        r2 = get_pipeline('p2').run(data)
        np.testing.assert_allclose(r1, 1.0)
        np.testing.assert_allclose(r2, 100.0)


if __name__ == '__main__':
    unittest.main()
