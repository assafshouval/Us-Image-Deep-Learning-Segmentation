"""
Workspace configuration management for segmentation tool.
Handles loading, saving, and validation of workspace settings.
"""

import json
import os
from pathlib import Path
from PyQt5.QtWidgets import QFileDialog, QMessageBox


class WorkspaceConfig:
    """Manages workspace configuration settings."""
    
    DEFAULT_WORKSPACE_ROOT = "./workspace"
    DEFAULT_NAMING_PATTERN = "{basename}_mask.png"
    CONFIG_FILE = "workspace_config.json"
    
    DEFAULT_CONFIG = {
        "workspace_root": DEFAULT_WORKSPACE_ROOT,
        "naming_pattern": DEFAULT_NAMING_PATTERN,
        "subdirs": {
            "original": "OriginalImage",
            "mask": "Mask"
        },
        "overwrite_existing": True,
        "create_timestamp_on_conflict": True
    }
    
    @classmethod
    def load(cls) -> dict:
        """
        Load configuration from file or return defaults.
        
        Returns:
            dict: Configuration dictionary with all settings
        """
        config_path = Path(cls.CONFIG_FILE)
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    config = cls.DEFAULT_CONFIG.copy()
                    config.update(loaded_config)
                    return config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load config file: {e}. Using defaults.")
                return cls.DEFAULT_CONFIG.copy()
        
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def save(cls, config: dict) -> None:
        """
        Save configuration to file.
        
        Args:
            config: Configuration dictionary to save
            
        Raises:
            IOError: If save operation fails
        """
        config_path = Path(cls.CONFIG_FILE)
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            raise IOError(f"Failed to save configuration: {e}")
    
    @classmethod
    def get_workspace_root(cls) -> str:
        """
        Get configured workspace root path.
        
        Returns:
            str: Path to workspace root directory
        """
        config = cls.load()
        return config.get("workspace_root", cls.DEFAULT_WORKSPACE_ROOT)
    
    @classmethod
    def get_subdir_names(cls) -> dict:
        """
        Get subdirectory names for original images and masks.
        
        Returns:
            dict: Dictionary with 'original' and 'mask' subdirectory names
        """
        config = cls.load()
        return config.get("subdirs", cls.DEFAULT_CONFIG["subdirs"])
    
    @classmethod
    def get_naming_pattern(cls) -> str:
        """
        Get mask filename naming pattern.
        
        Returns:
            str: Naming pattern string with {basename} placeholder
        """
        config = cls.load()
        return config.get("naming_pattern", cls.DEFAULT_NAMING_PATTERN)
    
    @classmethod
    def set_workspace_root(cls, new_root: str) -> None:
        """
        Update workspace root in configuration.
        
        Args:
            new_root: New workspace root path
        """
        config = cls.load()
        config["workspace_root"] = new_root
        cls.save(config)
    
    @classmethod
    def show_folder_selection_dialog(cls, parent=None) -> bool:
        """
        Show dialog to select workspace folder and update configuration.
        
        Args:
            parent: Parent widget for the dialog
            
        Returns:
            bool: True if folder was selected and saved, False if cancelled
        """
        current_workspace = cls.get_workspace_root()
        
        folder = QFileDialog.getExistingDirectory(
            parent,
            "Select Workspace Output Folder",
            current_workspace,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            try:
                cls.set_workspace_root(folder)
                QMessageBox.information(
                    parent,
                    "Workspace Updated",
                    f"Workspace folder set to:\n{folder}"
                )
                return True
            except IOError as e:
                QMessageBox.critical(
                    parent,
                    "Configuration Error",
                    f"Failed to save configuration: {e}"
                )
                return False
        
        return False
