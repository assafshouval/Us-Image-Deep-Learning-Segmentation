"""
Output directory and file management for segmentation tool.
Handles creation of workspace structure and saving of masks with original images.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from PyQt5.QtGui import QImage

from workspace_config import WorkspaceConfig


class OutputManager:
    """
    Manages output directory structure and file operations for segmentation workflow.
    
    Creates and maintains workspace structure:
    workspace/
    └── DirectoryName/
        ├── OriginalImage/
        └── Mask/
    """
    
    def __init__(self, source_directory_path, workspace_root=None):
        """
        Initialize output manager for a source directory.
        
        Args:
            source_directory_path: Path to directory being processed
            workspace_root: Root workspace location (default: from config)
        """
        self.source_directory_path = Path(source_directory_path)
        self.source_directory_name = self.source_directory_path.name
        
        if workspace_root is None:
            workspace_root = WorkspaceConfig.get_workspace_root()
        
        self.workspace_root = Path(workspace_root)
        self.subdirs = WorkspaceConfig.get_subdir_names()
        
        # Paths will be set by initialize_structure()
        self.workspace_dir = None
        self.original_dir = None
        self.mask_dir = None
    
    def initialize_structure(self) -> tuple:
        """
        Create workspace directory structure.
        
        Returns:
            tuple: (original_image_dir, mask_dir) - Paths to created directories
            
        Raises:
            OSError: If directory creation fails
        """
        # Build workspace path with directory name
        base_workspace_dir = self.workspace_root / self.source_directory_name
        
        # Handle duplicate directory names by appending timestamp
        if base_workspace_dir.exists():
            config = WorkspaceConfig.load()
            if config.get("create_timestamp_on_conflict", True):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                workspace_dir = self.workspace_root / f"{self.source_directory_name}_{timestamp}"
            else:
                workspace_dir = base_workspace_dir
        else:
            workspace_dir = base_workspace_dir
        
        # Create subdirectories
        original_dir = workspace_dir / self.subdirs["original"]
        mask_dir = workspace_dir / self.subdirs["mask"]
        
        try:
            original_dir.mkdir(parents=True, exist_ok=True)
            mask_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Failed to create workspace structure: {e}")
        
        # Store paths
        self.workspace_dir = workspace_dir
        self.original_dir = original_dir
        self.mask_dir = mask_dir
        
        return str(original_dir), str(mask_dir)
    
    def save_mask_with_original(self, image_path, mask_qimage, naming_pattern=None) -> tuple:
        """
        Save mask and copy original image to workspace.
        
        Args:
            image_path: Path to original image file (str or Path)
            mask_qimage: QImage object containing mask
            naming_pattern: Optional custom naming (default: from config)
            
        Returns:
            tuple: (saved_original_path, saved_mask_path) - Paths to saved files
            
        Raises:
            IOError: If save operation fails
            ValueError: If mask_qimage is invalid
        """
        if mask_qimage is None or mask_qimage.isNull():
            raise ValueError("Invalid mask image provided")
        
        if self.original_dir is None or self.mask_dir is None:
            raise RuntimeError("Workspace structure not initialized. Call initialize_structure() first.")
        
        image_path = Path(image_path)
        
        # Get naming pattern
        if naming_pattern is None:
            naming_pattern = WorkspaceConfig.get_naming_pattern()
        
        # Generate output paths
        original_filename = image_path.name
        original_dest = self.original_dir / original_filename
        
        # Create mask filename from pattern
        basename = image_path.stem  # filename without extension
        mask_filename = naming_pattern.format(basename=basename)
        mask_dest = self.mask_dir / mask_filename
        
        # Copy original image (if not already exists)
        try:
            if not original_dest.exists():
                shutil.copy2(str(image_path), str(original_dest))
        except (IOError, OSError) as e:
            raise IOError(f"Failed to copy original image: {e}")
        
        # Save mask
        try:
            success = mask_qimage.save(str(mask_dest), "PNG")
            if not success:
                raise IOError(f"QImage.save() returned False for {mask_dest}")
        except Exception as e:
            raise IOError(f"Failed to save mask: {e}")
        
        return str(original_dest), str(mask_dest)
    
    def get_workspace_info(self) -> dict:
        """
        Get information about current workspace structure.
        
        Returns:
            dict: Workspace information including paths and directory names
        """
        return {
            "workspace_root": str(self.workspace_root),
            "workspace_dir": str(self.workspace_dir) if self.workspace_dir else None,
            "original_dir": str(self.original_dir) if self.original_dir else None,
            "mask_dir": str(self.mask_dir) if self.mask_dir else None,
            "source_directory": str(self.source_directory_path),
            "source_directory_name": self.source_directory_name
        }
    
    def get_workspace_path(self):
        """
        Get the main workspace directory path.
        
        Returns:
            str or None: Path to workspace directory or None if not initialized
        """
        return str(self.workspace_dir) if self.workspace_dir else None
