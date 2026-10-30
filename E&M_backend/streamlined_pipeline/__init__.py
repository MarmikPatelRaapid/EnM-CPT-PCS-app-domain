from .schemas import PipelineRequest, PipelineResponse

__all__ = ["PipelineOrchestrator", "PipelineRequest", "PipelineResponse"]


def __getattr__(name: str):
    if name == "PipelineOrchestrator":
        from .orchestrator import PipelineOrchestrator

        return PipelineOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
