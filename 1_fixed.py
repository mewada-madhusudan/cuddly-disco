#  SplashScreen launch node - Enhanced Version
# =============================================================================
# Enhanced version with modern UI/UX while maintaining all original functionality
# This module contains the starting code for  Launcher and loads the initials details for the respective user
# request_ntlm and Sharepoint python packages are for operation related to SharePoint.
# ***

import getpass
import os
import random
import sys
import time

import pandas as pd
import urllib3
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QIcon, QPainter, QBrush, QColor, QPen, QFont
from PyQt6.QtWidgets import QApplication, QWidget, QProgressBar, QLabel, QFrame, QVBoxLayout, QPushButton, QGraphicsOpacityEffect
from requests_ntlm import HttpNtlmAuth
from sharepoint import Site

from launcherui import MainWindow
from static import resource_path, SID, SITE_URL, BACKUP_PATH, SHAREPOINT_LIST, BACKUP_FILE_NAME, LABEL_TEXT, USERBASE, \
    user_main, COST_CENTER

# Suppress ssl warnings for sharepoint api calls
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_cost_centers(site):  # 1 usage   4 Mewadata.Madhusudan
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


def fetch_user_data(site):  # 1 usage   4 Mewadata.Madhusudan
    """
    Fetch cost centers from SharePoint list.
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
        print(f'Error fetching cost centers: {str(e)}')
        return pd.DataFrame(columns=['sid', 'display_name', 'email', 'job_title', 'building_name', 'cost_center_id'])


class DataLoader(QThread):  # 1 usage   4 Mewadata.Madhusudan
    """
    DataLoader threaded class which loads the data from sharepoint while keeping UI live.
    """
    progress_updated = pyqtSignal(int, str)  # progress percentage and task name signal from thread
    data_loaded = pyqtSignal(object, object, object)  # data loaded signal for returning data with
    error_occurred = pyqtSignal(str)  # error signal for better error handling

    def __init__(self):  # 4 Mewadata.Madhusudan
        # constructor for inheriting QThread methods
        super().__init__()

    def run(self):  # 4 Mewadata.Madhusudan
        """
        default/mandatory run functions for calling a threaded processing capability
        :return: pd.DataFrame via data_loaded signal
        """
        try:
            """Try block to read data from sharepoint inventory, if it fails read handled from backup created for
            user on every successful run***"""
            os.makedirs(name=f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}", exist_ok=True)

            user = getpass.getuser()  # fetch user from os
            user = user.lower()  # turn it to lowercase

            # SharePoint client initialization
            self.progress_updated.emit(5, "Initializing connection...")
            cred = HttpNtlmAuth(SID, password='')

            self.progress_updated.emit(15, "Connecting to SharePoint...")
            site = Site(SITE_URL, auth=cred, verify_ssl=False)  # create sharepoint site session

            self.progress_updated.emit(35, "Fetching application data...")
            # Fetch data from SharePoint list
            sp_list = site.List(SHAREPOINT_LIST)
            sp_data = sp_list.GetListItems(view_name=None)
            df_all = pd.DataFrame(sp_data)
            df_all.fillna(value='', inplace=True)
            df_all['SIDs_For_SolutionAccess'] = df_all['SIDs_For_SolutionAccess'].str.lower()
            df_all.fillna(value='', inplace=True)
            all_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains('everyone', na=False)]
            processed_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains(user, na=False)]

            # Emit 60% progress for data fetch
            self.progress_updated.emit(60, "Processing user access...")
            # Process the DataFrame
            processed_df = pd.concat([all_df, processed_df])

            self.progress_updated.emit(75, "Saving local backup...")
            processed_df.reset_index(inplace=True)
            processed_df.to_excel(excel_writer=f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}",
                                  index=False)

            self.progress_updated.emit(85, "Loading additional data...")
            cc = fetch_cost_centers(site)
            user_data = fetch_user_data(site)

            self.progress_updated.emit(100, "Loading complete!")
            # Emit the processed data
            self.data_loaded.emit(processed_df, cc, user_data)

        except Exception as e:
            error_msg = f'Error loading data: {str(e)}'
            print(error_msg)
            self.error_occurred.emit("Failed to connect to SharePoint. Loading from backup...")

            # read access data from backup xlsx file created at location
            if os.path.exists(f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}"):
                processed_df = pd.read_excel(f"{os.environ.get('LOCALAPPDATA')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}")
                self.progress_updated.emit(100, "Loaded from backup")
                self.data_loaded.emit(processed_df, pd.DataFrame(), pd.DataFrame())
            else:
                processed_df = pd.DataFrame(
                    columns=['Expired', 'Solution_Name', 'Description', 'ApplicationExePath', 'Status', 'Release_Date',
                             'Validity_Period', 'Version_Number', 'UMAT_IAHub_ID'])
                self.error_occurred.emit("No backup data available. Please check your connection.")
                self.data_loaded.emit(processed_df, pd.DataFrame(), pd.DataFrame())


class ModernProgressBar(QProgressBar):
    """Enhanced progress bar with modern styling and animations"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(8)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        bg_rect = self.rect()
        painter.setBrush(QBrush(QColor(45, 55, 72)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 4, 4)
        
        # Progress
        if self.value() > 0:
            progress_width = int((self.value() / self.maximum()) * self.width())
            progress_rect = QRect(0, 0, progress_width, self.height())
            
            # Gradient effect
            gradient_color1 = QColor(56, 178, 172)  # Teal
            gradient_color2 = QColor(129, 230, 217)  # Light teal
            
            painter.setBrush(QBrush(gradient_color1))
            painter.drawRoundedRect(progress_rect, 4, 4)


class EnhancedSplashScreen(QWidget):  # 1 usage   4 Mewadata.Madhusudan
    def __init__(self):  # 4 Mewadata.Madhusudan
        """
        Enhanced SplashScreen constructor with modern UI design
        """
        super().__init__()
        icon_path = resource_path(f"resources/STOJustLogo.PNG")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle('STO Application Launcher')
        self.setFixedSize(1200, 600)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.counter = 0
        self.n = 100  # Changed to percentage-based progress
        self.processed_data = None
        self.can_cancel = False

        # Animation properties
        self.fade_in_animation = None
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self.pulse_effect)
        
        self.initUI()
        self.initAnimations()
        self.initDataLoader()

    def initAnimations(self):
        """Initialize fade-in animations for UI elements"""
        # Fade in effect for the entire window
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        
        self.fade_in_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_animation.setDuration(800)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_in_animation.start()

    def pulse_effect(self):
        """Create a subtle pulse effect for the loading label"""
        if hasattr(self, 'labelLoading'):
            current_color = self.labelLoading.palette().color(self.labelLoading.foregroundRole())
            alpha = 150 + int(50 * (0.5 + 0.5 * time.time() % 2))
            new_color = QColor(current_color.red(), current_color.green(), current_color.blue(), alpha)
            self.labelLoading.setStyleSheet(f"color: rgba({new_color.red()}, {new_color.green()}, {new_color.blue()}, {alpha});")

    def initDataLoader(self):
        # Initialize data loader
        self.data_loader = DataLoader()

        # Connect signals
        self.data_loader.progress_updated.connect(self.updateProgress)
        self.data_loader.data_loaded.connect(self.onDataLoaded)
        self.data_loader.error_occurred.connect(self.onError)

        # Start loading data
        self.data_loader.start()

    def initUI(self):  # 1 usage   4 Mewadata.Madhusudan
        # UI initialization code with modern design
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.frame = QFrame()
        self.frame.setObjectName('MainFrame')
        layout.addWidget(self.frame)

        # Main title with modern typography
        self.labelTitle = QLabel(self.frame)
        self.labelTitle.setObjectName('LabelTitle')
        self.labelTitle.resize(self.width() - 40, 120)
        self.labelTitle.move(20, 80)
        self.labelTitle.setText('Python Solution Launcher')
        self.labelTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Subtitle
        self.labelSubtitle = QLabel(self.frame)
        self.labelSubtitle.setObjectName('LabelSubtitle')
        self.labelSubtitle.resize(self.width() - 40, 40)
        self.labelSubtitle.move(20, 200)
        self.labelSubtitle.setText('for Virtual Desktop Infrastructure')
        self.labelSubtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Description with better spacing
        self.labelDescription = QLabel(self.frame)
        self.labelDescription.resize(self.width() - 80, 60)
        self.labelDescription.move(40, 260)
        self.labelDescription.setObjectName('LabelDesc')
        self.labelDescription.setText(LABEL_TEXT)
        self.labelDescription.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelDescription.setWordWrap(True)

        # Modern progress bar
        self.progressBar = ModernProgressBar(self.frame)
        self.progressBar.resize(self.width() - 200, 8)
        self.progressBar.move(100, 380)
        self.progressBar.setRange(minimum=0, maximum=self.n)
        self.progressBar.setValue(0)

        # Progress percentage label
        self.progressLabel = QLabel(self.frame)
        self.progressLabel.setObjectName('ProgressLabel')
        self.progressLabel.resize(80, 30)
        self.progressLabel.move(self.width() // 2 - 40, 350)
        self.progressLabel.setText('0%')
        self.progressLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Loading status with modern styling
        self.labelLoading = QLabel(self.frame)
        self.labelLoading.resize(self.width() - 40, 40)
        self.labelLoading.move(20, 420)
        self.labelLoading.setObjectName('LabelLoading')
        self.labelLoading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelLoading.setText('Initializing...')

        # Modern cancel button
        self.cancelButton = QPushButton("✕ Cancel", self.frame)
        self.cancelButton.resize(120, 40)
        self.cancelButton.move(self.width() // 2 - 60, 480)
        self.cancelButton.setObjectName('CancelButton')
        self.cancelButton.hide()
        self.cancelButton.clicked.connect(self.cancelLoading)

        # Start pulse effect
        self.pulse_timer.start(100)

    def updateProgress(self, value, task_name="Loading..."):  # 1 usage   4 Mewadata.Madhusudan
        """
        Enhanced progress update with smooth animations
        :param value: completion percentage(int)
        :param task_name: current task being performed
        :return:
        """
        # Animate progress bar
        self.progressBar.setValue(value)
        self.progressLabel.setText(f'{value}%')
        self.labelLoading.setText(task_name)

        # Show cancel button after initial connection attempt
        if value > 20 and not self.can_cancel:
            self.can_cancel = True
            self.cancelButton.show()
            
            # Fade in cancel button
            button_effect = QGraphicsOpacityEffect()
            self.cancelButton.setGraphicsEffect(button_effect)
            button_animation = QPropertyAnimation(button_effect, b"opacity")
            button_animation.setDuration(300)
            button_animation.setStartValue(0.0)
            button_animation.setEndValue(1.0)
            button_animation.start()

    def onError(self, error_message):
        """
        Enhanced error handling with better visual feedback
        """
        self.labelLoading.setText(error_message)
        self.labelLoading.setObjectName('LabelError')
        self.labelLoading.setStyleSheet("")  # Reset to use CSS styling
        
        # Stop pulse effect on error
        self.pulse_timer.stop()

    def cancelLoading(self):
        """
        Cancel the loading process with fade out effect
        """
        if self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()
        
        # Fade out animation before closing
        fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        fade_out.setDuration(300)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.finished.connect(self.close)
        fade_out.start()

    def onDataLoaded(self, data, cost_centers, user_data):  # 1 usage   4 Mewadata.Madhusudan
        """
        Enhanced data loaded handler with smooth transition
        :param data:
        :return:
        """
        self.processed_data = data
        self.progressBar.setValue(100)
        self.progressLabel.setText('100%')
        self.labelLoading.setText('Loading complete!')
        
        # Stop pulse effect
        self.pulse_timer.stop()
        
        # Smooth transition to main application
        QTimer.singleShot(500, lambda: self.launchMainApp(data, cost_centers, user_data))
    
    def launchMainApp(self, data, cost_centers, user_data):
        """Launch main application with fade transition"""
        app.setStyleSheet(None)
        
        # Pass the processed data to MainWindow
        self.myApp = MainWindow(data, cost_centers, user_data)
        self.myApp.show()
        
        # Fade out splash screen
        fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        fade_out.setDuration(400)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.finished.connect(self.close)
        fade_out.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Enhanced modern styling
    app.setStyleSheet('''
        #MainFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #1a202c, stop:0.5 #2d3748, stop:1 #1a202c);
            border-radius: 20px;
            border: 2px solid #4a5568;
        }

        #LabelTitle {
            font-size: 48px;
            font-weight: 700;
            color: #e2e8f0;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #38b2ac, stop:1 #81e6d9);
            -webkit-background-clip: text;
            background-clip: text;
        }
        
        #LabelSubtitle {
            font-size: 18px;
            font-weight: 300;
            color: #a0aec0;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-style: italic;
        }

        #LabelDesc {
            font-size: 16px;
            color: #cbd5e0;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            line-height: 1.5;
            font-weight: 400;
        }

        #LabelLoading {
            font-size: 18px;
            color: #81e6d9;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-weight: 500;
        }
        
        #LabelError {
            font-size: 18px;
            color: #fed7d7;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-weight: 500;
            background-color: rgba(254, 178, 178, 0.1);
            border-radius: 8px;
            padding: 8px;
        }
        
        #ProgressLabel {
            font-size: 14px;
            color: #e2e8f0;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-weight: 600;
        }

        #CancelButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #e53e3e, stop:1 #c53030);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 14px;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-weight: 600;
            padding: 8px 16px;
        }

        #CancelButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #c53030, stop:1 #9c2626);
            transform: translateY(-1px);
        }

        #CancelButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #9c2626, stop:1 #822727);
            transform: translateY(0px);
        }
    ''')

    splash = EnhancedSplashScreen()
    splash.show()

    try:
        sys.exit(app.exec())
    except SystemExit:
        print('Closing Window...')
