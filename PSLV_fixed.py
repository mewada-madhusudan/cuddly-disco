# PSLV SplashScreen launch node - FIXED VERSION
# =============================================================================
# This module contains the starting code for PSLV Launcher with improved threading
# and UI responsiveness fixes

import getpass
import os
import random
import sys
import time

import pandas as pd
import urllib3
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QWidget, QProgressBar, QLabel, QFrame, QVBoxLayout, QPushButton
from requests_ntlm import HttpNtlmAuth
from sharepoint import Site

from launcherui import MainWindow
from static import resource_path, SID, SITE_URL, BACKUP_PATH, SHAREPOINT_LIST, BACKUP_FILE_NAME, LABEL_TEXT, USERBASE, \
    user_main, COST_CENTER

# Suppress ssl warnings for sharepoint api calls
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_cost_centers(site):
    """
    Fetch cost centers from SharePoint list.
    """
    try:
        sp_list = site.List(COST_CENTER)
        sp_data = sp_list.GetListItems(view_name=None)
        df = pd.DataFrame(sp_data)
        df.fillna(value='', inplace=True)
        return df
    except Exception as e:
        print(f'Error fetching cost centers: {str(e)}')
        return pd.DataFrame(columns=['cost_center_code', 'cost_center_name', 'is_gfbm'])


def fetch_user_data(site):
    """
    Fetch user data from SharePoint list.
    """
    try:
        sp_list = site.List(USERBASE)
        query = {'Where': [('Contains', 'sid', user_main)]}

        # Fetch items with the query and row limit
        sp_data = sp_list.GetListItems(query=query)
        df = pd.DataFrame(sp_data)
        df.fillna(value='', inplace=True)
        return df
    except Exception as e:
        print(f'Error fetching user data: {str(e)}')
        return pd.DataFrame(columns=['sid', 'display_name', 'email', 'job_title', 'building_name', 'cost_center_id'])


