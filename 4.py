import getpass
import os
import sys
from datetime import timedelta, datetime
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import List, Dict, Any, Optional
import time

import pandas as pd
from requests_ntlm import HttpNtlmAuth
from sharepoint import Site
from PyQt6.QtCore import QObject, pyqtSignal, QThread

user_main = getpass.getuser()

# Set global socket timeout for all network operations
socket.setdefaulttimeout(30)

# Thread pool for async operations
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="StaticWorker")


class UserFriendlyError(Exception):
    """Custom exception for user-friendly error messages"""
    pass


class AsyncActionLogger(QObject):
    """Asynchronous action logger to prevent UI blocking"""
    finished = pyqtSignal(bool)  # Success status
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, action_data: List[Dict[str, str]]):
        super().__init__()
        self.action_data = action_data
        self._is_cancelled = False

    def cancel(self):
        """Cancel the logging operation"""
        self._is_cancelled = True

    def run(self):
        """Log action in background thread"""
        try:
            if self._is_cancelled:
                return

            # Perform the actual logging with retry mechanism
            success = self._log_with_retry(self.action_data, max_retries=3)
            
            if not self._is_cancelled:
                self.finished.emit(success)
                
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(f"Failed to log action: {str(e)}")
                self.finished.emit(False)

    def _log_with_retry(self, data: List[Dict[str, str]], max_retries: int = 3) -> bool:
        """Log action with retry mechanism"""
        for attempt in range(max_retries):
            if self._is_cancelled:
                return False
                
            try:
                # Create SharePoint connection with timeout
                cred = HttpNtlmAuth(SID, "")
                site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
                
                if self._is_cancelled:
                    return False
                
                # Log the action
                sp_list = site.List(ACTION_HISTORY)
                sp_list.UpdateListItems(data=data, kind='New')
                
                return True
                
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise e
                
                # Wait before retry (exponential backoff)
                if not self._is_cancelled:
                    time.sleep(2 ** attempt)
        
        return False


class AsyncUserAdder(QObject):
    """Asynchronous user adder to prevent UI blocking"""
    finished = pyqtSignal(bool)  # Success status
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, user_data: List[str]):
        super().__init__()
        self.user_data = user_data
        self._is_cancelled = False

    def cancel(self):
        """Cancel the user addition operation"""
        self._is_cancelled = True

    def run(self):
        """Add user in background thread"""
        try:
            if self._is_cancelled:
                return

            # Perform the actual user addition with retry mechanism
            success = self._add_user_with_retry(self.user_data, max_retries=3)
            
            if not self._is_cancelled:
                self.finished.emit(success)
                
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(f"Failed to add user: {str(e)}")
                self.finished.emit(False)

    def _add_user_with_retry(self, data: List[str], max_retries: int = 3) -> bool:
        """Add user with retry mechanism"""
        for attempt in range(max_retries):
            if self._is_cancelled:
                return False
                
            try:
                # Create SharePoint connection with timeout
                cred = HttpNtlmAuth(SID, password="")
                site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
                
                if self._is_cancelled:
                    return False
                
                # Add user to userbase
                sp_list = site.List(USERBASE)
                dictionary_as_list = [{
                    'id': data[0],
                    'display_name': data[1],
                    'email': data[2],
                    'job_title': data[3],
                    'building_name': data[4],
                    'cost_center_id': data[5]
                }]
                sp_list.UpdateListItems(data=dictionary_as_list, kind='New')
                
                return True
                
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise e
                
                # Wait before retry (exponential backoff)
                if not self._is_cancelled:
                    time.sleep(2 ** attempt)
        
        return False


def pslv_action_entry_async(dictionary_as_list: List[Dict[str, str]], 
                           callback_success=None, 
                           callback_error=None) -> None:
    """
    Asynchronous version of pslv_action_entry that doesn't block UI
    
    Args:
        dictionary_as_list: List of action dictionaries to log
        callback_success: Optional callback function for successful completion
        callback_error: Optional callback function for error handling
    """
    def _run_in_thread():
        """Internal function to run in thread pool"""
        try:
            # Create worker and run in background
            worker = AsyncActionLogger(dictionary_as_list)
            
            # Connect callbacks if provided
            if callback_success:
                worker.finished.connect(lambda success: callback_success() if success else None)
            if callback_error:
                worker.error.connect(callback_error)
            
            # Run the operation
            worker.run()
            
        except Exception as e:
            if callback_error:
                callback_error(f"Failed to log action: {str(e)}")

    # Submit to thread pool
    _executor.submit(_run_in_thread)


