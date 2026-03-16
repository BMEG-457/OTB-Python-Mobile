# A unified processing pipeline that tracks call.

class ProcessingPipeline:
    def __init__(self):
        self.stages = []  # list of callables

    def add_stage(self, func):
        self.stages.append(func)

    def run(self, data):
        x = data
        for stage in self.stages:
            x = stage(x)
        return x


# Simple registry to hold named pipelines so callers can configure pipelines
# before a receiver thread is created. Use `get_pipeline(name)` to obtain a
# shared ProcessingPipeline instance (created on demand).
_PIPELINES = {}

def get_pipeline(name: str) -> ProcessingPipeline:
    """Return a ProcessingPipeline for `name`, creating it if necessary.

    Example:
        from app.processing.pipeline import get_pipeline
        get_pipeline('filtered').add_stage(filters.butter_bandpass_lowpass)
    """
    if name not in _PIPELINES:
        _PIPELINES[name] = ProcessingPipeline()
    return _PIPELINES[name]

def clear_pipelines():
    """Clear all registered pipelines (useful for tests)."""
    _PIPELINES.clear()