class DataLoader(QThread):
    """
    FIXED: DataLoader threaded class with better error handling and progress reporting.
    """
    progress_updated = pyqtSignal(int, str)  # progress percentage and task name signal from thread
    data_loaded = pyqtSignal(object, object, object)  # data loaded signal for returning data
    error_occurred = pyqtSignal(str)  # error signal for better error handling

    def __init__(self):
        super().__init__()
        self.should_stop = False

    def stop(self):
        """Stop the data loading process"""
        self.should_stop = True

    def run(self):
        """
        FIXED: Improved run function with better error handling and cancellation support
        """
        try:
            if self.should_stop:
                return

            # Create backup directory
            os.makedirs(name=f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}", exist_ok=True)

            user = getpass.getuser().lower()

            # SharePoint client initialization
            self.progress_updated.emit(5, "Initializing connection...")
            if self.should_stop:
                return

            cred = HttpNtlmAuth(SID, password='')

            self.progress_updated.emit(15, "Connecting to SharePoint...")
            if self.should_stop:
                return

            # Add timeout to prevent hanging
            try:
                site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
            except Exception as e:
                raise ConnectionError(f"Failed to connect to SharePoint: {str(e)}")

            self.progress_updated.emit(35, "Fetching application data...")
            if self.should_stop:
                return

            # Fetch data from SharePoint list with timeout
            sp_list = site.List(SHAREPOINT_LIST)
            sp_data = sp_list.GetListItems(view_name=None)
            
            if self.should_stop:
                return

            df_all = pd.DataFrame(sp_data)
            df_all.fillna(value='', inplace=True)
            df_all['SIDs_For_SolutionAccess'] = df_all['SIDs_For_SolutionAccess'].str.lower()
            df_all.fillna(value='', inplace=True)

            self.progress_updated.emit(50, "Processing user access...")
            if self.should_stop:
                return

            all_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains('everyone', na=False)]
            processed_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains(user, na=False)]
            processed_df = pd.concat([all_df, processed_df])

            self.progress_updated.emit(70, "Saving local backup...")
            if self.should_stop:
                return

            processed_df.reset_index(inplace=True)
            backup_path = f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}"
            processed_df.to_excel(excel_writer=backup_path, index=False)

            self.progress_updated.emit(85, "Loading additional data...")
            if self.should_stop:
                return

            # Load additional data with error handling
            try:
                cc = fetch_cost_centers(site)
                user_data = fetch_user_data(site)
            except Exception as e:
                print(f"Warning: Failed to load additional data: {str(e)}")
                cc = pd.DataFrame()
                user_data = pd.DataFrame()

            if self.should_stop:
                return

            self.progress_updated.emit(100, "Loading complete!")
            # Emit the processed data
            self.data_loaded.emit(processed_df, cc, user_data)

        except ConnectionError as e:
            error_msg = f'Connection error: {str(e)}'
            print(error_msg)
            self.error_occurred.emit("Failed to connect to SharePoint. Loading from backup...")
            self._load_from_backup()

        except Exception as e:
            error_msg = f'Error loading data: {str(e)}'
            print(error_msg)
            self.error_occurred.emit("Failed to load data from SharePoint. Loading from backup...")
            self._load_from_backup()

    def _load_from_backup(self):
        """Load data from backup file"""
        try:
            backup_path = f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}"
            if os.path.exists(backup_path):
                processed_df = pd.read_excel(backup_path)
                self.progress_updated.emit(100, "Loaded from backup")
                self.data_loaded.emit(processed_df, pd.DataFrame(), pd.DataFrame())
            else:
                processed_df = pd.DataFrame(
                    columns=['Expired', 'Solution_Name', 'Description', 'ApplicationExePath', 'Status', 'Release_Date',
                             'Validity_Period', 'Version_Number', 'UMAT_IAHub_ID'])
                self.error_occurred.emit("No backup data available. Please check your connection.")
                self.data_loaded.emit(processed_df, pd.DataFrame(), pd.DataFrame())
        except Exception as e:
            print(f"Error loading backup: {str(e)}")
            processed_df = pd.DataFrame(
                columns=['Expired', 'Solution_Name', 'Description', 'ApplicationExePath', 'Status', 'Release_Date',
                         'Validity_Period', 'Version_Number', 'UMAT_IAHub_ID'])
            self.data_loaded.emit(processed_df, pd.DataFrame(), pd.DataFrame())