def add_new_user_to_userbase_async(data: List[str], 
                                  callback_success=None, 
                                  callback_error=None) -> None:
    """
    Asynchronous version of add_new_user_to_userbase that doesn't block UI
    
    Args:
        data: User data list [id, display_name, email, job_title, building_name, cost_center_id]
        callback_success: Optional callback function for successful completion
        callback_error: Optional callback function for error handling
    """
    def _run_in_thread():
        """Internal function to run in thread pool"""
        try:
            # Create worker and run in background
            worker = AsyncUserAdder(data)
            
            # Connect callbacks if provided
            if callback_success:
                worker.finished.connect(lambda success: callback_success() if success else None)
            if callback_error:
                worker.error.connect(callback_error)
            
            # Run the operation
            worker.run()
            
        except Exception as e:
            if callback_error:
                callback_error(f"Failed to add user: {str(e)}")

    # Submit to thread pool
    _executor.submit(_run_in_thread)


def pslv_action_entry(dictionary_as_list: List[Dict[str, str]]) -> None:
    """
    Enhanced SharePoint action entry with better error handling and timeout
    
    This function maintains backward compatibility while adding async capabilities.
    For UI applications, consider using pslv_action_entry_async instead.
    """
    try:
        # Check if we're in a GUI thread (basic check)
        current_thread = threading.current_thread()
        is_main_thread = isinstance(current_thread, threading._MainThread)
        
        if is_main_thread:
            # If called from main thread, use async version to avoid blocking
            pslv_action_entry_async(dictionary_as_list)
            return
        
        # Otherwise, run synchronously (for non-GUI contexts)
        _pslv_action_entry_sync(dictionary_as_list)
        
    except Exception as e:
        # Determine error type and provide user-friendly message
        error_msg = str(e).lower()
        if "connection" in error_msg or "timeout" in error_msg:
            raise UserFriendlyError("Unable to connect to SharePoint. Please check your network connection.")
        elif "authentication" in error_msg or "auth" in error_msg:
            raise UserFriendlyError("SharePoint authentication failed. Please contact IT support.")
        else:
            raise UserFriendlyError(f"Failed to save action history: {str(e)}")


def _pslv_action_entry_sync(dictionary_as_list: List[Dict[str, str]]) -> None:
    """Synchronous version with timeout and retry logic"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Create SharePoint connection with timeout
            cred = HttpNtlmAuth(SID, "")
            site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
            
            # Log the action
            sp_list = site.List(ACTION_HISTORY)
            sp_list.UpdateListItems(data=dictionary_as_list, kind='New')
            
            return  # Success
            
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                raise e
            
            # Wait before retry (exponential backoff)
            time.sleep(2 ** attempt)


def add_new_user_to_userbase(data: List[str]) -> None:
    """
    Enhanced user addition with better error handling and timeout
    
    This function maintains backward compatibility while adding async capabilities.
    For UI applications, consider using add_new_user_to_userbase_async instead.
    """
    try:
        # Check if we're in a GUI thread (basic check)
        current_thread = threading.current_thread()
        is_main_thread = isinstance(current_thread, threading._MainThread)
        
        if is_main_thread:
            # If called from main thread, use async version to avoid blocking
            add_new_user_to_userbase_async(data)
            return
        
        # Otherwise, run synchronously (for non-GUI contexts)
        _add_new_user_to_userbase_sync(data)
        
    except Exception as e:
        # Determine error type and provide user-friendly message
        error_msg = str(e).lower()
        if "connection" in error_msg or "timeout" in error_msg:
            raise UserFriendlyError("Unable to connect to SharePoint. Please check your network connection.")
        elif "authentication" in error_msg:
            raise UserFriendlyError("SharePoint authentication failed. Please contact IT support.")
        else:
            raise UserFriendlyError(f"Failed to add user to database: {str(e)}")


def _add_new_user_to_userbase_sync(data: List[str]) -> None:
    """Synchronous version with timeout and retry logic"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Create SharePoint connection with timeout
            cred = HttpNtlmAuth(SID, password="")
            site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
            
            # Add user to userbase
            sp_list = site.List(USERBASE)
            dictionary_as_list = [{
                'id': data[0],
                'display_name': data[1],
                'email': data[2],
                'job_title': data[3],
                'building_name': data[4],
                'cost_center_id': data[5]
            }]
            sp_list.UpdateListItems(data=dictionary_as_list, kind='New')
            
            print(f'User {data[0]} added to userbase.')
            return  # Success
            
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                raise e
            
            # Wait before retry (exponential backoff)
            time.sleep(2 ** attempt)


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def expire_sort(row) -> bool:
    """Check if application has expired with enhanced error handling"""
    try:
        release_date = pd.Timestamp(row['Release_Date'])
        expiry_date = release_date + timedelta(days=row['Validity_Period'])
        return datetime.now() > expiry_date
    except (ValueError, TypeError, KeyError) as e:
        print(f"Error checking expiry for row: {e}")
        return False


