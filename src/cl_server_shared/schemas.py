"""
Pydantic schemas for compute job parameters.
Shared between store service and compute worker.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, validator

class ComputeJobParams(BaseModel):
    """Base parameters for all compute jobs."""
    input_paths: List[str] = Field(default_factory=list, description="List of input file paths")
    output_paths: List[str] = Field(default_factory=list, description="List of output file paths")

    @validator("output_paths")
    def validate_output_paths_unique(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Output paths must be unique")
        return v

    @validator("output_paths")
    def validate_paths_length(cls, v, values):
        if "input_paths" in values and len(v) != len(values["input_paths"]):
            raise ValueError("Number of output paths must match number of input paths")
        return v

class ImageResizeParams(ComputeJobParams):
    """Parameters for image resize task."""
    width: int = Field(..., gt=0, description="Target width")
    height: int = Field(..., gt=0, description="Target height")

    @validator("input_paths")
    def validate_input_paths(cls, v):
        if not v:
            raise ValueError("At least one input path is required")
        return v

class ImageConversionParams(ComputeJobParams):
    """Parameters for image conversion task."""
    format: str = Field(..., description="Target format (e.g., JPEG, PNG)")
    quality: int = Field(85, ge=1, le=100, description="Compression quality (1-100)")

    @validator("input_paths")
    def validate_input_paths(cls, v):
        if not v:
            raise ValueError("At least one input path is required")
        return v
