"""
Test script for temporary file manager

This script tests the temporary file manager to ensure it properly handles
file creation and cleanup in various deployment environments.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Import the modules we want to test
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.temporary_file_manager import TemporaryFileManager, DeploymentConfig


class TestTemporaryFileManager:
    """Test cases for TemporaryFileManager"""
    
    def test_create_temp_file_success(self):
        """Test successful temporary file creation"""
        manager = TemporaryFileManager()
        
        with manager.create_temp_file(suffix='.png', prefix='test_') as temp_path:
            # Verify file was created
            assert os.path.exists(temp_path)
            assert temp_path.endswith('.png')
            assert 'test_' in os.path.basename(temp_path)
            
            # Write some test data
            with open(temp_path, 'wb') as f:
                f.write(b'test data')
            
            # Verify data was written
            with open(temp_path, 'rb') as f:
                assert f.read() == b'test data'
        
        # Verify file was cleaned up
        assert not os.path.exists(temp_path)
    
    def test_create_temp_file_exception_cleanup(self):
        """Test that temporary files are cleaned up even when exceptions occur"""
        manager = TemporaryFileManager()
        
        try:
            with manager.create_temp_file(suffix='.png', prefix='test_') as temp_path:
                # Verify file was created
                assert os.path.exists(temp_path)
                
                # Simulate an exception
                raise Exception("Test exception")
        except Exception:
            pass
        
        # Verify file was still cleaned up despite exception
        assert not os.path.exists(temp_path)
    
    def test_cleanup_all(self):
        """Test cleanup_all method"""
        manager = TemporaryFileManager()
        created_files = []
        
        # Create multiple temporary files
        for i in range(3):
            with manager.create_temp_file(suffix=f'_{i}.txt', prefix='test_') as temp_path:
                created_files.append(temp_path)
                with open(temp_path, 'w') as f:
                    f.write(f'test data {i}')
        
        # Verify files exist
        for file_path in created_files:
            assert os.path.exists(file_path)
        
        # Clean up all files
        manager.cleanup_all()
        
        # Verify all files were cleaned up
        for file_path in created_files:
            assert not os.path.exists(file_path)


class TestDeploymentConfig:
    """Test cases for DeploymentConfig"""
    
    def test_get_temp_directory(self):
        """Test getting appropriate temp directory"""
        temp_dir = DeploymentConfig.get_temp_directory()
        
        # Should return a valid directory
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
    
    @patch('os.access')
    def test_get_file_upload_strategy_writable(self, mock_access):
        """Test file upload strategy when temp directory is writable"""
        mock_access.return_value = True
        
        strategy = DeploymentConfig.get_file_upload_strategy()
        assert strategy == 'file_system'
    
    @patch('os.access')
    def test_get_file_upload_strategy_not_writable(self, mock_access):
        """Test file upload strategy when temp directory is not writable"""
        mock_access.return_value = False
        
        strategy = DeploymentConfig.get_file_upload_strategy()
        assert strategy == 'memory_only'
    
    @patch('os.access')
    def test_should_use_memory_fallback_true(self, mock_access):
        """Test memory fallback when file system is not available"""
        mock_access.return_value = False
        
        should_use = DeploymentConfig.should_use_memory_fallback()
        assert should_use == True
    
    @patch('os.access')
    def test_should_use_memory_fallback_false(self, mock_access):
        """Test memory fallback when file system is available"""
        mock_access.return_value = True
        
        should_use = DeploymentConfig.should_use_memory_fallback()
        assert should_use == False


def test_integration_with_environment_variables():
    """Test integration with environment variables"""
    # Test with custom temp directory
    custom_temp_dir = '/tmp/custom_temp'
    
    with patch.dict(os.environ, {'TEMP_DIRECTORY': custom_temp_dir}):
        # This should return the custom directory if it exists and is writable
        temp_dir = DeploymentConfig.get_temp_directory()
        
        # If the custom directory doesn't exist, it should fall back to system temp
        if not os.path.exists(custom_temp_dir):
            assert temp_dir == tempfile.gettempdir()


if __name__ == "__main__":
    # Run basic tests
    print("Testing TemporaryFileManager...")
    
    # Test basic functionality
    manager = TemporaryFileManager()
    
    try:
        with manager.create_temp_file(suffix='.png', prefix='test_') as temp_path:
            print(f"✓ Created temporary file: {temp_path}")
            
            # Write test data
            with open(temp_path, 'wb') as f:
                f.write(b'test data')
            print(f"✓ Wrote test data to file")
            
            # Verify file exists
            assert os.path.exists(temp_path)
            print(f"✓ File exists and is accessible")
        
        # Verify cleanup
        assert not os.path.exists(temp_path)
        print(f"✓ File was properly cleaned up")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        raise
    
    # Test deployment config
    print("\nTesting DeploymentConfig...")
    
    temp_dir = DeploymentConfig.get_temp_directory()
    print(f"✓ Temp directory: {temp_dir}")
    
    strategy = DeploymentConfig.get_file_upload_strategy()
    print(f"✓ Upload strategy: {strategy}")
    
    should_use_memory = DeploymentConfig.should_use_memory_fallback()
    print(f"✓ Should use memory fallback: {should_use_memory}")
    
    print("\n✓ All tests passed!") 