def split_user(users) -> List[str]:
    """Split user string into list with enhanced validation"""
    if isinstance(users, str) and users.strip():
        return [user.strip() for user in users.split(';') if user.strip()]
    else:
        return []


def validate_configuration() -> bool:
    """Validate configuration constants with timeout handling"""
    required_configs = {
        'SITE_URL': SITE_URL,
        'SHAREPOINT_LIST': SHAREPOINT_LIST,
        'USERBASE': USERBASE,
        'COST_CENTER': COST_CENTER,
        'ACTION_HISTORY': ACTION_HISTORY
    }

    missing_configs = []
    for config_name, config_value in required_configs.items():
        if not config_value or (isinstance(config_value, str) and config_value.strip() == ""):
            missing_configs.append(config_name)

    if missing_configs:
        raise UserFriendlyError(
            f"Missing configuration values: {', '.join(missing_configs)}. Please contact IT support.")

    return True


def test_sharepoint_connection(timeout: int = 30) -> bool:
    """Test SharePoint connection with timeout"""
    try:
        cred = HttpNtlmAuth(SID, "")
        site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=timeout)
        
        # Try to access a list to verify connection
        sp_list = site.List(SHAREPOINT_LIST)
        return True
        
    except Exception as e:
        print(f"SharePoint connection test failed: {e}")
        return False


def cleanup_async_operations() -> None:
    """Clean up async operations and thread pool"""
    try:
        _executor.shutdown(wait=True, timeout=5)
    except Exception as e:
        print(f"Error during cleanup: {e}")


# Configuration constants with enhanced validation
STO_CONFIG = r''
SITE_URL = ""
SID = ""
BACKUP_PATH = 'scratch/pslv_cache/access'
SHAREPOINT_LIST = 'STO_Inventory'
USERBASE = 'pslv_users'
COST_CENTER = 'cost_center'
ACTION_HISTORY = 'action_history'
ADMIN = 'pslv_sto_partner_admins'
BACKUP_FILE_NAME = 'launcher.xlsx'
APP_DIR = 'scratch/PSLV_Apps'
LABEL_TEXT = 'Developed and Maintained by <strong>To, GrSEM India</strong>'
DETAILS = [
    (getpass.getuser(), 'license-id-50.png'),
    ('john Doe', 'license-user-64.png'),
    ('john.doe@jpmorgan.com', 'license-email-50.png'),
    ('Associate', 'license-job-50.png'),
    ('GFGEM, India', 'license-location-50.png')
]

LOB = ['AAMI', 'CIB-GEFT', 'CIB-MS&OPS', 'CORP', 'FFCGEFSA', 'GFSM CPN', 'GFSM STO']
STATUS = ['UAT', 'BETA', 'PROD']

# Form fields with corrected validation
FIELDS = [
    ('Solution_Item_Epic_ID', 'JIRA ID', 'Enter the JIRA ID', None, 'text', 'text', True),
    ('Solution_Name', 'Application Name', 'Enter the name of the application', None, 'text', 'text', True),
    ('Description', 'Application Description', 'Enter a brief description', None, 'text', 'text', True),
    ('Line_of_Business', 'Line of Business', 'Select line or department', LOB, 'dropdown', 'dropdown', False),
    ('AAMI_Lead_ID', 'IAMID ID', 'Enter the IAMID registration id', None, 'text', 'text', False),
    ('Version_Number', 'Version', 'Enter application version', None, 'text', 'version', True),
    ('Release_Date', 'Release Date', 'Enter last update date (YYYY-MM-DD)', None, 'text', 'date', True),
    ('Status', 'Release Environment', 'Enter application release status', STATUS, 'dropdown', 'dropdown', False),
    ('ApplicationExePath', 'Executable Path', 'Enter the full path to the executable', None, 'text', 'app', True),
    ('Developer_By', 'Developer', 'Enter Developer\'s SID', None, 'text', 'text', True),
    ('TechnologyUsed', 'Technology Stack', 'Enter technology stack details', None, 'text', 'text', True)
]

# Styling constants
UAT = '#ea7317'
PROD = '#006770'
BETA = '#2a8265'

# Initialize configuration validation on import
try:
    validate_configuration()
except UserFriendlyError as e:
    print(f"Configuration warning: {e}")