class SplashScreen(QWidget):
    def __init__(self):
        """
        FIXED: SplashScreen constructor with improved initialization
        """
        super().__init__()
        icon_path = resource_path(f"resources/STOJustLogo.PNG")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle('STO Application Launcher')
        self.setFixedSize(1100, 500)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.counter = 0
        self.n = 100
        self.processed_data = None
        self.can_cancel = False
        self.data_loader = None

        self.initUI()
        # Delay data loading to allow UI to render first
        QTimer.singleShot(100, self.initDataLoader)

    def initDataLoader(self):
        """FIXED: Initialize data loader with proper cleanup"""
        if self.data_loader:
            self.data_loader.stop()
            self.data_loader.wait()

        self.data_loader = DataLoader()

        # Connect signals
        self.data_loader.progress_updated.connect(self.updateProgress)
        self.data_loader.data_loaded.connect(self.onDataLoaded)
        self.data_loader.error_occurred.connect(self.onError)

        # Start loading data
        self.data_loader.start()

    def initUI(self):
        """FIXED: UI initialization with better layout"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.frame = QFrame()
        layout.addWidget(self.frame)

        self.labelTitle = QLabel(self.frame)
        self.labelTitle.setObjectName('LabelTitle')
        self.labelTitle.resize(self.width() - 10, 150)
        self.labelTitle.move(0, 40)
        self.labelTitle.setText('Python Solution Launcher for VDI')
        self.labelTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.labelDescription = QLabel(self.frame)
        self.labelDescription.resize(self.width() - 10, 50)
        self.labelDescription.move(0, self.labelTitle.height())
        self.labelDescription.setObjectName('LabelDesc')
        self.labelDescription.setText(LABEL_TEXT)
        self.labelDescription.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progressBar = QProgressBar(self.frame)
        self.progressBar.resize(self.width() - 200 - 10, 50)
        self.progressBar.move(100, self.labelDescription.y() + 130)
        self.progressBar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progressBar.setFormat('%p%')
        self.progressBar.setTextVisible(True)
        self.progressBar.setRange(minimum=0, maximum=self.n)
        self.progressBar.setValue(0)

        self.labelLoading = QLabel(self.frame)
        self.labelLoading.resize(self.width() - 10, 50)
        self.labelLoading.move(0, self.progressBar.y() + 70)
        self.labelLoading.setObjectName('LabelLoading')
        self.labelLoading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelLoading.setText('Initializing...')

        # Add cancel button (initially hidden)
        self.cancelButton = QPushButton("Cancel", self.frame)
        self.cancelButton.resize(100, 30)
        self.cancelButton.move(self.width() // 2 - 50, self.labelLoading.y() + 50)
        self.cancelButton.setObjectName('CancelButton')
        self.cancelButton.hide()
        self.cancelButton.clicked.connect(self.cancelLoading)

    def updateProgress(self, value, task_name="Loading..."):
        """
        FIXED: Progress update with UI responsiveness
        """
        self.progressBar.setValue(value)
        self.labelLoading.setText(task_name)

        # Show cancel button after initial connection attempt
        if value > 20 and not self.can_cancel:
            self.can_cancel = True
            self.cancelButton.show()

        # Process events to keep UI responsive
        QApplication.processEvents()

    def onError(self, error_message):
        """
        FIXED: Handle error messages with better user feedback
        """
        self.labelLoading.setText(error_message)
        self.labelLoading.setStyleSheet("color: #ff9800;")  # Orange color for warnings

    def cancelLoading(self):
        """
        FIXED: Cancel the loading process properly
        """
        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.stop()
            self.data_loader.wait(3000)  # Wait up to 3 seconds
            if self.data_loader.isRunning():
                self.data_loader.terminate()
                self.data_loader.wait()
        self.close()

    def onDataLoaded(self, data, cost_centers, user_data):
        """
        FIXED: Handles Data loaded signal and initializes application screen
        """
        self.processed_data = data
        self.progressBar.setValue(100)
        app.setStyleSheet(None)

        # Pass the processed data to MainWindow
        self.myApp = MainWindow(self.processed_data, cost_centers, user_data)
        self.myApp.show()
        self.close()

    def closeEvent(self, event):
        """FIXED: Proper cleanup on close"""
        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.stop()
            self.data_loader.wait(3000)
            if self.data_loader.isRunning():
                self.data_loader.terminate()
                self.data_loader.wait()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet('''
        #LabelTitle {
            font-size: 60px;
            color: #93deed;
            font-family: Montserrat, serif;
        }

        #LabelDesc {
            font-size: 20px;
            color: #c2ced1;
            font-family: Montserrat, serif;
        }

        #LabelLoading {
            font-size: 20px;
            color: #e8e8eb;
        }

        #CancelButton {
            background-color: #f44336;
            color: white;
            border: none;
            border-radius: 15px;
            font-size: 14px;
            font-family: Montserrat, serif;
        }

        #CancelButton:hover {
            background-color: #d32f2f;
        }

        QFrame {
            background-color: #2F4454;
            color: rgb(220, 220, 220);
        }

        QProgressBar {
            background-color: #f3f8f5;
            color: rgb(173, 172, 176);
            border-style: none;
            border-radius: 10px;
            text-align: center;
            font-size: 30px;
        }

        QProgressBar::chunk {
            border-radius: 10px;
            background-color: qlineargradient(spread:pad x1:0, x2:1, y1:0.511364, y2:0.523, stop:0 #1C3334, stop:1 #376E6F);
        }
    ''')

    splash = SplashScreen()
    splash.show()

    try:
        sys.exit(app.exec())
    except SystemExit:
        print('Closing Window...')